import os
import json
from dataclasses import dataclass
from typing import List, Iterable, Tuple

from adapters.icecraft import IcecraftPosition, IcecraftBitPosition, RAMMode

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@dataclass
class SendBRAMMeta:
	mode: RAMMode
	asc_filename: str
	ram_block: IcecraftPosition
	initial_data: List[int]
	mask: int
	
	def __post_init__(self):
		if isinstance(self.mode, str):
			self.mode = RAMMode[f"RAM_{self.mode}"]
		self.ram_block = IcecraftPosition(*self.ram_block)
		self.asc_filename = os.path.join(TEST_DATA_DIR, self.asc_filename)


with open(os.path.join(TEST_DATA_DIR, "send_all_bram.json"), "r") as json_file:
	SEND_BRAM_META = tuple([SendBRAMMeta(*s) for s in json.load(json_file)])

def create_bits(x:int , y: int, bit_coords: Iterable[Tuple[int, int]]) -> Tuple[IcecraftBitPosition, ...]:
	return tuple(IcecraftBitPosition(x, y, g, i) for g, i in bit_coords)
