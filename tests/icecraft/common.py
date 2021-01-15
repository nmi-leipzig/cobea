import os
import json
from dataclasses import dataclass
from typing import List, Iterable, Tuple

import adapters.icecraft as icecraft

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@dataclass
class SendBRAMMeta:
	mode: str
	asc_filename: str
	ram_block: icecraft.TilePosition
	initial_data: List[int]
	mask: int
	
	def __post_init__(self):
		self.ram_block = icecraft.TilePosition(*self.ram_block)
		self.asc_filename = os.path.join(TEST_DATA_DIR, self.asc_filename)


with open(os.path.join(TEST_DATA_DIR, "send_all_bram.json"), "r") as json_file:
	SEND_BRAM_META = tuple([SendBRAMMeta(*s) for s in json.load(json_file)])

def create_bits(x:int , y: int, bit_coords: Iterable[Tuple[int, int]]) -> Tuple[icecraft.IcecraftBitPosition, ...]:
	return tuple(icecraft.IcecraftBitPosition.from_coords(x, y, g, i) for g, i in bit_coords)
