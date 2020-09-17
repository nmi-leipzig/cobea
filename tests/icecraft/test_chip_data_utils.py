import unittest

import adapters.icecraft.chip_data_utils as chip_data_utils

class ChipDataUtilsTest(unittest.TestCase):
	# test data
	tile_pos = (1, 2)
	seg_refs = [(0, 2), (2, 0)]
	seg_kinds = (
		((0, 0, "sp_v_0"), (0, 1, "sp_v_1"), (0, 2, "sp_v_2")),
		((0, 0, "sp_h_0"), (1, 0, "sp_h_1"), (2, 0, "sp_h_2")),
		((0, 0, "internal"), ),
	)
	segs = (
		((1, 0, "sp_v_0"), (1, 1, "sp_v_1"), (1, 2, "sp_v_2")),
		((1, 2, "internal"), )
	)
	
	def test_seg_from_seg_kind(self):
		for (kind_index, role), exp in zip(self.seg_refs, self.segs):
			kind = self.seg_kinds[kind_index]
			with self.subTest(role=role, kind=kind):
				res = chip_data_utils.seg_from_seg_kind(kind, self.tile_pos, role)
				self.assertEqual(exp, res)
	
	def test_get_segs_for_tile(self):
		
		res = chip_data_utils.get_segs_for_tile(self.seg_kinds, self.tile_pos, self.seg_refs)
		self.assertEqual(set(self.segs), set(res))

