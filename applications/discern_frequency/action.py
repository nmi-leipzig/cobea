import os

from typing import List, Tuple

from adapters.embed_driver import FixedEmbedDriver
from adapters.deap.simple_ea import SimpleEA
from adapters.gear.rigol import OsciDS1102E
from adapters.icecraft import IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen, IcecraftManager,\
IcecraftRawConfig
from adapters.prng import BuiltInPRNG
from adapters.unique_id import SimpleUID
from domain.interfaces import TargetDevice, InputData
from domain.model import AlleleAll, Gene
from domain.request_model import RequestObject
from domain.use_cases import Measure

# generate tiles
def tiles_from_corners(min_pos: Tuple[int, int], max_pos: Tuple[int, int]) -> List[IcecraftPosition]:
	req = RequestObject(identifier="expand_rectangle", description="")
	exp_rect = IcecraftPosTransLibrary.get_pos_trans(req)
	res = exp_rect([IcecraftPosition(*min_pos), IcecraftPosition(*max_pos)])
	return res

# generate representation
def create_xc6200_rep(min_pos: Tuple[int, int], max_pos: Tuple[int, int]) -> IcecraftRep:
	#TODO: add input and output port
	rep_gen = XC6200RepGen()
	
	tiles = tiles_from_corners(min_pos, max_pos)
	req = RequestObject(tiles=tiles)
	
	rep = rep_gen(req)
	
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
	
	setup.CHAN2.DISP.value_ = "ON"#"OFF"
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
	print("1 kHz")
	# prepare
	pkg_path = os.path.dirname(os.path.abspath(__file__))
	
	man = IcecraftManager()
	gen = man.acquire(args.generator)
	target = man.acquire(args.target)
	
	prepare_generator(gen, os.path.join(pkg_path, "freq_gen.asc"))
	
	hab_path = os.path.join(pkg_path, "dummy_hab.asc")
	hab_config = IcecraftRawConfig.create_from_file(hab_path)
	target.configure(hab_config)
	
	meter_setup = create_meter_setup()
	meter = OsciDS1102E(meter_setup)
	driver = FixedEmbedDriver(gen, "B")
	measure_uc = Measure(driver, meter)
	
	from tests.mocks import MockRepresentation
	rep = MockRepresentation([Gene([pow(i,j) for j in range(i)], AlleleAll(i), "") for i in range(3, 6)])
	
	ea = SimpleEA(rep, measure_uc, SimpleUID(), BuiltInPRNG())
	
	driver_req = RequestObject(
		driver_data = InputData([0]),
	)
	#data = measure_uc(driver_req)
	#print(len(data))
	ea.run()
	
	man.release(gen)

