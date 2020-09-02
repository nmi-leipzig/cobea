import unittest
import sys
import re

sys.path.append("/usr/local/bin")
import icebox

import adapters.icecraft.chip_data as chip_data

def get_names(segs):
	return tuple(n for x, y, n in segs)

def get_tiles(segs):
	return tuple((x, y) for x, y, n in segs)

class ChipDataTest(unittest.TestCase):
	
	representative_tiles = (
		(16, 17), 
		(1, 1), (1, 2), (2, 1), (7, 1), (7, 2), (9, 1), (9, 2),
		(24, 1), (24, 2), (26, 1), (26, 2), (31, 1), (32, 1), (32, 2),
		(1, 31), (1, 32), (2, 32), (7, 31), (7, 32), (9, 31), (9, 32),
		(24, 31), (24, 32), (26, 31), (26, 32), (31, 32), (32, 31), (32, 32),
		(8, 1), (8, 2), (25, 1), (25, 2), (8, 31), (8, 32), (25, 31), (25, 32)
	)
	
	class Issue:
		def __init__(self, ic_seg, cd_seg):
			self.ic_set = set(ic_seg)
			self.cd_set = set(cd_seg)
			
			self.common = self.ic_set & self.cd_set
			self.ic_only = {s: False for s in self.ic_set - self.cd_set}
			self.cd_only = {s: False for s in self.cd_set - self.ic_set}
		
		@property
		def is_explained(self):
			return all(self.ic_only.values()) and all(self.cd_only.values())
		
		def explain(self, entry, for_ic=True):
			rel_set = self.ic_only if for_ic else self.cd_only
			try:
				rel_set[entry] = True
			except KeyError:
				pass
	
	def known_issue_glb_netwk(self, ic, issue):
		# is glb_netwk
		glb_index = None
		for entry in issue.common:
			r = re.match(r"glb_netwk_(?P<index>\d)", entry[2])
			if r is not None:
				glb_index = int(r.group("index"))
				break
		
		if glb_index is None:
			return
		
		# check padin
		x, y, pad_index = ic.padin_pio_db()[glb_index]
		pad_entry = (x, y, f"padin_{pad_index}")
		issue.explain(pad_entry, False)
		
		# check fabout
		x, y = [(x, y) for x, y, i in ic.gbufin_db() if i==glb_index][0]
		fab_entry = (x, y, "fabout")
		issue.explain(fab_entry, False)
	
	def known_issue_ram_neigh(self, ic, issue):
		# handle the fact, that RAM tiles only use certain neigh_op_top/bot inputs
		
		# the segment (faulty or not) is only generated iff a valid neighbor is in the seed tiles
		# the prescence of the (invalid neighbor) RAM tile is irrelevant
		
		for entry in [e for e, v in issue.ic_only.items() if not v]:
			r = re.match(r"neigh_op_(?P<kind>top|bot)_(?P<index>\d)", entry[2])
			if r is None:
				continue
			
			tile_type = ic.tile_type(*entry[:2])
			
			if tile_type not in ("RAMT", "RAMB"):
				continue
			
			if tile_type == "RAMT":
				if r.group("kind") == "top" and r.group("index") in ("0", "2", "4", "6"):
					continue
			else:
				if r.group("kind") == "bot" and r.group("index") in ("0", "4"):
					continue
			
			issue.explain(entry, True)
	
	def check_segments(self, ic, ic_segs, cd_segs):
		exp_set = set(ic_segs)
		res_set = set(cd_segs)
		try:
			self.assertEqual(exp_set, res_set)
		except AssertionError as ae:
			# check if it's a known problem with iceconfig
			exp_not_res = exp_set - res_set
			res_not_exp = res_set - exp_set
			
			# match nets
			issue_list = []
			
			for e_seg in exp_not_res:
				e_set = set(e_seg)
				found = False
				
				for r_seg in res_not_exp:
					if e_set & set(r_seg):
						issue_list.append(self.Issue(e_set, r_seg))
						found = True
						break
				
				if found:
					res_not_exp.remove(r_seg)
				else:
					issue_list.append(self.Issue(e_set, []))
			
			for r_seg in res_not_exp:
				issue_list.append(self.Issue([], r_seg))
			
			for issue in issue_list:
				self.known_issue_glb_netwk(ic, issue)
				self.known_issue_ram_neigh(ic, issue)
				# not checked:
				# - net for io_global/latch doesn't contain all tiles on an edge
			
			if not all([i.is_explained for i in issue_list]):
				unexplained = [i for i in issue_list if not i.is_explained]
				msg = f"{len(unexplained)} unexplained issues:\n"
				for issue in unexplained:
					msg += f"segment {list(issue.common)[:5]}\n"
					msg += f"\ticeconfig: {[s for s, v in issue.ic_only.items() if not v]}\n"
					msg += f"\tchip_data: {[s for s, v in issue.cd_only.items() if not v]}\n"
					
				raise AssertionError(msg) from ae
	
	def test_meta_check_segments_test(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		# identical segments
		with self.subTest(desc="identical"):
			segs = ((22, 5, 'glb_netwk_5'), (22, 6, 'glb_netwk_5'), (22, 7, 'glb_netwk_5'))
			self.check_segments(ic, segs, segs)
		
		# known issues
		with self.subTest(desc="known issue RAM neighbors"):
			ic_segs = ((
				(7, 11, 'neigh_op_tnr_3'), (7, 12, 'neigh_op_rgt_3'), (7, 13, 'neigh_op_bnr_3'),
				(8, 11, 'neigh_op_top_3'), (8, 12, 'ram/RDATA_4'), (8, 13, 'neigh_op_bot_3'),
				(9, 11, 'neigh_op_tnl_3'), (9, 12, 'neigh_op_lft_3'), (9, 13, 'neigh_op_bnl_3')
			),)
			cd_segs = ((
				(7, 11, 'neigh_op_tnr_3'), (7, 12, 'neigh_op_rgt_3'), (7, 13, 'neigh_op_bnr_3'),
				(8, 12, 'ram/RDATA_4'),
				(9, 11, 'neigh_op_tnl_3'), (9, 12, 'neigh_op_lft_3'), (9, 13, 'neigh_op_bnl_3')
			),)
			self.check_segments(ic, ic_segs, cd_segs)
		
		with self.subTest(desc="known issue glb_netwk"):
			ic_segs = ((
				(33, 11, 'glb_netwk_0'), (33, 12, 'glb_netwk_0'), (33, 13, 'glb_netwk_0'),
				(33, 14, 'glb_netwk_0'), (33, 15, 'glb_netwk_0'), (33, 16, 'glb_netwk_0'),
			),)
			cd_segs = ((
				(33, 11, 'glb_netwk_0'), (33, 12, 'glb_netwk_0'), (33, 13, 'glb_netwk_0'),
				(33, 14, 'glb_netwk_0'), (33, 15, 'glb_netwk_0'), (33, 16, 'glb_netwk_0'),
				(33, 16, 'padin_1')
			),)
			self.check_segments(ic, ic_segs, cd_segs)
		
		# mismatch
		with self.subTest(desc="mismatch"):
			with self.assertRaises(AssertionError):
				ic_segs = ((
					(7, 11, 'neigh_op_tnr_3'), (7, 12, 'neigh_op_rgt_3'), (7, 13, 'neigh_op_bnr_3'),
					(8, 11, 'neigh_op_top_3'), (8, 12, 'ram/RDATA_4'), (8, 13, 'neigh_op_bot_3'),
					(9, 11, 'neigh_op_tnl_3'), (9, 12, 'neigh_op_lft_3'), (9, 13, 'neigh_op_bnl_3')
				),)
				cd_segs = ((
					(7, 12, 'neigh_op_rgt_3'), (7, 13, 'neigh_op_bnr_3'),
					(8, 12, 'ram/RDATA_4'),
					(9, 11, 'neigh_op_tnl_3'), (9, 12, 'neigh_op_lft_3'), (9, 13, 'neigh_op_bnl_3')
				),)
				self.check_segments(ic, ic_segs, cd_segs)
	
	def generic_get_segments_test(self, tiles, ic):
		res = chip_data.get_segments(tiles)
		res_set = set(res)
		
		self.assertEqual(len(res), len(res_set))
		
		exp_segs = ic.group_segments(tiles, connect_gb=True)
		
		self.check_segments(ic, exp_segs, res)
	
	def test_get_segments(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		# single tiles
		for tile in self.representative_tiles:
			with self.subTest(tiles=tile):
				self.generic_get_segments_test([tile], ic)
		
		# tile group
		tiles = [(16, 17), (16, 18), (16, 19)]
		with self.subTest(tiles=tiles):
			self.generic_get_segments_test(tiles, ic)
	
	def bits_to_str(self, bits):
		return self.merge_bit_values(bits, [True]*len(bits))
	
	def merge_bit_values(self, bits, values):
		if len(bits) != len(values):
			raise ValueError()
		
		merged = []
		for b, v in zip(bits, values):
			m = f"{'' if v else '!'}B{b[0]}[{b[1]}]"
			
			merged.append(m)
		
		return merged
	
	def test_meta_merge_bit_values(self):
		test_data = (
			(((0, 8), (0, 9), (0, 10)), (False, False, True), ['!B0[8]', '!B0[9]', 'B0[10]']),
			(((0, 0),), (True,), ['B0[0]']),
			(((14, 3), (15, 3)), (True, False), ['B14[3]', '!B15[3]']),
		)
		
		for bits, values, exp in test_data:
			merged = self.merge_bit_values(bits, values)
			self.assertEqual(exp, merged)
	
	def test_get_raw_conf(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		for tile in self.representative_tiles:
			with self.subTest(tiles=tile):
				res = chip_data.get_raw_conf(tile)
				res_set = set()
				# prepare results for comparison
				for kind, conf in res.items():
					if kind == "connection":
						for bits, (dst, src_data) in conf.items():
							res_set.update([(tuple(sorted(self.merge_bit_values(bits, v))), kind, s, dst) for v, s in src_data])
					elif kind == "tile":
						res_set.update([(tuple(sorted(self.bits_to_str(b))), n) for b, n in conf])
					elif kind == "ColBufCtrl":
						res_set.update([(tuple(sorted(self.bits_to_str(b))), "ColBufCtrl", f"glb_netwk_{i}") for i, b in enumerate(conf)])
					elif kind == "lut":
						for i, lut in enumerate(conf):
							bits = []
							for b, _ in lut:
								bits.extend(b)
							res_set.add((tuple(sorted(self.bits_to_str(bits))), f"LC_{i}"))
					elif kind in ("RamConfig", "RamCascade"):
						res_set.update([(tuple(sorted(self.bits_to_str(b))), kind, n) for b, n in conf])
					else:
						raise ValueError(f"Unknown configuration type {kind}")
				
				exp_set = set()
				tile_db = ic.tile_db(*tile)
				
				for entry in tile_db:
					if not ic.tile_has_entry(*tile, entry):
						continue
					
					# map buffer and routing to connection
					if entry[1] in ("routing", "buffer"):
						kind = "connection"
					else:
						kind = entry[1]
					exp_set.add((tuple(sorted(entry[0])), kind, *entry[2:]))
				
				self.assertEqual(exp_set, res_set)
		

