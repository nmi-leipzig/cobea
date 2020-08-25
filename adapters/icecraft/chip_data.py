# module to provide access to chip database

from typing import Iterable, Set, Tuple, List, Iterable, Mapping, Any, NewType, TextIO, Dict


SegEntryType = NewType("SegEntryType", Tuple[int, int, str])
SegType = NewType("SegType", Tuple[SegEntryType, ...])
TileType = NewType("TileType", Tuple[int, int])
SegRefType = NewType("SegRefType", Tuple[int, int])
ConfEntryType = NewType("ConfEntryType", tuple)
ConfKindType = NewType("ConfKindType", Tuple[ConfEntryType])

def get_nets_for_tile(seg_kinds: List[SegType], tile_pos: TileType, seg_refs: Iterable[SegRefType]) -> List[SegType]:
	nets = []
	for seg_index, role in seg_refs:
		seg_kind = seg_kinds[seg_index]
		x_off = tile_pos[0] - seg_kind[role][0]
		y_off = tile_pos[1] - seg_kind[role][1]
		net = tuple((x+x_off, y+y_off, n) for x, y, n in seg_kind)
		nets.append(net)
	
	return nets


