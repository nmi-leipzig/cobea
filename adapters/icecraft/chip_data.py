# module to provide access to chip database

from dataclasses import dataclass, astuple
from typing import Iterable, List, Dict, Union, Tuple, NewType

from .chip_data_utils import TileType, SegType, BitType, DriverType, NetData, ElementInterface, get_net_data_for_tile, seg_from_seg_kind
from .chip_database import seg_kinds, drv_kinds, seg_tile_map, config_kinds, config_tile_map, colbufctrl_tile_map, lut_io_kinds, lut_io_tiles
from .misc import IcecraftPosition, IcecraftBitPosition
from .config_item import ConfigItem, IndexedItem, ConnectionItem, NamedItem

MultiBitsType = NewType("MultiBitsType", Tuple[BitType, ...])
NamedBitsType = NewType("NamedBitsType", Tuple[MultiBitsType, str])
RawLUTType = NewType("RawLUTType", Tuple[NamedBitsType, ...])
ValueType = NewType("ValueType", Tuple[bool, ...])
SrcType = NewType("SrcType", Tuple[ValueType, str])
RawConType = NewType("RawConType", Tuple[str, Tuple[SrcType, ...]])
ConDictType = NewType("ConDictType", Dict[MultiBitsType, RawConType])

@dataclass
class ConfigAssemblage:
	"""collection of config items grouped by kind"""
	connection: Tuple[ConnectionItem, ...] = tuple()
	tile: Tuple[ConfigItem, ...] = tuple()
	col_buf_ctrl: Tuple[IndexedItem, ...] = tuple()
	lut: Tuple[Tuple[IndexedItem, ...], ...] = tuple()
	ram_config: Tuple[NamedItem, ...] = tuple()
	ram_cascade: Tuple[NamedItem, ...] = tuple()
	lut_io: Tuple[ElementInterface, ...] = tuple()

# tile -> config_kind
tile_to_config_kind_index = {IcecraftPosition(*t): k for k, tl in config_tile_map.items() for t in tl}
# tile -> colbufctrl tile
tile_to_colbufctrl = {IcecraftPosition(*t): IcecraftPosition(*c) for c, tl in colbufctrl_tile_map.items() for t in tl}
# tile -> LUT IO kind
tile_to_lut_io_kind_index = {IcecraftPosition(*t): i for i, tl in enumerate(lut_io_tiles) for t in tl}

def get_net_data(tiles: Iterable[IcecraftPosition]) -> List[NetData]:
	nets = set()
	for tile_pos in tiles:
		tile_nets = get_net_data_for_tile(seg_kinds, drv_kinds, astuple(tile_pos), seg_tile_map[astuple(tile_pos)])
		nets.update(tile_nets)
	
	return sorted(nets)

def get_seg_kind_examples() -> List[Tuple[SegType, TileType, DriverType]]:
	"""get an example segment for every segment kind"""
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

def get_raw_config_data(tile: IcecraftPosition) -> Dict[str, Union[Tuple[NamedBitsType, ...], Tuple[MultiBitsType, ...], Tuple[RawLUTType, ...], ConDictType]]:
	config_kind_index = tile_to_config_kind_index[tile]
	return config_kinds[config_kind_index]

def get_lut_io(tile: IcecraftPosition) -> Tuple[ElementInterface, ...]:
	try:
		kind_index = tile_to_lut_io_kind_index[tile]
	except KeyError:
		# no LUT IO for this tile
		return tuple()
	
	raw_tile = astuple(tile)
	kind = lut_io_kinds[kind_index]
	lut_io = tuple(
		ElementInterface(tuple((*raw_tile, name) for name in single_lut[0]), tuple((*raw_tile, name) for name in single_lut[1])) for single_lut in kind
	)
	return lut_io

def bits_to_bit_positions(tile_pos: IcecraftPosition, bits: Iterable[BitType]) -> Tuple[IcecraftBitPosition, ...]:
	return tuple(IcecraftBitPosition.from_tile(tile_pos, *b) for b in bits)

def get_config_items(tile: IcecraftPosition) -> ConfigAssemblage:
	raw_groups = get_raw_config_data(tile)
	item_dict = ConfigAssemblage()
	for grp_name, grp_data in raw_groups.items():
		if grp_name == "connection":
			con_list = []
			for bits, (dst_name, src_data) in grp_data.items():
				con_item = ConnectionItem(
					bits_to_bit_positions(tile, bits),
					"connection",
					dst_name,
					tuple(v for v, _ in src_data),
					tuple(s for _, s in src_data)
				)
				con_list.append(con_item)
			item_dict.connection = tuple(con_list)
		elif grp_name == "tile":
			item_dict.tile = tuple(
				ConfigItem(bits_to_bit_positions(tile, b), k) for b, k in grp_data
			)
		elif grp_name == "ColBufCtrl":
			item_dict.col_buf_ctrl = tuple(
				IndexedItem(bits_to_bit_positions(tile, b), "ColBufCtrl", i) for i, b in enumerate(grp_data)
			)
		elif grp_name == "lut":
			item_dict.lut = tuple(
				tuple(IndexedItem(bits_to_bit_positions(tile, b), k, i) for b, k in e) for i, e in enumerate(grp_data)
			)
		elif grp_name == "RamConfig":
			item_dict.ram_config = tuple(
				NamedItem(bits_to_bit_positions(tile, b), grp_name, n) for b, n in grp_data
			)
		elif grp_name == "RamCascade":
			item_dict.ram_cascade = tuple(
				NamedItem(bits_to_bit_positions(tile, b), grp_name, n) for b, n in grp_data
			)
		else:
			raise ValueError(f"Unkown group {grp_name}")
	
	item_dict.lut_io = get_lut_io(tile)
	
	return item_dict

def get_colbufctrl(tiles: Iterable[IcecraftPosition]) -> List[IcecraftPosition]:
	colbufctrl_set = set()
	for tile in tiles:
		cbc = tile_to_colbufctrl[tile]
		colbufctrl_set.add(cbc)
	
	return sorted(colbufctrl_set)
