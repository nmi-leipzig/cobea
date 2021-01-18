import unittest
import operator

from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftLUTPosition
from adapters.icecraft.inter_rep import InterRep, VertexDesig, EdgeDesig
from adapters.icecraft.chip_data_utils import NetData
from adapters.icecraft.config_item import ConnectionItem

from .common import create_bits

NET_DATA = (
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
		"connection", "long_span_4", ((True), ), ("out", )
	), # 9
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
	
	def create_edge_desigs(self):
		vert_desigs = self.create_vertex_desigs()
		edge_desigs = []
		for vd_1 in vert_desigs[:2]:
			for vd_2 in vert_desigs[2:]:
				edge_desigs.append(EdgeDesig(vd_1, vd_2))
		
		return edge_desigs
	
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

class TestInterRep(unittest.TestCase):
	def test_creation(self):
		with self.subTest(desc="no input"):
			dut = InterRep([])
		
		with self.subTest(desc="initial net data"):
			dut = InterRep(NET_DATA)
	# vertex from name
	# edge from name?
	# endpoints of edge
	# add Connectionconfig, update ConVertex
	# add LUT truth table, create LUTVertex
	

class TestVertex(unittest.TestCase):
	# get incoming edges
	# get outgoing edges
	pass

class TestConVertex(unittest.TestCase):
	# handle externally driven
	# multiple driver tiles
	# get bits and list of possibilities
	pass
