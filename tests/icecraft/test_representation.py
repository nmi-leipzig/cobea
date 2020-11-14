import unittest
import re
import copy
import itertools
from typing import NamedTuple, Iterable, List, Mapping, Callable, Tuple

import adapters.icecraft as icecraft
from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftColBufCtrl, LUTFunction
from adapters.icecraft.representation import NetRelation, SourceGroup
from domain.request_model import RequestObject
from domain.model import Gene
from domain.allele_sequence import AlleleList, AlleleAll, AllelePow, Allele
from adapters.icecraft.chip_data import ConfigDictType
from adapters.icecraft.chip_data_utils import NetData
from adapters.icecraft.config_item import ConnectionItem, IndexedItem, ConfigItem

from ..test_request_model import check_parameter_user

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
	
	def test_alleles_from_src_grps(self):
		bit_pos = IcecraftBitPosition.from_coords
		x = 2
		y = 3
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
			(
				"single source group", # description
				tile_items[:1], # connection config items
				lambda x: True, # used function
				[], # indices of unavailable nets
				tile_items[0].bits, # expected bits
				((False, False), (True, False), (True, True)), # expected allele values
				None # expected exception
			),
			(
				"multiple source groups, single tile",
				tile_items[:2],
				lambda x: True,
				[],
				tile_items[0].bits+tile_items[1].bits,
				(
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, False, False, False),
					(True, True, False, False)
				),
				None
			),
			(
				"multiple source groups, multiple tiles",
				tile_items[:1]+other_items[1:2],
				lambda x: True,
				[],
				tile_items[0].bits+other_items[1].bits,
				(
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, False, False, False),
					(True, True, False, False)
				),
				None
			),
			(
				"no source group",
				[],
				lambda x: True,
				[],
				tuple(),
				tuple(),
				ValueError
			),
			(
				"used function",
				tile_items[:2],
				lambda x: "src_0" not in [n for _, _, n in x.segment],
				[],
				tile_items[0].bits+tile_items[1].bits,
				(
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, True, False, False)
				),
				None
			),
			(
				"not available",
				tile_items[:2],
				lambda x: True,
				[1],
				tile_items[0].bits+tile_items[1].bits,
				(
					(False, False, False, False), (False, False, False, True),
					(False, False, True, False), (True, False, False, False)
				),
				None
			),
			(
				"none available",
				tile_items[:2],
				lambda x: int(x.segment[0][2][-1])%2 != 0,
				[1, 3],
				tile_items[0].bits+tile_items[1].bits,
				((False, False, False, False), ),
				None
			),
		)
		
		for desc, con_items, used_func, unavails, exp_bits, exp_allele_values, exp_exception in test_cases:
			with self.subTest(desc=desc):
				net_relations = NetRelation.from_net_data_iter(net_data_list, [(x, y)])
				net_map = NetRelation.create_net_map(net_relations)
				src_grps = SourceGroup.populate_net_relations(net_map, con_items)
				
				for i in unavails:
					net_relations[i].available = False
				
				if exp_exception is None:
					bits, alleles = icecraft.IcecraftRepGen.alleles_from_src_grps(src_grps, used_func)
					allele_values = tuple(a.values for a in alleles)
					
					self.assertEqual(exp_bits, bits)
					self.assertEqual(set(exp_allele_values), set(allele_values), "Wrong alleles")
					self.assertEqual(exp_allele_values, allele_values, "Wrong allele order")
				else:
					self.assertRaises(exp_exception, icecraft.IcecraftRepGen.alleles_from_src_grps, src_grps, used_func)
	
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
	
	def test_create_tile_genes(self):
		class TileGenesTestData(NamedTuple):
			desc: str
			single_tile_nets: Iterable[NetRelation] = []
			config_map: Mapping[TilePosition, ConfigDictType] = {}
			used_function: Callable[[NetRelation], bool] = lambda x: True
			lut_functions: Iterable[LUTFunction] = []
			exp_const: List[Gene] = []
			exp_genes: List[Gene] = []
			exp_sec: List[int] = []
		
		class TileGenesErrorTestData(NamedTuple):
			desc: str
			excep: Exception
			single_tile_nets: Iterable[NetRelation] = []
			config_map: Mapping[TilePosition, ConfigDictType] = {}
			used_function: Callable[[NetRelation], bool] = lambda x: True
			lut_functions: Iterable[LUTFunction] = []
		
		test_cases = []
		
		ec = TileGenesTestData(
			"NegClk",
			config_map = {
				(4, 2): {"tile": (ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), "NegClk"), )},
				(4, 3): {},
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
			(2, 3): {"lut": tuple(lut_conf)},
			(4, 3): {},
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
		net_data_list = []
		net_names = ("unavail", "no_src_grps", "one_src", "one_src_grp", "two_src_grps", "unused")
		for i in range(2):
			net_data_list.extend(NetData(((*org_tile, f"{n}_{i}"), ), False, (0, )) for n in net_names)
			# external
			net_data_list.append(NetData(((*org_tile, f"external_{i}"), (3, 4, f"external_{i}")), False, (0, 1)))
			# hard driven
			net_data_list.append(NetData(((*org_tile, f"hard_driven_{i}"), ), True, (0, )))
		
		offset = len(net_data_list)//2
		net_rels = NetRelation.from_net_data_iter(net_data_list, [org_tile])
		net_rels[0].available = False
		net_rels[offset].available = False
		dst_nets = {n.segment[0][2][:-2]: n for n in net_rels[:offset]}
		src_nets = {n.segment[0][2][:-2]: n for n in net_rels[offset:]}
		
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
		gene_data.append(RawGene([(0, 6), (0, 7)], "unavail", one_src_grp, [0, 1, 2], [2]))
		# no RawGene for no_src_grps
		gene_data.append(RawGene([(2, 6)], "one_src", [((True, ), "external")], [], [1]))
		gene_data.append(RawGene([(3, 6), (3, 7)], "one_src_grp", one_src_grp, [2], [2]))
		gene_data.append(RawGene([(4, 0), (4, 5), (4, 6)], "two_src_grps", two_src_grps, [1, 3], [1, 2]))
		gene_data.append(RawGene([(5, 0), (5, 5), (5, 6)], "unused", two_src_grps, [0, 1, 2, 3], [1, 2]))
		gene_data.append(RawGene([(6, 0), (6, 5), (6, 6)], "external", two_src_grps, [0, 1, 2, 3], [1, 2]))
		# no RawGene for hard_driven
		
		con_items = []
		exp_const = []
		exp_genes = []
		for gd in gene_data:
			all_bits = self.create_bits(*org_tile, gd.raw_bits)
			alleles = [Allele((False, )*len(all_bits), "")]
			alleles.extend([Allele(v, "") for i, (v, _) in enumerate(gd.src_list) if i not in gd.del_indices])
			gene = Gene(all_bits, AlleleList(alleles), "")
			
			if len(alleles) > 1:
				exp_genes.append(gene)
			else:
				exp_const.append(gene)
			
			dst_net = dst_nets[gd.dst_label]
			dst_name = dst_net.segment[0][2]
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
					src_name = src_net.segment[0][2]
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
			single_tile_nets = net_rels, 
			config_map = {org_tile: {"con": tuple(con_items)}},
			used_function = lambda n: not n.segment[0][2].startswith("unused"),
			exp_const = exp_const,
			exp_genes = exp_genes,
			exp_sec = [3]
		)
		test_cases.append(ec)
		
		exception_cases = []
		ec = TileGenesErrorTestData(
			"CarryInSet",
			ValueError,
			config_map = {
				(4, 2): {"tile": (
					ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), "NegClk"),
					ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 3), ), "CarryInSet"),
				)}
			},
		)
		exception_cases.append(ec)
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_tile_genes(tc.single_tile_nets, tc.config_map, tc.used_function, tc.lut_functions)
				
				self.assertEqual(tc.exp_const, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
		for tc in exception_cases:
			with self.subTest(desc=tc.desc):
				with self.assertRaises(tc.excep):
					icecraft.IcecraftRepGen.create_tile_genes(tc.single_tile_nets, tc.config_map, tc.used_function, tc.lut_functions)
	
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
