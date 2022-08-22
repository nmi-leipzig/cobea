import itertools

from copy import deepcopy
from typing import Dict, List, NamedTuple
from unittest import TestCase

from adapters.icecraft import IcecraftBitPosition, IcecraftPosition, IcecraftRawConfig
from adapters.icecraft.ice_board.device_data import SPECS_BY_ASC
from adapters.icecraft.inter_rep import PartConf
from adapters.icecraft.representation import IcecraftRep

from tests.icecraft.data.rep_data import ENCODE_DATA, EXP_REP, is_one

class IcecraftRepTest(TestCase):
	def test_creation(self):
		dut = IcecraftRep([], [], [], [], {})
	
	def check_ones(self, config, ones, tile_to_dim):
		for tile in ones:
			group_max, index_max = tile_to_dim[tile]
			for group, index in itertools.product(range(group_max), range(index_max)):
				bit = IcecraftBitPosition.from_tile(tile, group, index)
				exp = is_one(bit, ones)
				res = config.get_bit(bit)
				self.assertEqual(exp, res, f"{bit}")
	
	def set_ones(self, config, ones):
		for tile, tile_ones in ones.items():
			for group, group_ones in tile_ones.items():
				for index in group_ones:
					config.set_bit(IcecraftBitPosition.from_tile(tile, group, index), True)
	
	def get_tile_to_dim(self):
		spec = SPECS_BY_ASC["8k"]
		tile_to_dim = {}
		for pos, kind in spec.get_tile_types():
			tile_to_dim[IcecraftPosition(pos.x, pos.y)] = (spec.tile_height, spec.tile_type_width[kind])
		
		return tile_to_dim
	
	def test_decode(self):
		dut = EXP_REP
		tile_to_dim = self.get_tile_to_dim()
		
		for tc in ENCODE_DATA:
			config = IcecraftRawConfig.create_empty()
			with self.subTest(desc=tc.desc):
				self.check_ones(config, {t: {} for t in tc.ones}, tile_to_dim)
				dut.decode(config, tc.chromo)
				
				self.check_ones(config, tc.ones, tile_to_dim)
	
	def test_set_carry_enable(self):
		tile_15 = IcecraftPosition(15, 17)
		tile_16 = IcecraftPosition(16, 17)
		
		class CarryTD(NamedTuple):
			desc: str
			to_set: Dict[IcecraftPosition, Dict[int, List[int]]]
			ones: Dict[IcecraftPosition, Dict[int, List[int]]]
		
		test_data = [
			CarryTD("no carry enables to be set", {}, {tile_15: {}, tile_16: {}}),
			CarryTD(
				"only higher",
				{
					tile_16: {12: [32]},
					IcecraftPosition(15, 18): {1: [49]},
				},
				{
					tile_15: {0: [44], 2: [44], 4: [44], 6: [44], 8: [44], 10: [44], 12: [44], 14: [44]},
					tile_16: {0: [44], 2: [44], 4: [44], 6: [44], 8: [44], 10: [44], 12: [32]},
					IcecraftPosition(15, 18): {1: [49]},
				}
			),
			CarryTD(
				"multiple in series",
				{
					tile_15: {2: [32], 4: [32], 6: [32]},
					tile_16: {2: [32], 4: [32], 6: [32], 8: [32], 10: [32], 12: [32]},
				},
				{
					tile_15: {0: [44], 2: [32, 44], 4: [32, 44], 6: [32]},
					tile_16: {0: [44], 2: [32, 44], 4: [32, 44], 6: [32, 44], 8: [32, 44], 10: [32, 44], 12: [32]},
				}
			),
		]
		
		carry_data = deepcopy(EXP_REP.carry_data)
		carry_data[tile_15][7].carry_use.append(PartConf((IcecraftBitPosition(15, 18, 1, 49), ), (True, )))
		
		tile_to_dim = self.get_tile_to_dim()
		
		for td in test_data:
			config = IcecraftRawConfig.create_empty()
			self.set_ones(config, td.to_set)
			with self.subTest(desc=td.desc):
				IcecraftRep.set_carry_enable(config, carry_data)
				
				self.check_ones(config, td.ones, tile_to_dim)
