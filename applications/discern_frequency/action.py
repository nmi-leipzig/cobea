import numpy as np
import os
import re
import subprocess
import sys
import time

from argparse import Namespace
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import auto, Enum
from statistics import mean, median, stdev
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, TextIO, Tuple
from unittest.mock import MagicMock

import h5py

import applications.discern_frequency.write_map_util as write_map_util

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import EvalMode, Individual, SimpleEA
from adapters.dummies import DummyDriver
from adapters.gear.rigol import FloatCheck, IntCheck, OsciDS1102E, SetupCmd
from adapters.hdf5_sink import compose, HDF5Sink, IgnoreValue, MetaEntry, MetaEntryMap, ParamAim, ParamAimMap
from adapters.icecraft import CarryData, IcecraftBitPosition, IcecraftDevice, IcecraftPosition, IcecraftPosTransLibrary,\
	IcecraftRep, XC6200RepGen,IcecraftManager, IcecraftRawConfig, PartConf, XC6200Port, XC6200Direction, XC6200Cell
from adapters.input_gen import RandIntGen
from adapters.minvia import MinviaDriver
from adapters.icecraft.misc import IcecraftLUTPosition
from adapters.mcu_drv_mtr import MCUDrvMtr
from adapters.parallel_collector import CollectorDetails, InitDetails, ParallelCollector
from adapters.parallel_sink import ParallelSink
from adapters.pop_init import GivenPop, RandomPop
from adapters.prng import BuiltInPRNG
from adapters.simple_sink import TextfileSink
from adapters.temp_meter import TempMeter
from adapters.unique_id import SimpleUID
from applications.discern_frequency.hdf5_content import ContentType, get_content_type
from applications.discern_frequency.hdf5_desc import add_meta
from applications.discern_frequency.misc import DriverType
from applications.discern_frequency.read_hdf5_util import data_from_key, get_chromo_bits, read_carry_enable_bits, read_carry_enable_values, read_chromosome, read_fitness_chromo_id, read_generation, read_habitat, read_osci_setup, read_rep, read_s_t_index
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

class ExtractTarget(Enum):
	MEASUREMENT = auto()
	MEAN = auto()


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


# move representation to other tiles
def move_rep(rep: IcecraftRep, x_offset: int, y_offset: int, config: IcecraftRawConfig) -> IcecraftRep:
	# currently no support for colbufctrl
	if len(rep.colbufctrl):
		raise ValueError("Can't relocate colbuctrl")
	# check tile type
	# move coordinates
	def move_pos(org_pos):
		new_pos = IcecraftPosition(org_pos.x+x_offset, org_pos.y+y_offset)
		if config.get_tile_type(org_pos) != config.get_tile_type(new_pos):
			raise ValueError(f"Can't move {config.get_tile_type(org_bit.tile())} to {config.get_tile_type(new_pos)}")
		
		return new_pos
	
	def move_bit(org_bit):
		new_pos = move_pos(org_bit.tile)
		return IcecraftBitPosition.from_tile(new_pos, org_bit.group, org_bit.index)
	
	def move_gene(org_gene):
		return Gene(
			tuple(move_bit(b) for b in org_gene.bit_positions),
			deepcopy(org_gene.alleles),
			org_gene.description
		)
	
	def move_lut_pos(org_lut_pos):
		new_pos = move_pos(org_lut_pos.tile)
		return IcecraftLUTPosition.from_tile(new_pos, org_lut_pos.z)
	
	def move_part_conf(org_pc):
		new_bits = tuple(move_bit(b) for b in org_pc.bits)
		return PartConf(new_bits, deepcopy(org_pc.values))
	
	def move_carry_data(org_cd):
		ce = tuple(move_bit(b) for b in org_cd.carry_enable)
		cu = [move_part_conf(p) for p in org_cd.carry_use]
		return CarryData(org_cd.lut_index, ce, cu)
	
	genes = [move_gene(g) for g in rep.genes]
	constant = [move_gene(g) for g in rep.constant]
	output = [move_lut_pos(l) for l in rep.output]
	
	carry_data = {move_pos(k): {i: move_carry_data(c) for i, c in v.items()} for k, v in rep.carry_data.items()}
	
	return IcecraftRep(genes, constant, [], output, carry_data)


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
			driver_data = InputData([100]),
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
	driver_text: Optional[str] = None

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


@dataclass
class EASetup:
	pop_size: Optional[int] = None
	generations: Optional[int] = None
	crossover_prob: Optional[float] = None
	mutation_prob: Optional[float] = None
	eval_mode: Optional[EvalMode] = None

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


def prepare_fpga_driver(driver_sn: str, config_text: str, man: IcecraftManager, stack: ExitStack) -> Tuple[IcecraftDevice, IcecraftRawConfig]:
	# workaround for stuck serial buffer
	man.stuck_workaround(driver_sn)
	
	gen = man.acquire(driver_sn)
	stack.callback(man.release, gen)
	
	config = IcecraftRawConfig.from_text(config_text)
	gen.configure(config)
	
	return gen, config


def prepare_osci(cal_data: CalibrationData, stack: ExitStack) -> Tuple[OsciDS1102E, SetupCmd]:
	meter_setup = create_meter_setup()
	meter_setup.TIM.OFFS.value_ = cal_data.offset
	
	meter = OsciDS1102E(meter_setup, raw=True)
	stack.callback(meter.close)
	
	return meter, meter_setup


def prepare_target(target_sn: str, man: IcecraftManager, stack: ExitStack) -> IcecraftDevice:
	target = man.acquire(target_sn)
	target.set_fast(True)
	stack.callback(man.release, target)
	
	return target


def create_measure_setup(setup_info: MeasureSetupInfo, stack: ExitStack, write_map: ParamAimMap, metadata: MetaEntryMap
		) -> MeasureSetup:
	man = IcecraftManager()
	
	setup = MeasureSetup()
	
	if setup_info.driver_type == DriverType.FPGA:
		write_map_util.add_fpga_osci(write_map, metadata)
		
		gen, fg_config = prepare_fpga_driver(setup_info.driver_sn, setup_info.driver_text, man, stack)
		setup.driver = FixedEmbedDriver(gen, "B")
		
		cal_data = calibrate(setup.driver, setup_info.meter_sn)
		setup.sink_writes.extend([
			("freq_gen", {"text": fg_config.to_text(), }),
			("calibration", asdict(cal_data)),
		])
		
		setup.meter, meter_setup = prepare_osci(cal_data, stack)
		
		setup.preprocessing = create_preprocessing_fpga(setup.meter, meter_setup, cal_data)
		
		write_map_util.write_setup(metadata, meter_setup)
		add_meta(metadata, "osci.channel", meter.data_chan)
		add_meta(metadata, "fitness.driver.sn", gen.serial_number)
		add_meta(metadata, "fitness.driver.hw", gen.hardware_type)
		add_meta(metadata, "fitness.meter.fw", setup.meter.firmware_version)
	elif setup_info.driver_type == DriverType.DRVMTR:
		write_map_util.add_drvmtr(write_map, metadata)
		setup.meter = MCUDrvMtr(setup_info.meter_sn, 10*256, "<h", 2, 500000)
		
		stack.enter_context(setup.meter)
		
		setup.driver = setup.meter
		
		setup.preprocessing = create_preprocessing_mcu(256)
		
		add_meta(metadata, "fitness.driver.sn", setup.meter.serial_number)
		add_meta(metadata, "fitness.driver.hw", setup.meter.hardware_type)
	else:
		raise Exception(f"unsupported driver type '{setup_info.driver_type}'")
	
	setup.target = prepare_target(setup_info.target_sn, man, stack)
	
	add_meta(metadata, "fitness.driver_type", setup_info.driver_type)
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


def setup_from_args_hdf5(args: Namespace, hdf5_file: h5py.File, stack: ExitStack, write_map: ParamAimMap,
	metadata: MetaEntryMap) -> MeasureSetup:
	"""create MeasureSetup from arguments and existing HDF5 file"""
	
	if args.dummy:
		measure_setup = create_dummy_setup(25, write_map, metadata)
	else:
		# driver
		try:
			drv_type = DriverType[args.freq_gen_type or data_from_key(hdf5_file, "fitness.driver_type")]
		except KeyError as ke:
			raise ValueError("Driver type defined neither in HDF5 nor via argument")
		
		freq_gen_text = None
		if args.freq_gen:
			with open(args.freq_gen, "r") as freq_gen_file:
				freq_gen_text = freq_gen_file.read()
		elif drv_type == DriverType.FPGA:
			freq_gen_text = data_from_key(hdf5_file, "freq_gen")[:].tobytes().decode(encoding="utf-8")
		
		setup_info = MeasureSetupInfo(
			args.target or data_from_key(hdf5_file, "fitness.target.sn"),
			args.meter or data_from_key(hdf5_file, "fitness.meter.sn"),
			args.generator or data_from_key(hdf5_file, "fitness.driver.sn"),
			drv_type,
			freq_gen_text,
		)
		
		measure_setup = create_measure_setup(setup_info, stack, write_map, metadata)
	
	return measure_setup


def temp_from_args_hdf5(args: Namespace, hdf5_file: h5py.File) -> Tuple[bool, str]:
	"""Extract information about temperature recording from args and HDF5 file"""
	
	arduino_sn = args.temperature
	if arduino_sn == "":
		try:
			arduino_sn = data_from_key(hdf5_file, "temp.reader.sn")
		except KeyError:
			pass
	
	return arduino_sn is not None, arduino_sn


def ea_from_args_hdf5(args: Namespace, hdf5_file: h5py.File) -> EASetup:
	res = EASetup()
	
	# pop size always has to match HDF5 data
	res.pop_size = int(data_from_key(hdf5_file, "ea.pop_size"))
	res.generations = int(args.generations or data_from_key(hdf5_file, "ea.gen_count"))
	res.crossover_prob = float(args.crossover_prob or data_from_key(hdf5_file, "ea.crossover_prob"))
	res.mutation_prob = float(args.mutation_prob or data_from_key(hdf5_file, "ea.mutation_prob"))
	mode_name = args.eval_mode or data_from_key(hdf5_file, "ea.eval_mode")
	res.eval_mode = EvalMode[mode_name]
	
	return res


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

def copy_meta(hdf5_file: h5py.File, metadata: MetaEntryMap, key_list: Iterable[str]) -> None:
	"""Copy values directly to metadata"""
	for key in key_list:
		try:
			value = data_from_key(hdf5_file, key)
		except KeyError:
			print(f"Warning: {key} not found in original file")
			continue
		
		add_meta(metadata, key, value)


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
			asc_text = None
			if args.freq_gen:
				with open(args.freq_gen, "r") as asc_file:
					asc_text = asc_file.read()
			
			setup_info = MeasureSetupInfo(
				args.target,
				args.meter,
				args.generator,
				DriverType[args.freq_gen_type],
				asc_text,
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
		
		uid_gen = SimpleUID()
		popi = RandomPop(rep, uid_gen, adapter_setup.prng, sink)
		
		ea = SimpleEA(rep, mf_uc, uid_gen, popi, sink)
		
		ea.run(pop_size, args.generations, args.crossover_prob, args.mutation_prob, EvalMode[args.eval_mode])
		
		sink.write("prng", {"seed": adapter_setup.seed, "final_state": adapter_setup.prng.get_state()})

def remeasure(args: Namespace) -> None:
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	comb_list = args.comb_index
	
	with ExitStack() as stack:
		measurement_index = args.index
		
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# measure temperature?
		rec_temp, temp_sn = temp_from_args_hdf5(args, hdf5_file)
		
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
		copy_meta(hdf5_file, metadata, ["habitat.con", "freq_gen.con", "habitat.in_port.pos", "habitat.in_port.dir",
			"habitat.out_port.pos", "habitat.out_port.dir", "habitat.area.min", "habitat.area.max"])
		
		# prepare setup
		measure_setup = setup_from_args_hdf5(args, hdf5_file, stack, write_map, metadata)
		
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
			start_temp(temp_sn, stack, sink)
		
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

def restart(args: Namespace) -> None:
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	generation_index = args.index
	
	with ExitStack() as stack:
		
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# measure temperature?
		rec_temp, temp_sn = temp_from_args_hdf5(args, hdf5_file)
		
		# habitat
		hab_config = read_habitat(hdf5_file)
		
		# rep
		rep = read_rep(hdf5_file, no_carry=False)
		
		if args.offset:
			if not args.habitat:
				raise ValueError("offset requires a new habitat")
			hab_config = IcecraftRawConfig.create_from_filename(args.habitat)
			rep = move_rep(rep, args.offset[0], args.offset[1], hab_config)
		
		# ea_setup
		ea_setup = ea_from_args_hdf5(args, hdf5_file)
		
		# initial population
		fst_pop = read_generation(hdf5_file, generation_index)
		
		# write to sink
		chromo_bits = get_chromo_bits(hdf5_file)
		write_map, metadata = write_map_util.create_for_run(rep, ea_setup.pop_size, chromo_bits, rec_temp)
		
		# org filename
		add_meta(metadata, "re.org", args.data_file)
		
		add_version(metadata)
		
		meta_list = ["habitat.con", "freq_gen.con", "habitat.in_port.dir", "habitat.out_port.dir"]
		pos_list = ["habitat.in_port.pos", "habitat.out_port.pos",  "habitat.area.min", "habitat.area.max"]
		if args.offset:
			for key in pos_list:
				try:
					value = data_from_key(hdf5_file, key)
				except KeyError:
					print(f"Warning: {key} not found in original file")
					continue
				assert len(value) == 2
				
				add_meta(metadata, key, [value[i]+args.offset[i] for i in (0, 1)])
		else:
			meta_list.extend(pos_list)
		
		# copy simple metadata
		copy_meta(hdf5_file, metadata, meta_list)
		
		# prepare setup
		measure_setup = setup_from_args_hdf5(args, hdf5_file, stack, write_map, metadata)
		
		# prepare sink
		cur_date = datetime.now(timezone.utc)
		hdf5_filename = args.output or f"restart-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		sink = ParallelSink(HDF5Sink, (write_map, metadata, hdf5_filename))
		stack.enter_context(sink)
		
		for prms in measure_setup.sink_writes:
			sink.write(*prms)
		
		# chromosomes
		known_chromos = set()
		for chromo in fst_pop:
			if chromo.identifier in known_chromos:
				continue
			known_chromos.add(chromo.identifier)
			sink.write("GenChromo.perform", {"return": ResponseObject(chromosome=chromo)})
		# habitat
		sink.write("habitat", {"text": hab_config.to_text()})
		rep.prepare_config(hab_config)
		
		if rec_temp:
			start_temp(temp_sn, stack, sink)
		
		measure_uc = Measure(measure_setup.driver, measure_setup.meter, sink)
		dec_uc = DecTarget(rep, hab_config, measure_setup.target, extract_info=extract_carry_enable)
		
		adapter_setup = create_adapter_setup()
		
		mf_uc = MeasureFitness(dec_uc, measure_uc, adapter_setup.fit_func, adapter_setup.input_gen, prep=measure_setup.preprocessing, data_sink=sink)
		
		uid_gen = SimpleUID()
		uid_gen.exclude(known_chromos)
		popi = GivenPop(fst_pop)
		
		ea = SimpleEA(rep, mf_uc, uid_gen, popi, sink)
		
		ea.run(ea_setup.pop_size, ea_setup.generations, ea_setup.crossover_prob, ea_setup.mutation_prob,
			ea_setup.eval_mode)
		
		sink.write("prng", {"seed": adapter_setup.seed, "final_state": adapter_setup.prng.get_state()})

def clamp(args: Namespace) -> None:
	repeat = args.repeat
	
	with ExitStack() as stack:
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# measure temperature?
		rec_temp, temp_sn = temp_from_args_hdf5(args, hdf5_file)
		
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
		measure_setup = setup_from_args_hdf5(args, hdf5_file, stack, write_map, metadata)
		
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
			start_temp(temp_sn, stack, sink)
		
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
		limit = mean(org_fit)*0.99
		#if repeat > 1:
		#	limit -= stdev(org_fit)
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

def get_connected(cell_state: Dict[IcecraftPosition, XC6200Cell], out_pos: IcecraftPosition, out_dir: XC6200Direction
) -> Dict[IcecraftPosition, List[XC6200Direction]]:
	res = {}
	todo = [(out_pos, out_dir)]
	while todo:
		tile, dir_ = todo.pop()
		res.setdefault(tile, []).append(dir_)
		# iterate over all 
		for new_dir in cell_state[tile][dir_]:
			if new_dir == XC6200Direction.f:
				new_tile = tile
			else:
				new_tile = XC6200RepGen.get_neighbor(tile, new_dir)
				new_dir = new_dir.opposite()
			
			if new_tile not in cell_state:
				continue
			try:
				if new_dir in res[new_tile]:
					continue
			except KeyError:
				pass
			
			todo.append((new_tile, new_dir))
	
	return res

def generate_tikz(cell_state: Dict[IcecraftPosition, XC6200Cell], marks: Dict[IcecraftPosition, List[XC6200Direction]]={}, special_pos: List[IcecraftPosition]=[], in_port: Optional[XC6200Port]=None, out_port: Optional[XC6200Port]=None) -> str:
	offset = min(cell_state)
	
	res = []
	res.append(r"\begin{tikzpicture}")
	in_map = {
		XC6200Direction.top: 115,
		XC6200Direction.lft: 205,
		XC6200Direction.bot: 295,
		XC6200Direction.rgt: 25,
	}
	
	out_map = {
		XC6200Direction.top: 65,
		XC6200Direction.lft: 155,
		XC6200Direction.bot: 245,
		XC6200Direction.rgt: 335,
	}
	
	off_unit = [(0, 1), (-1, 0), (0, -1), (1, 0)]
	off_fac = lambda p, o: [tuple(p*a for a in t) for t in o]
	
	pos_scale = 0.8
	cell_width = 0.6
	arrow_off = off_fac(pos_scale-cell_width, off_unit)#[(0, 0.5), (-0.5, 0), (0, -0.5), (0.5, 0)]
	square_min_unit = [(-0.5, -1), (0, -0.5), (-0.5, 0), (-1, -0.5)]
	square_max_unit = [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
	square_min = off_fac(0.1, square_min_unit)
	square_max = off_fac(0.1, square_max_unit)
	
	for pos, cell in cell_state.items():
		try:
			mark_dir = marks[pos]
		except KeyError:
			mark_dir = []
		
		is_special = pos in special_pos
		cell_color = "clclamped" if is_special else "black"
		
		name = f"s{pos.x:02}{pos.y:02}"
		res.append(r"\draw ("+f"{(pos.x-offset.x)*pos_scale}, {(pos.y-offset.y)*pos_scale}) node[shape=rectangle, minimum height={cell_width:.3f}cm, minimum width={cell_width:.3f}cm, draw={cell_color}] ("+name+") {};")
		arrow = [False]*4
		box = [False]*4
		in_marked = [False]*4
		for dir_ in XC6200Direction:
			marked = dir_ in mark_dir
			color = "clcellout" if marked else ""
			if dir_ == XC6200Direction.f:
				for used in cell[dir_]:
					arrow[used] = True
					box[used] = True
					in_marked[used] |= marked
				continue
			for used in cell[dir_]:
				if used == XC6200Direction.f:
					continue
				arrow[used] = True
				in_marked[used] |= marked
				res.append(r"\draw["+color+"] ("+f"{name}.{in_map[used]}"+") -- ("+f"{name}.{out_map[dir_]}"+");")
		
		if XC6200Direction.f in mark_dir:
			f_color = "clcellout"
		elif is_special:
			f_color = cell_color
		else:
			f_color = ""
		for use, dir_ in zip(box, XC6200Direction):
			if not use:
				continue
			out = f"{name}.{in_map[dir_]}"
			res.append(f"\draw[{f_color}] ($({out})+{square_min[dir_]}$) rectangle ($({out})+{square_max[dir_]}$);")
		for use, dir_ in zip(arrow, XC6200Direction):
			color = "clcellout" if in_marked[dir_] else ""
			if not use:
				continue
			out = f"{name}.{in_map[dir_]}"
			res.append(f"\draw[<-, {color}] ({out}) -- ($({out})+({arrow_off[dir_][0]}, {arrow_off[dir_][1]})$);")
	if out_port:
		res.append(f"\draw[clcellout, ->] (s{out_port.tile.x:02}{out_port.tile.y:02}.{out_map[out_port.direction]}) -- ++({arrow_off[out_port.direction][0]*2}, {arrow_off[out_port.direction][1]*2}) node[above] {{Out}};")
	if in_port:
		res.append(f"\draw[<-] (s{in_port.tile.x:02}{in_port.tile.y:02}.{in_map[in_port.direction]}) -- ++({arrow_off[in_port.direction][0]*2}, {arrow_off[in_port.direction][1]*2}) node[left] {{In}};")
	
	res.append(r"\end{tikzpicture}")
	
	return "\n".join(res)

def explain(args: Namespace) -> None:
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
		
		# assume clamping
		all_ids = data_from_key(hdf5_file, "fitness.chromo_id")
		assert chromo_id == all_ids[0]
		
		# get clamped positions
		pos_list = data_from_key(hdf5_file, "clamp.cell")
		clamp_flag = data_from_key(hdf5_file, "clamp.clamped")
		assert len(pos_list) == len(clamp_flag)
		assert len(pos_list) == 100
		clamp_pos = [IcecraftPosition(*p) for p, f in zip(pos_list, clamp_flag) if f]
		
		rep.prepare_config(hab_config)
		rep.decode(hab_config, chromo)
		hab_config.write_asc("tmp.explain.asc")
		
		cell_state = XC6200Cell.get_cell_structure(rep, chromo)
		
		for tile in sorted(cell_state):
			out = [f"{tile.x}", f"{tile.y}"]
			for lut_dir in [XC6200Direction.top, XC6200Direction.lft, XC6200Direction.bot, XC6200Direction.rgt]:
				out.append(cell_state[tile][lut_dir][0].name)
			out.append(str(cell_state[tile][XC6200Direction.f]))
			print(",".join(out))
		
		def get_port(pos_key, dir_key):
			pos_raw = data_from_key(hdf5_file, pos_key)
			dir_raw = data_from_key(hdf5_file, dir_key)
			
			return XC6200Port(IcecraftPosition(*pos_raw), XC6200Direction[dir_raw])
		
		out_port = get_port("habitat.out_port.pos", "habitat.out_port.dir")
		in_port = get_port("habitat.in_port.pos", "habitat.in_port.dir")
		
		con = get_connected(cell_state, out_port.tile, out_port.direction)
		print("connected to output:", con)
		
		with open("explain.tex", "w") as tikz_file:
			tikz_file.write(generate_tikz(cell_state, con, clamp_pos, out_port=out_port, in_port=in_port))

def generation_info(hdf5_file: h5py.File, gen_index: int=-1):
	# generation
	gen = data_from_key(hdf5_file, "fitness.generation")[:]
	if gen_index == -1:
		gen_index = gen[-1]
	print(f"generation {gen_index}")
	
	fit = data_from_key(hdf5_file, "fitness.value")
	chromo_ids = data_from_key(hdf5_file, "fitness.chromo_id")
	last_indices = np.where(gen == gen_index)[0]
	last_fit = fit[last_indices]
	last_id = chromo_ids[last_indices]
	rank = last_fit.argsort()[::-1]#[:3]
	
	print("chromo_id fitness measurement_index")
	for f, i, r in zip(last_fit[rank], last_id[rank], last_indices[rank]):
		print(i, f, r)
	# top 3 chromosomes


def info(args: Namespace) -> None:
	with h5py.File(args.data_file, "r") as hdf5_file:
		cont_typ = get_content_type(hdf5_file)
		print(f"file contains data from {cont_typ.name}")
		
		if cont_typ in [ContentType.RUN, ContentType.RESTART]:
			generation_info(hdf5_file, args.index)
		

def spectrum(args: Namespace) -> None:
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	with ExitStack() as stack:
		cur_date = datetime.now(timezone.utc)
		
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		# measure temperature?
		rec_temp, temp_sn = temp_from_args_hdf5(args, hdf5_file)
		
		# habitat
		hab_config = read_habitat(hdf5_file)
		
		# rep
		rep = read_rep(hdf5_file, no_carry=False)
		
		# chromosome
		chromo_id = args.chromosome
		chromo = read_chromosome(hdf5_file, chromo_id)
		
		chromo_bits = get_chromo_bits(hdf5_file)
		
		# prepare setup
		target_sn = args.target or data_from_key(hdf5_file, "fitness.target.sn")
		meter_sn  = args.meter or data_from_key(hdf5_file, "fitness.meter.sn")
		driver_sn = args.generator or data_from_key(hdf5_file, "fitness.driver.sn")
		drv_type = DriverType[args.freq_gen_type]
		if drv_type != DriverType.FPGA:
			raise ValueError(f"spectrum requires FPGA driver, got {drv_type.name}")
		
		gen_path = os.path.join(pkg_path, "multi_freq_gen.asc")
		with open(gen_path, "r") as asc_file:
			freq_gen_text = asc_file.read()
		
		man = IcecraftManager()
		#TODO: add fpga osci to writemap
		gen, fg_config = prepare_fpga_driver(driver_sn, freq_gen_text, man, stack)
		driver = FixedEmbedDriver(gen, "<H")
		
		cal_data = calibrate(driver, meter_sn)
		
		# write to sink
		chromo_bits = get_chromo_bits(hdf5_file)
		write_map, metadata = write_map_util.create_for_spectrum(rep, chromo_bits, cal_data.trig_len, rec_temp)
		
		# org filename
		add_meta(metadata, "re.org", args.data_file)
		
		add_version(metadata)
		
		# copy simple metadata
		copy_meta(hdf5_file, metadata, ["habitat.con", "habitat.in_port.pos", "habitat.in_port.dir",
			"habitat.out_port.pos", "habitat.out_port.dir", "habitat.area.min", "habitat.area.max"])
		
		try:
			fg_con = args.freq_gen_con or data_from_key(hdf5_file, "freq_gen.con")
			add_meta(metadata, "freq_gen.con", fg_con)
		except KeyError:
			pass
		
		meter, meter_setup = prepare_osci(cal_data, stack)
		to_volt = meter.raw_to_volt_func()
		target = prepare_target(target_sn, man, stack)
		
		write_map_util.write_setup(metadata, meter_setup)
		add_meta(metadata, "osci.channel", meter.data_chan)
		add_meta(metadata, "fitness.driver.sn", gen.serial_number)
		add_meta(metadata, "fitness.driver.hw", gen.hardware_type)
		add_meta(metadata, "fitness.meter.fw", meter.firmware_version)
		add_meta(metadata, "fitness.driver_type", drv_type)
		add_meta(metadata, "fitness.target.sn", target.serial_number)
		add_meta(metadata, "fitness.target.hw", target.hardware_type)
		add_meta(metadata, "fitness.meter.sn", meter.serial_number)
		add_meta(metadata, "fitness.meter.hw", meter.hardware_type)
		
		
		# start sink
		sink_filename = args.output or f"spectrum-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		sink = ParallelSink(HDF5Sink, (write_map, metadata, sink_filename))
		stack.enter_context(sink)
		
		sink.write("freq_gen", {"text": fg_config.to_text(), })
		sink.write("calibration", asdict(cal_data))
		# chromosome
		sink.write("GenChromo.perform", {"return": ResponseObject(chromosome=chromo)})
		# habitat
		sink.write("habitat", {"text": hab_config.to_text()})
		
		if rec_temp:
			start_temp(temp_sn, stack, sink)
		else:
			print("Warning: No temperature measurement during spectrum")
		
		# target is constant -> prepare once
		rep.prepare_config(hab_config)
		rep.decode(hab_config, chromo)
		target.configure(hab_config)
		
		# carry enable
		carry_enable = extract_carry_enable(rep, hab_config, chromo).carry_enable
		
		measure_uc = Measure(driver, meter, sink)
		
		for cycles in [256*i for i in range(1, 75+1)]:
			freq = 12e6/cycles
			period = 1/freq
			print(cycles, freq, period)
			
			req = RequestObject(driver_data=InputData([cycles]))
			res = measure_uc(req)
			
			raw_measurement = res.measurement[-cal_data.trig_len:]
			volt_list = to_volt(raw_measurement)
			mean_volt = mean(volt_list)
			print("mean volt:", mean_volt)
			
			sink.write("spectrum.measure", {
				"volt": volt_list,
				"freq": freq,
				"period": period,
				"mean_volt": mean_volt,
			})
			
			sink.write("spectrum.carry", {"carry_enable": carry_enable})


def extract_measurement(args: Namespace, hdf5_file: h5py.File) -> None:
	data_chan = 1 # use default value
	osci_setup = read_osci_setup(hdf5_file)
	
	raw_to_volt = OsciDS1102E.raw_to_volt_from_setup(osci_setup, data_chan)
	
	# get trig len
	trig_len = data_from_key(hdf5_file, "osci.calibration.trig_len")
	trig_len = int(trig_len)
	
	# get scale
	time_scale = osci_setup.TIM.SCAL.value_
	
	# read measurement
	measurements = data_from_key(hdf5_file, "fitness.measurement")
	raw = [int(v) for v in measurements[args.index]]
	
	h_div = (12*time_scale) / len(raw)
	
	raw = raw[-trig_len:]
	# convert
	values = raw_to_volt(raw)
	
	# reduce data rate, but keep sharp spikes
	down = []
	win = 200
	for j in range((len(values)+win-1)//win):
		part = values[j*win: (j+1)*win]
		m = mean(part)
		#TODO: fixed value of 0.5 V is hacky
		outliers = [p for p in part if abs(p-m) > 0.5]
		if len(outliers) == 1:
			# keep spike
			val = outliers[0]
			print("spike", val)
		else:
			val = part[0]
		
		down.append(val)
	
	h_div *= win
	
	# write
	with open(f"meas.{os.path.basename(args.data_file)}.{args.index}.csv", "w") as out_file:
		for i, val in enumerate(down):
			out_file.write(f"{h_div*i}; {val:.4f}\n")


def extract_mean(args: Namespace, hdf5_file: h5py.File) -> None:
	def get_float(key):
		raw = data_from_key(hdf5_file, key)
		return [float(r) for r in raw]
	
	mean_data = get_float("spectrum.mean")
	
	period_data = get_float("spectrum.period")
	
	# write
	with open(f"mean.{os.path.basename(args.data_file)}.csv", "w") as out_file:
		for per, val in zip(period_data, mean_data):
			out_file.write(f"{per}; {val:.4f}\n")
	


def extract(args: Namespace) -> None:
	"""extract measurement data"""
	ext = ExtractTarget[args.extract_target]
	
	with ExitStack() as stack:
		# extract information from HDF5 file
		hdf5_file = h5py.File(args.data_file, "r")
		stack.enter_context(hdf5_file)
		
		if ext == ExtractTarget.MEASUREMENT:
			extract_measurement(args, hdf5_file)
		elif ext == ExtractTarget.MEAN:
			extract_mean(args, hdf5_file)
	
