import unittest
import sys
import re
import functools
from dataclasses import astuple
from multiprocessing import Pool

sys.path.append("/usr/local/bin")
import icebox

import adapters.icecraft.chip_data as chip_data
from adapters.icecraft.chip_data_utils import UNCONNECTED_NAME
from adapters.icecraft.misc import IcecraftPosition

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
	
	@functools.lru_cache(None)
	def get_destinations(self, ic, x, y):
		dst_names = []
		for entry in ic.tile_db(x, y):
			if not ic.tile_has_entry(x, y, entry):
				continue
			
			if entry[1] in ("buffer", "routing"):
				dst_names.append(entry[3])
		
		return dst_names
	
	def get_driver_type(self, ic, segment, seg_index):
		"""
		None -> not a driver
		True -> hardwired driver
		False -> configurable driver
		"""
		x, y, net_name = segment[seg_index]
		
		if net_name.startswith("padin"):
			return False
		
		if (net_name.endswith("out") and net_name != "fabout") or net_name.startswith("ram/RDATA") or\
		re.match(r"io_\d/D_IN", net_name) or UNCONNECTED_NAME == net_name:
			return True
		
		if net_name in self.get_destinations(ic, x, y):
			return False
		
		return None
	
	def check_drivers(self, ic, net_data):
		for net in net_data:
			for i in range(len(net.segment)):
				drv_type = self.get_driver_type(ic, net.segment, i)
				if drv_type is None:
					self.assertNotIn(i, net.drivers)
				else:
					self.assertIn(i, net.drivers)
					self.assertEqual(drv_type, net.hard_driven, f"{net.segment[i]}")
			if net.hard_driven:
				self.assertTrue(len(net.drivers) == 1)
	
	def generic_get_net_data_test(self, tiles, ic, exp_segs):
		res = chip_data.get_net_data([IcecraftPosition(*t) for t in tiles])
		res_set = set(res)
		segs = tuple(s.segment for s in res)
		
		# check: all entries unique
		self.assertEqual(len(res), len(res_set))
		self.assertEqual(len(segs), len(set(segs)))
		
		# check segments
		self.check_segments(ic, exp_segs, segs)
		
		# check drivers
		self.check_drivers(ic, res)
	
	@staticmethod
	def ic_seg(tiles, ic):
		return ic.group_segments(tiles, connect_gb=True)
	
	def test_get_net_data(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		test_tiles = [[t] for t in self.representative_tiles]
		test_tiles.append([(16, 17), (16, 18), (16, 19)])
		
		with Pool() as pool:
			seg_func = functools.partial(self.ic_seg, ic=ic)
			exp = pool.map(seg_func, test_tiles)
		
		for tiles, exp_segs in zip(test_tiles, exp):
			# add unconnected net
			exp_segs.update([((*t, UNCONNECTED_NAME), ) for t in tiles])
			with self.subTest(tiles=tiles):
				self.generic_get_net_data_test(tiles, ic, exp_segs)
		
	
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
	
	def prep_reference_config(self, ic, tile):
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
		
		return exp_set
	
	def test_get_raw_config_data(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		for tile in self.representative_tiles:
			with self.subTest(tiles=tile):
				res = chip_data.get_raw_config_data(IcecraftPosition(*tile))
				res_set = set()
				# prepare results for comparison
				for kind, config in res.items():
					if kind == "connection":
						for bits, (dst, src_data) in config.items():
							# check unconnected src
							try:
								uncon = [s for _, s in src_data].index(UNCONNECTED_NAME)
							except ValueError:
								self.fail("unconnected net missing")
							self.assertEqual((False, )*len(bits), src_data[uncon][0])
							
							# filter unconnected src as it not explicitly in the iceconfig results
							src_data = src_data[:uncon] + src_data[uncon+1:]
							
							res_set.update([(tuple(sorted(self.merge_bit_values(bits, v))), kind, s, dst) for v, s in src_data])
					elif kind == "tile":
						res_set.update([(tuple(sorted(self.bits_to_str(b))), n) for b, n in config])
					elif kind == "ColBufCtrl":
						res_set.update([(tuple(sorted(self.bits_to_str(b))), "ColBufCtrl", f"glb_netwk_{i}") for i, b in enumerate(config)])
					elif kind == "lut":
						for i, lut in enumerate(config):
							bits = []
							for b, _ in lut:
								bits.extend(b)
							res_set.add((tuple(sorted(self.bits_to_str(bits))), f"LC_{i}"))
					elif kind in ("RamConfig", "RamCascade"):
						res_set.update([(tuple(sorted(self.bits_to_str(b))), kind, n) for b, n in config])
					else:
						raise ValueError(f"Unknown configuration type {kind}")
				
				exp_set = self.prep_reference_config(ic, tile)
				
				self.assertEqual(exp_set, res_set)
	
	def test_get_lut_io(self):
		for tile in self.representative_tiles:
			with self.subTest(tiles=tile):
				res = chip_data.get_lut_io(IcecraftPosition(*tile))
				
				if tile[0] in list(range(1, 8))+list(range(9, 25))+list(range(26, 33)) and tile[1] in range(1, 33):
					self.assertEqual(8, len(res))
					for lut_index, lut_io in enumerate(res):
						self.assertEqual(4, len(lut_io.in_nets))
						for i, seg in enumerate(lut_io.in_nets):
							self.assertEqual(tile, seg[:2])
							self.assertEqual(f"lutff_{lut_index}/in_{i}", seg[2])
						
						if lut_index == 7:
							suffixes = ("cout", "out")
						else:
							suffixes = ("cout", "lout", "out")
						self.assertEqual(len(suffixes), len(lut_io.out_nets))
						for suf, seg in zip(suffixes, lut_io.out_nets):
							self.assertEqual(tile, seg[:2])
							self.assertEqual(f"lutff_{lut_index}/{suf}", seg[2])
				else:
					self.assertEqual(0, len(res))
	
	def bit_positions_to_bits(self, bit_positions):
		return [(b.group, b.index) for b in bit_positions]
	
	def bit_positions_to_str(self, bit_positions):
		return self.bits_to_str(self.bit_positions_to_bits(bit_positions))
	
	def merge_bit_positions_values(self, bit_positions, values):
		return self.merge_bit_values(self.bit_positions_to_bits(bit_positions), values)
	
	def config_items_to_raw(self, config_assemblage):
		raw_set = set()
		
		for item in config_assemblage.connection:
			# filter unconnected option, as it is implicit in iceconfig
			raw_set.update([(tuple(
				sorted(self.merge_bit_positions_values(item.bits, v))),
				item.kind,
				s,
				item.dst_net
			) for v, s in zip(item.values, item.src_nets) if s != UNCONNECTED_NAME])
		
		raw_set.update([(tuple(sorted(self.bit_positions_to_str(i.bits))), i.kind) for i in config_assemblage.tile])
		
		raw_set.update([(tuple(sorted(self.bit_positions_to_str(i.bits))), "ColBufCtrl", f"glb_netwk_{i.index}") for i in config_assemblage.col_buf_ctrl])
		
		for lut in config_assemblage.lut:
			bits = []
			for l in lut:
				bits.extend(l.bits)
				index = l.index
			raw_set.add((tuple(sorted(self.bit_positions_to_str(bits))), f"LC_{index}"))
		
		raw_set.update(
			(tuple(sorted(self.bit_positions_to_str(rc.bits))), rc.kind, rc.name) for rc in config_assemblage.ram_config
		)
		raw_set.update(
			(tuple(sorted(self.bit_positions_to_str(rc.bits))), rc.kind, rc.name) for rc in config_assemblage.ram_cascade
		)
		
		return raw_set
	
	def generic_get_config_items_test(self, ic, tile):
		res = chip_data.get_config_items(IcecraftPosition(*tile))
		
		# check unconnected net as it is not included in iceconfig output
		for con_item in res.connection:
			self.assertIn(UNCONNECTED_NAME, con_item.src_nets)
			uncon_pos = con_item.src_nets.index(UNCONNECTED_NAME)
			self.assertTrue(all(not v for v in con_item.values[uncon_pos]))
		
		res_set = self.config_items_to_raw(res)
		
		exp_set = self.prep_reference_config(ic, tile)
		
		self.assertEqual(exp_set, res_set)
	
	def test_get_config_items(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		for tile in self.representative_tiles:
			with self.subTest(tiles=tile):
				self.generic_get_config_items_test(ic, tile)
	
	def check_uniqueness(self, iterable):
		self.assertEqual(len(iterable), len(set(iterable)))
	
	def test_get_colbufctrl(self):
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		tile_cbc_map = {(x, y): (cx, cy) for cx, cy, x, y in ic.colbuf_db()}
		
		test_sets = [(t, ) for t in self.representative_tiles]
		test_sets.append(self.representative_tiles)
		
		for tiles in test_sets:
			with self.subTest(desc=f"tiles {str(tiles)[:40]}"):
				res = chip_data.get_colbufctrl(tuple(IcecraftPosition(*t) for t in tiles))
				
				self.check_uniqueness(res)
				
				exp_set = set(IcecraftPosition(*tile_cbc_map[t]) for t in tiles)
				
				self.assertEqual(exp_set, set(res))
				for r in res:
					self.assertIsInstance(r, IcecraftPosition)
	
	def test_hard_driven(self):
		exp_names = {
			UNCONNECTED_NAME,
			'io_0/D_IN_0', 'io_0/D_IN_1', 'io_1/D_IN_0', 'io_1/D_IN_1',
			'lutff_0/cout', 'lutff_0/lout', 'lutff_0/out',
			'lutff_1/cout', 'lutff_1/lout', 'lutff_1/out',
			'lutff_2/cout', 'lutff_2/lout', 'lutff_2/out',
			'lutff_3/cout', 'lutff_3/lout', 'lutff_3/out',
			'lutff_4/cout', 'lutff_4/lout', 'lutff_4/out',
			'lutff_5/cout', 'lutff_5/lout', 'lutff_5/out',
			'lutff_6/cout', 'lutff_6/lout', 'lutff_6/out',
			'lutff_7/cout', 'lutff_7/out',
			'ram/RDATA_0', 'ram/RDATA_1', 'ram/RDATA_10', 'ram/RDATA_11',
			'ram/RDATA_12', 'ram/RDATA_13', 'ram/RDATA_14', 'ram/RDATA_15',
			'ram/RDATA_2', 'ram/RDATA_3', 'ram/RDATA_4', 'ram/RDATA_5',
			'ram/RDATA_6', 'ram/RDATA_7', 'ram/RDATA_8', 'ram/RDATA_9'
		}

		
		hard_driven_list = []
		name_set = set()
		for sk, dk in zip(chip_data.seg_kinds, chip_data.drv_kinds):
			if dk[0]: # hard driven?
				hard_driven_list.append(sk)
				#print(sk[dk[1][0]])
				name_set.add(sk[dk[1][0]][2])
		
		#print("#########")
		#print(sorted(name_set))
		self.assertEqual(exp_names, name_set)
