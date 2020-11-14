# module to provide access to chip database

from typing import Iterable, List, Dict, Union, Tuple, NewType
from .chip_data_utils import TileType, SegType, BitType, DriverType, NetData, get_net_data_for_tile, seg_from_seg_kind
from .chip_database import seg_kinds, drv_kinds, seg_tile_map, config_kinds, config_tile_map, colbufctrl_tile_map
from .misc import TilePosition, IcecraftBitPosition
from .config_item import ConfigItem, IndexedItem, ConnectionItem, NamedItem

MultiBitsType = NewType("MultiBitsType", Tuple[BitType, ...])
NamedBitsType = NewType("NamedBitsType", Tuple[MultiBitsType, str])
RawLUTType = NewType("RawLUTType", Tuple[NamedBitsType, ...])
ValueType = NewType("ValueType", Tuple[bool, ...])
SrcType = NewType("SrcType", Tuple[ValueType, str])
RawConType = NewType("RawConType", Tuple[str, Tuple[SrcType, ...]])
ConDictType = NewType("ConDictType", Dict[MultiBitsType, RawConType])
ConfigDictType = NewType("ConfigDictType",Dict[str, Tuple[Union[ConfigItem, Tuple[IndexedItem, ...]]]])

# tile -> config_kind
tile_to_config_kind_index = {t: k for k, tl in config_tile_map.items() for t in tl}
# tile -> colbufctrl tile
tile_to_colbufctrl = {t: c for c, tl in colbufctrl_tile_map.items() for t in tl}

def get_net_data(tiles: Iterable[TileType]) -> List[NetData]:
	nets = set()
	for tile_pos in tiles:
		tile_nets = get_net_data_for_tile(seg_kinds, drv_kinds, tile_pos, seg_tile_map[tile_pos])
		nets.update(tile_nets)
	
	return sorted(nets)

def get_seg_kind_examples() -> List[Tuple[SegType, TileType, DriverType]]:
	"""get an example segment for every segemtn kind"""
	seg_kind_to_tile = [[] for _ in range(len(seg_kinds))]
	for tile in sorted(seg_tile_map):
		for seg_ref in sorted(seg_tile_map[tile]):
			seg_kind_to_tile[seg_ref[0]].append((tile, seg_ref[1]))
	
	examples = []
	for kind_index, tile_data in enumerate(seg_kind_to_tile):
		tile_pos, role = tile_data[0]
		seg = seg_from_seg_kind(seg_kinds[kind_index], tile_pos, role)
		#print(f"{kind_index:03d}: {tile_pos} {drv_kinds[kind_index][0]}, {str_max([seg[i][2] for i in drv_kinds[kind_index][1]], 8)}\n{str_max(seg, 10)}\n")
		examples.append((
			seg,
			tile_pos,
			drv_kinds[kind_index],
		))
	
	return examples

def get_raw_config_data(tile: TileType) -> Dict[str, Union[Tuple[NamedBitsType, ...], Tuple[MultiBitsType, ...], Tuple[RawLUTType, ...], ConDictType]]:
	config_kind_index = tile_to_config_kind_index[tile]
	return config_kinds[config_kind_index]

def bits_to_bit_positions(tile_pos: TilePosition, bits: Iterable[BitType]) -> Tuple[IcecraftBitPosition, ...]:
	return tuple(IcecraftBitPosition(tile_pos, *b) for b in bits)

def get_config_items(tile: TileType) -> ConfigDictType:
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

def get_colbufctrl(tiles: Iterable[TileType]) -> List[TileType]:
	colbufctrl_set = set()
	for tile in tiles:
		cbc = tile_to_colbufctrl[tile]
		colbufctrl_set.add(cbc)
	
	return sorted(colbufctrl_set)
