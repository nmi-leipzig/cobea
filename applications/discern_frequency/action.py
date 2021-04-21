import os
import time

from typing import List, Tuple

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import SimpleEA
from adapters.dummies import DummyDriver, DummyMeter
from adapters.gear.rigol import OsciDS1102E
from adapters.icecraft import IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen, IcecraftManager,\
IcecraftRawConfig, XC6200Port, XC6200Direction
from adapters.prng import BuiltInPRNG
from adapters.unique_id import SimpleUID
from domain.interfaces import TargetDevice, TargetManager, InputData
from domain.model import AlleleAll, Gene
from domain.request_model import RequestObject
from domain.use_cases import Measure

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
	req = RequestObject(tiles=tiles, in_ports=[])
	
	bef = time.perf_counter()
	rep = rep_gen(req)
	aft = time.perf_counter()
	print(f"rep gen took in {aft-bef} s")
	
	return rep

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

# measure

# 
def run(args) -> None:
	# prepare
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	use_dummy = False
	
	man = IcecraftManager()
	if use_dummy:
		meter = DummyMeter()
		driver = DummyDriver()
		from unittest.mock import MagicMock
		#target = DummyTargetDevice()
		target = MagicMock()
	else:
		gen = man.acquire(args.generator)
		target = man.acquire(args.target)
		
		prepare_generator(gen, os.path.join(pkg_path, "freq_gen.asc"))
		
		#target.configure(hab_config)
		
		meter_setup = create_meter_setup()
		meter = OsciDS1102E(meter_setup)
		
		driver = FixedEmbedDriver(gen, "B")
	
	measure_uc = Measure(driver, meter)
	
	hab_path = os.path.join(pkg_path, "dummy_hab.asc")
	hab_config = IcecraftRawConfig.create_from_file(hab_path)
	
	#from tests.mocks import MockRepresentation
	#rep = MockRepresentation([Gene([pow(i,j) for j in range(i)], AlleleAll(i), "") for i in range(3, 6)])
	rep = create_xc6200_rep((10, 23), (19, 32))
	ea = SimpleEA(rep, measure_uc, SimpleUID(), BuiltInPRNG(), hab_config, target)
	
	ea.run()
	
	if not use_dummy:
		man.release(gen)

