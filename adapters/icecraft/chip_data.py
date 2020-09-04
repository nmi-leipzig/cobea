# module to provide access to chip database

from typing import Iterable, List
from .chip_data_utils import TileType, SegType, get_segs_for_tile
from .chip_database import seg_kinds, seg_tile_map, config_kinds, config_tile_map

# tile -> config_kind
tile_to_config_kind_index = {t: k for k, tl in config_tile_map.items() for t in tl}

def get_segments(tiles: Iterable[TileType]) -> List[SegType]:
	segs = set()
	for tile_pos in tiles:
		tile_segs = get_segs_for_tile(seg_kinds, tile_pos, seg_tile_map[tile_pos])
		segs.update(tile_segs)
	
	return sorted(segs)

def get_raw_config_data(tile):
	config_kind_index = tile_to_config_kind_index[tile]
	return config_kinds[config_kind_index]
