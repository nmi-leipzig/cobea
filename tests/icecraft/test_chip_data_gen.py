import unittest
import copy

import adapters.icecraft.chip_data_gen as chip_data_gen
from adapters.icecraft.chip_data import get_segs_for_tile

class ChipDataGenTest(unittest.TestCase):
	# test data
	all_segs = (
		((1, 0, "sp_v_0"), (1, 1, "sp_v_1"), (1, 2, "sp_v_2")),
		((0, 1, "sp_h_0"), (1, 1, "sp_h_1"), (2, 1, "sp_h_2")),
		((0, 1, "internal"), ),
		((1, 0, "internal"), ),
		((1, 1, "internal"), ),
		((1, 2, "internal"), ),
		((2, 1, "internal"), ),
		((0, 1, "sp_c_0"), (1, 0, "sp_c_2"), (1, 1, "sp_c_1")),
	)
	org_seg_kinds = (
		((0, 0, "sp_v_0"), (0, 1, "sp_v_1"), (0, 2, "sp_v_2")),
		((0, 0, "sp_h_0"), (1, 0, "sp_h_1"), (2, 0, "sp_h_2")),
		((0, 0, "internal"), ),
		((0, 0, "sp_c_0"), (1, -1, "sp_c_2"), (1, 0, "sp_c_1")),
	)
	org_tile_map = {
		(1, 0): [(0, 0), (2, 0), (3, 1)],
		(1, 1): [(0, 1), (1, 1), (2, 0), (3, 2)],
		(1, 2): [(0, 2), (2, 0)],
		(0, 1): [(1, 0), (2, 0), (3, 0)],
		(2, 1): [(1, 2), (2, 0)],
	}
	
	def check_segments(self, seg_kinds, tile_map, all_segs):
		# group segments by tile
		tile_segs = {}
		for seg_grp in all_segs:
			for x, y, n in seg_grp:
				tile_segs.setdefault((x, y), set()).add(tuple(sorted(seg_grp)))
		
		for tile_pos in tile_map:
			segs = get_segs_for_tile(seg_kinds, tile_pos, tile_map[tile_pos])
			segs = set(tuple(sorted(s)) for s in segs)
			
			self.assertEqual(tile_segs[tile_pos], segs, f"Wrong segments for {tile_pos}")
	
	def test_test_data(self):
		self.check_segments(self.org_seg_kinds, self.org_tile_map, self.all_segs)
	
	def test_get_seg_kinds(self):
		seg_kinds, tile_map = chip_data_gen.get_seg_kinds(self.all_segs)
		
		self.check_segments(seg_kinds, tile_map, self.all_segs)
	
	def test_sort_net_data(self):
		# sort
		srt_seg_kinds, srt_tile_map = chip_data_gen.sort_net_data(self.org_seg_kinds, self.org_tile_map)
		
		# check order
		for i in range(len(srt_seg_kinds)-1):
			self.assertTrue(srt_seg_kinds[i]<=srt_seg_kinds[i+1])
		
		# check consistence
		self.assertEqual(set(self.org_seg_kinds), set(srt_seg_kinds))
		self.check_segments(srt_seg_kinds, srt_tile_map, self.all_segs)
