import os
import json
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Tuple

from adapters.icecraft import IcecraftPosition, IcecraftBitPosition, RAMMode

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FORMAT_DICT = {
	RAMMode.RAM_256x16: "<H",
	RAMMode.RAM_512x8: "B",
	RAMMode.RAM_1024x4: "B",
	RAMMode.RAM_2048x2: "B"
}

@dataclass
class SendBRAMMeta:
	mode: RAMMode
	asc_filename: str
	ram_block: IcecraftPosition
	initial_data: List[int]
	mask: int
	known_bits: Mapping[IcecraftPosition, Mapping[int, List[int]]]
	
	def bit_value(self, bit: IcecraftBitPosition) -> bool:
		ones = self.known_bits[bit.tile]
		try:
			group_ones = ones[bit.group]
		except KeyError:
			# whole group has no one
			return False
		
		return bit.index in group_ones
	
	@classmethod
	def from_json_data(cls, json_data: list) -> "SendBRAMMeta":
		return cls(
			RAMMode[f"RAM_{json_data[0]}"],
			os.path.join(TEST_DATA_DIR, json_data[1]),
			IcecraftPosition(*json_data[2]),
			json_data[3],
			json_data[4],
			{IcecraftPosition(x, y): {g: l for g, l in d} for x, y, d in json_data[5]}
		)


with open(os.path.join(TEST_DATA_DIR, "send_all_bram.json"), "r") as json_file:
	SEND_BRAM_META = tuple([SendBRAMMeta.from_json_data(s) for s in json.load(json_file)])

def create_bits(x: int , y: int, bit_coords: Iterable[Tuple[int, int]]) -> Tuple[IcecraftBitPosition, ...]:
	return tuple(IcecraftBitPosition(x, y, g, i) for g, i in bit_coords)
