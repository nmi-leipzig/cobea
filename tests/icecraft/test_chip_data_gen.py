import unittest
import copy
import sys

sys.path.append("/usr/local/bin")
import icebox

import adapters.icecraft.chip_data_gen as chip_data_gen
from adapters.icecraft.chip_data_utils import get_segs_for_tile

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
	
	def test_fix_known_issues(self):
		# description, in_segs, exp_segs
		test_data = (
			(
				"glb_netwk",
				[
					((0, 16, 'glb_netwk_1'), (0, 16, 'padin_1'), (0, 17, 'glb_netwk_1'), (0, 18, 'glb_netwk_1'), (17, 33, 'fabout')),
					((33, 14, 'glb_netwk_0'), (33, 15, 'glb_netwk_0'), (33, 16, 'glb_netwk_0')),
				],
				[
					((0, 16, 'glb_netwk_1'), (0, 16, 'padin_1'), (0, 17, 'glb_netwk_1'), (0, 18, 'glb_netwk_1'), (17, 33, 'fabout')),
					((17, 0, 'fabout'), (33, 14, 'glb_netwk_0'), (33, 15, 'glb_netwk_0'), (33, 16, 'glb_netwk_0'), (33, 16, 'padin_1')),
				]
			),
			(
				"RAM neigh_op_top/bot",
				[
					(
						(7, 29, 'neigh_op_tnr_3'), (7, 30, 'neigh_op_rgt_3'), (7, 31, 'neigh_op_bnr_3'),
						(8, 29, 'neigh_op_top_3'), (8, 30, 'ram/RDATA_4'), (8, 31, 'neigh_op_bot_3'),
						(9, 29, 'neigh_op_tnl_3'), (9, 30, 'neigh_op_lft_3'), (9, 31, 'neigh_op_bnl_3')
					),
					(
						(7, 1, 'neigh_op_bnr_1'), (7, 1, 'neigh_op_bnr_5'), (8, 0, 'io_0/D_IN_1'),
						(8, 1, 'neigh_op_bot_1'), (8, 1, 'neigh_op_bot_5'), (9, 1, 'neigh_op_bnl_1'),
						(9, 1, 'neigh_op_bnl_5')
					),
				],
				[
					(
						(7, 29, 'neigh_op_tnr_3'), (7, 30, 'neigh_op_rgt_3'), (7, 31, 'neigh_op_bnr_3'),
						(8, 30, 'ram/RDATA_4'),
						(9, 29, 'neigh_op_tnl_3'), (9, 30, 'neigh_op_lft_3'), (9, 31, 'neigh_op_bnl_3')
					),
					(
						(7, 1, 'neigh_op_bnr_1'), (7, 1, 'neigh_op_bnr_5'), (8, 0, 'io_0/D_IN_1'),
						(9, 1, 'neigh_op_bnl_1'), (9, 1, 'neigh_op_bnl_5')
					),
				]
			),
			(
				"io_global/latch",
				[
					((0, 15, 'fabout'), (0, 32, 'io_global/latch')),
				],
				[
					(
						(0, 1, 'io_global/latch'), (0, 2, 'io_global/latch'), (0, 3, 'io_global/latch'), (0, 4, 'io_global/latch'),
						(0, 5, 'io_global/latch'), (0, 6, 'io_global/latch'), (0, 7, 'io_global/latch'), (0, 8, 'io_global/latch'),
						(0, 9, 'io_global/latch'), (0, 10, 'io_global/latch'), (0, 11, 'io_global/latch'), (0, 12, 'io_global/latch'),
						(0, 13, 'io_global/latch'), (0, 14, 'io_global/latch'), (0, 15, 'fabout'), (0, 15, 'io_global/latch'),
						(0, 16, 'io_global/latch'), (0, 17, 'io_global/latch'), (0, 18, 'io_global/latch'), (0, 19, 'io_global/latch'),
						(0, 20, 'io_global/latch'), (0, 21, 'io_global/latch'), (0, 22, 'io_global/latch'), (0, 23, 'io_global/latch'),
						(0, 24, 'io_global/latch'), (0, 25, 'io_global/latch'), (0, 26, 'io_global/latch'), (0, 27, 'io_global/latch'),
						(0, 28, 'io_global/latch'), (0, 29, 'io_global/latch'), (0, 30, 'io_global/latch'), (0, 31, 'io_global/latch'),
						(0, 32, 'io_global/latch')
					),
				]
			)
		)
		
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		for desc, in_segs, exp_segs in test_data:
			with self.subTest(desc=desc):
				out_segs = chip_data_gen.fix_known_issues(ic, in_segs)
				
				self.assertEqual(exp_segs, out_segs)
	
	def test_get_driver_indices(self):
		test_data = (
			(
				((14, 17, 'sp4_h_r_10'), (15, 17, 'sp4_h_r_23'), (16, 17, 'sp4_h_r_34'), (17, 17, 'sp4_h_r_47'), (18, 17, 'sp4_h_l_47')),
				(False, (0, 1, 2, 4))
			),
			(((16, 17, 'local_g1_4'), ), (False, (0, ))),
			(
				(
					(14, 15, 'neigh_op_tnr_0'), (14, 16, 'neigh_op_rgt_0'), (14, 17, 'neigh_op_bnr_0'), (15, 15, 'neigh_op_top_0'),
					(15, 16, 'lutff_0/out'), (15, 17, 'neigh_op_bot_0'), (16, 15, 'neigh_op_tnl_0'), (16, 16, 'neigh_op_lft_0'),
					(16, 17, 'neigh_op_bnl_0')
				),
				(True, (4, ))
			),
			(((16, 17, 'lutff_5/cout'),), (True, (0, ))),
			(((16, 17, 'lutff_6/lout'),), (True, (0, ))),
			(
				(
					(7, 31, 'neigh_op_tnr_3'), (7, 32, 'neigh_op_rgt_3'), (7, 33, 'logic_op_bnr_3'), (8, 31, 'neigh_op_top_3'),
					(8, 32, 'ram/RDATA_4'), (8, 33, 'logic_op_bot_3'), (9, 31, 'neigh_op_tnl_3'), (9, 32, 'neigh_op_lft_3'),
					(9, 33, 'logic_op_bnl_3')
				),
				(True, (4, ))
			),
			(
				(
					(6, 32, 'neigh_op_tnr_2'), (6, 32, 'neigh_op_tnr_6'), (7, 32, 'neigh_op_top_2'), (7, 32, 'neigh_op_top_6'),
					(7, 33, 'io_1/D_IN_0'), (8, 32, 'neigh_op_tnl_2'), (8, 32, 'neigh_op_tnl_6')
				),
				(True, (4, ))
			),
		)
		
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		for seg, exp in test_data:
			with self.subTest(seg=seg):
				res = chip_data_gen.get_driver_indices(ic, seg)
				
				self.assertEqual(exp, res)
