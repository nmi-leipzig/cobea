import os
import numpy as np
import time

from dataclasses import asdict, dataclass
from typing import List, Tuple

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import SimpleEA
from adapters.dummies import DummyDriver, DummyMeter
from adapters.gear.rigol import OsciDS1102E
from adapters.hdf5_sink import HDF5Sink, ParamAim
from adapters.icecraft import IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen, IcecraftManager,\
IcecraftRawConfig, XC6200Port, XC6200Direction
from adapters.prng import BuiltInPRNG
from adapters.simple_sink import TextfileSink
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

# measure

# 
def run(args) -> None:
	# prepare
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	use_dummy = False
	
	rep = create_xc6200_rep((10, 23), (19, 32))
	chromo_bits = 16
	if not is_rep_fitting(rep, chromo_bits):
		raise ValueError(f"representation needs more than {chromo_bits} bits")
	
	man = IcecraftManager()
	#sink = TextfileSink("tmp.out.txt")
	chromo_aim = [
		ParamAim(
			"return", f"uint{chromo_bits}", "chromosome", as_attr=False, shape=(len(rep.genes), ),
			alter=lambda x: x.allele_indices
		),
		ParamAim("return", "uint64", "chromo_id", as_attr=False, alter=lambda x: x.identifier),
	]
	rep_src = "Action.rep"
	rep_genes = "genes"
	rep_const = "const"
	rep_ce = "carry_bits"
	
	write_map = {
		"Measure.perform": [
			ParamAim("driver_data", "uint8", "s_t_index", as_attr=False),
			ParamAim("return", "float64", "measurement", as_attr=False, shape=(2**19, )),
		],
		"SimpleEA.fitness": [
			ParamAim("fit", "float64", "fitness", as_attr=False),
			ParamAim("fast_sum", "float64", "fast_sum", as_attr=False),
			ParamAim("slow_sum", "float64", "slow_sum", as_attr=False),
			ParamAim("chromo_index", "uint64", "fitness_chromo_id", as_attr=False),
			ParamAim(
				"carry_enable",
				bool,
				"carry_enable",
				as_attr=False,
				shape=(len(list(rep.iter_carry_bits())), )
			),
			ParamAim("time", "float64", "fitness_time", as_attr=False, alter=lambda x: x.timestamp()),
		],
		"SimpleEA.ea_params": [
			ParamAim("pop_size", "uint64", "pop_size"),
			ParamAim("gen_count", "uint64", "gen_count"),
			ParamAim("crossover_prob", "float64", "crossover_prob"),
			ParamAim("mutation_prob", "float64", "mutation_prob"),
		],
		"RandomChromo.perform": chromo_aim,
		"GenChromo.perform": chromo_aim,
		rep_src: HDF5Sink.create_gene_aims(rep_genes, len(rep.genes), h5_path="genes")+\
			HDF5Sink.create_gene_aims(rep_const, len(rep.constant), h5_path="constant")+[
				ParamAim(rep_ce, "uint16", "bits", "carry_enable",
					alter=lambda x: [b.to_ints() for b in x]),
			],
		"Individual.wrap.cxTwoPoint": [
			ParamAim("in", "uint64", "crossover_parents", as_attr=False, shape=(2, )),
			ParamAim("out", "uint64", "crossover_child", as_attr=False, alter=lambda x: x[0]),
		],
		"Individual.wrap.mutUniformInt": [
			ParamAim("in", "uint64", "mutation_parent", as_attr=False, alter=lambda x: x[0]),
			ParamAim("out", "uint64", "mutation_child", as_attr=False, alter=lambda x: x[0]),
		],
		"calibration": [
			ParamAim("data", "float64", "calibration", as_attr=False),
			ParamAim("rising_edge", "uint64", "rising_edge", "calibration"),
			ParamAim("falling_edge", "uint64", "falling_edge", "calibration"),
			ParamAim("trig_len", "uint64", "trig_len", "calibration"),
			ParamAim("offset", "float64", "offset", "calibration"),
		],
	}
	
	sink = HDF5Sink(write_map)
	with sink:
		sink.write(rep_src, {
			rep_genes: rep.genes,
			rep_const: rep.constant,
			rep_ce: list(rep.iter_carry_bits()),
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
			
			#from tests.mocks import MockRepresentation
			#rep = MockRepresentation([Gene([pow(i,j) for j in range(i)], AlleleAll(i), "") for i in range(3, 6)])
			ea = SimpleEA(rep, measure_uc, SimpleUID(), BuiltInPRNG(), hab_config, target, cal_data.trig_len, sink)
			
			ea.run(4, 8, 0.7, 0.001756)
			#ea.run(50, 600, 0.7, 0.001756)
		finally:
			if not use_dummy:
				man.release(target)
				man.release(gen)
				meter.close()

