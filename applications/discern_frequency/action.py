import numpy as np
import os
import re
import subprocess
import sys
import time

from argparse import Namespace
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import auto, Enum
from io import StringIO
from statistics import mean, stdev
from typing import Any, Callable, Iterable, List, Mapping, Optional, TextIO, Tuple
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
from applications.discern_frequency.hdf5_desc import add_meta
from applications.discern_frequency.misc import DriverType
from applications.discern_frequency.read_hdf5_util import data_from_key, get_chromo_bits, read_carry_enable_bits, read_carry_enable_values, read_chromosome, read_fitness_chromo_id, read_habitat, read_rep, read_s_t_index
from applications.discern_frequency.s_t_comb import lexicographic_combinations
from domain.data_sink import DataSink
from domain.interfaces import Driver, FitnessFunction, InputData, InputGen, Meter, OutputData, PRNG, TargetDevice, \
TargetManager
from domain.model import AlleleAll, Chromosome, Gene
from domain.request_model import ResponseObject, RequestObject, Parameter, ParameterValues
from domain.use_cases import DecTarget, ExInfoCallable, GenChromo, Measure, MeasureFitness
from tests.mocks import RandomMeter


class CalibrationError(Exception):
	"""Indicates an error during calibration"""
	pass

class DataCollectionError(Exception):
	"""Raised when an error occured during data collection"""
	pass

class OutFormat(Enum):
	TXT = auto()

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
def prepare_generator(gen: TargetDevice, asc_file: TextIO) -> IcecraftRawConfig:
	config = IcecraftRawConfig.create_from_file(asc_file)
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

@dataclass
class MeasureSetupInfo:
	target_sn: str
	meter_sn: str
	driver_sn: Optional[str] = None
	driver_type: DriverType = DriverType.DRVMTR
	driver_asc_file: Optional[TextIO] = None

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
		
		fg_config = prepare_generator(gen, info.driver_asc_file)
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
		
		add_meta(metadata, "fitness.driver.sn", gen.serial_number)
		add_meta(metadata, "fitness.driver.hw", gen.hardware_type)
		add_meta(metadata, "fitness.meter.fw", setup.meter.firmware_version)
	elif info.driver_type == DriverType.DRVMTR:
		write_map_util.add_drvmtr(write_map, metadata)
		setup.meter = MCUDrvMtr(info.meter_sn, 10*256, "<h", 2, 500000)
		
		stack.enter_context(setup.meter)
		
		setup.driver = setup.meter
		
		setup.preprocessing = create_preprocessing_mcu(256)
		
		add_meta(metadata, "fitness.driver.sn", setup.meter.serial_number)
		add_meta(metadata, "fitness.driver.hw", setup.meter.hardware_type)
	else:
		raise Exception(f"unsupported driver type '{info.driver_type}'")
	
	setup.target = man.acquire(info.target_sn)
	setup.target.set_fast(True)
	stack.callback(man.release, setup.target)
	
	add_meta(metadata, "fitness.driver_type", info.driver_type)
	add_meta(metadata, "fitness.target.sn", setup.target.serial_number)
	add_meta(metadata, "fitness.target.hw", setup.target.hardware_type)
	add_meta(metadata, "fitness.meter.sn", setup.meter.serial_number)
	add_meta(metadata, "fitness.meter.hw", setup.meter.hardware_type)
	
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
	add_meta(metadata, "fitness.driver_type", DriverType.DUMMY)
	write_map_util.add_dummy(write_map, metadata, sub_count)
	
	return measure_setup


def setup_from_args_hdf5(args: Namespace, hdf5_file: h5py.File, write_map: ParamAimMap, metadata: MetaEntryMap
) -> MeasureSetup:
	"""create MeasureSetup from arguments and existing HDF5 file"""
	
	if args.dummy:
		measure_setup = create_dummy_setup(25, write_map, metadata)
	else:
		# driver
		try:
			drv_type = DriverType[args.freq_gen_type or data_from_key(hdf5_file, "fitness.driver_type")]
		except KeyError as ke:
			raise ValueError("Driver type defined neither in HDF5 nor via argument")
		
		with ExitStack() as stack:
			freq_gen_file = None
			if args.freq_gen:
				freq_gen_file = open(args.freq_gen, "r")
				stack.enter_context(freq_gen_file)
			elif drv_type == DriverType.FPGA:
				freq_gen_text = data_from_key(hdf5_file, "freq_gen")[:].tobytes().decode(encoding="utf-8")
				freq_gen_file = StringIO(freq_gen_text)
				stack.enter_context(freq_gen_file)
			
			setup_info = MeasureSetupInfo(
				args.target or data_from_key(hdf5_file, "fitness.target.sn"),
				args.meter or data_from_key(hdf5_file, "fitness.meter.sn"),
				args.generator or data_from_key(hdf5_file, "fitness.driver.sn"),
				drv_type,
				freq_gen_file,
			)
			
			measure_setup = create_measure_setup(setup_info, stack, write_map, metadata)
	
	return measure_setup


def add_version(metadata: MetaEntryMap) -> None:
		add_meta(metadata, "git_commit", get_git_commit())
		add_meta(metadata, "python", sys.version)


def create_fit_func() -> FitnessFunction:
	return FreqSumFF(5, 5)


def create_adapter_setup() -> AdapterSetup:
	setup = AdapterSetup()
	
	setup.seed = int(datetime.utcnow().timestamp())
	setup.prng = BuiltInPRNG(setup.seed)
	
	setup.fit_func = create_fit_func()
	
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
	add_version(metadata)
	
	add_meta(metadata, "habitat.in_port.pos", args.in_port[:2])
	add_meta(metadata, "habitat.in_port.dir", args.in_port[2])
	add_meta(metadata, "habitat.area.min", args.area[:2])
	add_meta(metadata, "habitat.area.max", args.area[2:])
	
	if args.out_port:
		# can access without setdefault as it is set above
		add_meta(metadata, "habitat.out_port.pos", args.out_port[:2])
		add_meta(metadata, "habitat.out_port.dir", args.out_port[2])
	if args.habitat_con:
		add_meta(metadata, "habitat.con", args.habitat_con)
	if args.freq_gen_con:
		add_meta(metadata, "freq_gen.con", args.freq_gen_con)
	
	with ExitStack() as stack:
		if use_dummy:
			measure_setup = create_dummy_setup(25, write_map, metadata)
		else:
			with open(args.freq_gen, "r") as asc_file:
				setup_info = MeasureSetupInfo(
					args.target,
					args.meter,
					args.generator,
					DriverType[args.freq_gen_type],
					asc_file,
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
		hab_config = read_habitat(hdf5_file)
		
		# rep
		rep = read_rep(hdf5_file, no_carry=False)
		
		# s-t index
		if not comb_list:
			comb_list = [read_s_t_index(hdf5_file, measurement_index)]
		
		# chromosome
		chromo_id = read_fitness_chromo_id(hdf5_file, measurement_index)
		chromo = read_chromosome(hdf5_file, chromo_id)
		
		chromo_bits = get_chromo_bits(hdf5_file)
		
		# write to sink
		write_map, metadata = write_map_util.create_for_remeasure(rep, chromo_bits, rec_temp)
		
		# org filename
		add_meta(metadata, "re.org", args.data_file)
		
		add_version(metadata)
		
		# copy simple metadata
		for key in ["habitat.con", "freq_gen.con", "habitat.in_port.pos", "habitat.in_port.dir", "habitat.out_port.pos",
			"habitat.out_port.dir", "habitat.area.min", "habitat.area.max"]:
			
			try:
				value = data_from_key(hdf5_file, key)
			except KeyError:
				print(f"Warning: {key} not found in original file")
				continue
			
			add_meta(metadata, key, value)
		
		# prepare setup
		measure_setup = setup_from_args_hdf5(args, hdf5_file, write_map, metadata)
		
		# prepare sink
		cur_date = datetime.now(timezone.utc)
		hdf5_filename = args.output or f"re-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		sink = ParallelSink(HDF5Sink, (write_map, metadata, hdf5_filename))
		stack.enter_context(sink)
		
		for prms in measure_setup.sink_writes:
			sink.write(*prms)
		
		# chromosome
		sink.write("GenChromo.perform", {"return": ResponseObject(chromosome=chromo)})
		# habitat
		sink.write("habitat", {"text": hab_config.to_text()})
		rep.prepare_config(hab_config)
		
		if rec_temp:
			start_temp(args.temperature, stack, sink)
		
		measure_uc = Measure(measure_setup.driver, measure_setup.meter, sink)
		dec_uc = DecTarget(rep, hab_config, measure_setup.target, extract_info=extract_carry_enable)
		
		#adapter_setup = create_adapter_setup()
		fit_func = create_fit_func()
		
		mf_uc = MeasureFitness(dec_uc, measure_uc, fit_func, None, prep=measure_setup.preprocessing, data_sink=sink)
		
		# run measurement
		for r in range(args.rounds):
			for comb_index in comb_list:
				req = RequestObject(chromosome=chromo, driver_data=InputData([comb_index]))
				fit_res = mf_uc(req)
				print(f"fit for {comb_index}: {fit_res.fitness}")
	
def clamp(args: Namespace) -> None:
	rec_temp = args.temperature is not None
	repeat = args.repeat
	
	with ExitStack() as stack:
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# habitat
		hab_config = read_habitat(hdf5_file)
		
		# rep
		rep = read_rep(hdf5_file, no_carry=False)
		
		# chromosome
		chromo_id = args.chromosome
		chromo = read_chromosome(hdf5_file, chromo_id)
		
		chromo_bits = get_chromo_bits(hdf5_file)
		
		# write to sink
		write_map, metadata = write_map_util.create_for_remeasure(rep, chromo_bits, rec_temp)
		
		# org filename
		add_meta(metadata, "re.org", args.data_file)
		
		add_version(metadata)
		
		# copy simple metadata
		for key in ["habitat.con", "freq_gen.con", "habitat.in_port.pos", "habitat.in_port.dir", "habitat.out_port.pos",
			"habitat.out_port.dir", "habitat.area.min", "habitat.area.max"]:
			
			try:
				value = data_from_key(hdf5_file, key)
			except KeyError:
				print(f"Warning: {key} not found in original file")
				continue
			
			add_meta(metadata, key, value)
		
		# prepare setup
		measure_setup = setup_from_args_hdf5(args, hdf5_file, write_map, metadata)
		
		write_map_util.add_clamp(write_map, metadata)
		
		# prepare sink
		cur_date = datetime.now(timezone.utc)
		hdf5_filename = args.output or f"clamp-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		sink = ParallelSink(HDF5Sink, (write_map, metadata, hdf5_filename))
		stack.enter_context(sink)
		
		for prms in measure_setup.sink_writes:
			sink.write(*prms)
		
		# chromosome
		sink.write("GenChromo.perform", {"return": ResponseObject(chromosome=chromo)})
		# habitat
		sink.write("habitat", {"text": hab_config.to_text()})
		rep.prepare_config(hab_config)
		
		if rec_temp:
			start_temp(args.temperature, stack, sink)
		
		measure_uc = Measure(measure_setup.driver, measure_setup.meter, sink)
		dec_uc = DecTarget(rep, hab_config, measure_setup.target, extract_info=extract_carry_enable)
		
		adapter_setup = create_adapter_setup()
		
		mf_uc = MeasureFitness(dec_uc, measure_uc, adapter_setup.fit_func, None,
			prep=measure_setup.preprocessing, data_sink=sink)
		
		id_gen = SimpleUID()
		id_gen.exclude([chromo_id])
		chromo_gen = GenChromo(id_gen, sink)
		
		@dataclass
		class FGene:
			gene: Gene
			index: int
			tile: IcecraftPosition
			const: Tuple[int, int] # index of const 0 and const 1 allele
			
			@classmethod
			def from_gene(cls, gene: Gene, index: int) -> "FGene":
				const_0 = gene.alleles.values_index([False]*len(gene.bit_positions))
				const_1 = gene.alleles.values_index([True]*len(gene.bit_positions))
				
				return cls(gene, index, gene.bit_positions[0].tile, (const_0, const_1))
		
		# get all tiles
		f_bits = set(XC6200RepGen.LUT_BITS[XC6200Direction.f])
		f_units = []
		for gene_index, gene in enumerate(rep.iter_genes()):
			gene_bits = set([(b.group, b.index) for b in gene.bit_positions])
			if not f_bits & gene_bits:
				#print(f"Nothing found in {gene_bits}")
				continue
			if f_bits ^ gene_bits:
				raise ValueError(f"Can't handle mixed gene: {f_bits ^ gene_bits}")
			
			gene_tiles = set([b.tile for b in gene.bit_positions])
			if len(gene_tiles) > 1:
				raise ValueError(f"Multiple tiles in f gene: {gene_tiles}")
			
			print("found", gene_tiles)
			
			f_units.append(FGene.from_gene(gene, gene_index))
		
		#TODO: sanity check with habitat area
		#print(candidates)
		# ignore the ones with fixed values
		candidates = [f for f in f_units if chromo.allele_indices[f.index] not in f.const]
		#print([f.tile for f in f_units if chromo.allele_indices[f.index] in f.const])
		
		fixed = []
		# choose one randomly -> shuffle
		adapter_setup.prng.shuffle(candidates)
		prev_chromo = chromo
		#print([c.tile for c in candidates])
		
		dd_list = [adapter_setup.input_gen.generate(RequestObject()).driver_data for _ in range(repeat)]
		def get_fit(dut):
			fit_list = []
			for driver_data in dd_list:
				req = RequestObject(chromosome=dut, driver_data=driver_data)
				res = mf_uc(req)
				fit_list.append(res.fitness)
			return fit_list
		
		org_fit = get_fit(chromo)
		limit = mean(org_fit)
		if repeat > 1:
			limit -= stdev(org_fit)
		print("limit", limit)
		for cur in candidates:
			# choose fixed value
			val = adapter_setup.prng.randint(0, 1)
			# set fixed value
			allele_indices = prev_chromo.allele_indices[:cur.index] + (cur.const[val], ) + prev_chromo.allele_indices[
				cur.index+1:]
			new_chromo = chromo_gen(RequestObject(allele_indices=allele_indices)).chromosome
			
			# measure
			new_fit = get_fit(new_chromo)
			print("fit", mean(new_fit), cur.tile)
			keep = limit <= mean(new_fit)
			
			sink.write("clamp", {
				"parent": prev_chromo.identifier,
				"child": new_chromo.identifier,
				"cell": cur.tile,
				"value": val,
				"clamped": keep,
			})
			
			if keep:
				prev_chromo = new_chromo
				fixed.append(cur)
		
		print([c.tile for c in fixed])
		sink.write("prng", {"seed": adapter_setup.seed, "final_state": adapter_setup.prng.get_state()})

def explain(args: Namespace) -> None:
	#TODO: move to XC6200 module
	# prepare lookup
	dst_to_src = {d: s for s, d in XC6200RepGen.STATIC_CONS}
	lut_port_to_dir = {}
	for dst in dst_to_src:
		res = re.match(r"lutff_(?P<index>\d)/in_(?P<port>\d)", dst)
		if res is None:
			continue
		index = int(res.group("index"))
		port = int(res.group("port"))
		
		# find transitive source
		src = dst
		while True:
			try:
				src = dst_to_src[src]
			except KeyError:
				break
		
		res = re.match(r"neigh_op_(?P<dir>\w+)_\d", src)
		if res is None:
			if src != "lutff_0/out":
				ValueError(f"Unexcpected source for {dst}: {src}")
			in_dir = XC6200Direction.f
		else:
			in_dir = XC6200Direction[res.group("dir")]
		
		lut_port_to_dir.setdefault(index, {})[port] = in_dir
	
	# dict to look up which input is routed trough by a lut
	mux_lut = {tuple((s & (1<<i)) > 0 for s in range(16)): i for i in range(4)}
	
	print(lut_port_to_dir)
	
	with ExitStack() as stack:
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# habitat
		hab_config = read_habitat(hdf5_file)
		
		# rep
		rep = read_rep(hdf5_file, no_carry=False)
		
		# chromosome
		chromo_id = args.chromosome
		chromo = read_chromosome(hdf5_file, chromo_id)
		
		bits_to_dir = {b: d for d, b in XC6200RepGen.LUT_BITS.items()}
		cell_map = {}
		for gene_index, gene in enumerate(rep.iter_genes()):
			gene_bits = tuple((b.group, b.index) for b in gene.bit_positions)
			try:
				lut_dir = bits_to_dir[gene_bits]
			except KeyError as ke:
				raise ValueError(f"incompatible representation {gene_bits} not in {list(bits_to_dir.keys())}") from ke
			
			gene_tiles = set([b.tile for b in gene.bit_positions])
			if len(gene_tiles) > 1:
				raise ValueError(f"Multiple tiles in gene: {gene}")
			
			cell_map.setdefault(gene_tiles.pop(), {})[lut_dir] = gene_index
		
		cell_state = {}
		for tile in sorted(cell_map):
			print(tile)
			cell_state[tile] = {}
			for lut_dir in sorted(cell_map[tile]):
				gene_index = cell_map[tile][lut_dir]
				gene = rep.genes[gene_index]
				allele_index = chromo.allele_indices[gene_index]
				value = gene.alleles[allele_index].values
				if lut_dir == XC6200Direction.f:
					print("function", value)
					cell_state[tile][lut_dir] = value
					continue
				lut_index = gene.bit_positions[0].group//2
				in_port = mux_lut[value]
				print(lut_dir, gene_index, lut_port_to_dir[lut_index][in_port])
				cell_state[tile][lut_dir] = lut_port_to_dir[lut_index][in_port]
		
		for tile in sorted(cell_state):
			out = [f"{tile.x}", f"{tile.y}"]
			for lut_dir in [XC6200Direction.top, XC6200Direction.lft, XC6200Direction.bot, XC6200Direction.rgt]:
				out.append(cell_state[tile][lut_dir].name)
			out.append(str(cell_state[tile][XC6200Direction.f]))
			print(",".join(out))

def generation_info(hdf5_file: h5py.File):
	# generation
	print("last generation")
	gen = data_from_key(hdf5_file, "fitness.generation")[:]
	fit = data_from_key(hdf5_file, "fitness.value")
	chromo_ids = data_from_key(hdf5_file, "fitness.chromo_id")
	last_indices = np.where(gen == gen[-1])[0]
	last_fit = fit[last_indices]
	last_id = chromo_ids[last_indices]
	rank = last_fit.argsort()[::-1]#[:3]
	
	for f, i in zip(last_fit[rank], last_id[rank]):
		print(i, f)
	# top 3 chromosomes

def info(args: Namespace) -> None:
	with h5py.File(args.data_file, "r") as hdf5_file:
		
		generation_info(hdf5_file)
		

