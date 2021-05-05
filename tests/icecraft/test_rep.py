import itertools

from unittest import TestCase

from adapters.icecraft import IcecraftBitPosition, IcecraftPosition, IcecraftRawConfig
from adapters.icecraft.ice_board.device_data import SPECS_BY_ASC
from adapters.icecraft.representation import IcecraftRep

from .data.rep_data import ENCODE_DATA, EXP_REP, is_one

class IcecraftRepTest(TestCase):
	def test_creation(self):
		dut = IcecraftRep([], [], [], [])
	
	def check_ones(self, config, ones, tile_to_dim):
		for tile in ones:
			group_max, index_max = tile_to_dim[tile]
			for group, index in itertools.product(range(group_max), range(index_max)):
				bit = IcecraftBitPosition.from_tile(tile, group, index)
				exp = is_one(bit, ones)
				res = config.get_bit(bit)
				self.assertEqual(exp, res, f"{bit}")
	
	def test_decode(self):
		dut = EXP_REP
		
		spec = SPECS_BY_ASC["8k"]
		tile_to_dim = {}
		for pos, kind in spec.get_tile_types():
			tile_to_dim[IcecraftPosition(pos.x, pos.y)] = (spec.tile_height, spec.tile_type_width[kind])
		
		for tc in ENCODE_DATA:
			config = IcecraftRawConfig.create_empty()
			with self.subTest(desc=tc.desc):
				self.check_ones(config, {t: {} for t in tc.ones}, tile_to_dim)
				dut.decode(config, tc.chromo)
				
				self.check_ones(config, tc.ones, tile_to_dim)
