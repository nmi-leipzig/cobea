import unittest

import adapters.icecraft.chip_data as chip_data

class ChipDataTest(unittest.TestCase):
	def test_get_nets_for_tile(self):
		tile_pos = (1, 2)
		seg_refs = [(0, 2), (2, 0)]
		seg_kinds = (
			((0, 0, "sp_v_0"), (0, 1, "sp_v_1"), (0, 2, "sp_v_2")),
			((0, 0, "sp_h_0"), (1, 0, "sp_h_1"), (2, 0, "sp_h_2")),
			((0, 0, "internal"), ),
		)
		segs = set((
			((1, 0, "sp_v_0"), (1, 1, "sp_v_1"), (1, 2, "sp_v_2")),
			((1, 2, "internal"), )
		))
		
		res = chip_data.get_segs_for_tile(seg_kinds, tile_pos, seg_refs)
		self.assertEqual(segs, set(res))

