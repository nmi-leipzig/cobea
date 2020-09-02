# module to provide access to chip database

from typing import Iterable, List
from .chip_data_utils import TileType, SegType, get_segs_for_tile
from .chip_database import seg_kinds, seg_tile_map, conf_kinds, conf_tile_map

def get_segments(tiles: Iterable[TileType]) -> List[SegType]:
	segs = set()
	for tile_pos in tiles:
		tile_segs = get_segs_for_tile(seg_kinds, tile_pos, seg_tile_map[tile_pos])
		segs.update(tile_segs)
	
	return sorted(segs)

def get_raw_conf(tile):
	return {}
