import numpy as np
import os
import subprocess
import sys
import time

from argparse import Namespace
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import auto, Enum
from typing import Any, Callable, Iterable, List, Mapping, Optional, Tuple
from unittest.mock import MagicMock

import h5py

import applications.discern_frequency.write_map_util as write_map_util

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import EvalMode, Individual, SimpleEA
from adapters.dummies import DummyDriver
from adapters.gear.rigol import FloatCheck, IntCheck, OsciDS1102E, SetupCmd
from adapters.hdf5_sink import compose, HDF5Sink, IgnoreValue, MetaEntry, MetaEntryMap, ParamAim, ParamAimMap
from adapters.icecraft import IcecraftBitPosition, IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen,\
IcecraftManager, IcecraftRawConfig, XC6200Port, XC6200Direction
from adapters.input_gen import RandIntGen
from adapters.minvia import MinviaDriver
from adapters.mcu_drv_mtr import MCUDrvMtr
from adapters.parallel_collector import CollectorDetails, InitDetails, ParallelCollector
from adapters.parallel_sink import ParallelSink
from adapters.prng import BuiltInPRNG
from adapters.simple_sink import TextfileSink
from adapters.temp_meter import TempMeter
from adapters.unique_id import SimpleUID
from applications.discern_frequency.s_t_comb import lexicographic_combinations
from domain.data_sink import DataSink
from domain.interfaces import Driver, FitnessFunction, InputData, InputGen, Meter, OutputData, PRNG, TargetDevice, \
TargetManager
from domain.model import AlleleAll, Chromosome, Gene
from domain.request_model import ResponseObject, RequestObject, Parameter, ParameterValues
from domain.use_cases import DecTarget, ExInfoCallable, Measure, MeasureFitness
from tests.mocks import RandomMeter


class CalibrationError(Exception):
	"""Indicates an error during calibration"""
	pass

class DataCollectionError(Exception):
	"""Raised when an error occured during data collection"""
	pass

# generate tiles
def tiles_from_corners(min_pos: Tuple[int, int], max_pos: Tuple[int, int]) -> List[IcecraftPosition]:
	ptl = IcecraftPosTransLibrary()
	exp_rect = ptl.get_item("expand_rectangle", ParameterValues())
	res = exp_rect([IcecraftPosition(*min_pos), IcecraftPosition(*max_pos)])
	return res

# generate representation
def create_xc6200_rep(min_pos: Tuple[int, int], max_pos: Tuple[int, int], in_port: XC6200Port) -> IcecraftRep:
	rep_gen = XC6200RepGen()
	
	tiles = tiles_from_corners(min_pos, max_pos)
	# output ports are implicit as they depend on which neigh_op nets the habitat takes from the evolved region
	req = RequestObject(tiles=tiles, in_ports=[in_port])
	
	bef = time.perf_counter()
	rep = rep_gen(req).representation
	aft = time.perf_counter()
	print(f"rep gen took {aft-bef} s, {sum(g.alleles.size_in_bits() for g in rep.genes)} bits")
	
	return rep

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
	setup.CHAN1.OFFS.value_ = -2
	
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
		data = measure_uc(eval_req).measurement
	
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

class FreqSumFF(FitnessFunction):
	"""Fitness function for discerning frequencies.
	
	Implementation of the formula provided by Thompson in the original paper.
	"""
	def __init__(self, slow_count: int, fast_count: int, slow_div: float=30730.746, fast_div: float=30527.973):
		self._slow_count = slow_count
		self._fast_count = fast_count
		self._slow_div = slow_div
		self._fast_div = fast_div
		self._comb_table = lexicographic_combinations(self._slow_count, self._fast_count)
	
	def compute(self, request: RequestObject) -> ResponseObject:
		if len(request.measurement) != self._slow_count + self._fast_count:
			raise ValueError(f"Wrong amount of measurements: {len(request.measurement)} instead of {self._slow_count + self._fast_count}")
		
		comb_seq = self._comb_table[request.driver_data[0]]
		fast_sum = 0
		slow_sum = 0
		for i, auc in enumerate(request.measurement):
			if ((comb_seq >> i) & 1):
				fast_sum += auc
			else:
				slow_sum += auc
		
		fit = abs(slow_sum/self._slow_div - fast_sum/self._fast_div)/(self._slow_count + self._fast_count)
		return ResponseObject(
			fitness=fit,
			fast_sum=fast_sum,
			slow_sum=slow_sum,
		)
	
	@property
	def comb_count(self) -> int:
		return len(self._comb_table)

class DriverType(Enum):
	FPGA = auto()
	DRVMTR = auto()

@dataclass
class MeasureSetupInfo:
	target_sn: str
	meter_sn: str
	driver_sn: Optional[str] = None
	driver_type: DriverType = DriverType.DRVMTR
	driver_asc_path: Optional[str] = None

@dataclass
class MeasureSetup:
	driver: Optional[Driver] = None
	target: Optional[TargetDevice] = None
	meter: Optional[Meter] = None
	cal_data: Optional[CalibrationData] = None
	input_gen: Optional[InputGen] = None
	sink_writes: List[Tuple[str, Mapping[str, Any]]] = field(default_factory=list)
	preprocessing: Callable[[OutputData], OutputData] = lambda x: x


@dataclass
class AdapterSetup:
	seed: Optional[int] = None
	prng: Optional[PRNG] = None
	fit_func: Optional[FitnessFunction] = None
	input_gen: Optional[InputGen] = None


def create_preprocessing_fpga(meter: Meter, meter_setup: SetupCmd, cal_data: CalibrationData) -> Callable[[OutputData], OutputData]:
	convert = meter.raw_to_volt_func()
	trig_len = cal_data.trig_len
	time_scale = meter_setup.TIM.SCAL.value_
	
	def func(raw_data: OutputData) -> OutputData:
		data = convert(raw_data)
		h_div = (12*time_scale) / len(data)
		
		# skip before trigger
		data = data[-trig_len:]
		
		data_parts = [data[i*len(data)//10: (i+1)*len(data)//10] for i in range(10)]
		
		sum_parts = [np.trapz(p, dx=h_div) for p in data_parts]
		"""
		for i, data_part in enumerate(data_parts):
			nd = np.array(data_part)
			auc = np.trapz(nd, dx=h_div)
		"""
		return OutputData(sum_parts)
	
	return func

def create_preprocessing_mcu(sub_count: int) -> Callable[[OutputData], OutputData]:
	
	def func(raw_data: OutputData) -> OutputData:
		assert len(raw_data) == 10*sub_count
		
		bursts = [raw_data[i: i+sub_count] for i in range(0, len(raw_data), sub_count)]
		
		# sum bursts and substract offset
		# the opamp of the analog integrator has a single power supply (0 to 5 V) therefore 2.5 V represent the
		# integration sum 0; yet the (10 bit) ADC measures the voltage from 0, so 512 represents integration sum 0
		# as the output of the target is mapped from 0-3.3 V to 2.5-3.5V negative integration sums are not expected
		sum_bursts = [sum(b)-512*sub_count for b in bursts]
		
		return OutputData(sum_bursts)
	
	return func


def create_preprocessing_dummy(sub_count: int) -> Callable[[OutputData], OutputData]:
	
	def func(raw_data: OutputData) -> OutputData:
		assert (len(raw_data)//sub_count)*sub_count == len(raw_data)
		
		sums = [sum(raw_data[i: i+sub_count]) for i in range(0, len(raw_data), sub_count)]
		
		return OutputData(sums)
	
	return func


def extract_carry_enable(rep: IcecraftRep, habitat: IcecraftRawConfig, chromo: Chromosome) -> ResponseObject:
	"""Extracts the carry enable state for icecraft targets
	
	Intended to passed to the extract_info parameter of DecTarget.__init__.
	"""
	carry_enable_state = []
	for bit in rep.iter_carry_bits():
		carry_enable_state.append(habitat.get_bit(bit))
	
	return ResponseObject(carry_enable=carry_enable_state)


def create_measure_setup(info: MeasureSetupInfo, stack: ExitStack, write_map: ParamAimMap, metadata: MetaEntryMap
		) -> MeasureSetup:
	man = IcecraftManager()
	
	setup = MeasureSetup()
	
	if info.driver_type == DriverType.FPGA:
		write_map_util.add_fpga_osci(write_map, metadata)
		
		# workaround for stuck serial buffer
		man.stuck_workaround(info.driver_sn)
		
		gen = man.acquire(info.driver_sn)
		stack.callback(man.release, gen)
		
		fg_config = prepare_generator(gen, info.driver_asc_path)
		setup.driver = FixedEmbedDriver(gen, "B")
		
		cal_data = calibrate(setup.driver, info.meter_sn)
		setup.sink_writes.extend([
			("freq_gen", {"text": fg_config.to_text(), }),
			("calibration", asdict(cal_data)),
		])
		
		meter_setup = create_meter_setup()
		meter_setup.TIM.OFFS.value_ = cal_data.offset
		metadata.setdefault("fitness/measurement", []).extend(write_map_util.meter_setup_to_meta(meter_setup))
		
		
		setup.meter = OsciDS1102E(meter_setup, raw=True)
		setup.preprocessing = create_preprocessing_fpga(setup.meter, meter_setup, cal_data)
		stack.callback(setup.meter.close)
		
		metadata.setdefault("fitness/measurement", []).extend([
			MetaEntry("driver_serial_number", gen.serial_number),
			MetaEntry("driver_hardware", gen.hardware_type),
			MetaEntry("meter_firmware", setup.meter.firmware_version),
		])
	elif info.driver_type == DriverType.DRVMTR:
		write_map_util.add_drvmtr(write_map, metadata)
		setup.meter = MCUDrvMtr(info.meter_sn, 10*256, "<h", 2, 500000)
		
		stack.enter_context(setup.meter)
		
		setup.driver = setup.meter
		
		setup.preprocessing = create_preprocessing_mcu(256)
		
		metadata.setdefault("fitness/measurement", []).extend([
			MetaEntry("driver_serial_number", setup.meter.serial_number),
			MetaEntry("driver_hardware", setup.meter.hardware_type),
		])
	else:
		raise Exception(f"unsupported driver type '{info.driver_type}'")
	
	setup.target = man.acquire(info.target_sn)
	setup.target.set_fast(True)
	stack.callback(man.release, setup.target)
	
	metadata.setdefault("fitness/measurement", []).extend([
		MetaEntry("target_serial_number", setup.target.serial_number),
		MetaEntry("target_hardware", setup.target.hardware_type),
		MetaEntry("meter_serial_number", setup.meter.serial_number),
		MetaEntry("meter_hardware", setup.meter.hardware_type),
	])
	
	return setup


def create_dummy_setup(sub_count: int, write_map: ParamAimMap, metadata: MetaEntryMap) -> MeasureSetup:
	measure_setup = MeasureSetup(
		driver = MinviaDriver(drive_params=[Parameter("driver_data", InputData)]),
		target = MagicMock(),
		#target = DummyTargetDevice(),
		meter = RandomMeter(sub_count*10, 0.1),
		cal_data = CalibrationData(None, 0, 0, 0, 0),
		sink_writes = [],
		preprocessing = create_preprocessing_dummy(sub_count),
	)
	write_map_util.add_dummy(write_map, metadata, sub_count)
	
	return measure_setup


def create_adapter_setup() -> AdapterSetup:
	setup = AdapterSetup()
	
	setup.seed = int(datetime.utcnow().timestamp())
	setup.prng = BuiltInPRNG(setup.seed)
	
	setup.fit_func = FreqSumFF(5, 5)
	
	setup.input_gen = RandIntGen(setup.prng, 0, setup.fit_func.comb_count-1)
	
	return setup


def collector_prep(driver: DummyDriver, meter: TempMeter, measure: Measure, sink: ParallelSink) -> None:
	sink.write("meta.temp", {
		"sn": meter.serial_number,
		"hw": meter.hardware_type,
		"sensor_sn": meter.sensor_serial_number,
		"sensor_hw": meter.sensor_type,
	})

def start_temp(arduino_sn: str, stack: ExitStack, sink: DataSink, start_timeout: float=3) -> None:
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
	if not par_col.wait_collecting(start_timeout):
		raise DataCollectionError("couldn't start temperature measurement")

def run(args: Namespace) -> None:
	# prepare
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	use_dummy = args.dummy
	pop_size = args.pop_size
	
	rec_temp = args.temperature is not None
	in_port = XC6200Port(IcecraftPosition(int(args.in_port[0]), int(args.in_port[1])), XC6200Direction[args.in_port[2]])
	rep = create_xc6200_rep(tuple(args.area[:2]), tuple(args.area[2:]), in_port)
	chromo_bits = 16
	
	#sink = TextfileSink("tmp.out.txt")
	write_map, metadata = write_map_util.create_for_run(rep, pop_size, chromo_bits, rec_temp)
	metadata.setdefault("/", []).extend([
		MetaEntry("git_commit", get_git_commit()),
		MetaEntry("python_version", sys.version),
	])
	metadata.setdefault("habitat", []).extend([
		MetaEntry("in_port_pos", args.in_port[:2], "uint16"),
		MetaEntry("in_port_dir", args.in_port[2]),
		MetaEntry("area_min_pos", args.area[:2], "uint16"),
		MetaEntry("area_max_pos", args.area[2:], "uint16"),
	])
	if args.out_port:
		# can access without setdefault as it is set above
		metadata["habitat"].extend([
			MetaEntry("out_port_pos", args.out_port[:2], "uint16"),
			MetaEntry("out_port_dir", args.out_port[2]),
		])
	if args.habitat_con:
		metadata["habitat"].append(MetaEntry("connection", args.habitat_con))
	if args.freq_gen_con:
		metadata.setdefault("freq_gen", []).append(MetaEntry("connection", args.freq_gen_con))
	
	with ExitStack() as stack:
		if use_dummy:
			measure_setup = create_dummy_setup(25, write_map, metadata)
		else:
			setup_info = MeasureSetupInfo(
				args.target,
				args.meter,
				args.generator,
				DriverType[args.freq_gen_type],
				args.freq_gen,
			)
			
			measure_setup = create_measure_setup(setup_info, stack, write_map, metadata)
		
		cur_date = datetime.now(timezone.utc)
		hdf5_filename = args.output or f"evo-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		sink = ParallelSink(HDF5Sink, (write_map, metadata, hdf5_filename))
		
		stack.enter_context(sink)
		
		if rec_temp and not use_dummy:
			start_temp(args.temperature, stack, sink)
		
		for prms in measure_setup.sink_writes:
			sink.write(*prms)
		
		sink.write("Action.rep", {
			"genes": rep.genes,
			"const": rep.constant,
			"carry_bits": list(rep.iter_carry_bits()),
			"output": rep.output,
			"colbufctrl": rep.colbufctrl,
		})
		
		measure_uc = Measure(measure_setup.driver, measure_setup.meter, sink)
		
		hab_config = IcecraftRawConfig.create_from_filename(args.habitat)
		sink.write("habitat", {
			"text": hab_config.to_text(),
		})
		rep.prepare_config(hab_config)
		adapter_setup = create_adapter_setup()
		
		dec_uc = DecTarget(rep, hab_config, measure_setup.target, extract_info=extract_carry_enable)
		mf_uc = MeasureFitness(dec_uc, measure_uc, adapter_setup.fit_func, adapter_setup.input_gen, prep=measure_setup.preprocessing, data_sink=sink)
		
		ea = SimpleEA(rep, mf_uc, SimpleUID(), adapter_setup.prng, sink)
		
		ea.run(pop_size, args.generations, args.crossover_prob, args.mutation_prob, EvalMode[args.eval_mode])
		
		sink.write("prng", {"seed": adapter_setup.seed, "final_state": adapter_setup.prng.get_state()})

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
		write_map, metadata = write_map_util.create_base(rep, chromo_bits)
		if rec_temp:
			write_map_util.add_temp(write_map, metadata)
		re_map = {
		#TODO: adapt to sink writes from MeasureFitness
			"SimpleEA.fitness": [
				ParamAim(["fitness"], "float64", "value", "fitness", as_attr=False, comp_opt=9, shuffle=True),
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
		hdf5_filename = args.output or f"re-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
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
		rep.prepare_config(hab_config)
		
		sink.write("misc", {
			"git_commit": get_git_commit(),
			"python_version": sys.version,
		})
		
		
		if rec_temp:
			start_temp(args.temperature, stack, sink)
		
		measure_uc = Measure(driver, meter, sink)
		dec_uc = DecTarget(rep, hab_config, target, extract_info=extract_carry_enable)
		
		# set carry enable correctly
		for bit, val in zip(carry_bits, carry_values):
			hab_config.set_bit(bit, val)
		
		adapter_setup =create_adapter_setup()
		
		#TODO: prep
		#mf_uc = MeasureFitness(dec_uc, measure_uc, fit_func, , data_sink=sink)
		
		# run measurement
		ea = SimpleEA(rep, measure_uc, dec_uc, adapter_setup.fit_func, SimpleUID(), adapter_setup.prng, cal_data.trig_len, sink)
		indi = Individual(chromo)
		for r in range(args.rounds):
			for comb_index in comb_list:
				fit = ea._evaluate(indi, comb_index)
				sink.write("remeasure.enable", {"carry_enable": carry_values})
				print(f"fit for {comb_index}: {fit}")
