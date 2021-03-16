import unittest
import operator
import copy
import itertools
import re
import pdb

from typing import NamedTuple, Iterable, Mapping, Union, Callable, List, Tuple, Optional
from dataclasses import fields, dataclass

from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftLUTPosition
from adapters.icecraft.inter_rep import InterRep, VertexDesig, EdgeDesig, Edge, SourceGroup, Vertex, ConVertex, LUTVertex, LUTBits
from adapters.icecraft.chip_data import ConfigAssemblage
from adapters.icecraft.chip_data_utils import NetData, ElementInterface, UNCONNECTED_NAME
from adapters.icecraft.config_item import ConnectionItem, IndexedItem
from adapters.icecraft.representation import CARRY_ONE_IN
from adapters.icecraft.misc import LUTFunction, IcecraftSatisfiabilityError
from domain.allele_sequence import AlleleList, AlleleAll, Allele

from .common import create_bits
from .data.chip_resources import NET_DATA, CON_DATA, LUT_DATA, LUT_CON
from .data.lut_data import TRUTH_TABLE

class TestDesignation(unittest.TestCase):
	class VDData(NamedTuple):
		tile: TilePosition
		net_name: Union[str, None]
		lut_index: Union[int, None]
		name: str
		order: int
	
	VERTEX_DESIG_DATA = (
		VDData(TilePosition(4, 1), "net_a", None, "NET#net_a", 2),
		VDData(TilePosition(4, 1), None, 2, "LUT#2", 0),
		VDData(TilePosition(4, 1), "net_b", None, "NET#net_b", 3),
		VDData(TilePosition(4, 1), None, 5, "LUT#5", 1),
	)
	NET_DESIG_DATA = (VERTEX_DESIG_DATA[0], VERTEX_DESIG_DATA[2])
	LUT_DESIG_DATA = (VERTEX_DESIG_DATA[1], VERTEX_DESIG_DATA[3])
	
	# test VertexDesig and EdgeDesig
	def create_vertex_desigs(self):
		vert_desigs = [VertexDesig(d.tile, d.name) for d in self.VERTEX_DESIG_DATA]
		return vert_desigs
	
	def check_vertex_desig(self, vertex_desig, tile, name):
		self.assertEqual(tile, vertex_desig.tile)
		self.assertEqual(name, vertex_desig.name)
	
	def check_edge_desig(self, edge_desig, tile, src_name, dst_name):
		self.check_vertex_desig(edge_desig.src, tile, src_name)
		self.check_vertex_desig(edge_desig.dst, tile, dst_name)
	
	def create_edge_desigs_and_data(self):
		edge_desigs = []
		edge_desig_data = []
		for vdd_1 in self.VERTEX_DESIG_DATA[:2]:
			for vdd_2 in self.VERTEX_DESIG_DATA[2:]:
				edge_desigs.append(EdgeDesig(
					VertexDesig(vdd_1.tile, vdd_1.name),
					VertexDesig(vdd_2.tile, vdd_2.name)
				))
				edge_desig_data.append((vdd_1, vdd_2))
		
		return edge_desigs, edge_desig_data
	
	def test_creation_vertex_desig(self):
		desigs = self.create_vertex_desigs()
		for dut, vdd in zip(desigs, self.VERTEX_DESIG_DATA):
			self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_from_net_name(self):
		for vdd in self.VERTEX_DESIG_DATA:
			if vdd.net_name is None:
				continue
			with self.subTest(test_data=vdd):
				dut = VertexDesig.from_net_name(vdd.tile, vdd.net_name)
				
				self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_from_lut_index(self):
		for vdd in self.VERTEX_DESIG_DATA:
			if vdd.lut_index is None:
				continue
			with self.subTest(test_data=vdd):
				dut = VertexDesig.from_lut_index(vdd.tile, vdd.lut_index)
				
				self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_from_net_position(self):
		for vdd in self.VERTEX_DESIG_DATA:
			if vdd.net_name is None:
				continue
			with self.subTest(test_data=vdd):
				net_pos = IcecraftNetPosition(vdd.tile, vdd.net_name)
				dut = VertexDesig.from_net_position(net_pos)
				
				self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_from_lut_position(self):
		for vdd in self.VERTEX_DESIG_DATA:
			if vdd.lut_index is None:
				continue
			with self.subTest(test_data=vdd):
				lut_pos = IcecraftLUTPosition(vdd.tile, vdd.lut_index)
				dut = VertexDesig.from_lut_position(lut_pos)
				
				self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_from_vertex_position(self):
		for vdd in self.VERTEX_DESIG_DATA:
			with self.subTest(test_data=vdd):
				if vdd.net_name is not None:
					pos = IcecraftNetPosition(vdd.tile, vdd.net_name)
				elif vdd.lut_index is not None:
					pos = IcecraftLUTPosition(vdd.tile, vdd.lut_index)
				else:
					raise ValueError("Invalid test data")
				
				dut = VertexDesig.from_vertex_position(pos)
				
				self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_from_seg_entry(self):
		for vdd in self.VERTEX_DESIG_DATA:
			if vdd.net_name is None:
				continue
			seg = (*vdd.tile, vdd.net_name)
			with self.subTest(seg=seg):
				dut = VertexDesig.from_seg_entry(seg)
				
				self.check_vertex_desig(dut, vdd.tile, vdd.name)
	
	def test_creation_edge_desig(self):
		vert_desigs = self.create_vertex_desigs()
		for vd_1 in vert_desigs[:2]:
			for vd_2 in vert_desigs[2:]:
				with self.subTest(vd_1=vd_1, vd_2=vd_2):
					dut = EdgeDesig(vd_1, vd_2)
					
					self.assertEqual(vd_1, dut.src)
					self.assertEqual(vd_2, dut.dst)
	
	def test_cmp_vertex(self):
		for op in [operator.lt, operator.le, operator.eq, operator.ne, operator.ge, operator.gt]:
			for vdd_1 in self.VERTEX_DESIG_DATA:
				for vdd_2 in self.VERTEX_DESIG_DATA:
					vd_1 = VertexDesig(vdd_1.tile, vdd_1.name)
					vd_2 = VertexDesig(vdd_2.tile, vdd_2.name)
					with self.subTest(vd_1=vd_1, op=op, vd_2=vd_2):
						exp = op(vdd_1.order, vdd_2.order)
						self.assertEqual(exp, op(vd_1, vd_2))
	
	def test_cmp_edge(self):
		edge_desigs, edge_data = self.create_edge_desigs_and_data()
		# (net_a, net_b), (net_a, lut_5), (lut_2, net_b), (lut_2, lut_5)
		for op in [operator.lt, operator.le, operator.eq, operator.ne, operator.ge, operator.gt]:
			for ed_1, edd_1 in zip(edge_desigs, edge_data):
				for ed_2, edd_2 in zip(edge_desigs, edge_data):
					with self.subTest(ed_1=ed_1, op=op, ed_2=ed_2):
						exp = op((edd_1[0].order, edd_1[1].order), (edd_2[0].order, edd_2[1].order))
						self.assertEqual(exp, op(ed_1, ed_2))
	
	def test_edge_post_init_check(self):
		src = VertexDesig.from_seg_entry((4, 1, "net_a"))
		dst = VertexDesig.from_seg_entry((5, 1, "net_b"))
		
		with self.assertRaises(AssertionError):
			EdgeDesig(src, dst)
	
	def test_net_to_net(self):
		src_vdd = self.NET_DESIG_DATA[0]
		dst_vdd = self.NET_DESIG_DATA[1]
		
		dut = EdgeDesig.net_to_net(src_vdd.tile, src_vdd.net_name, dst_vdd.net_name)
		self.check_edge_desig(dut, src_vdd.tile, src_vdd.name, dst_vdd.name)
	
	def test_net_to_lut(self):
		src_vdd = self.NET_DESIG_DATA[0]
		dst_vdd = self.LUT_DESIG_DATA[1]
		
		dut = EdgeDesig.net_to_lut(src_vdd.tile, src_vdd.net_name, dst_vdd.lut_index)
		self.check_edge_desig(dut, src_vdd.tile, src_vdd.name, dst_vdd.name)
	
	def test_lut_to_net(self):
		src_vdd = self.LUT_DESIG_DATA[0]
		dst_vdd = self.NET_DESIG_DATA[1]
		
		dut = EdgeDesig.lut_to_net(src_vdd.tile, src_vdd.lut_index, dst_vdd.net_name)
		self.check_edge_desig(dut, src_vdd.tile, src_vdd.name, dst_vdd.name)

class TestSourceGroup(unittest.TestCase):
	def test_creation(self):
		tile = TilePosition(2, 34)
		bits = (IcecraftBitPosition(tile, 4, 5), )
		dst_desig = VertexDesig.from_net_name(tile, "net_a")
		src_desig = VertexDesig.from_net_name(tile, "net_b")
		edge_desig = EdgeDesig(src_desig, dst_desig)
		dut = SourceGroup(bits, dst_desig, {edge_desig: (True, )})
	
	def test_post_init_checks(self):
		tile = TilePosition(2, 34)
		other_tile = TilePosition(3, 45)
		bits = (IcecraftBitPosition(tile, 4, 5), IcecraftBitPosition(tile, 6, 5))
		dst_desig = VertexDesig.from_net_name(tile, "net_a")
		src_desig_1 = VertexDesig.from_net_name(tile, "net_b")
		src_desig_2 = VertexDesig.from_net_name(tile, "net_c")
		edge_desig_1 = EdgeDesig(src_desig_1, dst_desig)
		edge_desig_2 = EdgeDesig(src_desig_2, dst_desig)
		edge_map = {edge_desig_1: (False, True), edge_desig_2: (True, True)}
		
		with self.subTest(desc="wrong value length"):
			broken_edge_map = {edge_desig_1: (False, True, False), edge_desig_2: (True, True, False)}
			with self.assertRaises(AssertionError):
				dut = SourceGroup(bits, dst_desig, broken_edge_map)
		
		with self.subTest(desc="wrong tile in edge src and dst"):
			other_dst_desig = VertexDesig.from_net_name(other_tile, "net_a")
			other_src_desig_1 = VertexDesig.from_net_name(other_tile, "net_b")
			other_src_desig_2 = VertexDesig.from_net_name(other_tile, "net_c")
			other_edge_desig_1 = EdgeDesig(other_src_desig_1, other_dst_desig)
			other_edge_desig_2 = EdgeDesig(other_src_desig_2, other_dst_desig)
			
			with self.assertRaises(AssertionError):
				dut = SourceGroup(bits, dst_desig, {other_edge_desig_1: (False, True), other_edge_desig_2: (True, True)})
		
		with self.subTest(desc="wrong tile in bits"):
			other_bits = (IcecraftBitPosition(other_tile, 4, 5), IcecraftBitPosition(other_tile, 6, 5))
			
			with self.assertRaises(AssertionError):
				dut = SourceGroup(other_bits, dst_desig, edge_map)

class TestInterRep(unittest.TestCase):
	def add_con_config(self, config_map=None):
		if config_map is None:
			config_map = {}
		
		for con_item in CON_DATA:
			config_assem = config_map.setdefault(con_item.bits[0].tile, ConfigAssemblage())
			config_assem.connection += (con_item, )
		
		return config_map
	
	def add_lut_config(self, config_map=None):
		if config_map is None:
			config_map = {}
		
		tile = LUT_DATA[0][0].bits[0].tile
		config_map.setdefault(tile, ConfigAssemblage()).lut = LUT_DATA
		config_map[tile].lut_io = LUT_CON
		
		return config_map
	
	def test_creation(self):
		class InterRepCreation(NamedTuple):
			desc: str
			net_data: Iterable[NetData]
			config_map: Mapping[TilePosition, ConfigAssemblage]
		
		test_cases = (
			InterRepCreation("no input", [], {}),
			InterRepCreation("initial net data", NET_DATA, {}),
			InterRepCreation("initial net data and LUT config", NET_DATA, self.add_lut_config()),
			InterRepCreation("initial net data and con config", NET_DATA, self.add_con_config()),
			InterRepCreation("initial net data, LUT config and con config", NET_DATA, self.add_con_config(self.add_lut_config())),
		)
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				dut = InterRep(tc.net_data, tc.config_map)
				self.check_consistency(self, dut)
				self.check_initial_data(tc.net_data, tc.config_map, dut)
	
	def check_initial_data(self, net_data_iter, config_map, rep):
		for raw_net in net_data_iter:
			desig = VertexDesig.from_seg_entry(raw_net.segment[0])
			self.assertIn(desig, rep._vertex_map)
			vertex = rep.get_vertex(desig)
			self.check_con_vertex(rep, raw_net, desig, vertex)
		
		all_edge_desigs = set(e.desig for e in rep.iter_edges())
		for tile, config_assem in config_map.items():
			for con_item in config_assem.connection:
				dst_desig = VertexDesig.from_net_name(tile, con_item.dst_net)
				for src_net in con_item.src_nets:
					src_desig = VertexDesig.from_net_name(tile, src_net)
					self.assertIn(EdgeDesig(src_desig, dst_desig), all_edge_desigs)
			
			for lut_grp in config_assem.lut:
				desig = VertexDesig.from_lut_index(tile, lut_grp[0].index)
				self.assertIn(desig, rep._vertex_map)
				vertex = rep.get_vertex(desig)
				
				self.check_lut_vertex(rep, lut_grp, vertex)
			
			for lut_index, single_lut in enumerate(config_assem.lut_io):
				desig = VertexDesig.from_lut_index(tile, lut_index)
				vertex = rep.get_vertex(desig)
				
				in_net_data = set((*e.desig.src.tile, e.desig.src.name[4:]) for e in vertex.iter_in_edges())
				self.assertEqual(set(single_lut.in_nets), in_net_data)
				
				out_net_data = set((*e.desig.dst.tile, e.desig.dst.name[4:]) for e in vertex.iter_out_edges())
				self.assertEqual(set(single_lut.out_nets), out_net_data)
			#TODO: fixed connections
	
	def check_con_vertex(self, rep, raw_net, desig, vertex):
		self.assertIn(desig, vertex.desigs)
		self.assertEqual(set(raw_net.segment), set((*d.tile, d.name[4:]) for d in vertex.desigs))
		self.assertEqual(raw_net.hard_driven, not vertex.configurable)
		self.assertEqual(raw_net.drivers, vertex.drivers)
		self.assertEqual(rep, vertex.rep)
		
		bits = [b for bt in vertex.get_bit_tuples() for b in bt]
		for b in bits:
			res = rep.get_vertex_for_bit(b)
			self.assertEqual(vertex, res)
		
		for desig in vertex.desigs:
			res = rep.get_vertices_of_tile(desig.tile)
			self.assertIn(vertex, res)
	
	def test_get_vertex(self):
		dut = InterRep(NET_DATA, self.add_lut_config())
		
		for raw_net in NET_DATA:
			with self.subTest(raw_net=raw_net):
				for seg in raw_net.segment:
					desig = VertexDesig.from_seg_entry(seg)
					res = dut.get_vertex(desig)
					
					self.check_con_vertex(dut, raw_net, desig, res)
					self.check_consistency(self, dut)
		
		for lut_index, single_lut in enumerate(LUT_DATA):
			with self.subTest(lut_index=lut_index):
				desig = VertexDesig.from_lut_index(single_lut[0].bits[0].tile, lut_index)
				res = dut.get_vertex(desig)
				
				self.check_lut_vertex(dut, single_lut, res)
				self.check_consistency(self, dut)
	
	def check_edge(self, rep, desig, edge):
		self.assertEqual(desig, edge.desig)
		self.assertEqual(rep, edge.rep)
	
	def test_get_edge(self):
		config_map = self.add_con_config(self.add_lut_config())
		dut = InterRep(NET_DATA, config_map)
		
		for tile, config_assem in config_map.items():
			for con_item in config_assem.connection:
				dst_desig = VertexDesig.from_net_name(tile, con_item.dst_net)
				for src_net in con_item.src_nets:
					src_desig = VertexDesig.from_net_name(tile, src_net)
					edge_desig = EdgeDesig(src_desig, dst_desig)
					res = dut.get_edge(edge_desig)
					
					self.check_edge(dut, edge_desig, res)
					self.check_consistency(self, dut)
			
			for lut_index, single_lut in enumerate(config_assem.lut_io):
				lut_desig = VertexDesig.from_lut_index(tile, lut_index)
				
				for raw_net in single_lut.in_nets:
					src_desig = VertexDesig.from_seg_entry(raw_net)
					in_desig = EdgeDesig(src_desig, lut_desig)
					res = dut.get_edge(in_desig)
					
					self.check_edge(dut, in_desig, res)
				
				for raw_net in single_lut.out_nets:
					dst_desig = VertexDesig.from_seg_entry(raw_net)
					out_desig = EdgeDesig(lut_desig, dst_desig)
					res = dut.get_edge(out_desig)
					
					self.check_edge(dut, out_desig, res)
				
	
	def test_add_con_vertex(self):
		dut = InterRep([], {})
		existing_vertices = []
		
		for raw_net in NET_DATA:
			with self.subTest(raw_net=raw_net):
				dut._add_con_vertex(raw_net)
				
				desig = VertexDesig.from_seg_entry(raw_net.segment[0])
				res = dut.get_vertex(desig)
				
				self.check_con_vertex(dut, raw_net, desig, res)
				self.check_consistency(self, dut)
				
				existing_vertices.append(res)
				
				for exp_vtx in existing_vertices:
					res = dut.get_vertex(exp_vtx.desigs[0])
					self.assertEqual(exp_vtx, res)
		
		for raw_net in NET_DATA:
			with self.subTest(desc=f"double adding '{raw_net.segment[0]}'"):
				with self.assertRaises(AssertionError):
					dut._add_con_vertex(raw_net)
		
	
	def check_lut_vertex(self, rep, lut_items, vertex):
		item_dict = {i.kind: i for i in lut_items}
		for kind, res in zip(LUTBits.names, vertex.lut_bits.as_tuple()):
			self.assertEqual(item_dict[kind].bits, res)
		
		tt_item = item_dict["TruthTable"]
		self.assertEqual(tt_item.index, int(vertex.desig.name[4:]))
		self.assertEqual(tt_item.bits[0].tile, vertex.desig.tile)
		self.assertEqual(rep, vertex.rep)
		
		for item in lut_items:
			if item.kind == "CarryEnable":
				continue
			for bit in item.bits:
				res = rep.get_vertex_for_bit(bit)
				self.assertEqual(vertex, res)
		
		res = rep.get_vertices_of_tile(vertex.desig.tile)
		self.assertIn(vertex, res)
	
	def test_add_lut_vertex(self):
		dut = InterRep(NET_DATA, {})
		existing_vertices = []
		
		for lut_items in LUT_DATA:
			with self.subTest(lut_items=lut_items):
				dut._add_lut_vertex(lut_items)
				
				desig = VertexDesig.from_lut_index(lut_items[0].bits[0].tile, lut_items[0].index)
				res = dut.get_vertex(desig)
				
				self.check_lut_vertex(dut, lut_items, res)
				self.check_consistency(self, dut)
		
		for lut_items in LUT_DATA:
			with self.subTest(desc=f"double adding lut_items[0].index"):
				with self.assertRaises(AssertionError):
					dut._add_lut_vertex(lut_items)
	
	def test_carry_in(self):
		tile = TilePosition(26, 19)
		config_map = {}
		net_data_list  = [
			NetData(((*tile, "carry_in_mux"),), False, (0, )),
			NetData(((tile.x, tile.y-1, "lutff_7/cout"), (*tile, "carry_in")), True, (0, )),
			NetData(((*tile, CARRY_ONE_IN),), True, (0, )),
		]
		ci_bits = create_bits(*tile, [(1, 49)])
		one_bits = create_bits(*tile, [(1, 50)])
		config_assem =  config_map.setdefault(tile, ConfigAssemblage())
		config_assem.connection = (
			ConnectionItem(ci_bits, "connection", "carry_in_mux", ((True, ), ), ("carry_in", )),
			ConnectionItem(one_bits, "connection", "carry_in_mux", ((True, ), ), (CARRY_ONE_IN, )),
		)
		
		dut = InterRep(net_data_list, config_map)
		self.check_consistency(self, dut)
		self.check_initial_data(net_data_list, config_map, dut)
		
		one_desig = VertexDesig.from_net_name(tile, CARRY_ONE_IN)
		one_vertex = dut.get_vertex(one_desig)
		self.assertEqual(0, len(list(one_vertex.iter_in_edges())))
		out_edges = list(one_vertex.iter_out_edges())
		self.assertEqual(1, len(out_edges))
		mux_desig = VertexDesig.from_net_name(tile, "carry_in_mux")
		self.assertIn(mux_desig, out_edges[0].dst.desigs)
	
	def test_add_edge(self):
		tile = TilePosition(4, 2)
		dut = InterRep(NET_DATA, {})
		vertices = [Vertex(dut, (VertexDesig.from_net_name(tile, f"net_{i}"), ), True, (0, )) for i in range(2)]
		dut._add_vertex(vertices[0])
		dut._add_vertex(vertices[1])
		edge_desig = EdgeDesig(vertices[0].desigs[0], vertices[1].desigs[0])
		res = dut.add_edge(edge_desig)
		
		self.assertIn(edge_desig, dut._edge_map)
		self.check_consistency(self, dut)
		
		with self.assertRaises(AssertionError):
			res = dut.add_edge(edge_desig)
	
	def test_register_bits(self):
		dut = InterRep([], {})
		desig = VertexDesig.from_seg_entry((3, 4, "my_net"))
		vtx = Vertex(dut, (desig, ), False, (0, ))
		bits = create_bits(3, 4, ((9, 1), (45, 12)))
		
		for bit in bits:
			self.assertNotIn(bit, dut._bit_map)
		
		dut.register_bits(bits, vtx)
		
		for bit in bits:
			self.assertIn(bit, dut._bit_map)
			self.assertEqual(vtx, dut._bit_map[bit])
		
		with self.assertRaises(AssertionError):
			dut.register_bits(bits, vtx)
	
	def test_get_vertex_for_bit(self):
		dut = InterRep([], {})
		desig = VertexDesig.from_seg_entry((3, 4, "my_net"))
		vtx = Vertex(dut, (desig, ), False, (0, ))
		bits = create_bits(3, 4, ((9, 1), (45, 12)))
		
		dut.register_bits(bits, vtx)
		
		for bit in bits:
			res = dut.get_vertex_for_bit(bit)
			self.assertEqual(vtx, res)
	
	def test_get_vertices_of_tile(self):
		dut = InterRep(NET_DATA, self.add_con_config(self.add_lut_config()))
		
		tile_names_map = {}
		for raw_net in NET_DATA:
			for x, y, raw_name in raw_net.segment:
				name_set = tile_names_map.setdefault(TilePosition(x, y), set())
				name = f"NET#{raw_name}"
				assert name not in name_set
				name_set.add(name)
		
		for item_list in LUT_DATA:
			index = item_list[0].index
			tile = item_list[0].bits[0].tile
			
			name_set = tile_names_map.setdefault(tile, set())
			name = f"LUT#{index}"
			assert name not in name_set
			name_set.add(name)
		
		vertex_desigs = set()
		for tile, name_set in tile_names_map.items():
			res = dut.get_vertices_of_tile(tile)
			vertex_desigs.update([v.desigs[0] for v in res])
			res_names = set()
			for vtx in res:
				res_names.update([d.name for d in vtx.desigs if d.tile==tile])
			self.assertEqual(name_set, res_names)
		
		exp_desigs = set(v.desigs[0] for v in dut.iter_vertices())
		self.assertEqual(exp_desigs, vertex_desigs)
	
	def test_get_edges_of_tile(self):
		dut = InterRep(NET_DATA, self.add_con_config(self.add_lut_config()))
		
		tile_names_map = {}
		for con_item in CON_DATA:
			tile = con_item.bits[0].tile
			for src_net in con_item.src_nets:
				tile_names_map.setdefault(tile, set()).add(EdgeDesig.net_to_net(tile, src_net, con_item.dst_net))
		
		for lut_index, lut_io in enumerate(LUT_CON):
			for lut_in in lut_io.in_nets:
				tile = TilePosition(*lut_in[:2])
				in_name = lut_in[2]
				tile_names_map.setdefault(tile, set()).add(EdgeDesig.net_to_lut(tile, in_name, lut_index))
			
			for lut_out in lut_io.out_nets:
				tile = TilePosition(*lut_out[:2])
				out_name = lut_out[2]
				tile_names_map.setdefault(tile, set()).add(EdgeDesig.lut_to_net(tile, lut_index, out_name))
		
		all_desigs = set()
		for tile, exp_set in tile_names_map.items():
			res = dut.get_edges_of_tile(tile)
			desig_set = set(e.desig for e in res)
			self.assertEqual(len(res), len(desig_set))
			
			self.assertEqual(exp_set, desig_set)
			
			all_desigs.update(desig_set)
		
		self.assertEqual(set(e.desig for e in dut.iter_edges()), all_desigs)
	
	# add LUT truth table, create LUTVertex
	@staticmethod
	def check_consistency(test_case, rep):
		for edge in rep.iter_edges():
			# all src/dst in vertices
			test_case.assertIn(edge.desig.src, rep._vertex_map)
			test_case.assertIn(edge.desig.dst, rep._vertex_map)
			test_case.assertIn(edge.src, rep._vertices)
			test_case.assertIn(edge.dst, rep._vertices)
			
			# all edges in vertex in/out
			test_case.assertIn(edge, edge.src.out_edges)
			test_case.assertIn(edge, edge.dst.in_edges)
		
		edge_list = list(rep.iter_edges())
		# all vertex in/out in edges
		for vertex in rep.iter_vertices():
			for edge in vertex.iter_in_edges():
				test_case.assertIn(edge.desig.dst, vertex.desigs)
				test_case.assertIn(edge, edge_list)
			
			for edge in vertex.iter_out_edges():
				test_case.assertIn(edge.desig.src, vertex.desigs)
				test_case.assertIn(edge, edge_list)
	

class TestEdge(unittest.TestCase):
	def test_creation(self):
		rep = InterRep([], {})
		tile = TilePosition(3, 6)
		src_desig = VertexDesig.from_lut_index(tile, 2)
		dst_desig = VertexDesig.from_net_name(tile, "net")
		edge_desig = EdgeDesig(src_desig, dst_desig)
		
		dut = Edge(rep, edge_desig)

class TestVertex(unittest.TestCase):
	def create_vertex_and_tile(self):
		rep = InterRep([], {})
		tile = TilePosition(6, 1)
		desig = VertexDesig.from_net_name(tile, "my_net")
		return Vertex(rep, (desig, ), False, (0, )), tile
	
	def test_creation(self):
		dut, _ = self.create_vertex_and_tile()
	
	def check_edges(self, dut, exp_in, exp_out):
		self.assertEqual(set(exp_in), set(e.desig for e in dut.iter_in_edges()))
		self.assertEqual(set(exp_out), set(e.desig for e in dut.iter_out_edges()))
	
	def test_add_edge(self):
		dut, tile = self.create_vertex_and_tile()
		vtx_desig = dut.desigs[0]
		
		exp_in = []
		exp_out = []
		
		self.check_edges(dut, exp_in, exp_out)
		
		src_desig = VertexDesig.from_net_name(tile, "src_net")
		edge_desig = EdgeDesig(src_desig, vtx_desig)
		edge = Edge(dut.rep, edge_desig)
		exp_in.append(edge_desig)
		dut.add_edge(edge, True)
		self.check_edges(dut, exp_in, exp_out)
		
		dst_desig = VertexDesig.from_net_name(tile, "dst_net")
		edge_desig = EdgeDesig(vtx_desig, dst_desig)
		edge = Edge(dut.rep, edge_desig)
		exp_out.append(edge_desig)
		dut.add_edge(edge, False)
		self.check_edges(dut, exp_in, exp_out)
		
	
	def test_in_edges(self):
		dut, tile = self.create_vertex_and_tile()
		exp = []
		
		with self.subTest(desc="empty"):
			res = list(dut.iter_in_edges())
			self.assertEqual(exp, res)
		
		dst_desig = VertexDesig.from_net_name(tile, "net_a")
		src_desig = VertexDesig.from_net_name(tile, "net_b")
		edge_desig = EdgeDesig(src_desig, dst_desig)
		edge = Edge(dut.rep, edge_desig)
		exp.append(edge)
		
		with self.subTest(desc="add edge to empty vertex"):
			dut.add_edge(edge, True)
			res = list(dut.iter_in_edges())
			self.assertEqual(exp, res)
	
	def test_out_edges(self):
		dut, tile = self.create_vertex_and_tile()
		exp = []
		
		with self.subTest(desc="empty"):
			res = list(dut.iter_out_edges())
			self.assertEqual(exp, res)
		
		dst_desig = VertexDesig.from_net_name(tile, "net_a")
		src_desig = VertexDesig.from_net_name(tile, "net_b")
		edge_desig = EdgeDesig(src_desig, dst_desig)
		edge = Edge(dut.rep, edge_desig)
		exp.append(edge)
		
		with self.subTest(desc="add edge to empty vertex"):
			dut.add_edge(edge, False)
			res = list(dut.iter_out_edges())
			self.assertEqual(exp, res)
	
	def test_driver_tiles(self):
		tiles = [ TilePosition(*d) for d in [
			(1, 6), (1, 7), (2, 1), (14, 0)
		]]
		desigs = tuple(VertexDesig.from_net_name(t, f"net_{j}") for j, t in enumerate(tiles))
		test_data = [
			((desigs, False, (2, )), (tiles[2], ), "single driver"),
			((desigs, True, (2, )), (tiles[2], ), "hard driven"),
			((desigs, False, (0, 2)), (tiles[0], tiles[2]), "multiple drivers"),
			((desigs[:3]+(VertexDesig.from_net_name(tiles[2], f"net_2_1"), )+desigs[3:], False, (2, 3)), (tiles[2], ), "multiple drivers, same tile"),
		]
		
		rep = InterRep([], {})
		for args, exp, desc in test_data:
			with self.subTest(desc=desc):
				dut = Vertex(rep, *args)
				res = dut.driver_tiles
				
				for i in range(len(res)-1):
					self.assertTrue(res[i]<res[i+1])
				
				self.assertEqual(exp, res)
	

class TestConVertex(unittest.TestCase):
	def test_creation(self):
		desig_1 = VertexDesig.from_seg_entry((5, 1, "net_a"))
		desig_2 = VertexDesig.from_seg_entry((6, 25, "net_b"))
		rep = InterRep([], {})
		
		with self.subTest(desc="hard driven"):
			dut = ConVertex(rep, (desig_1, ), True, (0, ))
		
		with self.subTest(desc="multi desig"):
			dut = ConVertex(rep, (desig_1, desig_2), False, (1, ))
	
	def test_post_init_checks(self):
		rep = InterRep([], {})
		
		with self.assertRaises(AssertionError):
			# no desig
			dut = ConVertex(rep, tuple(), True, tuple())
	
	def test_from_net_data(self):
		for raw_net in NET_DATA:
			with self.subTest(raw_net=raw_net):
				rep = InterRep([], {})
				dut = ConVertex.from_net_data(rep, raw_net)
				
				self.assertEqual(rep, dut.rep)
				self.assertEqual(not raw_net.hard_driven, dut.configurable)
				self.assertEqual(raw_net.drivers, dut.drivers)
				self.assertEqual(set(raw_net.segment), set((*d.tile, d.name[4:]) for d in dut.desigs))
	
	def check_registered_bits(self, rep, bits, vertex):
		for bit in bits:
			res = rep.get_vertex_for_bit(bit)
			self.assertEqual(vertex, res)
	
	def test_add_src_grp(self):
		rep = InterRep(NET_DATA, {})
		TestInterRep.check_consistency(self, rep)
		const_attrs = ("available", "ext_src", "out_edges", "desigs", "configurable", "drivers")
		
		for con_item in CON_DATA:
			with self.subTest(con_item=con_item):
				desig = VertexDesig.from_net_name(con_item.bits[0].tile, con_item.dst_net)
				
				dut = rep.get_vertex(desig)
				prev_vals = {a: copy.copy(getattr(dut, a)) for a in const_attrs}
				prev_in_edges = copy.copy(dut.in_edges)
				prev_src_grps = copy.copy(dut.src_grps)
				
				dut.add_src_grp(con_item)
				
				# check values that stay the same
				self.assertEqual(rep, dut.rep)
				for attr in const_attrs:
					self.assertEqual(prev_vals[attr], getattr(dut, attr))
				for src_grp in prev_src_grps:
					self.assertIn(src_grp, dut.src_grps)
				for in_edge in prev_in_edges:
					self.assertIn(in_edge, dut.in_edges)
				self.check_registered_bits(rep, [b for sg in prev_src_grps for b in sg.bits], dut)
				
				# check new source group
				new_grps = [s for s in dut.src_grps if s not in prev_src_grps]
				self.assertEqual(1, len(new_grps))
				src_grp = new_grps[0]
				self.assertEqual(con_item.bits, src_grp.bits)
				self.assertIn(src_grp.dst, dut.desigs)
				value_map = {n: v for n, v in zip(con_item.src_nets, con_item.values)}
				for edge_desig, values in src_grp.srcs.items():
					exp_vals = value_map[edge_desig.src.name[4:]]
					self.assertEqual(exp_vals, values)
					self.assertIn(edge_desig.dst, dut.desigs)
				
				new_edge_desigs = [e.desig for e in dut.in_edges if e not in prev_in_edges]
				self.assertEqual(set(new_edge_desigs), set(src_grp.srcs.keys()))
				
				self.check_registered_bits(rep, src_grp.bits, dut)
				
				TestInterRep.check_consistency(self, rep)
	
	def check_bit_count(self, rep, exp_map):
		for desig, exp in exp_map.items():
			vtx = rep.get_vertex(desig)
			
			self.assertEqual(exp, vtx.bit_count)
	
	def test_bit_count(self):
		rep = InterRep(NET_DATA, {})
		exp_map = {VertexDesig.from_seg_entry(n.segment[0]): 0 for n in NET_DATA}
		
		desig_to_desig = {}
		for raw_net in NET_DATA:
			pivot = VertexDesig.from_seg_entry(raw_net.segment[0])
			for seg in raw_net.segment:
				desig_to_desig[VertexDesig.from_seg_entry(seg)] = pivot
		
		self.check_bit_count(rep, exp_map)
		
		for con_item in CON_DATA:
			desig = VertexDesig.from_net_name(con_item.bits[0].tile, con_item.dst_net)
			pivot = desig_to_desig[desig]
			
			dut = rep.get_vertex(desig)
			dut.add_src_grp(con_item)
			
			exp_map[pivot] += len(con_item.bits)
			self.check_bit_count(rep, exp_map)
	
	def create_bit_and_config_map(self):
		config_map = {}
		bit_conf_map = {}
		for con_item in CON_DATA:
			config_assem = config_map.setdefault(con_item.bits[0].tile, ConfigAssemblage())
			config_assem.connection += (con_item, )
			
			assert con_item.bits[0] not in bit_conf_map
			bit_conf_map[con_item.bits[0]] = con_item
		
		return config_map, bit_conf_map
	
	def test_get_bit_tuples(self):
		config_map, bit_conf_map = self.create_bit_and_config_map()
		
		rep = InterRep(NET_DATA, config_map)
		
		seen = set()
		
		for dut in rep.iter_vertices():
			if not isinstance(dut, ConVertex):
				continue
			
			res = dut.get_bit_tuples()
			genes = dut.get_genes()
			
			self.assertEqual(len(genes), len(res), f"{genes}\n{res}")
			self.assertEqual([g.bit_positions for g in genes], res)
			
			for bits in res:
				index = 0
				while index < len(bits):
					con_item = bit_conf_map[bits[index]]
					self.assertEqual(con_item.bits, bits[index:index+len(con_item.bits)])
					self.assertNotIn(bits[index], seen)
					seen.add(bits[index])
					
					index += len(con_item.bits)
				
				self.assertEqual(len(bits), index)
			
		self.assertEqual(set(bit_conf_map), seen)
	
	def check_con_genes(self, rep, bits_to_vals, unavailable, bits_to_uncon):
		bit_to_bits = {b[0]: b for b in bits_to_vals}
		seen_bits = set()
		
		@dataclass
		class Section:
			bits: Optional[Tuple[IcecraftBitPosition, ...]] = None
			start: Optional[int] = None
			end: Optional[int] = None
			uncon: Optional[Tuple[bool, ...]] = None
		
		for dut in rep.iter_vertices():
			if not isinstance(dut, ConVertex):
				continue
			
			res = dut.get_genes()
			
			if dut.desigs[0] in unavailable:
				self.assertEqual([], res)
				continue
			
			for gene in res:
				bit_index = 0
				bit_count = len(gene.bit_positions)
				values = [a.values for a in gene.alleles]
				section_list = []
				
				# map bits to values
				while bit_index < bit_count:
					sec = Section()
					section_list.append(sec)
					sec.bits = bit_to_bits[gene.bit_positions[bit_index]]
					sec.start = bit_index
					sec.end = bit_index + len(sec.bits)
					try:
						sec.uncon = bits_to_uncon[sec.bits]
					except KeyError:
						pass
					
					self.assertEqual(sec.bits, gene.bit_positions[sec.start:sec.end])
					
					seen_bits.add(sec.bits)
					bit_index = sec.end
				
				self.assertEqual(bit_count, bit_index)
				
				# check values
				main_vals_list = [set() for _ in range(len(section_list))]
				for vals in values:
					main_indices = [i for i, s in enumerate(section_list) if vals[s.start:s.end]!=s.uncon]
					self.assertTrue(len(main_indices)<2, "More than one input connect, possible shortcut")
					
					if len(main_indices) == 0:
						# all unconnected -> include all in seen values
						main_indices = list(range(len(main_vals_list)))
					else:
						for i in range(len(section_list)):
							if i in main_indices:
								continue
							sec = section_list[i]
							self.assertEqual(sec.uncon, vals[sec.start:sec.end])
					
					# collect values that drove the output
					for i in main_indices:
						sec = section_list[i]
						main_vals_list[i].add(vals[sec.start:sec.end])
				
				for sec, main_vals in zip(section_list, main_vals_list):
					self.assertEqual(set(bits_to_vals[sec.bits]), main_vals)
				
		self.assertEqual(set(bits_to_vals), seen_bits)
	
	def test_get_genes(self):
		config_map, bit_conf_map = self.create_bit_and_config_map()
		uncon_name = VertexDesig.canonical_net_name(UNCONNECTED_NAME)
		
		rep = InterRep(NET_DATA, config_map)
		bits_to_vals = {}
		bits_to_uncon = {}
		ed_to_bit_vals = {}
		for vtx in rep.iter_vertices():
			try:
				src_grps = vtx.src_grps
			except AttributeError:
				continue
			
			for grp in src_grps:
				new_dict = {e: (grp.bits, v) for e, v in grp.srcs.items()}
				ed_to_bit_vals.update(new_dict)
				bits_to_vals[grp.bits] = list(grp.srcs.values())
				uncon_vals_list = [v for e, v in grp.srcs.items() if e.src.name==uncon_name]
				assert len(uncon_vals_list)<2, "More than one value for unconnected not supported"
				try:
					uncon_vals = uncon_vals_list[0]
					bits_to_uncon[grp.bits] = uncon_vals
				except KeyError:
					# no unconnected value, no problem here
					pass
		
		# no vertex available
		unavailable = set()
		for vtx in rep.iter_vertices():
			vtx.available = False
			unavailable.add(vtx.desigs[0])
		
		with self.subTest(desc="not available"):
			self.check_con_genes(rep, {}, unavailable, bits_to_uncon)
		
		for vtx in rep.iter_vertices():
			vtx.available = True
		
		# all vertices available
		with self.subTest(desc="all available"):
			self.check_con_genes(rep, bits_to_vals, [], bits_to_uncon)
		
		# unused vertices
		btv_vtx = copy.deepcopy(bits_to_vals)
		unused_data = [
			(2, 3, "internal"),
			(2, 3, "lut_out"),
			(2, 3, "empty_out"),
			(4, 2, "short_span_1"),
			(4, 1, "short_span_2"),
			(5, 0, "long_span_1"),
			(5, 3, "long_span_2"),
			(8, 0, UNCONNECTED_NAME),
		]
		vtx_list = []
		for vtx_desig in [VertexDesig.from_seg_entry(s) for s in unused_data]:
			vtx = rep.get_vertex(vtx_desig)
			for edge in itertools.chain(vtx.iter_out_edges(), vtx.iter_in_edges()):
				bits, vals = ed_to_bit_vals[edge.desig]
				if edge.desig.src.name == uncon_name and vtx_desig.name != uncon_name:
					# unconnected
					continue
				
				try:
					btv_vtx[bits].remove(vals)
				except ValueError:
					# the other vertex is also unused -> values were already removed
					pass
			
			vtx.used = False
			vtx_list.append(vtx)
		
		with self.subTest(desc="unused vertex"):
			self.check_con_genes(rep, btv_vtx, [], bits_to_uncon)
			
		for vtx in vtx_list:
			vtx.used = True
		
		# ext src
		btv_vtx = copy.deepcopy(bits_to_vals)
		es_data = [
			(2, 3, "internal_2"),
			(0, 3, "right"),
			(0, 3, "wire_in_1"),
			(4, 2, "out"),
			(8, 0, "long_span_3"),
			(5, 0, "long_span_4"),
			(7, 0, "out"),
		]
		vtx_list = []
		for vtx_desig in [VertexDesig.from_seg_entry(s) for s in es_data]:
			vtx = rep.get_vertex(vtx_desig)
			for edge in vtx.iter_in_edges():
				if edge.desig.src.name == uncon_name:
					# unconnected
					continue
				
				bits, vals = ed_to_bit_vals[edge.desig]
				btv_vtx[bits].remove(vals)
			
			vtx.ext_src = True
			vtx_list.append(vtx)
		
		with self.subTest(desc="ext_src"):
			self.check_con_genes(rep, btv_vtx, [], bits_to_uncon)
		
		for vtx in vtx_list:
			vtx.ext_src = False
		
		# edges unavailable
		btv_edge = copy.deepcopy(bits_to_vals)
		unavail_data = [
			(2, 3, "left", "internal"),
			(2, 3, "wire_out", "internal"),
			(1, 3, "out", "wire_in_2"),
			(4, 2, "short_span_1", "short_span_2"),
			(5, 3, "long_span_2", "long_span_1"),
			(5, 0, "long_span_1", "long_span_4"),
			(8, 0, UNCONNECTED_NAME, "long_span_3"),
		]
		edge_list = []
		for edge_desig in [EdgeDesig.net_to_net(TilePosition(*d[:2]), *d[2:]) for d in unavail_data]:
			bits, vals = ed_to_bit_vals[edge_desig]
			btv_edge[bits].remove(vals)
			
			edge = rep.get_edge(edge_desig)
			edge.available = False
			edge_list.append(edge)
		
		with self.subTest(desc="unavailable edge"):
			self.check_con_genes(rep, btv_edge, [], bits_to_uncon)
		
		for edge in edge_list:
			edge.available = True
		
		# edges unused
		btv_edge = copy.deepcopy(bits_to_vals)
		unused_data = [
			(2, 3, UNCONNECTED_NAME, "internal"),
			(2, 3, "wire_out", "internal_2"),
			(4, 2, "short_span_2", "short_span_1"),
			(4, 2, "out", "short_span_2"),
			(8, 3, "long_span_3", "long_span_2"),
			(8, 0, "long_span_4", "long_span_3"),
			(7, 0, "out", "long_span_4"),
		]
		edge_list = []
		for edge_desig in [EdgeDesig.net_to_net(TilePosition(*d[:2]), *d[2:]) for d in unused_data]:
			bits, vals = ed_to_bit_vals[edge_desig]
			btv_edge[bits].remove(vals)
			
			edge = rep.get_edge(edge_desig)
			edge.used = False
			edge_list.append(edge)
		
		with self.subTest(desc="unused edge"):
			self.check_con_genes(rep, btv_edge, [], bits_to_uncon)
		
		for edge in edge_list:
			edge.used = True
	
	def test_neutral_alleles(self):
		rep = InterRep(NET_DATA, {})
		seg = NET_DATA[0].segment[0]
		desig = VertexDesig.from_seg_entry(seg)
		dut = rep.get_vertex(desig)
		
		dut.add_src_grp(CON_DATA[0])
		with self.subTest("simple case"):
			res = dut.neutral_alleles()
			# single allele seq
			self.assertEqual(1, len(res))
			seq = res[0]
			self.assertEqual(1, len(seq))
			self.assertEqual(len(CON_DATA[0].bits), len(seq[0].values))
			# all false
			self.assertFalse(any(seq[0].values))
		
		bits = (IcecraftBitPosition.from_coords(2, 3, 5, 1), )
		config_item = ConnectionItem(
			bits,
			"connection", seg[2], ((True, ), ), ("lut_out", )
		)
		dut.add_src_grp(config_item)
		with self.subTest("missing unconnected"):
			with self.assertRaises(IcecraftSatisfiabilityError):
				res = dut.neutral_alleles()
	
	def generate_src_grps_test_cases(self, x, y):
		class SrcGrpsTestData(NamedTuple):
			desc: str # description
			con_items: Iterable[ConnectionItem] = [] # connection config items
			used_func: Callable[[Vertex], bool] = lambda x: True # used function
			unavails: List[int] = [] # indices of unavailable nets
			exp_bits: Tuple[IcecraftBitPosition, ...] = tuple() # expected bits
			exp_allele_values: Tuple[Tuple[bool, ...], ...] = tuple() # expected allele values
			exp_excep: Union[Exception, None] = None # expected exception
		
		bit_pos = IcecraftBitPosition.from_coords
		
		net_data_list = [NetData(((x, y, f"src_{i}"), ), True, (0,)) for i in range(4)]
		net_data_list.extend([NetData(((x+i, y, UNCONNECTED_NAME), ), True, (0,)) for i in range(2)])
		net_data_list.extend([NetData(((x+1, y, f"src_{i+4}"), ), True, (0,)) for i in range(4)])
		net_data_list.append(NetData(((x, y, "dst"), (x+1, y, "dst")), False, (0, 1)))
		tile_items = [
			ConnectionItem(
				(bit_pos(x, y, 7, 0), bit_pos(x, y, 7, 1)),
				"connection", "dst", ((False, False), (True, False), (True, True)), (UNCONNECTED_NAME, "src_0", "src_1")
			),
			ConnectionItem(
				(bit_pos(x, y, 3, 0), bit_pos(x, y, 3, 1)),
				"connection", "dst", ((False, False), (False, True), (True, False)), (UNCONNECTED_NAME, "src_2", "src_3")
			),
		]
		other_items = [
			ConnectionItem(
				(bit_pos(x+1, y, 7, 0), bit_pos(x+1, y, 7, 1)),
				"connection", "dst", ((False, False), (True, False), (True, True)), (UNCONNECTED_NAME, "src_4", "src_5")
			),
			ConnectionItem(
				(bit_pos(x+1, y, 3, 0), bit_pos(x+1, y, 3, 1)),
				"connection", "dst", ((False, False), (False, True), (True, False)), (UNCONNECTED_NAME, "src_6", "src_7")
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
				lambda v: "NET#src_0" not in [d.name for d in v.desigs],
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
				lambda v: v.desigs[0].name[-1] in ("1", "3"),
				[1, 3],
				tile_items[0].bits+tile_items[1].bits,
				((False, False, False, False), ),
			),
		)
		
		return net_data_list, test_cases
	
	def test_get_genes_with_src_gps(self):
		net_data, test_list = self.generate_src_grps_test_cases(6, 5)
		for tc in test_list:
			with self.subTest(desc=tc.desc):
				config_map = {}
				for con_item in tc.con_items:
					config_assem = config_map.setdefault(con_item.bits[0].tile, ConfigAssemblage())
					config_assem.connection += (con_item, )
				
				rep = InterRep(net_data, config_map)
				for vtx in rep.iter_vertices():
					vtx.used = tc.used_func(vtx)
				for index in tc.unavails:
					desig = VertexDesig.from_seg_entry(net_data[index].segment[0])
					vtx = rep.get_vertex(desig)
					vtx.available = False
				
				dst_desig = VertexDesig.from_seg_entry(net_data[-1].segment[0])
				dut = rep.get_vertex(dst_desig)
				if tc.exp_excep is None:
					res = dut.get_genes()
					self.assertEqual(1, len(res))
					gene = res[0]
					self.assertEqual(tc.exp_bits, gene.bit_positions)
					allele_values = tuple(a.values for a in gene.alleles)
					self.assertEqual(set(tc.exp_allele_values), set(allele_values))
					self.assertEqual(tc.exp_allele_values, allele_values)
				else:
					# no error but empty result if no genes can be generated
					res = dut.get_genes()
					self.assertEqual([], res)
	
	
	# handle externally driven
	# multiple driver tiles
	# get bits and list of possibilities

class TestLUTBits(unittest.TestCase):
	def test_creation(self):
		tile = TilePosition(9, 1)
		dff_bits = (IcecraftBitPosition(tile, 3, 45), )
		snr_bits = (IcecraftBitPosition(tile, 7, 32), )
		asr_bits = (IcecraftBitPosition(tile, 9, 54), )
		tt_bits = tuple(IcecraftBitPosition(tile, 0, 2+i) for i in range(16))
		
		dut = LUTBits(dff_bits, snr_bits, asr_bits, tt_bits)
		
		self.assertEqual(dff_bits, dut.dff_enable)
		self.assertEqual(snr_bits, dut.set_no_reset)
		self.assertEqual(asr_bits, dut.async_set_reset)
		self.assertEqual(tt_bits, dut.truth_table)
	
	def test_from_config_items(self):
		for lut_items in LUT_DATA:
			with self.subTest(lut_items=lut_items):
				bits_dict = {l.kind: l.bits for l in lut_items}
				
				dut = LUTBits.from_config_items(lut_items)
				
				self.assertEqual(bits_dict["DffEnable"], dut.dff_enable)
				self.assertEqual(bits_dict["Set_NoReset"], dut.set_no_reset)
				self.assertEqual(bits_dict["AsyncSetReset"], dut.async_set_reset)
				self.assertEqual(bits_dict["TruthTable"], dut.truth_table)
	
	def test_post_init_checks(self):
		arg_sets = []
		for k in range(2):
			tile = TilePosition(9, 1+k)
			arg_sets.append((
				(IcecraftBitPosition(tile, 3, 45), ),
				(IcecraftBitPosition(tile, 7, 32), ),
				(IcecraftBitPosition(tile, 9, 54), ),
				tuple(IcecraftBitPosition(tile, 0, 2+i) for i in range(16))
			))
		
		for l in range(len(arg_sets[0])):
			with self.assertRaises(AssertionError):
				cur_args = arg_sets[0][:l] + arg_sets[1][l:l+1] + arg_sets[0][l+1:]
				dut = LUTBits(*cur_args)
	
	def test_names(self):
		self.assertEqual(len(fields(LUTBits)), len(LUTBits.names))
	
	def test_as_tuple(self):
		for lut_items in LUT_DATA:
			with self.subTest(lut_items=lut_items):
				bits_dict = {l.kind: l.bits for l in lut_items}
				
				dut = LUTBits.from_config_items(lut_items)
				
				res = dut.as_tuple()
				
				self.assertEqual(len(LUTBits.names), len(res))
				
				for name, res_val in zip(LUTBits.names, res):
					self.assertEqual(bits_dict[name], res_val)
		

class TestLUTVertex(unittest.TestCase):
	def check_registered_lut_bits(self, lut_vertex):
		rep = lut_vertex.rep
		for bit in [b for bg in lut_vertex.lut_bits.as_tuple() for b in bg]:
			res = rep.get_vertex_for_bit(bit)
			self.assertEqual(lut_vertex, res)
	
	def test_creation(self):
		tile = TilePosition(4, 21)
		index = 4
		rep = InterRep([], {})
		bits = LUTBits(
			(IcecraftBitPosition(tile, 4, 5), ),
			(IcecraftBitPosition(tile, 6, 5), ),
			(IcecraftBitPosition(tile, 6, 6), ),
			(IcecraftBitPosition(tile, 7, 8), IcecraftBitPosition(tile, 7, 9))
		)
		desig = VertexDesig.from_lut_index(tile, index)
		
		dut = LUTVertex(rep, (desig, ), bits)
		
		self.assertEqual(bits, dut.lut_bits)
		self.assertEqual(index, int(dut.desig.name[4:]))
		self.assertEqual(desig, dut.desig)
		self.assertEqual(rep, dut.rep)
		self.assertEqual(True, dut.configurable)
		self.check_registered_lut_bits(dut)
	
	def test_from_config_items(self):
		for lut_items in LUT_DATA:
			rep = InterRep([], {})
			with self.subTest(lut_items=lut_items):
				dut = LUTVertex.from_config_items(rep, lut_items)
				
				self.assertEqual(LUTBits.from_config_items(lut_items), dut.lut_bits)
				self.assertEqual(lut_items[0].index, int(dut.desig.name[4:]))
				self.assertEqual(lut_items[0].bits[0].tile, dut.desig.tile)
				self.assertEqual(rep, dut.rep)
				self.assertEqual(True, dut.configurable)
				self.check_registered_lut_bits(dut)
	
	def test_desigs(self):
		for lut_items in LUT_DATA:
			rep = InterRep([], {})
			with self.subTest(lut_items=lut_items):
				dut = LUTVertex.from_config_items(rep, lut_items)
				
				res = dut.desigs
				self.assertIn(dut.desig, res)
				self.assertEqual(1, len(res))
	
	def test_bit_count(self):
		for lut_items in LUT_DATA:
			rep = InterRep([], {})
			with self.subTest(lut_items=lut_items):
				exp = sum(len(l.bits) for l in lut_items if l.kind != "CarryEnable")
				dut = LUTVertex.from_config_items(rep, lut_items)
				
				self.assertEqual(exp, dut.bit_count)
		
	def test_get_bit_tuples(self):
		for lut_items in LUT_DATA:
			rep = InterRep([], {})
			with self.subTest(lut_items=lut_items):
				exp = [l.bits for l in lut_items if l.kind != "CarryEnable"]
				dut = LUTVertex.from_config_items(rep, lut_items)
				
				res = dut.get_bit_tuples()
				
				self.assertEqual(exp, res)
				
				# check same consistency with genes
				genes = dut.get_genes()
				self.assertEqual([g.bit_positions for g in genes], res)
		
	
	def test_post_init_checks(self):
		tile = TilePosition(4, 21)
		other_tile = TilePosition(5, 21)
		rep = InterRep([], {})
		bits = LUTBits(
			(IcecraftBitPosition(tile, 4, 5), ),
			(IcecraftBitPosition(tile, 6, 5), ),
			(IcecraftBitPosition(tile, 6, 6), ),
			(IcecraftBitPosition(tile, 7, 8), IcecraftBitPosition(tile, 7, 9))
		)
		desig = VertexDesig.from_lut_index(tile, 5)
		
		with self.subTest(desc="no desig"):
			with self.assertRaises(AssertionError):
				dut = LUTVertex(rep, tuple(), bits)
		
		with self.subTest(desc="desig and bits inconsistent"):
			other_desig = VertexDesig.from_lut_index(other_tile, 5)
			
			with self.assertRaises(AssertionError):
				dut = LUTVertex(rep, (other_desig, ), bits)
		
		#with self.subTest(desc="inconsistent bits"):
		#	other_bits = (IcecraftBitPosition(tile, 4, 5), IcecraftBitPosition(other_tile, 6, 5))
		#	
		#	with self.assertRaises(AssertionError):
		#		dut = LUTVertex(rep, (desig, ), other_bits)
	
	def test_connect(self):
		for lut_items, lut_con in zip(LUT_DATA, LUT_CON):
			rep = InterRep(NET_DATA, {})
			with self.subTest(lut_items=lut_items):
				dut = LUTVertex.from_config_items(rep, lut_items)
				rep._add_vertex(dut)
				
				# unconnected before call
				self.assertEqual(0, len(dut.in_edges))
				self.assertEqual(0, len(dut.out_edges))
				
				dut.connect(lut_con)
				
				# connected after call
				self.assertEqual(len(lut_con.in_nets), len(dut.in_edges))
				# order has to be preserved for inputs
				for in_edge, in_net in zip(dut.in_edges, lut_con.in_nets):
					self.assertEqual(in_net[0], in_edge.desig.src.tile.x)
					self.assertEqual(in_net[1], in_edge.desig.src.tile.y)
					self.assertEqual(in_net[2], in_edge.desig.src.name[4:])
					self.assertEqual(dut.desig, in_edge.desig.dst)
					self.assertEqual(dut, in_edge.dst)
				
				self.assertEqual(len(lut_con.out_nets), len(dut.out_edges))
				# order preservation is not expected for out_edges
				out_net_set = set(lut_con.out_nets)
				for out_edge in dut.out_edges:
					self.assertEqual(dut.desig, out_edge.desig.src)
					self.assertEqual(dut, out_edge.src)
					dst_desig = out_edge.desig.dst
					self.assertIn((*dst_desig.tile, dst_desig.name[4:]), out_net_set)
				
				TestInterRep.check_consistency(self, rep)
	
	def check_genes(self, bits_list, allele_seq_list, genes):
		assert len(bits_list) == len(allele_seq_list)
		self.assertEqual(len(bits_list), len(genes))
		
		for exp_bits, exp_seq, res in zip(bits_list, allele_seq_list, genes):
			self.assertEqual(exp_bits, res.bit_positions)
			self.assertEqual(exp_seq, res.alleles)
	
	def test_get_genes(self):
		# test with made up names to check for hard coded name references
		tile = TilePosition(5, 20)
		for i, test_data in enumerate(TRUTH_TABLE):
			with self.subTest(test_data=test_data):
				net_names = [f"lut_in_{l}" for l in range(test_data.input_count)]
				net_data = [NetData(((*tile, n), ), False, (0,)) for n in net_names]
				rep = InterRep(net_data, {})
				tt_width = pow(2, test_data.input_count)
				bits = LUTBits(
					(IcecraftBitPosition(tile, 4, 5), ),
					(IcecraftBitPosition(tile, 6, 5), ),
					(IcecraftBitPosition(tile, 6, 6), ),
					tuple(IcecraftBitPosition(tile, 7, j) for j in range(tt_width))
				)
				lut_desig = VertexDesig.from_lut_index(tile, 5)
				
				dut = LUTVertex(rep, (lut_desig, ), bits)
				rep._add_vertex(dut)
				dut.connect(ElementInterface(tuple((*tile, n) for n in net_names), tuple()))
				
				dut.functions = test_data.lut_functions
				
				# input unused
				for index in test_data.unused_inputs:
					desig = VertexDesig.from_net_name(tile, net_names[index])
					vtx = rep.get_vertex(desig)
					vtx.used = False
				
				res = dut.get_genes()
				exp_bits = bits.as_tuple()
				exp_alleles = [AlleleAll(1), AlleleAll(1), AlleleAll(1), test_data.allele_seq]
				self.check_genes(exp_bits, exp_alleles, res)
				
				# input unavailable
				for index in test_data.unused_inputs:
					desig = VertexDesig.from_net_name(tile, net_names[index])
					vtx = rep.get_vertex(desig)
					vtx.used = True
					vtx.available = False
				
				res = dut.get_genes()
				self.check_genes(exp_bits, exp_alleles, res)
				
				# edge unused
				for index in test_data.unused_inputs:
					desig = VertexDesig.from_net_name(tile, net_names[index])
					vtx = rep.get_vertex(desig)
					vtx.available = True
					edge_desig = EdgeDesig(desig, lut_desig)
					edge = rep.get_edge(edge_desig)
					edge.used = False
				
				res = dut.get_genes()
				self.check_genes(exp_bits, exp_alleles, res)
				
				# edge unavailable
				for index in test_data.unused_inputs:
					desig = VertexDesig.from_net_name(tile, net_names[index])
					edge_desig = EdgeDesig(desig, lut_desig)
					edge = rep.get_edge(edge_desig)
					edge.used = True
					edge.available = False
				
				res = dut.get_genes()
				self.check_genes(exp_bits, exp_alleles, res)
				
				# lut unused
				for index in test_data.unused_inputs:
					desig = VertexDesig.from_net_name(tile, net_names[index])
					edge_desig = EdgeDesig(desig, lut_desig)
					edge = rep.get_edge(edge_desig)
					edge.available = True
				dut.used = False
				
				res = dut.get_genes()
				exp_alleles = [AlleleList([Allele((False, ), "")]) for _ in range(3)]
				exp_alleles.append(AlleleList([Allele((False, )*tt_width, "")]))
				self.check_genes(exp_bits, exp_alleles, res)
				
				# lut unavailable
				dut.used = True
				dut.available = False
				res = dut.get_genes()
				
				self.assertEqual([], res)
			
	
	def test_neutral_alleles(self):
		for lut_items in LUT_DATA:
			rep = InterRep([], {})
			with self.subTest(lut_items=lut_items):
				dut = LUTVertex.from_config_items(rep, lut_items)
				res = dut.neutral_alleles()
				
				bits_list = dut.get_bit_tuples()
				self.assertEqual(len(bits_list), len(res))
				for bits, res_seq in zip(bits_list, res):
					self.assertEqual(1, len(res_seq))
					res_vals = res_seq[0].values
					self.assertEqual(len(bits), len(res_vals))
					self.assertFalse(any(v for v in res_vals))
		
	
	def test_lut_function_to_truth_table(self):
		for func_enum in LUTFunction:
			for in_count in range(9):
				for used_count in range(in_count):
					for used_inputs in itertools.combinations(range(in_count), used_count):
						with self.subTest(func_enum=func_enum, used_inputs=used_inputs):
							truth_table = LUTVertex.lut_function_to_truth_table(func_enum, in_count, used_inputs)
							for in_values in itertools.product((0, 1), repeat=used_count):
								
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
								unused_inputs = sorted(set(range(in_count))-set(used_inputs))
								for invariant_values in itertools.product((0, 1), repeat=len(unused_inputs)):
									index = used_index
									for i, shift in zip(invariant_values, unused_inputs):
										index |= i << shift
									
									self.assertEqual(expected, truth_table[index], f"Wrong truth table value {func_enum.name} {used_inputs} for input 0b{index:04b}")
			
