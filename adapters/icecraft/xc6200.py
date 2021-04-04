from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping

from domain.interfaces import RepresentationGenerator
from domain.request_model import RequestObject, Parameter

from .representation import IcecraftRep, IcecraftRepGen
from .position_transformation import IcecraftPosTransLibrary
from .misc import IcecraftPosition, IcecraftBitPosition, IcecraftResource,\
IcecraftResCon, TILE_ALL, TILE_ALL_LOGIC, IcecraftGeneConstraint
from .chip_data_utils import UNCONNECTED_NAME

class XC6200Direction(IntEnum):
	top = 0
	lft = 1
	bot = 2
	rgt = 3
	f = 4
	
	def opposite(self):
		if self.value == self.f.value:
			raise ValueError("f has no opposite")
		return self.__class__((self + 2) % 4)
	

@dataclass(frozen=True, order=True)
class XC6200Port:
	tile: IcecraftPosition
	direction: XC6200Direction

class XC6200RepGen(RepresentationGenerator):
	def __init__(self) -> None:
		self._parameters = {"__call__": [
			Parameter("tiles", IcecraftPosition, multiple=True),
			Parameter("in_ports", XC6200Port, default=[], multiple=True),
			#Parameter("include_resources", IcecraftResource, default=[], multiple=True),
			#Parameter("include_connections", IcecraftResCon, default=[], multiple=True),
			#Parameter("output_lutffs", IcecraftLUTPosition, multiple=True),
		]}
		
	@property
	def parameters(self) -> Mapping[str, Parameter]:
		return self._parameters
	
	def __call__(self, request: RequestObject) -> IcecraftRep:
		rep_gen = IcecraftRepGen()
		#TODO: check all tile are logic tiles
		tile_set = set(request.tiles)
		
		border = {d: set() for d in XC6200Direction if d.name != "f"}
		for tile in tile_set:
			for direction, dir_set in border.items():
				if self.get_neighbor(tile, direction) not in tile_set:
					dir_set.add(tile)
		
		# check consistency of in ports
		for ip in request.in_ports:
			# tile included
			assert ip.tile in tile_set
			# neighbor tile not included
			assert ip.tile in border[ip.direction]
		
		req = RequestObject()
		req["tiles"] = request.tiles
		req["exclude_resources"] = [IcecraftResource(TILE_ALL, TILE_ALL, "")]
		req["include_resources"] = [
			IcecraftResource(TILE_ALL, TILE_ALL, f"LUT#{l}") for l in range(5)
		] + [
			IcecraftResource(TILE_ALL, TILE_ALL, f"NET#lutff_{l}/in_{i}") for l in range(5) for i in range(4)
		] + [
			IcecraftResource(TILE_ALL, TILE_ALL, f"NET#{n}") for n in [
				"local_g0_1", "local_g0_4", "local_g1_0", "local_g1_1", "local_g1_3", "local_g3_2",
				"lutff_0/out", UNCONNECTED_NAME,
			]
		] + [
			IcecraftResource(t.x, t.y, "NET#neigh_op_bot_1") for t in tile_set if t not in border[XC6200Direction["bot"]]
		] + [
			IcecraftResource(t.x, t.y, "NET#neigh_op_rgt_2") for t in tile_set if t not in border[XC6200Direction["rgt"]]
		] + [
			IcecraftResource(t.x, t.y, "NET#neigh_op_top_3") for t in tile_set if t not in border[XC6200Direction["top"]]
		] + [
			IcecraftResource(t.x, t.y, "NET#neigh_op_lft_4") for t in tile_set if t not in border[XC6200Direction["lft"]]
		]
		req["exclude_connections"] = [IcecraftResCon(TILE_ALL, TILE_ALL, "", "")]
		req["include_connections"] = [IcecraftResCon(TILE_ALL, TILE_ALL, f"NET#{s}$", f"NET#{d}$") for s, d in [
			("neigh_op_bot_1", "local_g0_1"), ("neigh_op_bot_1", "local_g1_1"), ("neigh_op_lft_4", "local_g0_4"),
			("neigh_op_rgt_2", "local_g3_2"), ("neigh_op_top_3", "local_g1_3"), ("lutff_0/out", "local_g1_0"),
			("local_g0_1", "lutff_0/in_1"), ("local_g0_1", "lutff_4/in_1"), ("local_g0_4", "lutff_0/in_0"),
			("local_g0_4", "lutff_1/in_3"), ("local_g0_4", "lutff_3/in_1"), ("local_g0_4", "lutff_4/in_0"),
			("local_g1_0", "lutff_1/in_0"), ("local_g1_0", "lutff_2/in_1"), ("local_g1_0", "lutff_3/in_0"),
			("local_g1_0", "lutff_4/in_3"), ("local_g1_1", "lutff_1/in_1"), ("local_g1_1", "lutff_2/in_2"),
			("local_g1_3", "lutff_0/in_2"), ("local_g1_3", "lutff_2/in_0"), ("local_g1_3", "lutff_3/in_3"),
			("local_g1_3", "lutff_4/in_2"), ("local_g3_2", "lutff_0/in_3"), ("local_g3_2", "lutff_1/in_2"),
			("local_g3_2", "lutff_2/in_3"), ("local_g3_2", "lutff_3/in_2")
		]] + [
			IcecraftResCon(TILE_ALL, TILE_ALL, f"NET#lutff_{l}/in_{i}$", f"LUT#{l}$") for l in range(5) for i in range(4)
		] + [
			IcecraftResCon(TILE_ALL, TILE_ALL, f"LUT#{l}$", f"NET#lutff_{l}/out") for l in range(5)
		] + [
			IcecraftResCon(t.x, t.y, f"NET#{UNCONNECTED_NAME}", "NET#local_g0_1") for t in border[XC6200Direction["bot"]]
		] + [
			IcecraftResCon(t.x, t.y, f"NET#{UNCONNECTED_NAME}", "NET#local_g1_1") for t in border[XC6200Direction["bot"]]
		] + [
			IcecraftResCon(t.x, t.y, f"NET#{UNCONNECTED_NAME}", "NET#local_g1_3") for t in border[XC6200Direction["top"]]
		] + [
			IcecraftResCon(t.x, t.y, f"NET#{UNCONNECTED_NAME}", "NET#local_g0_4") for t in border[XC6200Direction["lft"]]
		] + [
			IcecraftResCon(t.x, t.y, f"NET#{UNCONNECTED_NAME}", "NET#local_g3_2") for t in border[XC6200Direction["rgt"]]
		]
		req["output_lutffs"] = []
		req["lut_functions"] = []
		req["gene_constraints"] = [
			IcecraftGeneConstraint(
				tuple(IcecraftBitPosition(TILE_ALL_LOGIC, TILE_ALL_LOGIC, *c) for c in b),
				tuple(
					tuple((s & (1<<i)) > 0 for s in range(16)) for i in range(4)
				)
			) for b in [
				(
					(2, 40), (3, 40), (3, 41), (2, 41), (2, 42), (3, 42), (3, 43), (2, 43),
					(2, 39), (3, 39), (3, 38), (2, 38), (2, 37), (3, 37), (3, 36), (2, 36)
				),
				(
					(4, 40), (5, 40), (5, 41), (4, 41), (4, 42), (5, 42), (5, 43), (4, 43),
					(4, 39), (5, 39), (5, 38), (4, 38), (4, 37), (5, 37), (5, 36), (4, 36)
				),
				(
					(6, 40), (7, 40), (7, 41), (6, 41), (6, 42), (7, 42), (7, 43), (6, 43),
					(6, 39), (7, 39), (7, 38), (6, 38), (6, 37), (7, 37), (7, 36), (6, 36)
				),
				(
					(8, 40), (9, 40), (9, 41), (8, 41), (8, 42), (9, 42), (9, 43), (8, 43),
					(8, 39), (9, 39), (9, 38), (8, 38), (8, 37), (9, 37), (9, 36), (8, 36)
				)
			]
		] + [# truth table LUT 0
			IcecraftGeneConstraint(
				tuple(IcecraftBitPosition(TILE_ALL_LOGIC, TILE_ALL_LOGIC, *c) for c in [
					(0, 40), (1, 40), (1, 41), (0, 41), (0, 42), (1, 42), (1, 43), (0, 43),
					(0, 39), (1, 39), (1, 38), (0, 38), (0, 37), (1, 37), (1, 36), (0, 36)
				]),
				(
					(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
					(False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, True),
					(False, False, False, False, False, False, False, False, False, False, True, True, False, False, True, True),
					(False, False, False, False, False, False, False, False, False, True, False, True, False, True, False, True),
					(False, False, False, False, False, False, False, False, True, False, True, False, True, False, True, False),
					(False, False, False, False, False, False, False, False, True, True, False, False, True, True, False, False),
					(False, False, False, False, False, False, False, False, True, True, True, True, False, False, False, False),
					(False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True),
					(False, False, False, False, False, False, True, True, False, False, False, False, False, False, True, True),
					(False, False, False, False, False, False, True, True, True, True, False, False, True, True, True, True),
					(False, False, False, False, False, False, True, True, True, True, True, True, False, False, True, True),
					(False, False, False, False, False, True, False, True, False, False, False, False, False, True, False, True),
					(False, False, False, False, False, True, False, True, True, False, True, False, True, True, True, True),
					(False, False, False, False, False, True, False, True, True, True, True, True, False, True, False, True),
					(False, False, False, False, True, False, True, False, False, False, False, False, True, False, True, False),
					(False, False, False, False, True, False, True, False, False, True, False, True, True, True, True, True),
					(False, False, False, False, True, False, True, False, True, True, True, True, True, False, True, False),
					(False, False, False, False, True, True, False, False, False, False, False, False, True, True, False, False),
					(False, False, False, False, True, True, False, False, False, False, True, True, True, True, True, True),
					(False, False, False, False, True, True, False, False, True, True, True, True, True, True, False, False),
					(False, False, False, False, True, True, True, True, False, False, False, False, False, False, False, False),
					(False, False, False, False, True, True, True, True, False, False, False, False, True, True, True, True),
					(False, False, False, False, True, True, True, True, False, False, True, True, False, False, True, True),
					(False, False, False, False, True, True, True, True, False, True, False, True, False, True, False, True),
					(False, False, False, False, True, True, True, True, True, False, True, False, True, False, True, False),
					(False, False, False, False, True, True, True, True, True, True, False, False, True, True, False, False),
					(False, False, False, False, True, True, True, True, True, True, True, True, False, False, False, False),
					(False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True),
					(False, False, False, True, False, False, False, True, False, False, False, True, False, False, False, True),
					(False, False, False, True, False, False, False, True, True, False, True, True, True, False, True, True),
					(False, False, False, True, False, False, False, True, True, True, False, True, True, True, False, True),
					(False, False, False, True, True, False, True, True, False, False, False, True, True, False, True, True),
					(False, False, False, True, True, True, False, True, False, False, False, True, True, True, False, True),
					(False, False, True, False, False, False, True, False, False, False, True, False, False, False, True, False),
					(False, False, True, False, False, False, True, False, False, True, True, True, False, True, True, True),
					(False, False, True, False, False, False, True, False, True, True, True, False, True, True, True, False),
					(False, False, True, False, False, True, True, True, False, False, True, False, False, True, True, True),
					(False, False, True, False, True, True, True, False, False, False, True, False, True, True, True, False),
					(False, False, True, True, False, False, False, False, False, False, True, True, False, False, False, False),
					(False, False, True, True, False, False, False, False, False, False, True, True, True, True, True, True),
					(False, False, True, True, False, False, False, False, True, True, True, True, True, True, False, False),
					(False, False, True, True, False, False, True, True, False, False, False, False, False, False, False, False),
					(False, False, True, True, False, False, True, True, False, False, False, False, True, True, True, True),
					(False, False, True, True, False, False, True, True, False, False, True, True, False, False, True, True),
					(False, False, True, True, False, False, True, True, False, True, False, True, False, True, False, True),
					(False, False, True, True, False, False, True, True, True, False, True, False, True, False, True, False),
					(False, False, True, True, False, False, True, True, True, True, False, False, True, True, False, False),
					(False, False, True, True, False, False, True, True, True, True, True, True, False, False, False, False),
					(False, False, True, True, False, False, True, True, True, True, True, True, True, True, True, True),
					(False, False, True, True, False, True, False, True, False, False, True, True, False, True, False, True),
					(False, False, True, True, True, False, True, False, False, False, True, True, True, False, True, False),
					(False, False, True, True, True, True, False, False, False, False, True, True, True, True, False, False),
					(False, False, True, True, True, True, True, True, False, False, False, False, True, True, False, False),
					(False, False, True, True, True, True, True, True, False, False, True, True, False, False, False, False),
					(False, False, True, True, True, True, True, True, False, False, True, True, True, True, True, True),
					(False, True, False, False, False, True, False, False, False, True, False, False, False, True, False, False),
					(False, True, False, False, False, True, False, False, False, True, True, True, False, True, True, True),
					(False, True, False, False, False, True, False, False, True, True, True, False, True, True, True, False),
					(False, True, False, False, False, True, True, True, False, True, False, False, False, True, True, True),
					(False, True, False, False, True, True, True, False, False, True, False, False, True, True, True, False),
					(False, True, False, True, False, False, False, False, False, True, False, True, False, False, False, False),
					(False, True, False, True, False, False, False, False, False, True, False, True, True, True, True, True),
					(False, True, False, True, False, False, False, False, True, True, True, True, True, False, True, False),
					(False, True, False, True, False, False, True, True, False, True, False, True, False, False, True, True),
					(False, True, False, True, False, True, False, True, False, False, False, False, False, False, False, False),
					(False, True, False, True, False, True, False, True, False, False, False, False, True, True, True, True),
					(False, True, False, True, False, True, False, True, False, False, True, True, False, False, True, True),
					(False, True, False, True, False, True, False, True, False, True, False, True, False, True, False, True),
					(False, True, False, True, False, True, False, True, True, False, True, False, True, False, True, False),
					(False, True, False, True, False, True, False, True, True, True, False, False, True, True, False, False),
					(False, True, False, True, False, True, False, True, True, True, True, True, False, False, False, False),
					(False, True, False, True, False, True, False, True, True, True, True, True, True, True, True, True),
					(False, True, False, True, True, False, True, False, False, True, False, True, True, False, True, False),
					(False, True, False, True, True, True, False, False, False, True, False, True, True, True, False, False),
					(False, True, False, True, True, True, True, True, False, False, False, False, True, False, True, False),
					(False, True, False, True, True, True, True, True, False, True, False, True, False, False, False, False),
					(False, True, False, True, True, True, True, True, False, True, False, True, True, True, True, True),
					(False, True, True, False, False, True, True, False, False, True, True, False, False, True, True, False),
					(False, True, True, True, False, False, True, False, False, True, True, True, False, False, True, False),
					(False, True, True, True, False, True, False, False, False, True, True, True, False, True, False, False),
					(False, True, True, True, False, True, True, True, False, False, True, False, False, False, True, False),
					(False, True, True, True, False, True, True, True, False, True, False, False, False, True, False, False),
					(False, True, True, True, False, True, True, True, False, True, True, True, False, True, True, True),
					(True, False, False, False, True, False, False, False, True, False, False, False, True, False, False, False),
					(True, False, False, False, True, False, False, False, True, False, True, True, True, False, True, True),
					(True, False, False, False, True, False, False, False, True, True, False, True, True, True, False, True),
					(True, False, False, False, True, False, True, True, True, False, False, False, True, False, True, True),
					(True, False, False, False, True, True, False, True, True, False, False, False, True, True, False, True),
					(True, False, False, True, True, False, False, True, True, False, False, True, True, False, False, True),
					(True, False, True, False, False, False, False, False, True, False, True, False, False, False, False, False),
					(True, False, True, False, False, False, False, False, True, False, True, False, True, True, True, True),
					(True, False, True, False, False, False, False, False, True, True, True, True, False, True, False, True),
					(True, False, True, False, False, False, True, True, True, False, True, False, False, False, True, True),
					(True, False, True, False, False, True, False, True, True, False, True, False, False, True, False, True),
					(True, False, True, False, True, False, True, False, False, False, False, False, False, False, False, False),
					(True, False, True, False, True, False, True, False, False, False, False, False, True, True, True, True),
					(True, False, True, False, True, False, True, False, False, False, True, True, False, False, True, True),
					(True, False, True, False, True, False, True, False, False, True, False, True, False, True, False, True),
					(True, False, True, False, True, False, True, False, True, False, True, False, True, False, True, False),
					(True, False, True, False, True, False, True, False, True, True, False, False, True, True, False, False),
					(True, False, True, False, True, False, True, False, True, True, True, True, False, False, False, False),
					(True, False, True, False, True, False, True, False, True, True, True, True, True, True, True, True),
					(True, False, True, False, True, True, False, False, True, False, True, False, True, True, False, False),
					(True, False, True, False, True, True, True, True, False, False, False, False, False, True, False, True),
					(True, False, True, False, True, True, True, True, True, False, True, False, False, False, False, False),
					(True, False, True, False, True, True, True, True, True, False, True, False, True, True, True, True),
					(True, False, True, True, False, False, False, True, True, False, True, True, False, False, False, True),
					(True, False, True, True, True, False, False, False, True, False, True, True, True, False, False, False),
					(True, False, True, True, True, False, True, True, False, False, False, True, False, False, False, True),
					(True, False, True, True, True, False, True, True, True, False, False, False, True, False, False, False),
					(True, False, True, True, True, False, True, True, True, False, True, True, True, False, True, True),
					(True, True, False, False, False, False, False, False, True, True, False, False, False, False, False, False),
					(True, True, False, False, False, False, False, False, True, True, False, False, True, True, True, True),
					(True, True, False, False, False, False, False, False, True, True, True, True, False, False, True, True),
					(True, True, False, False, False, False, True, True, True, True, False, False, False, False, True, True),
					(True, True, False, False, False, True, False, True, True, True, False, False, False, True, False, True),
					(True, True, False, False, True, False, True, False, True, True, False, False, True, False, True, False),
					(True, True, False, False, True, True, False, False, False, False, False, False, False, False, False, False),
					(True, True, False, False, True, True, False, False, False, False, False, False, True, True, True, True),
					(True, True, False, False, True, True, False, False, False, False, True, True, False, False, True, True),
					(True, True, False, False, True, True, False, False, False, True, False, True, False, True, False, True),
					(True, True, False, False, True, True, False, False, True, False, True, False, True, False, True, False),
					(True, True, False, False, True, True, False, False, True, True, False, False, True, True, False, False),
					(True, True, False, False, True, True, False, False, True, True, True, True, False, False, False, False),
					(True, True, False, False, True, True, False, False, True, True, True, True, True, True, True, True),
					(True, True, False, False, True, True, True, True, False, False, False, False, False, False, True, True),
					(True, True, False, False, True, True, True, True, True, True, False, False, False, False, False, False),
					(True, True, False, False, True, True, True, True, True, True, False, False, True, True, True, True),
					(True, True, False, True, False, False, False, True, True, True, False, True, False, False, False, True),
					(True, True, False, True, True, False, False, False, True, True, False, True, True, False, False, False),
					(True, True, False, True, True, True, False, True, False, False, False, True, False, False, False, True),
					(True, True, False, True, True, True, False, True, True, False, False, False, True, False, False, False),
					(True, True, False, True, True, True, False, True, True, True, False, True, True, True, False, True),
					(True, True, True, False, False, False, True, False, True, True, True, False, False, False, True, False),
					(True, True, True, False, False, True, False, False, True, True, True, False, False, True, False, False),
					(True, True, True, False, True, True, True, False, False, False, True, False, False, False, True, False),
					(True, True, True, False, True, True, True, False, False, True, False, False, False, True, False, False),
					(True, True, True, False, True, True, True, False, True, True, True, False, True, True, True, False),
					(True, True, True, True, False, False, False, False, False, False, False, False, False, False, False, False),
					(True, True, True, True, False, False, False, False, False, False, False, False, True, True, True, True),
					(True, True, True, True, False, False, False, False, False, False, True, True, False, False, True, True),
					(True, True, True, True, False, False, False, False, False, True, False, True, False, True, False, True),
					(True, True, True, True, False, False, False, False, True, False, True, False, True, False, True, False),
					(True, True, True, True, False, False, False, False, True, True, False, False, True, True, False, False),
					(True, True, True, True, False, False, False, False, True, True, True, True, False, False, False, False),
					(True, True, True, True, False, False, False, False, True, True, True, True, True, True, True, True),
					(True, True, True, True, False, False, True, True, False, False, False, False, False, False, True, True),
					(True, True, True, True, False, False, True, True, True, True, False, False, False, False, False, False),
					(True, True, True, True, False, False, True, True, True, True, True, True, False, False, True, True),
					(True, True, True, True, False, True, False, True, False, False, False, False, False, True, False, True),
					(True, True, True, True, False, True, False, True, True, False, True, False, False, False, False, False),
					(True, True, True, True, False, True, False, True, True, True, True, True, False, True, False, True),
					(True, True, True, True, True, False, True, False, False, False, False, False, True, False, True, False),
					(True, True, True, True, True, False, True, False, False, True, False, True, False, False, False, False),
					(True, True, True, True, True, False, True, False, True, True, True, True, True, False, True, False),
					(True, True, True, True, True, True, False, False, False, False, False, False, True, True, False, False),
					(True, True, True, True, True, True, False, False, False, False, True, True, False, False, False, False),
					(True, True, True, True, True, True, False, False, True, True, True, True, True, True, False, False),
					(True, True, True, True, True, True, True, True, False, False, False, False, False, False, False, False),
					(True, True, True, True, True, True, True, True, False, False, False, False, True, True, True, True),
					(True, True, True, True, True, True, True, True, False, False, True, True, False, False, True, True),
					(True, True, True, True, True, True, True, True, False, True, False, True, False, True, False, True),
					(True, True, True, True, True, True, True, True, True, False, True, False, True, False, True, False),
					(True, True, True, True, True, True, True, True, True, True, False, False, True, True, False, False),
					(True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False),
					(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
				)
			)
		]
		
		res = rep_gen(req)
		
		return res
	
	@staticmethod
	def get_neighbor(tile: IcecraftPosition, direction: XC6200Direction) -> IcecraftPosition:
		x_off = [0, -1, 0, 1][direction]
		y_off = [1, 0, -1, 0][direction]
		
		return IcecraftPosition(tile.x+x_off, tile.y+y_off)
