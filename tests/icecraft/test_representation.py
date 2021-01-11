import unittest
import re
import copy
import itertools
import pdb
from typing import NamedTuple, Iterable, List, Mapping, Callable, Tuple, Union, Dict
from enum import Enum, auto
from dataclasses import dataclass, field

import adapters.icecraft as icecraft
from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftColBufCtrl, LUTFunction
from adapters.icecraft.representation import NetRelation, SourceGroup
from domain.request_model import RequestObject
from domain.model import Gene
from domain.allele_sequence import AlleleList, AlleleAll, AllelePow, Allele
from adapters.icecraft.chip_data import ConfigDictType, get_config_items, get_net_data
from adapters.icecraft.chip_data_utils import NetData
from adapters.icecraft.config_item import ConnectionItem, IndexedItem, ConfigItem

from ..test_request_model import check_parameter_user

class Comparison(Enum):
	DIFFERENT = auto()
	DISORDERED = auto()
	EQUIVALENT = auto()
	IDENTICAL = auto()

class NetRelationTest(unittest.TestCase):
	raw_nets = [
		NetData(((2, 3, "internal"), ), False, (0,)), # 0
		NetData(((2, 3, "internal_2"), ), False, (0,)), # 1
		NetData(((0, 3, "right"), (1, 3, "out"), (2, 3, "left")), True, (1, )), # 2
		NetData(((0, 3, "wire_in_1"), (1, 3, "wire_in_2"), (2, 3, "wire_out")), False, (0, 1)), # 3
		NetData(((2, 3, "empty_out"), ), False, tuple()), # 4 no driver
		NetData(((4, 2, "short_span_1"), (4, 3, "short_span_1")), False, (0, 1)), # 5
		NetData(((4, 1, "short_span_2"), (4, 2, "short_span_2")), False, (0, 1)), # 6
		NetData(((4, 2, "out"), ), True, (0, )), # 7
		NetData(((5, 0, "long_span_1"), (5, 3, "long_span_1")), False, (0, 1)), # 8
		NetData(((5, 3, "long_span_2"), (8, 3, "long_span_2")), False, (0, 1)), # 9
		NetData(((8, 0, "long_span_3"), (8, 3, "long_span_3")), False, (0, 1)), # 10
		NetData(((5, 0, "long_span_4"), (7, 0, "long_span_4"), (8, 0, "long_span_4")), False, (0, 1, 2)), # 11
		NetData(((7, 0, "out"), ), True, (0, )), # 12
	]
	
	# left, wire_out -> internal
	# wire_out -> internal_2
	# out -> wire_in_2
	# short_span_1 <-> short_span_2
	# out -> short_span_2
	# long_span_4 -> long_span_3 -> long_span_2 -> long_span_1
	# out, long_span_1 -> long_span_4
	raw_configs = [
		ConnectionItem(
			(IcecraftBitPosition.from_coords(2, 3, 7, 0), IcecraftBitPosition.from_coords(2, 3, 7, 1)),
			"connection", "internal", ((True, False), (True, True)), ("left", "wire_out")
		), # 0
		ConnectionItem(
			(IcecraftBitPosition.from_coords(2, 3, 7, 2), IcecraftBitPosition.from_coords(2, 3, 7, 3)),
			"connection", "internal_2", ((True, True), ), ("wire_out", )
		), # 1
		ConnectionItem(
			(IcecraftBitPosition.from_coords(1, 3, 6, 10), IcecraftBitPosition.from_coords(1, 3, 6, 11)),
			"connection", "wire_in_2", ((True, False), ), ("out", )
		), # 2
		ConnectionItem(
			(IcecraftBitPosition.from_coords(4, 2, 11, 30), ),
			"connection", "short_span_1", ((True, ), ), ("short_span_2", )
		), # 3
		ConnectionItem(
			(IcecraftBitPosition.from_coords(4, 2, 2, 0), IcecraftBitPosition.from_coords(4, 2, 2, 1)),
			"connection", "short_span_2", ((False, True), (True, False)), ("short_span_1", "out")
		), # 4
		ConnectionItem(
			(IcecraftBitPosition.from_coords(5, 3, 5, 1), ),
			"connection", "long_span_1", ((True, ), ), ("long_span_2", )
		), # 5
		ConnectionItem(
			(IcecraftBitPosition.from_coords(8, 3, 5, 1), ),
			"connection", "long_span_2", ((True, ), ), ("long_span_3", )
		), # 6
		ConnectionItem(
			(IcecraftBitPosition.from_coords(8, 0, 5, 1), ),
			"connection", "long_span_3", ((True, ), ), ("long_span_4", )
		), # 7
		ConnectionItem(
			(IcecraftBitPosition.from_coords(5, 0, 5, 1), ),
			"connection", "long_span_4", ((True, ), ), ("long_span_1", )
		), # 8
		ConnectionItem(
			(IcecraftBitPosition.from_coords(7, 0, 5, 3), ),
			"connection", "long_span_4", ((True), ), ("out", )
		), # 9
	]
	
	def test_creation(self):
		tiles = [TilePosition(1, 3), TilePosition(2, 3)]
		for net_data in self.raw_nets:
			dut = NetRelation(net_data)
			dut_2 = NetRelation(net_data, tiles)
	
	def test_from_net_data_iter(self):
		res = NetRelation.from_net_data_iter(self.raw_nets, [])
		for exp_data, net_rel in zip(self.raw_nets, res):
			self.assertEqual(exp_data, net_rel.net_data)
	
	def test_net_data(self):
		for net_data in self.raw_nets:
			with self.subTest(net_data=net_data):
				dut = NetRelation(net_data)
				self.assertEqual(dut.net_data, net_data)
				self.assertEqual(dut.segment, net_data.segment)
				self.assertEqual(dut.hard_driven, net_data.hard_driven)
				self.assertEqual(dut.drivers, net_data.drivers)
	
	def test_has_external_driver(self):
		for net_data in self.raw_nets:
			for i in range(len(net_data.drivers)+1):
				with self.subTest(net_data=net_data, i=i):
					exp = (i != len(net_data.drivers))
					tiles = [TilePosition(*net_data.segment[d][:2]) for d in net_data.drivers[:i]]
					dut = NetRelation(net_data, tiles)
					self.assertEqual(exp, dut.has_external_driver)
	
	def test_available(self):
		for net_data in self.raw_nets:
			with self.subTest(net_data=net_data):
				dut = NetRelation(net_data)
				self.assertTrue(dut.available)
				dut.available = False
				self.assertFalse(dut.available)
				dut.available = True
				self.assertTrue(dut.available)
	
	def test_create_net_map(self):
		test_input = self.raw_nets
		net_relations = NetRelation.from_net_data_iter(test_input, [])
		res = NetRelation.create_net_map(net_relations)
		
		# check all net_data in map
		for net_data in test_input:
			for net_id in net_data.segment:
				net_res = res[net_id]
				self.assertEqual(net_data, net_res.net_data)
		
		for net_rel in net_relations:
			self.assertIn(net_rel, res.values())
		
		self.assertEqual(set(net_relations), set(res.values()))
		
		# check consistency
		for net_id, net_res in res.items():
			self.assertIn(net_id, net_res.segment)
			self.assertIn(net_res.net_data, test_input)
	
	def check_is_viable_source(self, exp, net_relations):
		for exp_value, net_rel in zip(exp, net_relations):
			self.assertEqual(exp_value, net_rel.is_viable_src, f"{net_rel}")
	
	def test_is_viable_src(self):
		tiles = set(TilePosition(*n.segment[i][:2]) for n in self.raw_nets for i in n.drivers)
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, tiles)
		net_map = NetRelation.create_net_map(net_relations)
		exp = [False]*len(net_relations)
		exp[2] = exp[7] = exp[12] = True
		
		# variance in sources
		with self.subTest(desc="unconnected"):
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="directly connected"):
			SourceGroup.populate_net_relations(net_map, self.raw_configs[:2])
			exp[0] = True
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="transitive connection"):
			SourceGroup.populate_net_relations(net_map, self.raw_configs[2:3])
			exp[1] = exp[3] = True
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="short loop, additional driver"):
			SourceGroup.populate_net_relations(net_map, self.raw_configs[3:5])
			exp[5] = exp[6] = True
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="long loop, no driver"):
			SourceGroup.populate_net_relations(net_map, self.raw_configs[5:9])
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="long loop, additional driver"):
			SourceGroup.populate_net_relations(net_map, self.raw_configs[9:10])
			exp[8] = exp[9] = exp[10] = exp[11] = True
			self.check_is_viable_source(exp, net_relations)
		
		# variance in availability
		
		# not correctly implemented at the moment
		#with self.subTest(desc="long loop, unavailable driver"):
		#	net_relations[12].available = False
		#	exp[8] = exp[9] = exp[10] = exp[11] = exp[12] = False
		#	self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="long loop, again available driver"):
			net_relations[12].available = True
			exp[8] = exp[9] = exp[10] = exp[11] = exp[12] = True
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="long loop, broken"):
			net_relations[10].available = False
			exp[8] = exp[9] = exp[10] = False
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="short loop, broken"):
			net_relations[6].available = False
			exp[5] = exp[6] = False
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="direct and transitive not available"):
			net_relations[2].available = False
			exp[0] = exp[1] = exp[2] = exp[3] = False
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="none available"):
			for i in range(len(net_relations)):
				net_relations[i].available = False
				exp[i] = False
			self.check_is_viable_source(exp, net_relations)
		
		# variance in external drivers
		with self.subTest(desc="all external"):
			net_relations = NetRelation.from_net_data_iter(self.raw_nets, [])
			net_map = NetRelation.create_net_map(net_relations)
			SourceGroup.populate_net_relations(net_map, self.raw_configs)
			exp = [True]*len(net_relations)
			exp[4] = False
			self.check_is_viable_source(exp, net_relations)
		
		with self.subTest(desc="partial external"):
			part_tiles = set(tiles)
			part_tiles.remove((*self.raw_nets[2].segment[0][:2], ))
			part_tiles.remove((*self.raw_nets[9].segment[0][:2], ))
			net_relations = NetRelation.from_net_data_iter(self.raw_nets, part_tiles)
			net_map = NetRelation.create_net_map(net_relations)
			SourceGroup.populate_net_relations(net_map, self.raw_configs[1:2]+self.raw_configs[6:9])
			exp = [True]*len(net_relations)
			exp[0] = exp[4] = exp[5] = exp[6] = False
			self.check_is_viable_source(exp, net_relations)
	
	def test_add_src_grp(self):
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, [])
		net_map = NetRelation.create_net_map(net_relations)
		for rc in self.raw_configs:
			with self.subTest(raw_conf=rc):
				tile_pos = rc.bits[0].tile
				dst = net_map[(*tile_pos, rc.dst_net)]
				src_list = tuple(net_map[(*tile_pos, s)] for s in rc.src_nets)
				src_grp = SourceGroup(rc, dst, src_list)
				
				prev_src_grps = list(dst.iter_src_grps())
				self.assertNotIn(src_grp, prev_src_grps)
				
				dst.add_src_grp(src_grp)
				
				post_src_grps = list(dst.iter_src_grps())
				self.assertIn(src_grp, post_src_grps)
				self.assertEqual(len(prev_src_grps)+1, len(post_src_grps))
				self.assertEqual(set([src_grp]), set(post_src_grps)-set(prev_src_grps))
				self.assertEqual(set(), set(prev_src_grps)-set(post_src_grps))
	
	def test_add_dst_grp(self):
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, [])
		net_map = NetRelation.create_net_map(net_relations)
		for rc in self.raw_configs:
			with self.subTest(raw_conf=rc):
				tile_pos = rc.bits[0].tile
				dst = net_map[(*tile_pos, rc.dst_net)]
				src_list = tuple(net_map[(*tile_pos, s)] for s in rc.src_nets)
				src_grp = SourceGroup(rc, dst, src_list)
				
				for i, net_rel in enumerate(src_list):
					prev_dst_grps = list(net_rel.iter_dst_grps())
					self.assertNotIn(src_grp, prev_dst_grps)
					self.assertNotIn(dst, net_rel.iter_dsts())
					
					net_rel.add_dst(src_grp, i)
					
					self.assertIn(dst, net_rel.iter_dsts())
					post_dst_grps = list(net_rel.iter_dst_grps())
					self.assertIn(src_grp, post_dst_grps)
					self.assertEqual(len(prev_dst_grps)+1, len(post_dst_grps))
					self.assertEqual(set([src_grp]), set(post_dst_grps)-set(prev_dst_grps))
					self.assertEqual(set(), set(prev_dst_grps)-set(post_dst_grps))
					for dst_index, dst_grp in zip(net_rel.iter_dst_indices(), net_rel.iter_dst_grps()):
						self.assertEqual(net_rel, dst_grp.src_list[dst_index])
	
	def test_single_tile(self):
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, [])
		net_map = NetRelation.create_net_map(net_relations)
		SourceGroup.populate_net_relations(net_map, self.raw_configs)
		
		exp = [False] * len(net_relations)
		exp[11] = True
		
		for net_rel, exp_val in zip(net_relations, exp):
			self.assertEqual(exp_val, net_rel.multiple_src_tiles())
	
	def test_iter_drv_tiles(self):
		test_cases = (
			("no driver", NetData(((2, 3, "none"), ), False, tuple()), []),
			("one driver", NetData(((2, 3, "one"), ), False, (0, )), [TilePosition(2, 3)]),
			("two drivers single tile", NetData(((7, 1, "potato"), (7, 1, "tomato")), False, (0, 1)), [TilePosition(7, 1)]),
			("two drivers, two tiles", NetData(((5, 6, "chip"), (1, 6, "chip")), False, (0, 1)), [TilePosition(1, 6), TilePosition(5, 6)]),
			("hard wired", NetData(((7, 3, "out"), (8, 1, "in"), (9, 3, "out")), True, (1, )), [TilePosition(8, 1)]),
		)
		
		for desc, net_data, exp in test_cases:
			dut = NetRelation(net_data)
			
			res = list(dut.iter_drv_tiles())
			self.assertEqual(exp, res)
	
	def test_multiple_driver_tiles_in_net_data(self):
		exp_raw_nets = (False, False, False, True, False, True, True, False, True, True, True, True, False)
		test_cases = [(f"raw net {i}", r, n) for i, (n, r) in enumerate(zip(self.raw_nets, exp_raw_nets))]
		test_cases.append(("no driver", False, NetData(((2, 3, "net"), ), False, tuple())))
		
		for desc, exp, net_data in test_cases:
			with self.subTest(desc=desc):
				res = NetRelation.multiple_driver_tiles_in_net_data(net_data)
				self.assertEqual(exp, res)

class SourceGroupTest(unittest.TestCase):
	raw_nets = NetRelationTest.raw_nets
	raw_configs = NetRelationTest.raw_configs
	
	def create_net_map(self):
		tiles = [TilePosition(*r) for r in ((1, 3), (2, 3), (4, 1), (4, 2), (4, 3), (5, 0), (5, 3), (7, 0), (8, 0), (8, 3))]
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, tiles)
		net_map = NetRelation.create_net_map(net_relations)
		
		return net_map
	
	def test_creation(self):
		net_map = self.create_net_map()
		for item in self.raw_configs:
			with self.subTest(item=item):
				tile = item.bits[0].tile
				dst = net_map[(*tile, item.dst_net)]
				src_list = tuple(net_map[(*tile, s)] for s in item.src_nets)
				
				dut = SourceGroup(item, dst, src_list)
				
				self.assertEqual(tile, dut.tile)
				self.assertEqual(item, dut.config_item)
				self.assertEqual(dst, dut.dst)
				self.assertEqual(src_list, dut.src_list)
	
	def check_uniqueness(self, iterable):
		self.assertEqual(len(iterable), len(set(iterable)))
	
	def test_populate_net_relations(self):
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, [])
		net_map = NetRelation.create_net_map(net_relations)
		
		con_configs = self.raw_configs
		
		res = SourceGroup.populate_net_relations(net_map, con_configs)
		
		res_configs = [s.config_item for s in res]
		self.check_uniqueness(res_configs)
		
		self.assertEqual(set(con_configs), set(res_configs))
		
		with self.subTest(desc="source group to destination"):
			for src_grp in res:
				self.assertIn(src_grp, src_grp.dst.iter_src_grps())
		
		with self.subTest(desc="destination to source group"):
			for net_rel in net_relations:
				if net_rel.hard_driven:
					self.assertEqual(0, len(tuple(net_rel.iter_src_grps())), f"{tuple(net_rel.iter_src_grps())}")
				for src_grp in net_rel.iter_src_grps():
					self.assertEqual(net_rel, src_grp.dst)
		
		with self.subTest(desc="source group to source"):
			for src_grp in res:
				for i, src in enumerate(src_grp.src_list):
					self.assertIn((*src_grp.tile, src_grp.config_item.src_nets[i]), src.segment)
					self.assertIn(src_grp, src.iter_dst_grps())
		
		with self.subTest(desc="source to source group"):
			for net_rel in net_relations:
				for index, dst_grp in zip(net_rel.iter_dst_indices(), net_rel.iter_dst_grps()):
					self.assertEqual(net_rel, dst_grp.src_list[index])

class IcecraftRepGenTest(unittest.TestCase):
	raw_nets = NetRelationTest.raw_nets
	raw_configs = NetRelationTest.raw_configs
	
	def test_creation(self):
		dut = icecraft.IcecraftRepGen()
	
	def test_call(self):
		dut = icecraft.IcecraftRepGen()
		req = RequestObject()
		req["x_min"] = 2
		req["y_min"] = 2
		req["x_max"] = 2
		req["y_max"] = 2
		req["exclude_nets"] = ["sp4", "sp12", "glb_netwk"]
		req["include_nets"] = []
		req["output_lutffs"] = [icecraft.IcecraftLUTPosition.from_coords(2, 2, 2)]
		req["joint_input_nets"] = []
		req["lone_input_nets"] = []
		req["lut_functions"] = [icecraft.LUTFunction.NAND, icecraft.LUTFunction.AND]
		
		dut(req)
	
	def parse_gene(self, raw_gene, desc=""):
		tile = icecraft.TilePosition(*raw_gene[0])
		
		bit_pos = []
		for raw_bit in raw_gene[1]:
			bit_pos.append(icecraft.IcecraftBitPosition(tile, *raw_bit))
		
		raw_alleles = raw_gene[2]
		if raw_alleles == []:
			alleles = model.AlleleAll(len(bit_pos))
		else:
			tmp_alleles = []
			for j, raw_allele in enumerate(raw_alleles):
				tmp_alleles.append(model.Allele(raw_allele, f"allele {j}"))
			
			alleles = model.AlleleList(tmp_alleles)
		
		return model.Gene(tuple(bit_pos), alleles, desc)
	
	@unittest.skip
	def test_correct_rep(self):
		with open(os.path.join(TEST_DATA_DIR, "rep_creation.json"), "r") as json_file:
			raw_test_data = json.load(json_file)
		dut = icecraft.IcecraftRepGen()
		
		for raw_test in raw_test_data:
			with self.subTest():
				# read test data and create request
				req = RequestObject()
				req["x_min"] = raw_test[0]
				req["y_min"] = raw_test[1]
				req["x_max"] = raw_test[2]
				req["y_max"] = raw_test[3]
				req["exclude_nets"] = [v for v, d in raw_test[4]]
				req["include_nets"] = [v for v, d in raw_test[5]]
				output = [icecraft.IcecraftLUTPosition.from_coords(*c) for c in raw_test[6]]
				req["output_lutffs"] = list(output)
				req["joint_input_nets"] = raw_test[7]
				req["lone_input_nets"] = raw_test[8]
				req["lut_functions"] = [icecraft.LUTFunction[s] for s in raw_test[9]]
				
				genes = []
				
				for i, raw_gene in enumerate(raw_test[10]):
					genes.append(self.parse_gene(raw_gene, f"gene {i}"))
				
				const_bits = []
				for i, raw_const in enumerate(raw_test[11]):
					const_bits.append(self.parse_gene(raw_const, f"const {i}"))
				
				used_colbufctrl = []
				for raw_ctrl in raw_test[12]:
					used_colbufctrl.append(icecraft.IcecraftColBufCtrl.from_coords(*raw_ctrl))
				
				# call DUT
				rep = dut(req)
				
				# check representation
				self.assertEqual(set(genes), set(rep.genes))
				self.assertEqual(set(const_bits), set(constant))
				self.assertEqual(set(used_colbufctrl), set(rep.colbufctrl))
				self.assertEqual(set(output), set(rep.output))
				
		
	
	def test_parameter_user(self):
		rep_gen = icecraft.IcecraftRepGen()
		check_parameter_user(self, rep_gen)
	
	def test_tiles_from_rectangle(self):
		test_data = (
			((2, 2, 2, 2), [(2, 2)]), # single tile
			((3, 5, 7, 5), [(3, 5), (4, 5), (5, 5), (6, 5), (7, 5)]), # row
			((7, 9, 7, 13), [(7, 9), (7, 10), (7, 11), (7, 12), (7, 13)]), # colum
			((4, 6, 5, 7), [(4, 6), (4, 7), (5, 6), (5, 7)]), # no inner tile
			((5, 8, 7, 10), [(5, 8), (5, 9), (5, 10), (6, 8), (6, 9), (6, 10), (7, 8), (7, 9), (7, 10)]), # inner tile
		)
		
		for rect, exp in test_data:
			res = icecraft.IcecraftRepGen.tiles_from_rectangle(*rect)
			res_set = set(res)
			
			# no duplicates
			self.assertEqual(len(res), len(res_set))
			
			# correct tiles
			self.assertEqual(set(exp), res_set)
	
	def check_available(self, exp, net_relations):
		for exp_value, net_rel in zip(exp, net_relations):
			self.assertEqual(exp_value, net_rel.available, f"{net_rel}")
	
	def cond_func(self, net_rel):
		for seg in net_rel.segment:
			if re.match(r".*out$", seg[2]):
				return True
		return False
	
	def test_set_available(self):
		tiles = set(TilePosition(*n.segment[i][:2]) for n in self.raw_nets for i in n.drivers)
		part_tiles = set(tiles)
		for net_index in (2, 12):
			net = self.raw_nets[net_index]
			seg_index = net.drivers[0]
			part_tiles.remove((*net.segment[seg_index][:2], ))
		net_relations = [NetRelation(d, part_tiles) for d in self.raw_nets]
		
		with self.subTest(desc="all to False"):
			icecraft.IcecraftRepGen.set_available(net_relations, False, lambda x: True)
			self.check_available([False]*len(net_relations), net_relations)
		
		with self.subTest(desc="all to True"):
			icecraft.IcecraftRepGen.set_available(net_relations, True, lambda x: True)
			exp = [True]*len(net_relations)
			self.check_available([True]*len(net_relations), net_relations)
		
		with self.subTest(desc="no change"):
			icecraft.IcecraftRepGen.set_available(net_relations, False, lambda x: False)
			self.check_available(exp, net_relations)
		
		with self.subTest(desc="regex"):
			# reset
			icecraft.IcecraftRepGen.set_available(net_relations, True, lambda x: True)
			
			exp = [True]*len(net_relations)
			exp[2] = exp[3] = exp[4] = exp[7] = exp[12] = False
			icecraft.IcecraftRepGen.set_available(net_relations, False, lambda x: any(re.match(r".*out$", n) for _, _, n in x.segment))
			self.check_available(exp, net_relations)
		
		with self.subTest(desc="regex function"):
			# reset
			icecraft.IcecraftRepGen.set_available(net_relations, True, lambda x: True)
			icecraft.IcecraftRepGen.set_available(net_relations, False, self.cond_func)
			self.check_available(exp, net_relations)
		
		with self.subTest(desc="external driver"):
			# reset
			icecraft.IcecraftRepGen.set_available(net_relations, True, lambda x: True)
			
			exp = [True]*len(net_relations)
			exp[2] = exp[3] = exp[11] = exp[12] = False
			icecraft.IcecraftRepGen.set_available(net_relations, False, lambda x: x.has_external_driver)
			self.check_available(exp, net_relations)
			
	
	def test_create_regex_condition(self):
		test_data = (
			(r"", (True, )*13),
			(r"never_seen", (False, )*13),
			(r"internal", (True, True, False, False, False, False, False, False, False, False, False, False, False)),
			(r".*span_\d", (False, False, False, False, False, True, True, False, True, True, True, True, False))
		)
		
		net_relations = NetRelation.from_net_data_iter(self.raw_nets, [])
		
		for regex_str, exp in test_data:
			with self.subTest(regex=regex_str):
				func = icecraft.IcecraftRepGen.create_regex_condition(regex_str)
				for net_rel, exp_val in zip(net_relations, exp):
					val = func(net_rel)
					self.assertEqual(exp_val, val, f"{net_rel}")
	
	def test_choose_nets(self):
		tiles = set(TilePosition(*n.segment[i][:2]) for n in self.raw_nets for i in n.drivers)
		for net_index in (2, 12):
			net = self.raw_nets[net_index]
			seg_index = net.drivers[0]
			tiles.remove((*net.segment[seg_index][:2], ))
		no_ext_drv = [True] * len(self.raw_nets)
		no_ext_drv[2] = no_ext_drv[3] = no_ext_drv[11] = no_ext_drv[12] = False
		
		test_data = (
			("empty parameters, only external driven unavailable", (
				[], [], [], []
			), [True, True, False, False, True, True, True, True, True, True, True, False, False]),
			("exclude nets", (
				[r".*span"], [], [], []
			), [True, True, False, False, True, False, False, True, False, False, False, False, False]),
			("include nets", (
				[], ["left$"], [], []
			), [True, True, True, False, True, True, True, True, True, True, True, False, False]),
			("joint_input_nets", (
				[], [], ["left"], []
			), [True, True, True, False, True, True, True, True, True, True, True, False, False]),
			("lone_input_nets", (
				[], [], [], [IcecraftNetPosition.from_coords(2, 3, "left")]
			), [True, True, True, False, True, True, True, True, True, True, True, False, False]),
			("complete example", (
				[r".*span"], ["^long_span_\d$"], ["out"], [IcecraftNetPosition.from_coords(2, 3, "left")]
			), [True, True, True, False, True, False, False, True, True, True, True, True, True]),
		)
		
		
		with self.subTest(desc="default values of available"):
			net_relations = NetRelation.from_net_data_iter(self.raw_nets, tiles)
			self.check_available([True] * len(net_relations), net_relations)
		
		for desc, in_data, exp in test_data:
			with self.subTest(desc=desc):
				net_relations = NetRelation.from_net_data_iter(self.raw_nets, tiles)
				net_map = NetRelation.create_net_map(net_relations)
				
				req = RequestObject()
				req["exclude_nets"], req["include_nets"], req["joint_input_nets"], req["lone_input_nets"] = in_data
				
				icecraft.IcecraftRepGen._choose_nets(net_relations, net_map, req)
				
				self.check_available(exp, net_relations)
	
	def test_get_colbufctrl_coordinates(self):
		net_data_list = [NetData(tuple(
			[(0, i, "padin_1")]+[(x, y, f"glb_netwk_{i}") for x in range(1, 33) for y in range(1, 33)]
		), False, (0,)) for i in range(8)]
		net_relations = NetRelation.from_net_data_iter(net_data_list, [])
		net_map = NetRelation.create_net_map(net_relations)
		
		for net_rel, avail in zip(net_relations, (True, False, False, False, False, True, False, False)):
			net_rel.available = avail
		
		test_data = (
			("no tile", [], []),
			("single tile", [TilePosition(16, 17)], [
				IcecraftColBufCtrl.from_coords(16, 24, 0), IcecraftColBufCtrl.from_coords(16, 24, 5)
			]),
			("multiple tiles", [TilePosition(*t) for t in ((3, 24), (3, 25), (4, 24), (4, 25))], [
				IcecraftColBufCtrl.from_coords(3, 24, 0), IcecraftColBufCtrl.from_coords(3, 24, 5),
				IcecraftColBufCtrl.from_coords(3, 25, 0), IcecraftColBufCtrl.from_coords(3, 25, 5),
				IcecraftColBufCtrl.from_coords(4, 24, 0), IcecraftColBufCtrl.from_coords(4, 24, 5),
				IcecraftColBufCtrl.from_coords(4, 25, 0), IcecraftColBufCtrl.from_coords(4, 25, 5),
			]),
			("RAM tiles", [TilePosition(*t) for t in ((8, 3), (8, 29), (25, 16), (25, 17))], [
				IcecraftColBufCtrl.from_coords(8, 8, 0), IcecraftColBufCtrl.from_coords(8, 8, 5),
				IcecraftColBufCtrl.from_coords(8, 25, 0), IcecraftColBufCtrl.from_coords(8, 25, 5),
				IcecraftColBufCtrl.from_coords(25, 9, 0), IcecraftColBufCtrl.from_coords(25, 9, 5),
				IcecraftColBufCtrl.from_coords(25, 24, 0), IcecraftColBufCtrl.from_coords(25, 24, 5),
			]),
			("column", [TilePosition(6, y) for y in range(10, 17)], [
				IcecraftColBufCtrl.from_coords(6, 9, 0), IcecraftColBufCtrl.from_coords(6, 9, 5),
			]),
		)
		
		for desc, tiles, exp in test_data:
			with self.subTest(desc=desc):
				res = icecraft.IcecraftRepGen.get_colbufctrl_coordinates(net_map, tiles)
				
				self.assertEqual(exp, res)
		
	
	def test_get_colbufctrl_config(self):
		test_data = (
			(
				[IcecraftColBufCtrl.from_coords(1, 8, 0), IcecraftColBufCtrl.from_coords(13, 9, 4)],
				[
					IndexedItem((IcecraftBitPosition.from_coords(1, 8, 9, 7), ), "ColBufCtrl", 0), 
					IndexedItem((IcecraftBitPosition.from_coords(13, 9, 13, 7), ), "ColBufCtrl", 4), 
				]
			),
			(
				[IcecraftColBufCtrl.from_coords(8, 8, 0), IcecraftColBufCtrl.from_coords(25, 24, 4)],
				[
					IndexedItem((IcecraftBitPosition.from_coords(8, 8, 9, 7), ), "ColBufCtrl", 0), 
					IndexedItem((IcecraftBitPosition.from_coords(25, 24, 13, 7), ), "ColBufCtrl", 4), 
				]
			),
		)
		
		for coords, exp in test_data:
			with self.subTest(coords=coords):
				res = icecraft.IcecraftRepGen.get_colbufctrl_config(coords)
				self.assertEqual(exp, res)
	
	def generate_src_grps_test_cases(self, x, y):
		class SrcGrpsTestData(NamedTuple):
			desc: str # description
			con_items: Iterable[ConnectionItem] = [] # connection config items
			used_func: Callable[[NetRelation], bool] = lambda x: True # used function
			unavails: List[int] = [] # indices of unavailable nets
			exp_bits: Tuple[IcecraftBitPosition, ...] = tuple() # expected bits
			exp_allele_values: Tuple[Tuple[bool, ...], ...] = tuple() # expected allele values
			exp_excep: Union[Exception, None] = None # expected exception
		
		bit_pos = IcecraftBitPosition.from_coords
		
		net_data_list = [NetData(((x, y, f"src_{i}"), ), True, (0,)) for i in range(4)]
		net_data_list.extend([NetData(((x+1, y, f"src_{i+4}"), ), True, (0,)) for i in range(4)])
		net_data_list.append(NetData(((x, y, "dst"), (x+1, y, "dst")), False, (0, 1)))
		tile_items = [
			ConnectionItem(
				(bit_pos(x, y, 7, 0), bit_pos(x, y, 7, 1)),
				"connection", "dst", ((True, False), (True, True)), ("src_0", "src_1")
			),
			ConnectionItem(
				(bit_pos(x, y, 3, 0), bit_pos(x, y, 3, 1)),
				"connection", "dst", ((False, True), (True, False)), ("src_2", "src_3")
			),
		]
		other_items = [
			ConnectionItem(
				(bit_pos(x+1, y, 7, 0), bit_pos(x+1, y, 7, 1)),
				"connection", "dst", ((True, False), (True, True)), ("src_4", "src_5")
			),
			ConnectionItem(
				(bit_pos(x+1, y, 3, 0), bit_pos(x+1, y, 3, 1)),
				"connection", "dst", ((False, True), (True, False)), ("src_6", "src_7")
			),
		]
		test_cases = (
			SrcGrpsTestData(
				"single source group",
				tile_items[:1],
				exp_bits = tile_items[0].bits,
				exp_allele_values = ((False, False), (True, False), (True, True)),
			),
			SrcGrpsTestData(
				"multiple source groups, single tile",
				tile_items[:2],
				exp_bits = tile_items[0].bits+tile_items[1].bits,
				exp_allele_values = (
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, False, False, False),
					(True, True, False, False)
				),
			),
			SrcGrpsTestData(
				"multiple source groups, multiple tiles",
				tile_items[:1]+other_items[1:2],
				exp_bits = tile_items[0].bits+other_items[1].bits,
				exp_allele_values = (
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, False, False, False),
					(True, True, False, False)
				),
			),
			SrcGrpsTestData(
				"no source group",
				exp_excep = ValueError
			),
			SrcGrpsTestData(
				"used function",
				tile_items[:2],
				lambda x: "src_0" not in [n for _, _, n in x.segment],
				exp_bits = tile_items[0].bits+tile_items[1].bits,
				exp_allele_values = (
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, True, False, False)
				),
			),
			SrcGrpsTestData(
				"not available",
				tile_items[:2],
				unavails = [1],
				exp_bits = tile_items[0].bits+tile_items[1].bits,
				exp_allele_values = (
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, False, False, False)
				),
			),
			SrcGrpsTestData(
				"none available",
				tile_items[:2],
				lambda x: int(x.segment[0][2][-1])%2 != 0,
				[1, 3],
				tile_items[0].bits+tile_items[1].bits,
				((False, False, False, False), ),
			),
		)
		
		return net_data_list, test_cases
	
	def test_alleles_from_src_grps(self):
		x = 2
		y = 3
		net_data_list, test_cases = self.generate_src_grps_test_cases(x, y)
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				net_relations = NetRelation.from_net_data_iter(net_data_list, [(x, y)])
				net_map = NetRelation.create_net_map(net_relations)
				src_grps = SourceGroup.populate_net_relations(net_map, tc.con_items)
				
				for i in tc.unavails:
					net_relations[i].available = False
				
				if tc.exp_excep is None:
					bits, alleles = icecraft.IcecraftRepGen.alleles_from_src_grps(src_grps, tc.used_func)
					allele_values = tuple(a.values for a in alleles)
					
					self.assertEqual(tc.exp_bits, bits)
					self.assertEqual(set(tc.exp_allele_values), set(allele_values), "Wrong alleles")
					self.assertEqual(tc.exp_allele_values, allele_values, "Wrong allele order")
				else:
					self.assertRaises(tc.exp_excep, icecraft.IcecraftRepGen.alleles_from_src_grps, src_grps, tc.used_func)
	
	def test_create_unused_gene(self):
		x = 2
		y = 3
		net_data_list, test_cases = self.generate_src_grps_test_cases(x, y)
		
		for tc in test_cases:
				net_relations = NetRelation.from_net_data_iter(net_data_list, [(x, y)])
				net_map = NetRelation.create_net_map(net_relations)
				src_grps = SourceGroup.populate_net_relations(net_map, tc.con_items)
				
				if tc.exp_excep is None:
					res = icecraft.IcecraftRepGen.create_unused_gene(src_grps)
					
					self.assertEqual(tc.exp_bits, res.bit_positions)
					self.assertEqual(1, len(res.alleles))
					self.assertFalse(any(res.alleles[0].values), "All allele values have to be False")
				else:
					self.assertRaises(tc.exp_excep, icecraft.IcecraftRepGen.create_unused_gene, src_grps)
			
	
	def test_create_unused_gene_from_net(self):
		x = 5
		y = 4
		
		net_data_list, test_cases = self.generate_src_grps_test_cases(x, y)
		
		for tc in test_cases:
				net_relations = NetRelation.from_net_data_iter(net_data_list, [(x, y)])
				net_map = NetRelation.create_net_map(net_relations)
				src_grps = SourceGroup.populate_net_relations(net_map, tc.con_items)
				
				dst_net = [n for n in net_relations if n.segment[0][2]=="dst"][0]
				
				if tc.exp_excep is None:
					res = icecraft.IcecraftRepGen.create_unused_gene_from_net(dst_net)
					
					self.assertEqual(tc.exp_bits, res.bit_positions)
					self.assertEqual(1, len(res.alleles))
					self.assertFalse(any(res.alleles[0].values), "All allele values have to be False")
				else:
					self.assertRaises(tc.exp_excep, icecraft.IcecraftRepGen.create_unused_gene_from_net, dst_net)
	
	def generic_carry_in_net_test(self, exp_map, exp_nets, config_map, raw_nets):
		in_map = copy.deepcopy(config_map)
		in_nets = list(raw_nets)
		
		icecraft.IcecraftRepGen.carry_in_set_net(in_map, in_nets)
		
		self.assertEqual(exp_map, in_map)
		self.assertEqual(exp_nets, in_nets)
	
	def test_carry_in_set_net(self):
		one_cis_pos = (4, 2)
		no_cis_pos = (8, 3)
		in_nets = list(self.raw_nets)
		
		# create config map from connection config
		in_map = {}
		for con_item in self.raw_configs:
			tile_configs = in_map.setdefault(con_item.bits[0].tile, {"connection": tuple()})
			tile_configs["connection"] += (con_item, )
		for x, y in (one_cis_pos, no_cis_pos):
			in_map[(x, y)]["tile"] = (ConfigItem((IcecraftBitPosition.from_coords(x, y, 0, 2), ), "NegClk"), )
		
		exp_map = copy.deepcopy(in_map)
		in_map[one_cis_pos]["tile"] += (ConfigItem((IcecraftBitPosition.from_coords(*one_cis_pos, 1, 50), ), "CarryInSet"), )
		
		exp_map[one_cis_pos]["connection"] += (ConnectionItem(
			(IcecraftBitPosition.from_coords(*one_cis_pos, 1, 50), ),
			"connection", "carry_in_mux", ((True, ), ), (icecraft.representation.CARRY_ONE_IN, )
		), )
		
		exp_nets = list(in_nets)
		exp_nets.append(NetData(((*one_cis_pos, icecraft.representation.CARRY_ONE_IN), ), True, (0, )))
		
		with self.subTest(desc="no and one CarryInSet items and map entries without 'tile' key"):
			self.generic_carry_in_net_test(exp_map, exp_nets, in_map, in_nets)
		
		with self.subTest(desc="two CarryInSet items"):
			in_map[one_cis_pos]["tile"] += (ConfigItem((IcecraftBitPosition.from_coords(*one_cis_pos, 1, 51), ), "CarryInSet"), )
			with self.assertRaises(ValueError):
				self.generic_carry_in_net_test(exp_map, exp_nets, in_map, in_nets)
	
	def create_bits(self, x:int , y: int, bit_coords: Iterable[Tuple[int, int]]) -> Tuple[IcecraftBitPosition, ...]:
		return tuple(IcecraftBitPosition.from_coords(x, y, g, i) for g, i in bit_coords)
	
	def transform_to_type(self, raw_data, type_hint):
		from typing import get_type_hints
		
		if hasattr(type_hint, "__origin__"):
			# from typing
			org = type_hint.__origin__
			args = type_hint.__args__
			
			if org == tuple:
				if len(args) == 0:
					return tuple(raw_data)
				
				if len(args) == 2 and args[1] == Ellipsis:
					sub_types = [args[0]]*len(raw_data)
				else:
					sub_types = args
				
				data = []
				for raw, sub in zip(raw_data, sub_types):
					sub_data = self.transform_to_type(raw, sub)
					data.append(sub_data)
				return tuple(data)
			elif org == list:
				if len(args) == 0:
					return list(raw_data)
				
				sub_type = args[0]
				data = []
				for raw in raw_data:
					sub_data = self.transform_to_type(raw, sub_type)
					data.append(sub_data)
				return data
			else:
				raise ValueError(f"Unsupported typing class {type_hint}")
		else:
			sub_types = get_type_hints(type_hint).values()
			
			if len(sub_types) == 0:
				return type_hint(raw_data)
			
			assert len(raw_data) == len(sub_types)
			data = []
			for raw, sub in zip(raw_data, sub_types):
				sub_data = self.transform_to_type(raw, sub)
				data.append(sub_data)
			
			return type_hint(*data)
		
		return None
	
	def compare_allele_seq(self, seq_a, seq_b):
		if seq_a == seq_b:
			return Comparison.IDENTICAL
		
		if len(seq_a) == len(seq_b):
			if set(seq_a) == set(seq_b):
				for a, b in zip(seq_a, seq_b):
					if a != b:
						return Comparison.DISORDERED
				return Comparison.EQUIVALENT
		
		return Comparison.DIFFERENT
	
	@unittest.skip("creates wrong fails")
	def test_create_genes_prev(self):
		# test create_genes with stored results from previous implementation
		class PrevGeneData(NamedTuple):
			tile: Tuple[int, int]
			bits: Tuple[Tuple[int, int], ...]
			values: List[Tuple[bool, ...]]
		
		class GeneData(NamedTuple):
			bits: Tuple[IcecraftBitPosition, ...]
			values: List[Tuple[bool, ...]]
			
			def val_list(self):
				if self.values != []:
					return self.values
				
				return list(itertools.product((False, True), repeat=len(self.bits)))
		
		class MappingCase(NamedTuple):
			x_min: int
			y_min: int
			x_max: int
			y_max: int
			exclude_nets: List[Tuple[str, str]]
			include_nets: List[Tuple[str, str]]
			output_lutffs: List[Tuple[int, int, int]]
			joint_input_nets: List[str]
			lone_input_nets: List[Tuple[int, int, str]]
			lut_functions: List[str]
			genes: List[PrevGeneData]
			const_genes: List[PrevGeneData]
			colbufctrl: List[Tuple[int, int, int]]
		
		def gene_to_data(gene):
			if isinstance(gene.alleles, AlleleAll) or (isinstance(gene.alleles, AllelePow) and len(gene.alleles._unused) == 0):
				values = []
			else:
				if len(gene.alleles) > 1000:
					raise Exception(f"{len(gene.alleles)} alleles in {type(gene.alleles)}")
				values = [a.values for a in gene.alleles]
			
			return GeneData(gene.bit_positions, values)
		
		def prev_to_data(prev_gene_data):
			bits = self.create_bits(*prev_gene_data.tile, prev_gene_data.bits)
			return GeneData(bits, prev_gene_data.values)
		
		def gen_bit_dict(gene_iter):
			bit_dict = {b: g for g in gene_iter for b in g.bits}
			return bit_dict
		
		def bits_to_str(bits):
			parts = [f"B{b.group}[{b.index}]@({b.x}, {b.y})" for b in bits]
			return f"({', '.join(parts)})"
		
		def sub_values(bits, gene_data):
			indices = [gene_data.bits.index(b) for b in bits]
			values = [tuple(v[i] for i in indices) for v in gene_data.values]
			return values
		
		class MissingComp(NamedTuple):
			gene: GeneData
			missing: List[IcecraftBitPosition] = []
		
		class DiffValueComp(NamedTuple):
			bits: Tuple[IcecraftBitPosition, ...]
			missing: List[Tuple[bool, ...]] = []
			additional: List[Tuple[bool, ...]] = []
			
			@classmethod
			def from_sets(cls, bits, value_set, ref_set):
				return cls(bits, sorted(ref_set-value_set), sorted(value_set-ref_set))
			
			@classmethod
			def from_iters(cls, bits, value_iter, ref_iter):
				return cls.from_sets(bits, set(value_iter), set(ref_iter))
		
		@dataclass
		class GeneComp:
			identical: List[Tuple[IcecraftBitPosition, ...]] = field(default_factory=list)
			subset: Dict[Tuple[IcecraftBitPosition, ...], DiffValueComp] = field(default_factory=dict)
			reordered_bits: Dict[Tuple[IcecraftBitPosition, ...], Tuple[IcecraftBitPosition, ...]] = field(default_factory=dict)
			reordered_values: List[Tuple[IcecraftBitPosition, ...]] = field(default_factory=list)
			different_values: Dict[Tuple[IcecraftBitPosition, ...], DiffValueComp] = field(default_factory=dict)
			partial: Dict[Tuple[IcecraftBitPosition, ...], Tuple[IcecraftBitPosition, ...]] = field(default_factory=dict)
			missing: Dict[IcecraftBitPosition, MissingComp] = field(default_factory=dict)
		
		def compare_genes(gene_data, gene_dict):
			"""compare iterable of a group of GeneData to dict based on another group of GeneData
			
			the first group is seen as "expected" and the second group as to be tested
			e.g. if a gene is in the first group, but not in the second, it is missing
			if a value is not in the first group, but in the second it is additional
			
			compare_genes(a, gen_bit_dict(b)) -> compare_genes(b, gen_bit_dict(a))
			identical -> identical
			subset -> missing or partial
			reordered_bits -> reordered_bits
			reordered_values -> reordered_values
			different_values.missing -> different_values.additional
			different_values.additional -> different_values.missing
			partial -> subset or missing
			missing -> nothing (all bits of gene missing), partial or subset
			"""
			comp_res = GeneComp()
			for r in gene_data:
				#if r not in gene_res_data:
				#	print(f"-: {r[:2]} {str(r[2])[:400]}")
				bit_set = set(r.bits)
				missing_bits = []
				img_genes = []
				while len(bit_set) > 0:
					bit = bit_set.pop()
					try:
						img = gene_dict[bit]
					except KeyError:
						missing_bits.append(bit)
						continue
					
					img_genes.append(img)
					
					bit_set.difference_update(img.bits)
				
				if len(missing_bits) == 0 and len(img_genes) == 1:
					img = img_genes[0]
					if len(img.bits) > len(r.bits):
						#print(f"*{bits_to_str(r.bits)}: subset of {bits_to_str(img.bits)}")
						comp_res.subset[r.bits] = DiffValueComp.from_iters(img.bits, r.val_list(), sub_values(r.bits, img))
					elif img.bits != r.bits:
						#print("f*{bits_to_str(r.bits)}: reordered bits")
						#TODO: take a look at the values
						comp_res.reordered_bits[r.bits] = img.bits
					elif r.values != img.values:
						r_set = set(r.val_list())
						img_set = set(img.val_list())
						if r_set == img_set:
							#print(f"*{bits_to_str(r.bits)}: value order differs")
							comp_res.reordered_values.append(r.bits)
						else:
							#print(f"*{bits_to_str(r.bits)}: values differ ({len(r.values)})")
							#print(f"\t*{len(r_set-img_set)} missing, {len(img_set-r_set)} additional: {str(img_set-r_set)[:100]}")
							comp_res.different_values[r.bits] = DiffValueComp(r.bits, list(r_set-img_set), list(img_set-r_set))
					else:
						comp_res.identical.append(r.bits)
				else:
					#print(f"*{bits_to_str(r.bits)}:")
					#if len(missing_bits) > 0:
					#	print(f"\t-{bits_to_str(sorted(missing_bits))}: bits not found")
					mc = MissingComp(r, missing_bits)
					for mb in missing_bits:
						comp_res.missing[mb] = mc
					
					for img in img_genes:
						img_bits = set(r.bits) & set(img.bits)
						#print(f"\t*{bits_to_str(sorted(img_bits))}: represented in {bits_to_str(img.bits)}")
						comp_res.partial[tuple(img_bits)] = r.bits
			
			return comp_res
		
		import json
		import os
		from pprint import pprint
		
		json_path = os.path.join(os.path.dirname(__file__), "mapping_creation.json")
		with open(json_path, "r") as json_file:
			raw_data = json.load(json_file)
			#print(raw_data)
			#print(get_type_hints(MappingCase))
			data = self.transform_to_type(raw_data, List[MappingCase])
			#print(data)
		
		for i, mc in enumerate(data):#[1:2]):
			with self.subTest(desc=f"mapping case {i}"):
				tiles = icecraft.IcecraftRepGen.tiles_from_rectangle(mc.x_min, mc.y_min, mc.x_max, mc.y_max)
				
				config_map = {t: get_config_items(t) for t in tiles}
				
				raw_nets = get_net_data(tiles)
				icecraft.IcecraftRepGen.carry_in_set_net(config_map, raw_nets)
				
				net_relations = NetRelation.from_net_data_iter(raw_nets, tiles)
				net_map = NetRelation.create_net_map(net_relations)
				con_items = []
				for ci in config_map.values():
					try:
						tile_cons = ci["connection"]
					except KeyError:
						continue
					con_items.extend(tile_cons)
				SourceGroup.populate_net_relations(net_map, con_items)
				
				req = RequestObject()
				req["x_min"] = mc.x_min
				req["y_min"] = mc.y_min
				req["x_max"] = mc.x_max
				req["y_max"] = mc.y_max
				req["exclude_nets"] = [n for n, _ in mc.exclude_nets]
				req["include_nets"] = [n for n, _ in mc.include_nets]
				req["output_lutffs"] = [icecraft.IcecraftLUTPosition.from_coords(*c) for c in mc.output_lutffs]
				req["joint_input_nets"] = mc.joint_input_nets
				req["lone_input_nets"] = [IcecraftNetPosition.from_coords(*c) for c in mc.lone_input_nets]
				req["lut_functions"] = [icecraft.LUTFunction[n] for n in mc.lut_functions]
				icecraft.IcecraftRepGen._choose_nets(net_relations, net_map, req)
				
				#print(req)
				print(f"available: {sum([n.available for n in net_relations])}")
				#pprint(config_map)
				
				#pdb.set_trace()
				const_res, gene_res, sec_res = icecraft.IcecraftRepGen.create_genes(
					net_relations,
					config_map,
					lambda _: True,
					req.lut_functions,
					net_map
				)
				#pdb.set_trace()
				const_exp_data = [prev_to_data(g) for g in mc.const_genes]
				gene_exp_data = [prev_to_data(g) for g in mc.genes]
				
				exp_gene_dict = gen_bit_dict(const_exp_data)
				exp_gene_dict.update(gen_bit_dict(gene_exp_data))
				
				const_res_data = [gene_to_data(g) for g in const_res]
				#self.assertEqual(mc.const_genes, const_res_data)
				
				gene_res_data = [gene_to_data(g) for g in gene_res]
				#self.assertEqual(sorted(mc.genes), sorted(gene_res_data))
				
				res_gene_dict = gen_bit_dict(const_res_data)
				res_gene_dict.update(gen_bit_dict(gene_res_data))
				
				#print("expected genes in results")
				exp_to_res = compare_genes(gene_exp_data, res_gene_dict)
				
				#print("result genes in expected")
				res_to_exp = compare_genes(gene_res_data, exp_gene_dict)
				
				for bit, mc in res_to_exp.missing.items():
					values = set(sub_values([bit], mc.gene))
					if values != set([(False, )]):
						self.fail(f"Additional meaningful bit: {bit}")
				
				if len(exp_to_res.missing) > 0:
					self.fail(f"{len(exp_to_res.missing)} bits missing in result: {bits_to_str(exp_to_res.missing.keys())}")
				
				for diff in exp_to_res.different_values.values():
					gene = exp_gene_dict[diff.bits[0]]
					# known cases
					raw_bits = tuple((b.group, b.index) for b in diff.bits)
					if (raw_bits, diff.missing, diff.additional) in [
						# the previous implementation automatically cascaded the unused property
						# still there may have been a bug that excludes glb2local_0 despite an global input net available
						(((2, 14), (3, 14), (3, 15), (3, 16), (3, 17)), [], [(False, False, False, False, True)]), # glb2local_0 -> local_g0_4
						(((2, 15), (2, 16), (2, 17), (2, 18), (3, 18)), [], [(False, False, True, False, False)]), # glb2local_1 -> local_g0_5
						(((2, 25), (3, 22), (3, 23), (3, 24), (3, 25)), [], [(False, True, False, False, False)]), # glb2local_2 -> local_g0_6
						(((2, 21), (2, 22), (2, 23), (2, 24), (3, 21)), [], [(False, True, False, False, False)]), # glb2local_3 -> local_g0_7
					]:
						continue
					self.fail(f"{bits_to_str(diff.bits)} values differ:\n\t{len(diff.missing)} missing: {diff.missing}\n\t{len(diff.additional)} additional: {diff.additional}\n\t\t{gene.values}\n\t\t{req}")
				
				#self.assertEqual(len(mc.genes), len(gene_res_data))
	
	def test_create_genes(self):
		class GeneTestCase(NamedTuple):
			desc: str
			net_rels: Iterable[NetRelation] = []
			config_map: Mapping[TilePosition, ConfigDictType] = {}
			used_function: Callable[[NetRelation], bool] = lambda x: True
			lut_functions: Iterable[LUTFunction] = []
			exp_const: List[Gene] = []
			exp_genes: List[Gene] = []
			exp_sec: List[int] = []
		
		
		test_cases = []
		
		# carry in set and carry mux
		tile = TilePosition(26, 19)
		net_rels = NetRelation.from_net_data_iter(
			[
				NetData(((*tile, "carry_in_mux"),), False, (0, )),
				NetData(((tile.x, tile.y-1, "lutff_7/cout"), (*tile, "carry_in")), True, (0, )),
				NetData(((*tile, icecraft.representation.CARRY_ONE_IN),), True, (0, )),
			],
			[tile]
		)
		ci_bits = self.create_bits(*tile, [(1, 49)])
		one_bits = self.create_bits(*tile, [(1, 50)])
		con_items = [
			ConnectionItem(ci_bits, "connection", "carry_in_mux", ((True, ), ), ("carry_in", )),
			ConnectionItem(one_bits, "connection", "carry_in_mux", ((True, ), ), (icecraft.representation.CARRY_ONE_IN, )),
		]
		net_map = NetRelation.create_net_map(net_rels)
		src_grps = SourceGroup.populate_net_relations(net_map, con_items)
		ec = GeneTestCase(
			"carry mux",
			net_rels,
			{tile: {"connection": tuple(con_items)}},
			exp_genes = [
				Gene(tuple(ci_bits+one_bits), AlleleList([Allele(v, "") for v in ((False, False), (False, True), (True, False))]), "")
			],
			exp_sec = [1]
		)
		test_cases.append(ec)
		
		# glb2local_1 -> local_g0_5
		(((2, 15), (2, 16), (2, 17), (2, 18), (3, 18)), [], [(False, False, True, False, False)]),
		net_rels = NetRelation.from_net_data_iter([
			NetData(((*tile, "glb2local_1"), ), False, (0, )),
			NetData(((*tile, "local_g0_5"), ), False, (0, )),
		], [tile])
		bits = self.create_bits(*tile, [(2, 15), (2, 16), (2, 17), (2, 18), (3, 18)])
		con_items = [ConnectionItem(bits, "connection", "local_g0_5", ((False, False, True, False, False), ), ("glb2local_1", )),]
		net_map = NetRelation.create_net_map(net_rels)
		src_grps = SourceGroup.populate_net_relations(net_map, con_items)
		ec = GeneTestCase(
			"glb2local_1 -> local_g0_5",
			net_rels,
			{tile: {"connection": tuple(con_items)}},
			exp_genes = [
				Gene(bits, AlleleList([Allele(v, "") for v in ((False, False, False, False, False), (False, False, True, False, False))]), "")
			],
			exp_sec = [1]
		)
		test_cases.append(ec)
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				net_map = NetRelation.create_net_map(tc.net_rels)
				#pdb.set_trace()
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_genes(tc.net_rels, tc.config_map, tc.used_function, tc.lut_functions, net_map)
				
				self.assertEqual(tc.exp_const, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
	
	def test_create_genes_tile_cases(self):
		# test cases for single tile nets also have to work for more general create_genes function
		st_test_cases = self.generate_tile_genes_test_cases()
		st_exception_cases = self.generate_tile_genes_fail_test_cases()
		
		for tc in st_test_cases:
			with self.subTest(desc=f"single tile case: {tc.desc}"):
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_genes(tc.single_tile_nets, tc.config_map, tc.used_function, tc.lut_functions)
				
				self.assertEqual(tc.exp_const, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
		for tc in st_exception_cases:
			if not tc.general:
				continue
			with self.subTest(desc=f"single tile exception case: {tc.desc}"):
				with self.assertRaises(tc.excep):
					icecraft.IcecraftRepGen.create_genes(tc.single_tile_nets, tc.config_map, tc.used_function, tc.lut_functions)
	
	def generate_tile_genes_test_cases(self):
		class TileGenesTestData(NamedTuple):
			desc: str
			single_tile_nets: Iterable[NetRelation] = []
			config_map: Mapping[TilePosition, ConfigDictType] = {}
			used_function: Callable[[NetRelation], bool] = lambda x: True
			lut_functions: Iterable[LUTFunction] = []
			exp_const: List[Gene] = []
			exp_genes: List[Gene] = []
			exp_sec: List[int] = []
		
		test_cases = []
		
		ec = TileGenesTestData(
			"NegClk",
			config_map = {
				TilePosition(4, 2): {"tile": (ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), "NegClk"), )},
				TilePosition(4, 3): {},
			},
			exp_genes = [Gene((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), AlleleAll(1), "")],
			exp_sec = [1]
		)
		test_cases.append(ec)
		
		# LUT test cases
		lut_in_unused = ([], [1], [3], [1, 2], [0, 3], [0, 1, 2], [0, 1, 3], [0, 1, 2, 3])
		def lut_in_profile(net):
			res = re.match(r"lutff_(\d)/in_(\d)", net.segment[0][2])
			if res is None:
				return True
			
			l = int(res.group(1))
			i = int(res.group(2))
			
			if i in lut_in_unused[l]:
				return False
			else:
				return True
		
		# corresponding to cases in lut_in_unused
		truth_tables_enum = [
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True),
				(False, True, True, False, True, False, False, True, True, False, False, True, False, True, True, False),
				(False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
				(True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, True),
				(False, True, False, True, True, False, True, False, True, False, True, False, False, True, False, True),
				(False, True, False, True, True, True, True, True, True, True, True, True, True, True, True, True),
				(True, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, False, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, True),
				(False, True, True, False, True, False, False, True, False, True, True, False, True, False, False, True),
				(False, True, True, True, True, True, True, True, False, True, True, True, True, True, True, True),
				(True, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, False, True, True, True, True, True, True, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, False, False, True, False, True, False, True, False, True),
				(False, True, False, True, False, True, False, True, True, False, True, False, True, False, True, False),
				(False, True, False, True, False, True, False, True, True, True, True, True, True, True, True, True),
				(True, False, True, False, True, False, True, False, False, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, True, True, False, True, False, True, False, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, True, True, False, False, False, False, False, False, True, True),
				(False, False, True, True, True, True, False, False, False, False, True, True, True, True, False, False),
				(False, False, True, True, True, True, True, True, False, False, True, True, True, True, True, True),
				(True, True, False, False, False, False, False, False, True, True, False, False, False, False, False, False),
				(True, True, True, True, True, True, False, False, True, True, True, True, True, True, False, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0
				(False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True), # AND, OR, PARITY
				(True, True, True, True, True, True, True, True, False, False, False, False, False, False, False, False), # NAND, NOR
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0
				(False, False, False, False, True, True, True, True, False, False, False, False, True, True, True, True), # AND, OR, PARITY
				(True, True, True, True, False, False, False, False, True, True, True, True, False, False, False, False), # NAND, NOR
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0, OR, NAND, PARITY
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1, AND, NOR
			),
		]
		
		lut_conf = []
		exp_genes_no = []
		exp_genes_enum = []
		lut_kinds = ('CarryEnable', 'DffEnable', 'Set_NoReset', 'AsyncSetReset', 'TruthTable')
		for l in range(8):
			raw_bits_list = [
				((0+2*l, 44),),
				((0+2*l, 45),),
				((1+2*l, 44),),
				((1+2*l, 45),),
				(
					(0+2*l, 40), (1+2*l, 40), (1+2*l, 41), (0+2*l, 41),
					(0+2*l, 42), (1+2*l, 42), (1+2*l, 43), (0+2*l, 43),
					(0+2*l, 39), (1+2*l, 39), (1+2*l, 38), (0+2*l, 38),
					(0+2*l, 37), (1+2*l, 37), (1+2*l, 36), (0+2*l, 36)
				)
			]
			bits_list = [self.create_bits(2, 3, r) for r in raw_bits_list]
			lut_conf.append(tuple(IndexedItem(b, k, l) for b, k in zip(bits_list, lut_kinds)))
			# CarryEnable should not be put in a gene
			# DffEnable, Set_NoReset, AsyncSetReset
			other = [Gene(b, AlleleAll(1), "") for b in bits_list[1:4]]
			exp_genes_no.extend(other)
			exp_genes_enum.extend(other)
			# TruthTable
			exp_genes_no.append(Gene(bits_list[4], AllelePow(4, lut_in_unused[l]), ""))
			exp_genes_enum.append(Gene(bits_list[4], AlleleList([Allele(v, "") for v in truth_tables_enum[l]]), ""))
		
		single_tile_nets = NetRelation.from_net_data_iter([
			NetData(((2, 3, f"lutff_{l}/in_{i}"), ), False, (0, )) for l in range(8) for i in range(4)
		], [(2, 3)])
		config_map = {
			TilePosition(2, 3): {"lut": tuple(lut_conf)},
			TilePosition(4, 3): {},
		}
		
		ec = TileGenesTestData(
			"LUT, no function restriction",
			single_tile_nets = single_tile_nets, 
			config_map = config_map,
			used_function = lut_in_profile,
			lut_functions = [],
			exp_genes = exp_genes_no,
			exp_sec = [32]
		)
		test_cases.append(ec)
		
		ec = TileGenesTestData(
			"LUT, function restricted",
			single_tile_nets = single_tile_nets, 
			config_map = config_map,
			used_function = lut_in_profile,
			lut_functions = list(LUTFunction),
			exp_genes = exp_genes_enum,
			exp_sec = [32]
		)
		test_cases.append(ec)
		
		
		org_tile = TilePosition(2, 3)
		def org_name(n):
			# find name of net in org_tile
			for x, y, name in n.segment:
				if org_tile.x == x and org_tile.y == y:
					return name
			raise ValueError("no name in original tile")
		
		net_data_list = []
		net_names = ("unavail", "no_src_grps", "one_src", "one_src_grp", "two_src_grps", "unused")
		for i in range(2):
			net_data_list.extend(NetData(((*org_tile, f"{n}_{i}"), ), False, (0, )) for n in net_names[:3])
			net_data_list.extend(NetData(((1, 1, f"other_{n}_{i}"), (*org_tile, f"{n}_{i}")), False, (1, )) for n in net_names[3:4])
			net_data_list.extend(NetData(((*org_tile, f"{n}_{i}"), ), False, (0, )) for n in net_names[4:])
			# external
			net_data_list.append(NetData(((*org_tile, f"external_{i}"), (3, 4, f"external_{i}")), False, (0, 1)))
			# hard driven
			net_data_list.append(NetData(((*org_tile, f"hard_driven_{i}"), ), True, (0, )))
		
		offset = len(net_data_list)//2
		net_rels = NetRelation.from_net_data_iter(net_data_list, [org_tile])
		net_rels[0].available = False
		net_rels[offset].available = False
		dst_nets = {org_name(n)[:-2]: n for n in net_rels[:offset]}
		src_nets = {org_name(n)[:-2]: n for n in net_rels[offset:]}
		single_nets = [n for n in net_rels if not n.segment[0][2].startswith("external")]
		
		gene_data = []
		# bits, dst_name, srcs, del_indices, conf_lengths
		# a tuple describes the data to construct a gene and the original connection item
		# del_indices define indices of srcs that will not be included in the gene
		# conf_lengths define which parts of the bits are included in one connection item
		class RawGene(NamedTuple):
			raw_bits: List[Tuple[int, int]]
			dst_label: str
			src_list: List[Tuple[Tuple[bool, ...], str]]
			del_indices: List[int]
			conf_lengths: List[int]
			create_gene: bool = True
		
		one_src_grp = [
			((False, True), "hard_driven"),
			((True, False), "external"),
			((True, True), "unavail"),
		]
		two_src_grps = [
			((False, False, True),  "external"),
			((False, True, False), "unused"),
			((False, True, True), "hard_driven"),
			((True, False, False), "unavail"),
		]
		gene_data.append(RawGene([(0, 6), (0, 7)], "unavail", one_src_grp, [0, 1, 2], [2], False))
		# no RawGene for no_src_grps
		gene_data.append(RawGene([(2, 6)], "one_src", [((True, ), "external")], [], [1]))
		gene_data.append(RawGene([(3, 6), (3, 7)], "one_src_grp", one_src_grp, [2], [2]))
		gene_data.append(RawGene([(4, 0), (4, 5), (4, 6)], "two_src_grps", two_src_grps, [1, 3], [1, 2]))
		gene_data.append(RawGene([(5, 0), (5, 5), (5, 6)], "unused", two_src_grps, [0, 1, 2, 3], [1, 2]))
		gene_data.append(RawGene([(6, 0), (6, 5), (6, 6)], "external", two_src_grps, [0, 1, 2, 3], [1, 2], False))
		# no RawGene for hard_driven
		
		con_items = []
		exp_const = []
		exp_genes = []
		for gd in gene_data:
			all_bits = self.create_bits(*org_tile, gd.raw_bits)
			if gd.create_gene:
				alleles = [Allele((False, )*len(all_bits), "")]
				alleles.extend([Allele(v, "") for i, (v, _) in enumerate(gd.src_list) if i not in gd.del_indices])
				gene = Gene(all_bits, AlleleList(alleles), "")
				
				if len(alleles) > 1:
					exp_genes.append(gene)
				else:
					exp_const.append(gene)
			
			dst_net = dst_nets[gd.dst_label]
			dst_name = org_name(dst_net)
			prev = 0
			for l in gd.conf_lengths:
				part_values_list = []
				part_src_list = []
				part_bits = all_bits[prev:prev+l]
				for values, src_label in gd.src_list:
					part_values = values[prev:prev+l]
					if not any(part_values):
						continue
					
					part_values_list.append(part_values)
					
					src_net = src_nets[src_label]
					src_name = org_name(src_net)
					part_src_list.append(src_name)
				
				con_items.append(ConnectionItem(
					part_bits,
					"connection",
					dst_name,
					tuple(part_values_list),
					tuple(part_src_list)
				))
				
				prev += l
		
		net_map = NetRelation.create_net_map(net_rels)
		src_grps = SourceGroup.populate_net_relations(net_map, con_items)
		self.maxDiff = None
		ec = TileGenesTestData(
			"Single tile nets",
			single_tile_nets = single_nets, 
			config_map = {org_tile: {"connection": tuple(con_items)}},
			used_function = lambda n: not n.segment[0][2].startswith("unused"),
			exp_const = exp_const,
			exp_genes = exp_genes,
			exp_sec = [3]
		)
		test_cases.append(ec)
		
		return test_cases
	
	def generate_tile_genes_fail_test_cases(self):
		class TileGenesErrorTestData(NamedTuple):
			desc: str
			excep: Exception
			single_tile_nets: Iterable[NetRelation] = []
			config_map: Mapping[TilePosition, ConfigDictType] = {}
			used_function: Callable[[NetRelation], bool] = lambda x: True
			lut_functions: Iterable[LUTFunction] = []
			general: bool = True # general error case, i.e. also for create_genes
		
		exception_cases = []
		
		ec = TileGenesErrorTestData(
			"CarryInSet",
			ValueError,
			config_map = {
				TilePosition(4, 2): {"tile": (
					ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), "NegClk"),
					ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 3), ), "CarryInSet"),
				)}
			},
		)
		exception_cases.append(ec)
		
		org_tile = TilePosition(4, 2)
		other_tile = TilePosition(3, 1)
		net_data_list = [
			NetData(((*other_tile, "dst"), (*org_tile, "dst")), False, (0, 1)),
			NetData(((*other_tile, f"src_1"), ), True, (0, )),
			NetData(((*org_tile, f"src_2"), ), True, (0, )),
		]
		org_con = ConnectionItem(
			self.create_bits(*other_tile, [(9, 7), (9, 8)]),
			"connection",
			"dst",
			((True, True), ),
			("src_1", )
		)
		other_con = ConnectionItem(
			self.create_bits(*org_tile, [(4, 5), (4, 6)]),
			"connection",
			"dst",
			((True, True), ),
			("src_2", )
		)
		
		net_rels = NetRelation.from_net_data_iter(net_data_list, [other_tile, org_tile])
		net_map = NetRelation.create_net_map(net_rels)
		src_grps = SourceGroup.populate_net_relations(net_map, [org_con, other_con])
		ec = TileGenesErrorTestData(
			"multitile",
			ValueError,
			net_rels,
			{
				org_tile: {"connection": (org_con, )},
				other_tile: {"connection": (other_con, )}
			},
			general = False
		)
		exception_cases.append(ec)
		
		return exception_cases
	
	def test_create_tile_genes(self):
		test_cases = self.generate_tile_genes_test_cases()
		exception_cases = self.generate_tile_genes_fail_test_cases()
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				net_map = NetRelation.create_net_map(tc.single_tile_nets)
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_tile_genes(tc.single_tile_nets, tc.config_map, tc.used_function, tc.lut_functions, net_map)
				
				self.assertEqual(tc.exp_const, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
		for tc in exception_cases:
			with self.subTest(desc=tc.desc):
				with self.assertRaises(tc.excep):
					net_map = NetRelation.create_net_map(tc.single_tile_nets)
					icecraft.IcecraftRepGen.create_tile_genes(tc.single_tile_nets, tc.config_map, tc.used_function, tc.lut_functions, net_map)
	
	def test_lut_function_to_truth_table(self):
		for func_enum in LUTFunction:
			for in_count in range(5):
				for used_inputs in itertools.combinations(range(4), in_count):
					with self.subTest(func_enum=func_enum, used_inputs=used_inputs):
						truth_table = icecraft.IcecraftRepGen.lut_function_to_truth_table(func_enum, used_inputs)
						for in_values in itertools.product((0, 1), repeat=in_count):
							
							if func_enum == LUTFunction.AND:
								expected = all(in_values)
							elif func_enum == LUTFunction.OR:
								expected = any(in_values)
							elif func_enum == LUTFunction.NAND:
								expected = not all(in_values)
							elif func_enum == LUTFunction.NOR:
								expected = not any(in_values)
							elif func_enum == LUTFunction.PARITY:
								expected = (in_values.count(1) % 2) == 1
							elif func_enum == LUTFunction.CONST_0:
								expected = False
							elif func_enum == LUTFunction.CONST_1:
								expected = True
							else:
								self.error("No test for {}".format(func_enum))
							
							used_index = 0
							for i, shift in zip(in_values, used_inputs):
								used_index |= i << shift
							
							# output should be invariant to value of unused inputs
							unused_inputs = sorted(set(range(4))-set(used_inputs))
							for invariant_values in itertools.product((0, 1), repeat=len(unused_inputs)):
								index = used_index
								for i, shift in zip(invariant_values, unused_inputs):
									index |= i << shift
								
								self.assertEqual(expected, truth_table[index], f"Wrong truth table value {func_enum.name} {used_inputs} for input 0b{index:04b}")
