# module to provide access to chip database

from typing import Iterable, List
from .chip_data_utils import TileType, SegType, get_segs_for_tile
from .chip_database import seg_kinds, seg_tile_map, config_kinds, config_tile_map
from .misc import TilePosition, IcecraftBitPosition
from .config_item import ConfigItem, IndexedItem, ConnectionItem, NamedItem

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

def bits_to_bit_positions(tile_pos, bits):
	return tuple(IcecraftBitPosition(tile_pos, *b) for b in bits)

def get_config_items(tile):
	tile_pos = TilePosition(*tile)
	raw_groups = get_raw_config_data(tile)
	item_dict = {}
	for grp_name, grp_data in raw_groups.items():
		if grp_name == "connection":
			con_list = []
			for bits, (dst_name, src_data) in grp_data.items():
				con_item = ConnectionItem(
					bits_to_bit_positions(tile_pos, bits),
					"connection",
					dst_name,
					tuple(v for v, _ in src_data),
					tuple(s for _, s in src_data)
				)
				con_list.append(con_item)
			item_dict["connection"] = tuple(con_list)
		elif grp_name == "tile":
			item_dict["tile"] = tuple(
				ConfigItem(bits_to_bit_positions(tile_pos, b), k) for b, k in grp_data
			)
		elif grp_name == "ColBufCtrl":
			item_dict["ColBufCtrl"] = tuple(
				IndexedItem(bits_to_bit_positions(tile_pos, b), "ColBufCtrl", i) for i, b in enumerate(grp_data)
			)
		elif grp_name == "lut":
			item_dict["lut"] = tuple(
				tuple(IndexedItem(bits_to_bit_positions(tile_pos, b), k, i) for b, k in e) for i, e in enumerate(grp_data)
			)
		elif grp_name in ("RamConfig", "RamCascade"):
			item_dict[grp_name] = tuple(
				NamedItem(bits_to_bit_positions(tile_pos, b), grp_name, n) for b, n in grp_data
			)
		else:
			raise ValueError(f"Unkown group {grp_name}")
	
	return item_dict
