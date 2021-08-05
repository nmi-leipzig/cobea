import numpy as np
import os
import subprocess
import sys
import time

from argparse import Namespace
from contextlib import ExitStack
from dataclasses import asdict, astuple, dataclass
from datetime import datetime, timezone
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from typing import Any, Iterable, List, Mapping, Tuple

import h5py

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import EvalMode, Individual, SimpleEA
from adapters.dummies import DummyDriver, DummyMeter
from adapters.gear.rigol import FloatCheck, IntCheck, OsciDS1102E, SetupCmd
from adapters.hdf5_sink import compose, HDF5Sink, IgnoreValue, MetaEntry, MetaEntryMap, ParamAim, ParamAimMap
from adapters.icecraft import IcecraftBitPosition, IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen,\
IcecraftManager, IcecraftRawConfig, XC6200Port, XC6200Direction
from adapters.parallel_collector import CollectorDetails, InitDetails, ParallelCollector
from adapters.parallel_sink import ParallelSink
from adapters.prng import BuiltInPRNG
from adapters.simple_sink import TextfileSink
from adapters.temp_meter import TempMeter
from adapters.unique_id import SimpleUID
from domain.data_sink import DataSink
from domain.interfaces import Driver, InputData, Meter, TargetDevice, TargetManager
from domain.model import AlleleAll, Chromosome, Gene
from domain.request_model import RequestObject
from domain.use_cases import Measure

class CalibrationError(Exception):
	"""Indicates an error during calibration"""
	pass

class DataCollectionError(Exception):
	"""Raised when an error occured during data collection"""
	pass

# generate tiles
def tiles_from_corners(min_pos: Tuple[int, int], max_pos: Tuple[int, int]) -> List[IcecraftPosition]:
	req = RequestObject(identifier="expand_rectangle", description="")
	ptl = IcecraftPosTransLibrary()
	exp_rect = ptl.get_pos_trans(req)
	res = exp_rect([IcecraftPosition(*min_pos), IcecraftPosition(*max_pos)])
	return res

# generate representation
def create_xc6200_rep(min_pos: Tuple[int, int], max_pos: Tuple[int, int], in_port: XC6200Port) -> IcecraftRep:
	rep_gen = XC6200RepGen()
	
	tiles = tiles_from_corners(min_pos, max_pos)
	# output ports are implicit as they depend on which neigh_op nets the habitat takes from the evolved region
	req = RequestObject(tiles=tiles, in_ports=[in_port])
	
	bef = time.perf_counter()
	rep = rep_gen(req)
	aft = time.perf_counter()
	print(f"rep gen took {aft-bef} s, {sum(g.alleles.size_in_bits() for g in rep.genes)} bits")
	
	return rep

def is_rep_fitting(rep: IcecraftRep, chromo_bits: int) -> bool:
	"""check if representation fits in a certain number of bits"""
	for gene in rep.iter_genes():
		if len(gene.alleles) > 1<<chromo_bits:
			return False
	
	return True

# flash FPGAs
def prepare_generator(gen: TargetDevice, asc_path: str) -> IcecraftRawConfig:
	config = IcecraftRawConfig.create_from_filename(asc_path)
	gen.configure(config)
	
	return config

def create_meter_setup() -> SetupCmd:
	setup = OsciDS1102E.create_setup()
	setup.CHAN1.DISP.value_ = "ON"
	setup.CHAN1.PROB.value_ = 10
	setup.CHAN1.SCAL.value_ = 1
	setup.CHAN1.OFFS.value_ = 0
	
	setup.CHAN2.DISP.value_ = "ON"#"OFF"#
	setup.CHAN2.PROB.value_ = 1
	setup.CHAN2.SCAL.value_ = 1
	
	setup.ACQ.MEMD.value_ = "LONG"
	setup.ACQ.TYPE.value_ = "NORM"
	setup.ACQ.MODE.value_ = "RTIM"
	
	setup.TIM.SCAL.value_ = 0.5
	setup.TIM.OFFS.value_ = 2
	
	setup.TRIG.MODE.value_ = "EDGE"
	setup.TRIG.EDGE.SOUR.value_ = "CHAN2"
	setup.TRIG.EDGE.SLOP.value_ = "POS"
	setup.TRIG.EDGE.SWE.value_ = "SING"
	setup.TRIG.EDGE.COUP.value_ = "DC"
	setup.TRIG.EDGE.LEV.value_ = 1
	
	return setup

@dataclass
class CalibrationData:
	data: np.ndarray
	rising_edge: int
	falling_edge: int
	trig_len: int
	offset: float

def calibrate(driver: Driver, sn=None) -> CalibrationData:
	meter_setup = create_meter_setup()
	meter_setup.TIM.OFFS.value_ = 2.5
	
	meter = OsciDS1102E(meter_setup, serial_number=sn, data_chan=2)
	with meter:
		measure_uc = Measure(driver, meter)
		
		eval_req = RequestObject(
			driver_data = InputData([0]),
			retry = 2,
			measure_timeout = 20,
		)
		data = measure_uc(eval_req)
	
	nd = np.array(data)
	trig_lev = 1.5
	rise = np.flatnonzero(((nd[:-1] <= trig_lev) & (nd[1:] > trig_lev))) + 1
	if len(rise) != 1:
		raise CalibrationError(f"Couldn't find unique rising edge: {rise}")
	rise = rise[0]
	fall = np.flatnonzero(((nd[:-1] >= trig_lev) & (nd[1:] < trig_lev))) + 1
	if len(fall) != 1:
		raise CalibrationError(f"Couldn't find unique fallng edge: {fall}")
	fall = fall[0]
	
	if abs(rise - 524288//12) > 5:
		raise CalibrationError(f"rising edge at {rise} too far of off expected point {524288//12}")
	
	trig_len = fall - 524288//12
	offset = (trig_len/2**18 - 1) * 0.5 * 6
	
	return CalibrationData(nd, rise, fall, trig_len, offset)

def get_git_commit() -> str:
	try:
		label = subprocess.check_output(["git", "describe", "--always"], universal_newlines=True).strip()
		return label
	except:
		return "UNKNOWN"

def create_rng_aim(name: str, prefix: str) -> List[ParamAim]:
	return [
		ParamAim([name], "int64", f"{prefix}version", alter=partial(compose, funcs=[itemgetter(0), itemgetter(0)])),
		ParamAim([name], "int64", f"{prefix}mt_state", alter=partial(compose, funcs=[itemgetter(0), itemgetter(1)])),
		ParamAim([name], "float64",f"{prefix}next_gauss",alter=partial(compose, funcs=[itemgetter(0), itemgetter(2)])),
	]

def ignore_same(x: list) -> Any:
	"""raise IgnoreValue of first two elements are equal, else return the last
	
	That way a third value can be rejected when two other values are identical
	"""
	if x[0] == x[1]:
		raise IgnoreValue()
	return x[-1]

def create_base_write_map(rep: IcecraftRep, chromo_bits: 16) -> Tuple[ParamAimMap, MetaEntryMap]:
	"""Create HDF5Sink write map with entries that are always required"""
	if not is_rep_fitting(rep, chromo_bits):
		raise ValueError(f"representation needs more than {chromo_bits} bits")
	
	# use attrgetter and so on to allow pickling for multiprocessing
	
	chromo_aim = [
		ParamAim(
			["return"], f"uint{chromo_bits}", "chromosome", "individual", as_attr=False, shape=(len(rep.genes), ),
			alter=partial(compose, funcs=[itemgetter(0), attrgetter("allele_indices")]), comp_opt=9, shuffle=True
		),
		ParamAim(["return"], "uint64", "chromo_id", "individual", as_attr=False, 
			alter=partial(compose, funcs=[itemgetter(0), attrgetter("identifier")]), comp_opt=9, shuffle=True),
	]
	
	write_map = {
		"Measure.perform": [
			ParamAim(["driver_data"], "uint8", "s_t_index", "fitness", as_attr=False, comp_opt=9, shuffle=True),
			ParamAim(["return"], "float64", "measurement", "fitness", as_attr=False, shape=(2**19, ), shuffle=False),
		],
		"Measure.additional": [
			ParamAim(["time"], "float64", "time", "fitness", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), methodcaller("timestamp")]), comp_opt=9, shuffle=True),
		],
		"RandomChromo.perform": chromo_aim,
		"GenChromo.perform": chromo_aim,
		"Action.rep": HDF5Sink.create_gene_aims("genes", len(rep.genes), h5_path="mapping/genes")+\
			HDF5Sink.create_gene_aims("const", len(rep.constant), h5_path="mapping/constant")+[
				ParamAim(["carry_bits"], "uint16", "bits", "fitness/carry_enable",
					alter=partial(compose, funcs=[itemgetter(0), partial(map, methodcaller("to_ints")), list])),
				ParamAim(["output"], "uint16", "output_lutff", "mapping", alter=partial(compose, funcs=[itemgetter(0),
					partial(map, astuple), list])),
				ParamAim(["colbufctrl"], "uint16", "colbufctrl_bits", "mapping", alter=partial(compose, funcs=[
					itemgetter(0), partial(map, partial(compose, funcs=[attrgetter("bits"), astuple])), list])),
				ParamAim(["colbufctrl"], "uint16", "colbufctrl_index", "mapping", alter=partial(compose, funcs=[
					itemgetter(0), partial(map, attrgetter("index")), list])),
			],
		"calibration": [
			ParamAim(["data"], "float64", "calibration", as_attr=False, shuffle=False),
			ParamAim(["rising_edge"], "uint64", "rising_edge", "calibration"),
			ParamAim(["falling_edge"], "uint64", "falling_edge", "calibration"),
			ParamAim(["trig_len"], "uint64", "trig_len", "calibration"),
			ParamAim(["offset"], "float64", "offset", "calibration"),
		],
		"habitat": [ParamAim(
			["text"], "uint8", "habitat", as_attr=False,
			alter=partial(compose, funcs=[itemgetter(0), partial(bytearray, encoding="utf-8")]), comp_opt=9
		),],
		"freq_gen": [ParamAim(
			["text"], "uint8", "freq_gen", as_attr=False,
			alter=partial(compose, funcs=[itemgetter(0), partial(bytearray, encoding="utf-8")]), comp_opt=9
		),],
	}
	
	metadata = {
		"individual": [MetaEntry("description", "data for the genotype")],
		"individual/chromo_id": [MetaEntry("description", "unique ID of every chromosome")],
		"individual/chromosome": [MetaEntry("description", "allele choices for every chromosome")],
		"fitness": [MetaEntry("description", "data regarding the fitness values")],
		"fitness/s_t_index": [MetaEntry("description", "index of the s-t-combination used for determining the order of "
			"5 1 kHz and 5 10 kHz bursts")],
		"fitness/measurement": [
			MetaEntry("description", "output of the phenotype measured by an oscilloscope; each " 
				"measurement took 6 s; in the last 5 s 10 bursts of either 1 kHz or 10 kHz were presented at the input;"
				" only this last 5 s are relevant for the fitness value"),
			MetaEntry("unit", "Volt")
		],
		"fitness/time": [
			MetaEntry("description", "time the measurement started; timezone UTC"),
			MetaEntry("unit", "seconds since 01.01.1970 00:00:00")
		],
		"mapping": [MetaEntry("description", "mapping of the genotype (allele indices) to configuration bits")],
		"mapping/genes": [MetaEntry("description", "part of the configuration bits that is configurable")],
		"mapping/constant": [MetaEntry("description", "part of the configuration bits that is fixed")],
		"fitness/carry_enable": [MetaEntry("description", "values of carry enable bits; derived from the configuration "
			"bits defined by the genotype")],
		"mapping/carry_data": [MetaEntry("description", "data describing how to derive the carry bits from the "
			"configuration bits defined by the genotype")],
		"calibration": [
			MetaEntry("description", "calibrate the measurement time to the exact duration of the 10 bursts; the "
				"trigger signaling the bursts should start at 0.5 s"),
			MetaEntry("unit", "Volt"),
		],
		"habitat": [
			MetaEntry("description", "basic configuration of the target FPGA that defines the periphery of the evolved "
				"part; the values are bytes of the asc format"),
			MetaEntry("connection", "input from the driver to habitat at pin R15; output from habitat to meter at pin "
				"D14"),
		],
		"freq_gen": [
			MetaEntry("description", "configuration of the driver FPGA that creates the frequency bursts; the values "
				"are bytes of the asc format"),
			MetaEntry("connection", "output of the frequency bursts to the target at pin R15; output of the trigger "
				"signal to the meter at pin D14"),
		]
	}
	
	for i, cd in enumerate(rep.iter_carry_data()):
		metadata[f"mapping/carry_data/carry_data_{i}"] = [
			MetaEntry("lut_index", cd.lut_index, "uint8"),
			MetaEntry("carry_enable", [astuple(b) for b in cd.carry_enable], "uint16"),
		] + [
			MetaEntry(f"carry_use_{k}_bits", [astuple(b) for b in p.bits], "uint16") for k, p in enumerate(cd.carry_use)
		] + [
			MetaEntry(f"carry_use_{k}_values", p.values, bool) for k, p in enumerate(cd.carry_use)
		]
	
	return write_map, metadata

def add_temp_writes(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	temp_map = {
		"temperature.perform": [
			ParamAim(["return"], "float16", "celsius", "temperature", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), itemgetter(0)]), comp_opt=9, shuffle=True),
		],
		"temperature.additional": [
			ParamAim(["time"], "float64", "time", "temperature", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), methodcaller("timestamp")]), comp_opt=9, shuffle=True),
		],
		# use ParamAim for temp serial as it is collected in a separate process
		"meta.temp": [
			ParamAim(["sn"], str, "temp_reader_serial_number", "temperature"),
			ParamAim(["hw"], str, "temp_reader_hardware", "temperature"),
			ParamAim(["sensor_sn"], str, "temp_sensor_serial_number", "temperature"),
			ParamAim(["sensor_hw"], str, "temp_sensor_hardware", "temperature"),
		],
	}
	
	temp_meta = {
		"temperature": [MetaEntry("description", "temperature recorded at the surface of the FPGA")],
		"temperature/celsius": [MetaEntry("description", "measured temperature"), MetaEntry("unit", "degree celsius")],
		"temperature/time": [
			MetaEntry("description", "time the temperature measurement started; timezone UTC"),
			MetaEntry("unit", "seconds since 01.01.1970 00:00:00")
		],
	}
	
	write_map.update(temp_map)
	metadata.update(temp_meta)

def add_ea_writes(write_map: ParamAimMap, metadata: MetaEntryMap, rep: IcecraftRep, pop_size: int,) -> None:
	"""Add the entries for an evolutionary algorithm to an existing HDF5Sink write map"""
	
	ea_map = {
		"SimpleEA.fitness": [
			ParamAim(["fit"], "float64", "value", "fitness", as_attr=False, comp_opt=9, shuffle=True),
			ParamAim(["fast_sum"], "float64", "fast_sum", "fitness", as_attr=False, comp_opt=9, shuffle=True),
			ParamAim(["slow_sum"], "float64", "slow_sum", "fitness", as_attr=False, comp_opt=9, shuffle=True),
			ParamAim(["chromo_index"], "uint64", "chromo_id", "fitness", as_attr=False, comp_opt=9, shuffle=True),
			ParamAim(
				["carry_enable"],
				bool,
				"carry_enable",
				"fitness",
				as_attr=False,
				shape=(len(list(rep.iter_carry_bits())), ),
				comp_opt=4,
			),
			ParamAim(["generation"], "uint64", "generation", "fitness", as_attr=False, comp_opt=9, shuffle=True),
		],
		"SimpleEA.ea_params": [
			ParamAim(["pop_size"], "uint64", "pop_size"),
			ParamAim(["gen_count"], "uint64", "gen_count"),
			ParamAim(["crossover_prob"], "float64", "crossover_prob"),
			ParamAim(["mutation_prob"], "float64", "mutation_prob"),
			ParamAim(["eval_mode"], str, "eval_mode"),
		],
		"SimpleEA.random_initial": create_rng_aim("state", "random_initial_"),
		"SimpleEA.random_final": create_rng_aim("state", "random_final_"),
		"SimpleEA.gen":[
			ParamAim(["pop"], "uint64", "population", as_attr=False, shape=(pop_size, ), shuffle=True),
		],
		"Individual.wrap.cxOnePoint": [
			ParamAim(["in"], "uint64", "parents", "crossover", as_attr=False, shape=(2, ), comp_opt=9, shuffle=True),
			ParamAim(["out"], "uint64", "children", "crossover", as_attr=False, shape=(2, ), comp_opt=9, shuffle=True),
			ParamAim(["generation"], "uint64", "generation", "crossover", as_attr=False, comp_opt=9, shuffle=True),
		],
		"Individual.wrap.mutUniformInt": [
			ParamAim(
				["out", "in"], "uint64", "parent", "mutation", as_attr=False,
				alter=partial(compose, funcs=[ignore_same, itemgetter(0)]), comp_opt=9, shuffle=True
			),
			ParamAim(
				["in", "out"], "uint64", "child", "mutation", as_attr=False,
				alter=partial(compose, funcs=[ignore_same, itemgetter(0)]), comp_opt=9, shuffle=True
			),
			ParamAim(
				["in", "out", "generation"], "uint64", "generation", "mutation", as_attr=False,
				alter=ignore_same, comp_opt=9, shuffle=True
			),
		],
		"prng": [ParamAim(["seed"], "int64", "prng_seed")] + create_rng_aim("final_state", "prng_final_"),
	}
	
	ea_meta = {
		"fitness/value": [MetaEntry("description", "actual fitness value")],
		"fitness/fast_sum": [MetaEntry("description", "aggregated area under the curve for all 10 kHz bursts")],
		"fitness/slow_sum": [MetaEntry("description", "aggregated area under the curve for all 1 kHz bursts")],
		"fitness/chromo_id": [MetaEntry("description", "ID of the corresponding chromosome")],
		"fitness/generation": [MetaEntry("description", "generation in which the fitness was evaluated")],
		"population": [MetaEntry("description", "IDs of the chromosomes included in each generation")],
		"crossover": [MetaEntry("description", "IDs of the chromosomes participating in and resulting from crossover")],
		"crossover/generation": [MetaEntry("description", "value i means crossover occured while generating generation "
			"i from generation i-1")],
		"mutation": [MetaEntry("description", "IDs of chromosomes resulting from mutation; as all chromosomes of a "
			"generation participate in mutation, only alterations are recorded")],
		"mutation/generation": [MetaEntry("description", "value i means mutation occured while generating generation "
			"i from generation i-1")],
	}
	
	write_map.update(ea_map)
	metadata.update(ea_meta)

def create_write_map(rep: IcecraftRep, pop_size: int, chromo_bits: 16, temp: bool=True)-> Tuple[ParamAimMap,
	MetaEntryMap]:
	"""Create HDF5Sink write map for running a full evolutionary algorithm"""
	write_map, metadata = create_base_write_map(rep, chromo_bits)
	if temp:
		add_temp_writes(write_map, metadata)
	add_ea_writes(write_map, metadata, rep, pop_size)
	
	return write_map, metadata

def meter_setup_to_meta(setup: SetupCmd) -> List[MetaEntry]:
	if not setup.condition_(setup):
		return []
	
	res = []
	if setup.values_ is not None:
		if setup.value_ not in setup.values_:
			raise ValueError(f"'{setup.value_}' invalid for {setup.name_}")
		
		if isinstance(setup.values_, FloatCheck):
			data_type = float
		elif isinstance(setup.values_, IntCheck):
			data_type = int
		else:
			data_type = type(setup.values_[0])
		res.append(MetaEntry(setup.cmd_(full=False), setup.value_, data_type))
	
	for subcmd in setup.subcmds_:
		res.extend(meter_setup_to_meta(subcmd))
	
	return res

def create_measure_setup(driver_sn: str, target_sn: str, meter_sn: str, driver_asc: str, stack: ExitStack,
		metadata: MetaEntryMap
	) -> Tuple[Driver, TargetDevice, Meter, CalibrationData, List[Tuple[str, Mapping[str, Any]]]]:
	man = IcecraftManager()
	
	# workaround for stuck serial buffer
	man.stuck_workaround(driver_sn)
	
	gen = man.acquire(driver_sn)
	stack.callback(man.release, gen)
	
	target = man.acquire(target_sn)
	stack.callback(man.release, target)
	
	fg_config = prepare_generator(gen, driver_asc)
	driver = FixedEmbedDriver(gen, "B")
	
	cal_data = calibrate(driver)
	sink_writes = [
		("freq_gen", {"text": fg_config.to_text(), }),
		("calibration", asdict(cal_data)),
	]
	
	meter_setup = create_meter_setup()
	meter_setup.TIM.OFFS.value_ = cal_data.offset
	metadata.setdefault("fitness/measurement", []).extend(meter_setup_to_meta(meter_setup))
	
	meter = OsciDS1102E(meter_setup)
	stack.callback(meter.close)
	
	metadata.setdefault("fitness/measurement", []).extend([
		MetaEntry("driver_serial_number", gen.serial_number),
		MetaEntry("driver_hardware", gen.hardware_type),
		MetaEntry("target_serial_number", target.serial_number),
		MetaEntry("target_hardware", target.hardware_type),
		MetaEntry("meter_serial_number", meter.serial_number),
		MetaEntry("meter_hardware", meter.hardware_type),
		MetaEntry("meter_firmware", meter.firmware_version),
	])
	
	return driver, target, meter, cal_data, sink_writes

def collector_prep(driver: DummyDriver, meter: TempMeter, measure: Measure, sink: ParallelSink) -> None:
	sink.write("meta.temp", {
		"sn": meter.serial_number,
		"hw": meter.hardware_type,
		"sensor_sn": meter.sensor_serial_number,
		"sensor_hw": meter.sensor_type,
	})

def start_temp(arduino_sn: str, stack: ExitStack, sink: ParallelSink) -> None:
	if arduino_sn == "":
		# slightly differnet meaning of values in TempMeter: None means search (in args None means no TempMeter)
		arduino_sn = None
	
	temp_det = CollectorDetails(
		InitDetails(DummyDriver),
		InitDetails(TempMeter, kwargs={"arduino_sn": arduino_sn}),
		sink.get_sub(),
		0,
		"temperature",
		collector_prep,
	)
	par_col = ParallelCollector(temp_det)
	stack.enter_context(par_col)
	if not par_col.wait_collecting(3):
		raise DataCollectionError("couldn't start temperature measurement")

def run(args) -> None:
	# prepare
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	use_dummy = args.dummy
	pop_size = args.pop_size
	
	rec_temp = args.temperature is not None
	in_port = XC6200Port(IcecraftPosition(int(args.in_port[0]), int(args.in_port[1])), XC6200Direction[args.in_port[2]])
	rep = create_xc6200_rep(tuple(args.area[:2]), tuple(args.area[2:]), in_port)
	chromo_bits = 16
	
	#sink = TextfileSink("tmp.out.txt")
	write_map, metadata = create_write_map(rep, pop_size, chromo_bits, rec_temp)
	metadata.setdefault("/", []).extend([
		MetaEntry("git_commit", get_git_commit()),
		MetaEntry("python_version", sys.version),
	])
	metadata.setdefault("habitat", []).extend([
		MetaEntry("in_port_pos", args.in_port[:2], "uint16"),
		MetaEntry("in_port_dir", args.in_port[2]),
		MetaEntry("out_port_pos", [13, 32], "uint16"),
		MetaEntry("out_port_dir", "top"),
		MetaEntry("area_min_pos", args.area[:2], "uint16"),
		MetaEntry("area_max_pos", args.area[2:], "uint16"),
	])
	
	with ExitStack() as stack:
		if use_dummy:
			cal_data = CalibrationData(None, 0, 0, 0, 0)
			meter = DummyMeter()
			driver = DummyDriver()
			from unittest.mock import MagicMock
			#target = DummyTargetDevice()
			target = MagicMock()
			sink_writes = []
			print("dummies don't support real EA -> abort")
			return
		else:
			driver, target, meter, cal_data, sink_writes = create_measure_setup(
				args.generator,
				args.target,
				"",
				args.freq_gen,
				stack,
				metadata
			)
		
		sink = ParallelSink(HDF5Sink, (write_map, metadata))
		
		stack.enter_context(sink)
		
		if rec_temp and not use_dummy:
			start_temp(args.temperature, stack, sink)
		
		for prms in sink_writes:
			sink.write(*prms)
		
		sink.write("Action.rep", {
			"genes": rep.genes,
			"const": rep.constant,
			"carry_bits": list(rep.iter_carry_bits()),
			"output": rep.output,
			"colbufctrl": rep.colbufctrl,
		})
		
		measure_uc = Measure(driver, meter, sink)
		
		#hab_path = os.path.join(pkg_path, "dummy_hab.asc")
		#hab_path = os.path.join(pkg_path, "nhabitat.asc")
		
		hab_config = IcecraftRawConfig.create_from_filename(args.habitat)
		sink.write("habitat", {
			"text": hab_config.to_text(),
		})
		
		#from tests.mocks import MockRepresentation
		#rep = MockRepresentation([Gene([pow(i,j) for j in range(i)], AlleleAll(i), "") for i in range(3, 6)])
		seed = int(datetime.utcnow().timestamp())
		prng = BuiltInPRNG(seed)
		ea = SimpleEA(rep, measure_uc, SimpleUID(), prng, hab_config, target, cal_data.trig_len, sink)
		
		ea.run(pop_size, args.generations, args.crossover_prob, args.mutation_prob, EvalMode.NEW)
		
		sink.write("prng", {"seed": seed, "final_state": prng.get_state()})

def remeasure(args: Namespace) -> None:
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	comb_list = args.comb_index
	
	rec_temp = args.temperature is not None
	
	with ExitStack() as stack:
		measurement_index = args.index
		
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# habitat
		hab_text = hdf5_file["habitat"][:].tobytes().decode(encoding="utf-8")
		hab_config = IcecraftRawConfig.from_text(hab_text)
		
		# rep
		genes = HDF5Sink.extract_genes(hdf5_file["mapping/genes"], IcecraftBitPosition)
		const = HDF5Sink.extract_genes(hdf5_file["mapping/constant"], IcecraftBitPosition)
		# assume colbufctrl and output as empty
		colbufctrl = []
		output = []
		# carry data empty as the bits are set according to stored values
		carry_data = {}
		rep = IcecraftRep(genes, const, colbufctrl, output, carry_data)
		
		# carry enable
		carry_ints = hdf5_file["fitness/carry_enable"].attrs["bits"]
		carry_bits = [IcecraftBitPosition(*c) for c in carry_ints]
		carry_values = hdf5_file["fitness/carry_enable"][measurement_index]
		
		# s-t index
		if not comb_list:
			comb_list = [hdf5_file["fitness/s_t_index"][measurement_index]]
		
		# serial numbers
		gen_sn = args.generator or hdf5_file["fitness/measurement"].attrs["driver_serial_number"]
		tar_sn = args.target or hdf5_file["fitness/measurement"].attrs["target_serial_number"]
		mes_sn = args.meter or hdf5_file["fitness/measurement"].attrs["meter_serial_number"]
		
		# chromosome
		chromo_id = hdf5_file["fitness/chromo_id"][measurement_index]
		chromo_index = np.where(hdf5_file["individual/chromo_id"][:] == chromo_id)[0][0]
		allele_indices = tuple(hdf5_file["individual/chromosome"][chromo_index])
		chromo = Chromosome(chromo_id, allele_indices)
		
		chromo_bits = hdf5_file["individual/chromosome"].dtype.itemsize * 8
		
		# write to sink
		write_map, metadata = create_base_write_map(rep, chromo_bits)
		if rec_temp:
			add_temp_writes(write_map, metadata)
		re_map = {
			"SimpleEA.fitness": [
				ParamAim(["fit"], "float64", "value", "fitness", as_attr=False, comp_opt=9, shuffle=True),
				ParamAim(["fast_sum"], "float64", "fast_sum", "fitness", as_attr=False, comp_opt=9, shuffle=True),
				ParamAim(["slow_sum"], "float64", "slow_sum", "fitness", as_attr=False, comp_opt=9, shuffle=True),
				ParamAim(["chromo_index"], "uint64", "chromo_id", "fitness", as_attr=False, comp_opt=9, shuffle=True),
			],
			"remeasure.enable": [
				ParamAim(
					["carry_enable"],
					bool,
					"carry_enable",
					"fitness",
					as_attr=False,
					shape=(len(carry_bits), ),
					comp_opt=4,
				),
			],
			"remeasure.meta": [
				ParamAim(["org_filename"], str, "original_filename"),
			],
		}
		write_map.update(re_map)
		metadata.setdefault("/", []).extend([
			MetaEntry("git_commit", get_git_commit()),
			MetaEntry("python_version", sys.version),
		])
		
		# prepare setup
		driver, target, meter, cal_data, sink_writes = create_measure_setup(
			gen_sn,
			tar_sn,
			mes_sn,
			os.path.join(pkg_path, "freq_gen.asc"), #TODO: from HDF5
			stack,
			metadata
		)
		
		# prepare sink
		cur_date = datetime.now(timezone.utc)
		hdf5_filename = f"re-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		sink = ParallelSink(HDF5Sink, (write_map, metadata, hdf5_filename))
		stack.enter_context(sink)
		
		# chromosome
		sink.write("GenChromo.perform", {"return": chromo})
		# org filename
		sink.write("remeasure.meta", {"org_filename": args.data_file})
		# habitat
		sink.write("habitat", {"text": hab_config.to_text()})
		# representation
		sink.write("Action.rep", {
			"genes": rep.genes,
			"const": rep.constant,
			"carry_bits": list(rep.iter_carry_bits()),
			"output": rep.output,
			"colbufctrl": rep.colbufctrl,
		})
		
		sink.write("misc", {
			"git_commit": get_git_commit(),
			"python_version": sys.version,
		})
		
		
		if rec_temp:
			start_temp(args.temperature, stack, sink)
		
		measure_uc = Measure(driver, meter, sink)
		
		# set carry enable correctly
		for bit, val in zip(carry_bits, carry_values):
			hab_config.set_bit(bit, val)
		
		prng = BuiltInPRNG()
		
		# run measurement
		ea = SimpleEA(rep, measure_uc, SimpleUID(), prng, hab_config, target, cal_data.trig_len, sink)
		indi = Individual(chromo)
		for r in range(args.rounds):
			for comb_index in comb_list:
				fit = ea._evaluate(indi, comb_index)
				sink.write("remeasure.enable", {"carry_enable": carry_values})
				print(f"fit for {comb_index}: {fit}")
