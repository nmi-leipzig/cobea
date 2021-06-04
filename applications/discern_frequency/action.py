import numpy as np
import os
import subprocess
import sys
import time

from dataclasses import asdict, dataclass
from datetime import datetime
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from typing import Any, Iterable, List, Mapping, Tuple

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import SimpleEA
from adapters.dummies import DummyDriver, DummyMeter
from adapters.gear.rigol import OsciDS1102E
from adapters.hdf5_sink import compose, HDF5Sink, IgnoreValue, ParamAim
from adapters.icecraft import IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen, IcecraftManager,\
IcecraftRawConfig, XC6200Port, XC6200Direction
from adapters.parallel_collector import CollectorDetails, InitDetails, ParallelCollector
from adapters.parallel_sink import ParallelSink
from adapters.prng import BuiltInPRNG
from adapters.simple_sink import TextfileSink
from adapters.temp_meter import TempMeter
from adapters.unique_id import SimpleUID
from domain.interfaces import Driver, InputData, TargetDevice, TargetManager
from domain.model import AlleleAll, Gene
from domain.request_model import RequestObject
from domain.use_cases import Measure

class CalibrationError(Exception):
	"""Indicates an error during calibration"""
	pass

# generate tiles
def tiles_from_corners(min_pos: Tuple[int, int], max_pos: Tuple[int, int]) -> List[IcecraftPosition]:
	req = RequestObject(identifier="expand_rectangle", description="")
	ptl = IcecraftPosTransLibrary()
	exp_rect = ptl.get_pos_trans(req)
	res = exp_rect([IcecraftPosition(*min_pos), IcecraftPosition(*max_pos)])
	return res

# generate representation
def create_xc6200_rep(min_pos: Tuple[int, int], max_pos: Tuple[int, int]) -> IcecraftRep:
	#TODO: add input port to function parameters
	rep_gen = XC6200RepGen()
	
	tiles = tiles_from_corners(min_pos, max_pos)
	# output ports are implicit as they depend on which neigh_op nets the habitat takes from the evolved region
	in_port = XC6200Port(IcecraftPosition(10, 29), XC6200Direction.lft)
	req = RequestObject(tiles=tiles, in_ports=[in_port])
	
	bef = time.perf_counter()
	rep = rep_gen(req)
	aft = time.perf_counter()
	print(f"rep gen took in {aft-bef} s, {sum(g.alleles.size_in_bits() for g in rep.genes)} bits")
	
	return rep

def is_rep_fitting(rep: IcecraftRep, chromo_bits: int) -> bool:
	"""check if representation fits in a certain number of bits"""
	for gene in rep.iter_genes():
		if len(gene.alleles) > 1<<chromo_bits:
			return False
	
	return True

# flash FPGAs
def prepare_generator(gen: TargetDevice, asc_path: str) -> None:
	config = IcecraftRawConfig.create_from_file(asc_path)
	gen.configure(config)

def create_meter_setup():
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

def calibrate(driver: Driver) -> CalibrationData:
	meter_setup = create_meter_setup()
	meter_setup.TIM.OFFS.value_ = 2.5
	
	meter = OsciDS1102E(meter_setup, data_chan=2)
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
	"""raise IgnoreValue of first two elements are equal, els return the first"""
	if x[0] == x[1]:
		raise IgnoreValue()
	return x[0]

def create_write_map(rep: IcecraftRep, pop_size: int, chromo_bits: 16) -> Mapping[str, List[ParamAim]]:
	if not is_rep_fitting(rep, chromo_bits):
		raise ValueError(f"representation needs more than {chromo_bits} bits")
	
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
		],
		"SimpleEA.ea_params": [
			ParamAim(["pop_size"], "uint64", "pop_size"),
			ParamAim(["gen_count"], "uint64", "gen_count"),
			ParamAim(["crossover_prob"], "float64", "crossover_prob"),
			ParamAim(["mutation_prob"], "float64", "mutation_prob"),
		],
		"SimpleEA.random_initial": create_rng_aim("state", "random_initial_"),
		"SimpleEA.random_final": create_rng_aim("state", "random_final_"),
		"SimpleEA.gen":[
			ParamAim(["pop"], "uint64", "population", as_attr=False, shape=(pop_size, ), shuffle=True),
		],
		"RandomChromo.perform": chromo_aim,
		"GenChromo.perform": chromo_aim,
		"Action.rep": HDF5Sink.create_gene_aims("genes", len(rep.genes), h5_path="mapping/genes")+\
			HDF5Sink.create_gene_aims("const", len(rep.constant), h5_path="mapping/constant")+[
				ParamAim(["carry_bits"], "uint16", "bits", "fitness/carry_enable",
					alter=partial(compose, funcs=[itemgetter(0), partial(map, methodcaller("to_ints")), list])),
			],
		"Individual.wrap.cxOnePoint": [
			ParamAim(["in"], "uint64", "parents", "crossover", as_attr=False, shape=(2, ), comp_opt=9, shuffle=True),
			ParamAim(["out"], "uint64", "children", "crossover", as_attr=False, shape=(2, ), comp_opt=9, shuffle=True),
		],
		"Individual.wrap.mutUniformInt": [
			ParamAim(
				["in", "out"], "uint64", "parent", "mutation", as_attr=False,
				alter=partial(compose, funcs=[ignore_same, itemgetter(0)]), comp_opt=9, shuffle=True
			),
			ParamAim(
				["out", "in"], "uint64", "child", "mutation", as_attr=False,
				alter=partial(compose, funcs=[ignore_same, itemgetter(0)]), comp_opt=9, shuffle=True
			),
		],
		"calibration": [
			ParamAim(["data"], "float64", "calibration", as_attr=False, shuffle=False),
			ParamAim(["rising_edge"], "uint64", "rising_edge", "calibration"),
			ParamAim(["falling_edge"], "uint64", "falling_edge", "calibration"),
			ParamAim(["trig_len"], "uint64", "trig_len", "calibration"),
			ParamAim(["offset"], "float64", "offset", "calibration"),
		],
		"prng": [ParamAim(["seed"], "int64", "prng_seed")] + create_rng_aim("final_state", "prng_final_"),
		"misc": [
			ParamAim(["git_commit"], str, "git_commit"), 
			ParamAim(["python_version"], str, "python_version"),
		],
		"habitat": [ParamAim(
			["text"], "uint8", "habitat", as_attr=False,
			alter=partial(compose, funcs=[itemgetter(0), partial(bytearray, encoding="utf-8")]), comp_opt=9
		),],
		"temperature.perform": [
			ParamAim(["return"], "float16", "celcius", "temperature", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), itemgetter(0)]), comp_opt=9, shuffle=True),
		],
		"temperature.additional": [
			ParamAim(["time"], "float64", "time", "temperature", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), methodcaller("timestamp")]), comp_opt=9, shuffle=True),
		],
	}
	
	return write_map

def run(args) -> None:
	# prepare
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	use_dummy = False
	pop_size = 4
	
	rep = create_xc6200_rep((10, 23), (19, 32))
	chromo_bits = 16
	
	man = IcecraftManager()
	#sink = TextfileSink("tmp.out.txt")
	# use attrgetter and so on to allow pickling for multiprocessing
	write_map = create_write_map(rep, pop_size, chromo_bits)
	
	sink = ParallelSink(HDF5Sink, (write_map, ))
	with ExitStack() as stack:
		stack.enter_context(sink)
		
		temp_det = CollectorDetails(
			InitDetails(DummyDriver),
			InitDetails(TempMeter),
			sink.get_sub(),
			0,
			"temperature",
		)
		stack.enter_context(ParallelCollector(temp_det))
		
		sink.write("Action.rep", {
			"genes": rep.genes,
			"const": rep.constant,
			"carry_bits": list(rep.iter_carry_bits()),
		})
		sink.write("misc", {
			"git_commit": get_git_commit(),
			"python_version": sys.version,
		})
		
		if use_dummy:
			meter = DummyMeter()
			driver = DummyDriver()
			from unittest.mock import MagicMock
			#target = DummyTargetDevice()
			target = MagicMock()
		else:
			# workaround for stuck serial buffer
			man.stuck_workaround(args.generator)
			
			gen = man.acquire(args.generator)
			
			target = man.acquire(args.target)
			
			prepare_generator(gen, os.path.join(pkg_path, "freq_gen.asc"))
			driver = FixedEmbedDriver(gen, "B")
			cal_data = calibrate(driver)
			sink.write("calibration", asdict(cal_data))
			
			meter_setup = create_meter_setup()
			meter_setup.TIM.OFFS.value_ = cal_data.offset
			meter = OsciDS1102E(meter_setup)
			
		
		try:
			measure_uc = Measure(driver, meter, sink)
			
			#hab_path = os.path.join(pkg_path, "dummy_hab.asc")
			hab_path = os.path.join(pkg_path, "nhabitat.asc")
			hab_config = IcecraftRawConfig.create_from_file(hab_path)
			sink.write("habitat", {
				"text": hab_config.to_text(),
			})
			
			#from tests.mocks import MockRepresentation
			#rep = MockRepresentation([Gene([pow(i,j) for j in range(i)], AlleleAll(i), "") for i in range(3, 6)])
			seed = int(datetime.utcnow().timestamp())
			prng = BuiltInPRNG(seed)
			ea = SimpleEA(rep, measure_uc, SimpleUID(), prng, hab_config, target, cal_data.trig_len, sink)
			
			ea.run(pop_size, 2, 0.7, 0.001756)
			#ea.run(pop_size, 600, 0.7, 0.001756)
			sink.write("prng", {"seed": seed, "final_state": prng.get_state()})
		finally:
			if not use_dummy:
				man.release(target)
				man.release(gen)
				meter.close()

