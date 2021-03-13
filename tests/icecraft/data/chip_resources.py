from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftLUTPosition
from adapters.icecraft.chip_data_utils import NetData, ElementInterface, UNCONNECTED_NAME
from adapters.icecraft.config_item import ConnectionItem, IndexedItem
from ..common import create_bits

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
	NetData(((2, 3, UNCONNECTED_NAME), ), True, (0, )), # 14
	NetData(((1, 3, UNCONNECTED_NAME), ), True, (0, )), # 15
	NetData(((4, 2, UNCONNECTED_NAME), ), True, (0, )), # 16
	NetData(((5, 3, UNCONNECTED_NAME), ), True, (0, )), # 17
	NetData(((8, 3, UNCONNECTED_NAME), ), True, (0, )), # 18
	NetData(((8, 0, UNCONNECTED_NAME), ), True, (0, )), # 19
	NetData(((5, 0, UNCONNECTED_NAME), ), True, (0, )), # 20
	NetData(((7, 0, UNCONNECTED_NAME), ), True, (0, )), # 21
)

# left, wire_out -> internal -> LUT -> lut_out
# wire_out -> internal_2 -> LUT -> lut_out
# out -> wire_in_2
# short_span_1 <-> short_span_2
# out -> short_span_2
# long_span_4 -> long_span_3 -> long_span_2 -> long_span_1
# out, long_span_1 -> long_span_4
CON_DATA = (
	ConnectionItem(
		create_bits(2, 3, ((7, 0), (7, 1))),
		"connection", "internal", ((False, False), (True, False), (True, True)), (UNCONNECTED_NAME, "left", "wire_out")
	), # 0
	ConnectionItem(
		create_bits(2, 3, ((7, 2), (7, 3))),
		"connection", "internal_2", ((False, False), (True, True)), (UNCONNECTED_NAME, "wire_out")
	), # 1
	ConnectionItem(
		create_bits(1, 3, ((6, 10), (6, 11))),
		"connection", "wire_in_2", ((False, False), (True, False)), (UNCONNECTED_NAME, "out")
	), # 2
	ConnectionItem(
		(IcecraftBitPosition.from_coords(4, 2, 11, 30), ),
		"connection", "short_span_1", ((False, ), (True, )), (UNCONNECTED_NAME, "short_span_2")
	), # 3
	ConnectionItem(
		create_bits(4, 2, ((2, 0), (2, 1))),
		"connection", "short_span_2", ((False, False), (False, True), (True, False)), (UNCONNECTED_NAME, "short_span_1", "out")
	), # 4
	ConnectionItem(
		(IcecraftBitPosition.from_coords(5, 3, 5, 1), ),
		"connection", "long_span_1", ((False, ), (True, )), (UNCONNECTED_NAME, "long_span_2")
	), # 5
	ConnectionItem(
		(IcecraftBitPosition.from_coords(8, 3, 5, 1), ),
		"connection", "long_span_2", ((False, ), (True, )), (UNCONNECTED_NAME, "long_span_3")
	), # 6
	ConnectionItem(
		(IcecraftBitPosition.from_coords(8, 0, 5, 1), ),
		"connection", "long_span_3", ((False, ), (True, )), (UNCONNECTED_NAME, "long_span_4")
	), # 7
	ConnectionItem(
		(IcecraftBitPosition.from_coords(5, 0, 5, 1), ),
		"connection", "long_span_4", ((False, ), (True, )), (UNCONNECTED_NAME, "long_span_1")
	), # 8
	ConnectionItem(
		(IcecraftBitPosition.from_coords(7, 0, 5, 3), ),
		"connection", "long_span_4", ((False, ), (True, )), (UNCONNECTED_NAME, "out")
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

