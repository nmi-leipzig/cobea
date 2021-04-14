import os

from typing import List, Tuple

from adapters.embed_driver import EmbedDriver
from adapters.icecraft import IcecraftPosition, IcecraftPosTransLibrary, IcecraftRep, XC6200RepGen, IcecraftManager,\
IcecraftRawConfig
from domain.interfaces import TargetDevice, InputData
from domain.request_model import RequestObject
#from domain.use_cases import 

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
	
	driver = EmbedDriver()
	driver_req = RequestObject(
		driver_data = InputData([0]),
		driver_format = "B",
		driver_dev = gen,
	)
	driver.drive(driver_req)
	
	man.release(gen)

