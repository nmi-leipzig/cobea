import unittest
import operator
import copy

from typing import NamedTuple, Iterable, Mapping

from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftLUTPosition
from adapters.icecraft.inter_rep import InterRep, VertexDesig, EdgeDesig, EdgeData, SourceGroup, Vertex, ConVertex, LUTVertex
from adapters.icecraft.chip_data import ConfigAssemblage
from adapters.icecraft.chip_data_utils import NetData, ElementInterface
from adapters.icecraft.config_item import ConnectionItem, IndexedItem

from .common import create_bits

NET_DATA = (
	NetData(((2, 3, "internal"), ), False, (0,)), # 0
	NetData(((2, 3, "internal_2"), ), False, (0,)), # 1
	NetData(((2, 3, "lut_out"), ), True, (0, )), # 2
	NetData(((0, 3, "right"), (1, 3, "out"), (2, 3, "left")), True, (1, )), # 3
	NetData(((0, 3, "wire_in_1"), (1, 3, "wire_in_2"), (2, 3, "wire_out")), False, (0, 1)), # 4
	NetData(((2, 3, "empty_out"), ), False, tuple()), # 5 no driver
	NetData(((4, 2, "short_span_1"), (4, 3, "short_span_1")), False, (0, 1)), # 6
	NetData(((4, 1, "short_span_2"), (4, 2, "short_span_2")), False, (0, 1)), # 7
	NetData(((4, 2, "out"), ), True, (0, )), # 8
	NetData(((5, 0, "long_span_1"), (5, 3, "long_span_1")), False, (0, 1)), # 9
	NetData(((5, 3, "long_span_2"), (8, 3, "long_span_2")), False, (0, 1)), # 10
	NetData(((8, 0, "long_span_3"), (8, 3, "long_span_3")), False, (0, 1)), # 11
	NetData(((5, 0, "long_span_4"), (7, 0, "long_span_4"), (8, 0, "long_span_4")), False, (0, 1, 2)), # 12
	NetData(((7, 0, "out"), ), True, (0, )), # 13
)

# left, wire_out -> internal
# wire_out -> internal_2
# out -> wire_in_2
# short_span_1 <-> short_span_2
# out -> short_span_2
# long_span_4 -> long_span_3 -> long_span_2 -> long_span_1
# out, long_span_1 -> long_span_4
CON_DATA = (
	ConnectionItem(
		create_bits(2, 3, ((7, 0), (7, 1))),
		"connection", "internal", ((True, False), (True, True)), ("left", "wire_out")
	), # 0
	ConnectionItem(
		create_bits(2, 3, ((7, 2), (7, 3))),
		"connection", "internal_2", ((True, True), ), ("wire_out", )
	), # 1
	ConnectionItem(
		create_bits(1, 3, ((6, 10), (6, 11))),
		"connection", "wire_in_2", ((True, False), ), ("out", )
	), # 2
	ConnectionItem(
		(IcecraftBitPosition.from_coords(4, 2, 11, 30), ),
		"connection", "short_span_1", ((True, ), ), ("short_span_2", )
	), # 3
	ConnectionItem(
		create_bits(4, 2, ((2, 0), (2, 1))),
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
		"connection", "long_span_4", ((True, ), ), ("out", )
	), # 9
)

LUT_DATA = tuple(
	tuple(IndexedItem(create_bits(2, 3, b), k, 0) for b, k in r)
	for r in ((
		(((14, 44),), 'CarryEnable'), (((14, 45),), 'DffEnable'),
		(((15, 44),), 'Set_NoReset'), (((15, 45),), 'AsyncSetReset'),
		(((14, 40), (15, 40), (15, 41), (14, 41)), 'TruthTable')
	), )
)

LUT_CON = (
	ElementInterface(
		((2, 3, "internal"), (2, 3, "internal_2")),
		((2, 3, "lut_out"), )
	),
)

class TestDesignation(unittest.TestCase):
	# test VertexDesig and EdgeDesig
	def create_vertex_desigs(self):
		tile = TilePosition(4, 1)
		positions = [
			IcecraftNetPosition(tile, "net_a"),
			IcecraftLUTPosition(tile, 2),
			IcecraftNetPosition(tile, "net_b"),
			IcecraftLUTPosition(tile, 5),
		]
		vert_desigs = [VertexDesig(p) for p in positions]
		return vert_desigs
	
	def check_vertex_values(self, vertex, tile, net_name=None, lut_index=None):
		if net_name is None and lut_index is None:
			raise ValueError("Either net_name or lut_index has to be not None")
		
		self.assertEqual(tile, vertex.tile)
		if net_name is None:
			self.assertIsInstance(vertex.position, IcecraftLUTPosition)
			self.assertEqual(lut_index, vertex.position.z)
		else:
			self.assertIsInstance(vertex.position, IcecraftNetPosition)
			self.assertEqual(net_name, vertex.position.name)
	
	def create_edge_desigs(self):
		vert_desigs = self.create_vertex_desigs()
		edge_desigs = []
		for vd_1 in vert_desigs[:2]:
			for vd_2 in vert_desigs[2:]:
				edge_desigs.append(EdgeDesig(vd_1, vd_2))
		
		return edge_desigs
	
	def test_creation_vertex_desig(self):
		desigs = self.create_vertex_desigs()
		tile = TilePosition(4, 1)
		self.check_vertex_values(desigs[0], tile, net_name="net_a")
		self.check_vertex_values(desigs[1], tile, lut_index=2)
		self.check_vertex_values(desigs[2], tile, net_name="net_b")
		self.check_vertex_values(desigs[3], tile, lut_index=5)
	
	def test_from_net_name(self):
		tile = TilePosition(21, 14)
		net_name = "test_wire"
		dut = VertexDesig.from_net_name(tile, net_name)
		self.check_vertex_values(dut, tile, net_name=net_name)
	
	def test_from_lut_index(self):
		tile = TilePosition(21, 14)
		lut_index = 4
		dut = VertexDesig.from_lut_index(tile, lut_index)
		self.check_vertex_values(dut, tile, lut_index=lut_index)
	
	def test_creation_edge_desig(self):
		vert_desigs = self.create_vertex_desigs()
		for vd_1 in vert_desigs[:2]:
			for vd_2 in vert_desigs[2:]:
				with self.subTest(vd_1=vd_1, vd_2=vd_2):
					dut = EdgeDesig(vd_1, vd_2)
	
	def test_cmp(self):
		edge_desigs = self.create_edge_desigs()
		# (net_a, net_b), (net_a, lut_5), (lut_2, net_b), (lut_2, lut_5)
		order = [3, 2, 1, 0]
		for op in [operator.lt, operator.le, operator.eq, operator.ne, operator.ge, operator.gt]:
			for i_1, ed_1 in enumerate(edge_desigs):
				for i_2, ed_2 in enumerate(edge_desigs):
					with self.subTest(op=op, ed_1=ed_1, ed_2=ed_2):
						self.assertEqual(op(order[i_1], order[i_2]), op(ed_1, ed_2))
	
	def test_edge_post_init_check(self):
		src = VertexDesig(IcecraftNetPosition.from_coords(4, 1, "net_a"))
		dst = VertexDesig(IcecraftNetPosition.from_coords(5, 1, "net_b"))
		
		with self.assertRaises(AssertionError):
			EdgeDesig(src, dst)

class TestSourceGroup(unittest.TestCase):
	def test_creation(self):
		tile = TilePosition(2, 34)
		bits = (IcecraftBitPosition(tile, 4, 5), )
		dst = VertexDesig(IcecraftNetPosition(tile, "net_a"))
		src = VertexDesig(IcecraftNetPosition(tile, "net_b"))
		edge = EdgeDesig(src, dst)
		dut = SourceGroup(bits, dst, {edge: (True, )})
	
	def test_post_init_checks(self):
		tile = TilePosition(2, 34)
		other_tile = TilePosition(3, 45)
		bits = (IcecraftBitPosition(tile, 4, 5), IcecraftBitPosition(tile, 6, 5))
		dst = VertexDesig(IcecraftNetPosition(tile, "net_a"))
		src_1 = VertexDesig(IcecraftNetPosition(tile, "net_b"))
		src_2 = VertexDesig(IcecraftNetPosition(tile, "net_c"))
		edge_1 = EdgeDesig(src_1, dst)
		edge_2 = EdgeDesig(src_1, dst)
		edge_map = {edge_1: (False, True), edge_2: (True, True)}
		
		with self.subTest(desc="wrong value length"):
			broken_edge_map = {edge_1: (False, True, False), edge_2: (True, True, False)}
			with self.assertRaises(AssertionError):
				dut = SourceGroup(bits, dst, broken_edge_map)
		
		with self.subTest(desc="wrong tile in edge src and dst"):
			other_dst = VertexDesig(IcecraftNetPosition(other_tile, "net_a"))
			other_src_1 = VertexDesig(IcecraftNetPosition(other_tile, "net_b"))
			other_src_2 = VertexDesig(IcecraftNetPosition(other_tile, "net_c"))
			other_edge_1 = EdgeDesig(other_src_1, other_dst)
			other_edge_2 = EdgeDesig(other_src_1, other_dst)
			
			with self.assertRaises(AssertionError):
				dut = SourceGroup(bits, dst, {other_edge_1: (False, True), other_edge_2: (True, True)})
		
		with self.subTest(desc="wrong tile in bits"):
			other_bits = (IcecraftBitPosition(other_tile, 4, 5), IcecraftBitPosition(other_tile, 6, 5))
			
			with self.assertRaises(AssertionError):
				dut = SourceGroup(other_bits, dst, edge_map)

class TestInterRep(unittest.TestCase):
	def create_config_map(self):
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
			InterRepCreation("initial net data and LUT config", NET_DATA, self.create_config_map())
		)
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				dut = InterRep(tc.net_data, tc.config_map)
				self.check_consistency(self, dut)
				self.check_initial_data(tc.net_data, tc.config_map, dut)
	
	def check_initial_data(self, net_data_iter, config_map, rep):
		for raw_net in net_data_iter:
			desig = VertexDesig(IcecraftNetPosition.from_coords(*raw_net.segment[0]))
			self.assertIn(desig, rep._vertex_map)
			vertex = rep.get_vertex(desig)
			self.check_con_vertex(rep, raw_net, desig, vertex)
		
		for tile, config_assem in config_map.items():
			for lut_grp in config_assem.lut:
				tt_list = [c for c in lut_grp if c.kind == "TruthTable"]
				tt_item = tt_list[0]
				desig = VertexDesig(IcecraftLUTPosition(tile, tt_item.index))
				self.assertIn(desig, rep._vertex_map)
				vertex = rep.get_vertex(desig)
				
				self.check_lut_vertex(rep, tt_item, vertex)
			
			for lut_index, single_lut in enumerate(config_assem.lut_io):
				desig = VertexDesig.from_lut_index(tile, lut_index)
				vertex = rep.get_vertex(desig)
				
				in_net_data = set((*e.src.tile, e.src.position.name) for e in vertex.iter_in_edges())
				self.assertEqual(set(single_lut.in_nets), in_net_data)
				
				out_net_data = set((*e.dst.tile, e.dst.position.name) for e in vertex.iter_out_edges())
				self.assertEqual(set(single_lut.out_nets), out_net_data)
			#TODO: fixed connections
	
	def check_con_vertex(self, rep, raw_net, desig, vertex):
		self.assertIn(desig, vertex.desigs)
		self.assertEqual(set(raw_net.segment), set((*d.tile, d.position.name) for d in vertex.desigs))
		self.assertEqual(raw_net.hard_driven, vertex.hard_driven)
		self.assertEqual(raw_net.drivers, vertex.drivers)
		self.assertEqual(rep, vertex.rep)
	
	def test_get_vertex(self):
		dut = InterRep(NET_DATA, {})
		
		for raw_net in NET_DATA:
			with self.subTest(raw_net=raw_net):
				for seg in raw_net.segment:
					desig = VertexDesig(IcecraftNetPosition.from_coords(*seg))
					res = dut.get_vertex(desig)
					
					self.check_con_vertex(dut, raw_net, desig, res)
					self.check_consistency(self, dut)
	
	def test_add_con_vertex(self):
		dut = InterRep(NET_DATA, {})
		existing_vertices = []
		
		for raw_net in NET_DATA:
			with self.subTest(raw_net=raw_net):
				dut._add_con_vertex(raw_net)
				
				desig = VertexDesig(IcecraftNetPosition.from_coords(*raw_net.segment[0]))
				res = dut.get_vertex(desig)
				
				self.check_con_vertex(dut, raw_net, desig, res)
				self.check_consistency(self, dut)
				
				existing_vertices.append(res)
				
				for exp_vtx in existing_vertices:
					res = dut.get_vertex(exp_vtx.desigs[0])
					self.assertEqual(exp_vtx, res)
		
		# add Connectionconfig, update ConVertex
	
	def check_lut_vertex(self, rep, tt_item, vertex):
		self.assertEqual(tt_item.bits, vertex.truth_table_bits)
		self.assertEqual(tt_item.index, vertex.desig.position.z)
		self.assertEqual(tt_item.bits[0].tile, vertex.desig.tile)
		self.assertEqual(rep, vertex.rep)
	
	def test_add_lut_vertex(self):
		dut = InterRep(NET_DATA, {})
		existing_vertices = []
		
		for lut_items in LUT_DATA:
			tt_item = lut_items[-1]
			with self.subTest(tt_item=tt_item):
				dut._add_lut_vertex(tt_item)
				
				desig = VertexDesig(IcecraftLUTPosition(tt_item.bits[0].tile, tt_item.index))
				res = dut.get_vertex(desig)
				
				self.check_lut_vertex(dut, tt_item, res)
				self.check_consistency(self, dut)
	
	# add LUT truth table, create LUTVertex
	@staticmethod
	def check_consistency(test_case, rep):
		for edge in rep.iter_edges():
			# all src/dst in vertices
			test_case.assertIn(edge.src, rep._vertex_map)
			test_case.assertIn(edge.dst, rep._vertex_map)
			
			# all edges in vertex in/out
			src_vtx = rep.get_vertex(edge.src)
			test_case.assertIn(edge, src_vtx.out_edges)
			dst_vtx = rep.get_vertex(edge.dst)
			test_case.assertIn(edge, dst_vtx.in_data)
		
		edge_set = set(rep.iter_edges())
		# all vertex in out in edges
		for vertex in rep.iter_vertices():
			for edge in vertex.in_data:
				test_case.assertIn(edge.dst, vertex.desigs)
				test_case.assertIn(edge, edge_set)
			
			for edge in vertex.out_edges:
				test_case.assertIn(edge.src, vertex.desigs)
				test_case.assertIn(edge, edge_set)

class TestVertex(unittest.TestCase):
	def create_vertex(self):
		rep = InterRep([], {})
		return Vertex(rep)
	
	def test_creation(self):
		dut = self.create_vertex()
	
	def test_in_edges(self):
		dut = self.create_vertex()
		tile = TilePosition(7, 2)
		exp = []
		
		with self.subTest(desc="empty"):
			res = list(dut.iter_in_edges())
			self.assertEqual(exp, res)
		
		dst = VertexDesig(IcecraftNetPosition(tile, "net_a"))
		src = VertexDesig(IcecraftNetPosition(tile, "net_b"))
		edge = EdgeDesig(src, dst)
		exp.append(edge)
		
		with self.subTest(desc="add edge to empty vertex"):
			dut.add_edge(edge, True)
			res = list(dut.iter_in_edges())
			self.assertEqual(exp, res)
			
			res_data = dut.get_in_data(edge)
			self.assertEqual(EdgeData(), res_data)
	
	def test_out_edges(self):
		dut = self.create_vertex()
		tile = TilePosition(7, 2)
		exp = []
		
		with self.subTest(desc="empty"):
			res = list(dut.iter_out_edges())
			self.assertEqual(exp, res)
		
		dst = VertexDesig(IcecraftNetPosition(tile, "net_a"))
		src = VertexDesig(IcecraftNetPosition(tile, "net_b"))
		edge = EdgeDesig(src, dst)
		exp.append(edge)
		
		with self.subTest(desc="add edge to empty vertex"):
			dut.add_edge(edge, False)
			res = list(dut.iter_out_edges())
			self.assertEqual(exp, res)
		

class TestConVertex(unittest.TestCase):
	def test_creation(self):
		desig_1 = VertexDesig(IcecraftNetPosition.from_coords(5, 1, "net_a"))
		desig_2 = VertexDesig(IcecraftNetPosition.from_coords(6, 25, "net_b"))
		rep = InterRep([], {})
		
		with self.subTest(desc="hard driven"):
			dut = ConVertex(rep, (desig_1, ), True, (0, ))
		
		with self.subTest(desc="multi desig"):
			dut = ConVertex(rep, (desig_1, desig_2), False, (1, ))
	
	def test_from_net_data(self):
		for raw_net in NET_DATA:
			with self.subTest(raw_net=raw_net):
				rep = InterRep([], {})
				dut = ConVertex.from_net_data(rep, raw_net)
				
				self.assertEqual(rep, dut.rep)
				self.assertEqual(raw_net.hard_driven, dut.hard_driven)
				self.assertEqual(raw_net.drivers, dut.drivers)
				self.assertEqual(set(raw_net.segment), set((*d.tile, d.position.name) for d in dut.desigs))
	
	def test_add_src_grp(self):
		rep = InterRep(NET_DATA, {})
		TestInterRep.check_consistency(self, rep)
		const_attrs = ("available", "ext_src", "out_edges", "desigs", "hard_driven", "drivers")
		
		for con_item in CON_DATA:
			with self.subTest(con_item=con_item):
				desig = VertexDesig(IcecraftNetPosition(con_item.bits[0].tile, con_item.dst_net))
				
				dut = rep.get_vertex(desig)
				prev_vals = {a: copy.copy(getattr(dut, a)) for a in const_attrs}
				prev_in_data = copy.copy(dut.in_data)
				prev_src_grps = copy.copy(dut.src_grps)
				
				dut.add_src_grp(con_item)
				
				# check values that stay the same
				self.assertEqual(rep, dut.rep)
				for attr in const_attrs:
					self.assertEqual(prev_vals[attr], getattr(dut, attr))
				for src_grp in prev_src_grps:
					self.assertIn(src_grp, dut.src_grps)
				
				# check new source group
				new_grps = [s for s in dut.src_grps if s not in prev_src_grps]
				self.assertEqual(1, len(new_grps))
				src_grp = new_grps[0]
				self.assertEqual(con_item.bits, src_grp.bits)
				self.assertIn(src_grp.dst, dut.desigs)
				value_map = {n: v for n, v in zip(con_item.src_nets, con_item.values)}
				for edge, values in src_grp.srcs.items():
					exp_vals = value_map[edge.src.position.name]
					self.assertEqual(exp_vals, values)
					self.assertIn(edge.dst, dut.desigs)
					
				
				TestInterRep.check_consistency(self, rep)
	
	# handle externally driven
	# multiple driver tiles
	# get bits and list of possibilities

class TestLUTVertex(unittest.TestCase):
	def test_creation(self):
		tile = TilePosition(4, 21)
		index = 4
		rep = InterRep([], {})
		bits = (IcecraftBitPosition(tile, 4, 5), IcecraftBitPosition(tile, 6, 5))
		desig = VertexDesig(IcecraftLUTPosition(tile, index))
		
		dut = LUTVertex(rep, desig, bits)
		
		self.assertEqual(bits, dut.truth_table_bits)
		self.assertEqual(index, dut.desig.position.z)
		self.assertEqual(desig, dut.desig)
		self.assertEqual(rep, dut.rep)
	
	def test_from_truth_table(self):
		for lut_items in LUT_DATA:
			tt_item = lut_items[-1]
			rep = InterRep([], {})
			with self.subTest(tt_item=tt_item):
				dut = LUTVertex.from_truth_table(rep, tt_item)
				
				self.assertEqual(tt_item.bits, dut.truth_table_bits)
				self.assertEqual(tt_item.index, dut.desig.position.z)
				self.assertEqual(tt_item.bits[0].tile, dut.desig.tile)
				self.assertEqual(rep, dut.rep)
	
	def test_desigs(self):
		for lut_items in LUT_DATA:
			tt_item = lut_items[-1]
			rep = InterRep([], {})
			with self.subTest(tt_item=tt_item):
				dut = LUTVertex.from_truth_table(rep, tt_item)
				
				res = dut.desigs
				self.assertIn(dut.desig, res)
				self.assertEqual(1, len(res))
	
	def test_post_init_checks(self):
		tile = TilePosition(4, 21)
		other_tile = TilePosition(5, 21)
		rep = InterRep([], {})
		bits = (IcecraftBitPosition(tile, 4, 5), IcecraftBitPosition(tile, 6, 5))
		desig = VertexDesig(IcecraftLUTPosition(tile, 5))
		
		with self.subTest(desc="desig and bits inconsistent"):
			other_desig = VertexDesig(IcecraftLUTPosition(other_tile, 5))
			
			with self.assertRaises(AssertionError):
				dut = LUTVertex(rep, other_desig, bits)
		
		with self.subTest(desc="inconsistent bits"):
			other_bits = (IcecraftBitPosition(tile, 4, 5), IcecraftBitPosition(other_tile, 6, 5))
			
			with self.assertRaises(AssertionError):
				dut = LUTVertex(rep, desig, other_bits)
	
	def test_connect(self):
		for lut_items, lut_con in zip(LUT_DATA, LUT_CON):
			tt_item = lut_items[-1]
			rep = InterRep(NET_DATA, {})
			with self.subTest(tt_item=tt_item):
				dut = LUTVertex.from_truth_table(rep, tt_item)
				rep._add_vertex(dut)
				
				# unconnected before call
				self.assertEqual(0, len(dut.in_data))
				self.assertEqual(0, len(dut.out_edges))
				
				dut.connect(lut_con)
				
				# connected after call
				self.assertEqual(set(dut.in_data.keys()), set(dut.inputs))
				self.assertEqual(len(lut_con.in_nets), len(dut.inputs))
				# order has to be preserved for inputs
				for in_desig, in_net in zip(dut.inputs, lut_con.in_nets):
					self.assertEqual(in_net[0], in_desig.src.tile.x)
					self.assertEqual(in_net[1], in_desig.src.tile.y)
					self.assertEqual(in_net[2], in_desig.src.position.name)
					self.assertEqual(dut.desig, in_desig.dst)
				
				self.assertEqual(len(lut_con.out_nets), len(dut.out_edges))
				# order preservation is not expected for out_edges
				out_net_set = set(lut_con.out_nets)
				for out_edge in dut.out_edges:
					self.assertEqual(dut.desig, out_edge.src)
					dst = out_edge.dst
					self.assertIn((*dst.tile, dst.position.name), out_net_set)
				
				TestInterRep.check_consistency(self, rep)
		
