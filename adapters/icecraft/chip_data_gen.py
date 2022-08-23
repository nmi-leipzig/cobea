#!/usr/bin/env python3
"""Script to generate chip_database.py

The main function extracts the architecture information of iCE40 8k chips
from icebox and converts them to Python data structures. At the moment
only inner tiles are process, IO tiles are ignored.

As there are many instances of the single FPGA elements (tiles, nets,
LUTs, ...), the idea is to find common pattens ('kinds'), so only the
pattern and a map from the concrete element to the corresponding kind
have to be stored.
"""

import sys
import re
import functools
from typing import Iterable, Set, Tuple, List, Iterable, Mapping, Any, TextIO, Dict
from dataclasses import dataclass, field

sys.path.append("/usr/local/bin")
import icebox

try:
	# execution as script
	from adapters.icecraft.chip_data_utils import TileType, SegType, SegRefType, ConfigKindType, ConfigEntryType, DriverType, InterfaceType, UNCONNECTED_NAME
except ModuleNotFoundError:
	# import as module in tests
	from adapters.icecraft.chip_data_utils import TileType, SegType, SegRefType, ConfigKindType, ConfigEntryType, DriverType, InterfaceType, UNCONNECTED_NAME

def get_inner_tiles(ic: icebox.iceconfig) -> Set[TileType]:
	"""Get set of inner tiles for an iceconfig."""
	inner_tiles = set()
	for x in range(1, ic.max_x):
		for y in range(1, ic.max_y):
			if ic.tile(x, y) is None:
				continue
			inner_tiles.add((x, y))
	return inner_tiles

def get_segments(ic: icebox.iceconfig, tiles: Set[TileType]) -> List[SegType]:
	"""Get sorted list of all segments for a set of tiles."""
	all_segments_set = ic.group_segments(tiles, connect_gb=True)
	
	# list
	all_segments = sorted(all_segments_set)
	
	return all_segments

def fix_known_issues(ic: icebox.iceconfig, seg_list: Iterable[SegType]) -> List[SegType]:
	"""Fix known issues in a list of segments.
	
	Unfortunately icebox doesn't generate fully consistent segment lists.
	Nets (represented by theirs segment) that span multiple tiles should
	be included independent of the tile. Sometimes this is not the case.
	
	These inconsistency issues are fixed by this function.
	"""
	fixed_list = []
	for seg in seg_list:
		fixed = list(seg)
		
		# RAM neigh_op_top/bot
		filtered = []
		for entry in fixed:
			r = re.match(r"neigh_op_(?P<kind>top|bot)_(?P<index>\d)", entry[2])
			if r is not None:
				neigh_index = int(r.group("index"))
				tile_kind = ic.tile_type(*entry[:2])
				
				if tile_kind in ("RAMB", "RAMT") and\
					not (tile_kind == "RAMB" and r.group("kind") == "bot" and neigh_index in (0, 4)) and\
					not (tile_kind == "RAMT" and r.group("kind") == "top" and neigh_index in (0, 2, 4, 6)):
					continue
			
			filtered.append(entry)
		fixed = filtered
		
		# glb_netwk
		glb_names = [n for x, y, n in fixed if n.startswith("glb_netwk_")]
		if len(glb_names) > 0:
			r = re.match(r"glb_netwk_(?P<index>\d)", glb_names[0])
			glb_index = int(r.group("index"))
			
			if not any([n.startswith("padin_") for _, _, n in fixed]):
				x, y, pad_index = ic.padin_pio_db()[glb_index]
				fixed.append((x, y, f"padin_{pad_index}"))
			
			if not any([n == "fabout" for _, _, n in fixed]):
				x, y = [(x, y) for x, y, i in ic.gbufin_db() if i==glb_index][0]
				fixed.append((x, y, "fabout"))
		
		# io_global/latch
		if any([n == "io_global/latch" for _, _, n in fixed]):
			x, y = [(x, y) for x, y, n in fixed if n == "fabout"][0]
			if x in (0, ic.max_x):
				fixed = [(x, i, "io_global/latch") for i in range(1, ic.max_y)]
			elif y in (0, ic.max_y):
				fixed = [(i, y, "io_global/latch") for i in range(1, ic.max_x)]
			else:
				raise ValueError()
			
			fixed.append((x, y, "fabout"))
		
		fixed_list.append(tuple(sorted(fixed)))
	
	return fixed_list

@functools.lru_cache(None)
def get_destination_names(ic: icebox.iceconfig, x: int, y: int) -> Set[str]:
	"""Get the names of all nets that can be driven by a tile.
	
	A net can be driven as long as it at least once the destination of a
	buffer or routing entry.
	"""
	dst_names = set()
	
	for db_entry in ic.tile_db(x, y):
		if not ic.tile_has_entry(x, y, db_entry):
			continue
		
		if db_entry[1] not in ("buffer", "routing"):
			continue
		
		dst_names.add(db_entry[3])
	
	return dst_names

def get_driver_indices(ic: icebox.iceconfig, segment: SegType) -> DriverType:
	"""Collect information regarding the potential drivers of a net.
	
	The net is represented by its segment.
	"""
	hard_drivers = []
	config_drivers = []
	for i, (x, y, net_name) in enumerate(segment):
		# check hardwired
		if re.match(r"ram/RDATA_\d", net_name) or re.match(r"io_\d/D_IN_\d", net_name) or\
		re.match(r"lutff_\d/(c|l)?out", net_name) or UNCONNECTED_NAME == net_name:
			hard_drivers.append(i)
		
		# check configurable driver
		# current net is destination
		if net_name in get_destination_names(ic, x, y):
			config_drivers.append(i)
		
		# padin is configured by extra bits, even so this tile is the driver in the end
		if net_name.startswith("padin"):
			config_drivers.append(i)
	
	# check consistency
	if len(hard_drivers) > 1:
		raise ValueError(f"Multiple hardwired drivers {[segment[i] for i in hard_drivers]}")
	
	if len(hard_drivers) > 0 and len(config_drivers) > 0:
		raise ValueError(f"Simultaneously hardwired and configuable sources: {[segment[i] for i in hard_drivers]} vs {[segment[i] for i in config_drivers]}")
	
	return len(hard_drivers)>0, tuple(hard_drivers + config_drivers)

def get_seg_kinds_and_drivers(ic: icebox.iceconfig, all_segments: Iterable[SegType]) -> Tuple[Iterable[SegType], Mapping[TileType, Set[SegRefType]], Iterable[DriverType]]:
	"""Generate segement kind, tile to segment kind map and driver kind for a group of segments.
	
	The map assigns every tile a set of tuples of segment kind index and
	role.
	
	The 'role' of a tile is the index of its segment entry in the
	segment kind (and therefore in the segment).
	
	The segment kind is extracted by sorting the segment and subtracting
	the of coordinates of the first segment entry from the coordinates
	of every segment entry.
	
	The index for the driver kind is the same as the index for the
	segment kind.
	
	example: 
	segment_a  = ((1, 2, "a"), (2, 2, "b"))
	seg_kind_a = ((0, 0, "a"), (1, 0, "b"))
	role_tile_1_2 = 0
	role_tile_2_2 = 1
	
	segment_b  = ((2, 3, "a"), (3, 3, "b"))
	seg_kind_b = ((0, 0, "a"), (1, 0, "b"))
	role_tile_2_3 = 0
	role_tile_3_3 = 1
	
	segment_kinds = [((0, 0, "a"), (1, 0, "b"))]
	tile_to_segment_kind_map = {
		(1, 2): {(0, 0)}, (2, 2): {(0, 1)},
		(2, 3): {(0, 0)}, (3, 3): {(0, 1)},
	}
	"""
	# kinds of segments
	seg_kinds = []
	# drv of segment kinds
	drv_kinds = []
	# mapping seg_kind -> index
	seg_kind_map = {}
	# mapping (x, y) -> list of (seg_kind, role)
	seg_tile_map = {}
	
	for seg_group in all_segments:
		# generate seg_kind
		sorted_seg_group = sorted(seg_group)
		base = sorted_seg_group[0]
		
		seg_kind = tuple([(x-base[0], y-base[1], r) for x, y, r in sorted_seg_group])
		drivers = get_driver_indices(ic, sorted_seg_group)
		
		try:
			seg_kind_index = seg_kind_map[seg_kind]
		except KeyError:
			seg_kind_index = len(seg_kinds)
			seg_kinds.append(seg_kind)
			seg_kind_map[seg_kind] = seg_kind_index
			drv_kinds.append(drivers)
		
		# check driver consistency
		if drivers != drv_kinds[seg_kind_index]:
			raise ValueError(f"Inconsistent driver {drivers} != {drv_kinds[seg_kind_index]} for {str(sorted_seg_group)[:80]}")
		
		for role, entry in enumerate(sorted_seg_group):
			tile_id = (entry[0], entry[1])
			#if tile_id not in inner_tiles:
			#	continue
			# create relative segements
			seg_tile_map.setdefault(tile_id, set()).add((seg_kind_index, role))
	
	return seg_kinds, seg_tile_map, drv_kinds

def add_config_set(
	config_kind_list: List[ConfigKindType],
	config_kind_map: Mapping[ConfigKindType, int],
	config_tile_map: Mapping[int, List[TileType]],
	tile_pos: TileType,
	config_set: Set[ConfigEntryType]
) -> None:
	"""Find the config kind of the config_set. Add the config kind if it
	is not yet known. Update the config_tile_map.
	"""
	config_kind = tuple(sorted(config_set))
	try:
		config_kind_index = config_kind_map[config_kind]
	except KeyError:
		config_kind_index = len(config_kind_list)
		config_kind_list.append(config_kind)
		config_kind_map[config_kind] = config_kind_index
	
	config_tile_map.setdefault(config_kind_index, list()).append(tile_pos)

def get_config_data(ic: icebox.iceconfig, tiles: Iterable[TileType]) -> Tuple[List[ConfigKindType], Mapping[int, List[TileType]]]:
	"""Generate the config kinds and the mapping from config kind to
	tile for a group of tiles.
	
	The map assigns every config kind index a list of tiles that comply
	to that config kind.
	"""
	config_kind_list = []
	config_kind_map = {}
	config_tile_map = {}
	
	for tile_pos in sorted(tiles):
		tile_db = ic.tile_db(*tile_pos)
		
		config_set = set()
		for entry in tile_db:
			if not ic.tile_has_entry(*tile_pos, entry):
				print("Tile ({},{}) has no entry {}".format(*tile_pos, entry))
				continue
			
			config_set.add((tuple(entry[0]), *entry[1:]))
		
		add_config_set(config_kind_list, config_kind_map, config_tile_map, tile_pos, config_set)
	
	return config_kind_list, config_tile_map

def get_net_config_data(
	ic: icebox.iceconfig,
	seg_tile_map: Mapping[TileType, SegRefType],
	seg_kinds: List[SegType],
	config_kind_list: List[ConfigKindType],
	config_tile_map: Mapping[int, List[TileType]]
) -> None:
	"""
	Update config_tile_map and if necessary config_kind_list with 
	connection configurations for specific nets in specific tiles.
	
	The tiles and nets are specified by seg_tile_map.
	
	Purpose:
	Currently only inner tiles are included, yet some nets connect
	inner and IO tiles. The connection configuration of these nets in
	the IO tiles needs to be extracted and added to complete the
	configuration.
	"""
	config_kind_map = {c: i for i, c in enumerate(config_kind_list)}
	for tile_pos in sorted(seg_tile_map):
		# get requested nets
		nets = set(seg_kinds[s][r][2] for s, r in seg_tile_map[tile_pos])
		#print(f"{tile_pos} ({len(nets)}): {list(nets)[:5]}")
		tile_db = ic.tile_db(*tile_pos)
		
		config_set = set()
		for entry in tile_db:
			# important for io tiles as the spans differ between left/right and top/bottom
			if not ic.tile_has_entry(*tile_pos, entry):
				#print(f"Tile {tile_pos} has no entry {entry}")
				continue
			
			if entry[1] not in ("buffer", "routing"):
				continue
			
			if entry[3] not in nets:
				continue
			
			config_set.add((tuple(entry[0]), *entry[1:]))
		
		add_config_set(config_kind_list, config_kind_map, config_tile_map, tile_pos, config_set)

def sort_net_data(seg_kinds: List[SegType], seg_tile_map: Mapping[TileType, SegRefType], drv_kinds: List[DriverType]) -> Tuple[List[SegType], Mapping[TileType, SegRefType], List[DriverType]]:
	"""Sort the segment kind list and generate a corresponding map from tile to segment kinds, and driver kinds list."""
	# sort seg_kinds
	sorted_indices = sorted(range(len(seg_kinds)), key=lambda i: seg_kinds[i])
	srt_seg_kinds = [seg_kinds[i] for i in sorted_indices]
	srt_drv_kinds = [drv_kinds[i] for i in sorted_indices]
	# update seg_tile_map
	index_map = {o: n for n, o in enumerate(sorted_indices)}
	srt_tile_map = {}
	for tile_id in seg_tile_map:
		srt_tile_map[tile_id] = [(index_map[s], r) for s, r in seg_tile_map[tile_id]]
	
	return srt_seg_kinds, srt_tile_map, srt_drv_kinds

def get_colbufctrl_data(ic: icebox.iceconfig, tiles: Iterable[TileType]) -> Mapping[TileType, Tuple[TileType, ...]]:
	"""extract ColBufCtrl tiles mapping
	
	return map: colbufctrl_tile -> tuple(controlled_tiles)
	"""
	
	cbc_db = ic.colbuf_db()
	cbc_tile_map = {}
	for cbc_x, cbc_y, x, y in cbc_db:
		tile = (x, y)
		if tile not in tiles:
			continue
		
		cbc_tile_map.setdefault((cbc_x, cbc_y), set()).add(tile)
	
	return {c: tuple(sorted(t)) for c, t in cbc_tile_map.items()}

def get_lut_io(seg_iter: Iterable[SegType]) -> Tuple[List[InterfaceType], List[Tuple[TileType, ...]]]:
	@dataclass
	class LUTIO:
		in_nets: List[str] = field(default_factory=list)
		out_nets: List[str] = field(default_factory=list)
	
	# create lut io
	tile_io_map = {}
	for seg in seg_iter:
		for x, y, name in seg:
			if not name.startswith("lutff"):
				continue
			
			if name.startswith("lutff_global"):
				continue
			
			res = re.match(r"lutff_(?P<lut_index>\d)/(?P<kind>.+)", name)
			assert res is not None, f"unknown lutff net: '{name}'"
			
			lut_index = int(res.group("lut_index"))
			cur_io = tile_io_map.setdefault((x, y), {}).setdefault(lut_index, LUTIO())
			kind = res.group("kind")
			if kind.endswith("out"):
				cur_io.out_nets.append(name)
			else:
				assert kind.startswith("in"), f"unknown lutff kind: '{kind}'"
				cur_io.in_nets.append(name)
	
	# create lut io kinds
	kind_tile_map = {}
	for tile, index_io_map in tile_io_map.items():
		tuple_map = {i: (tuple(sorted(o.in_nets)), tuple(sorted(o.out_nets))) for i, o in index_io_map.items()}
		io_kind = tuple(tuple_map[i] if i in tuple_map else tuple(tuple(), tuple()) for i in range(max(tuple_map)+1))
		kind_tile_map.setdefault(io_kind, []).append(tile)
	
	io_kind_list = sorted(kind_tile_map)
	kind_tile_list = [tuple(sorted(kind_tile_map[k])) for k in io_kind_list]
	
	return io_kind_list, kind_tile_list

def split_bit_values(bit_comb: Tuple[str, ...]) -> Tuple[Tuple[Tuple[int, int], ...], Tuple[bool, ...]]:
	"""
	Split an collection of bit values in the icebox format into bit coordinates and values.
	
	E.g.
	input: 
	["!B3[36]", "B13"[4]]
	output:
	(
		(Bit(3, 36), Bit(13, 4)),
		(False, True)
	)
	
	Returns a tuple of int tuples and a tuple of booleans
	"""
	bit_list = []
	bit_values = []
	
	for b in bit_comb:
		res = re.match(r'(?P<neg>!)?B(?P<group>\d+)\[(?P<index>\d+)\]', b)
		bit_list.append((int(res.group("group")), int(res.group("index"))))
		bit_values.append(res.group("neg") is None)
	
	
	return (tuple(bit_list), tuple(bit_values))

def write_iterable(chip_file: TextIO, iterable: Iterable[Any], per_line: int, level: int=1, indent: str="\t") -> None:
	"""Write an iterable to a text IO stream.
	
	The iterable is split over multiple line according to per_line.
	"""
	if len(iterable) <= per_line:
		chip_file.write(f"{tuple(iterable)}")
	else:
		chip_file.write(f"(\n")
		
		for j in range(0, len(iterable), per_line):
			chip_file.write(f"{indent*(level+1)}")
			for k, item in enumerate(iterable[j:j+per_line]):
				chip_file.write(f"{item},")
				if k < per_line - 1:
					chip_file.write(" ")
			chip_file.write("\n")
		chip_file.write(f"{indent*level})")

def write_iterable_iterable(chip_file: TextIO, iteriter: Iterable[Iterable[Any]], per_line: int, level: int=0, indent: str="\t", index: bool=True) -> None:
	"""Write an iterable of iterables to a text IO stream.
	
	Every iterable is written to a new line and my be is split over
	multiple line according to per_line.
	"""
	chip_file.write(f"(\n")
	for i, iterable in enumerate(iteriter):
		chip_file.write(f"{indent*(level+1)}")
		write_iterable(
			chip_file,
			iterable,
			per_line,
			level=level+1,
			indent="\t"
		)
		chip_file.write(f",{f' # {i}' if index else ''}\n")
	chip_file.write(f"{indent*level})")

def write_dict_iterable(chip_file: TextIO, dict_iterable: Dict[Any, Iterable[Any]], per_line: int, level: int=1, indent: str="\t") -> None:
	"""Write a dict of iterables to a text IO stream.
	
	Every iterable is written to a new line and my be is split over
	multiple line according to per_line.
	"""
	chip_file.write("{\n")
	for key in sorted(dict_iterable.keys()):
		chip_file.write(f"{indent*(level+1)}{key}: ")
		write_iterable(chip_file, dict_iterable[key], per_line, level+1, indent)
		chip_file.write(f",\n")
	
	chip_file.write(f"{indent*level}}}")

def write_chip_data(chip_file: TextIO) -> None:
	"""Write chip data of iCE40 8k to a text IO stream."""
	ic = icebox.iceconfig()
	ic.setup_empty_8k()
	
	inner_tiles = get_inner_tiles(ic)
	inner_segs = get_segments(ic, inner_tiles)
	
	# add unconnected netto explicitly represent unconnected state
	inner_segs.extend([((*t, UNCONNECTED_NAME), ) for t in inner_tiles])
	inner_segs = sorted(inner_segs)
	
	inner_segs = fix_known_issues(ic, inner_segs)
	
	seg_kinds, seg_tile_map, drv_kinds = get_seg_kinds_and_drivers(ic, inner_segs)
	seg_kinds, seg_tile_map, drv_kinds = sort_net_data(seg_kinds, seg_tile_map, drv_kinds)
	#for tile_pos in seg_tile_map:
	#	if tile_pos[0] in (0, 33) or tile_pos[1] in (0, 33):
	#		print(f"{tile_pos}: {len(seg_tile_map[tile_pos])}")
	#		#print(seg_tile_map[tile_pos])
	
	name_set = {n for s in seg_kinds for x, y, n in s}
	name_list = sorted(name_set)
	name_map = {n: i for i, n in enumerate(name_list)}
	
	config_kind_list, config_tile_map = get_config_data(ic, inner_tiles)
	
	# find routing info in outer tiles
	io_tile_map = {k: v for k, v in seg_tile_map.items() if k[0] in (0, 33) or k[1] in (0, 33)}
	o = len(config_kind_list)
	get_net_config_data(ic, io_tile_map, seg_kinds, config_kind_list, config_tile_map)
	#print(f"new: {o}-{len(config_kind_list)-1}:\n{config_kind_list[o:]}")
	
	config_data_list = []
	for config_kind in config_kind_list:
		config_data = {}
		for entry in config_kind:
			bits, values = split_bit_values(entry[0])
			
			if entry[1] in ("routing", "buffer"):
				# [0] -> bits
				# [1] -> type
				# [2] -> source
				# [3] -> destination
				config_data.setdefault("connection", {}).setdefault(bits, (entry[3], []))[1].append((values, entry[2]))
			elif entry[1] in ("CarryInSet", "NegClk"):
				config_data.setdefault("tile", []).append((bits, entry[1]))
			elif entry[1] == "ColBufCtrl":
				net_name = entry[2]
				res = re.match(r"glb_netwk_(?P<index>\d+)$", net_name)
				index = int(res.group("index"))
				
				config_data.setdefault("ColBufCtrl", [None]*8)[index] = bits
			elif entry[1].startswith("LC_"):
				lut_index = int(entry[1][3:])
				tmp_bits = []
				
				for index, kind in ((8, "CarryEnable"), (9, "DffEnable"), (18, "Set_NoReset"), (19, "AsyncSetReset")):
					tmp_bits.append(((bits[index], ), kind))
				
				tmp_bits.append((
					# order bits so index is equal to binary i_3 i_2 i_1 i_0
					tuple([bits[i] for i in (4, 14, 15, 5, 6, 16, 17, 7, 3, 13, 12, 2, 1, 11, 10, 0)]),
					"TruthTable",
				))
				
				config_data.setdefault("lut", [None]*8)[lut_index] = tuple(tmp_bits)
			elif entry[1] in ("RamConfig", "RamCascade"):
				config_data.setdefault(entry[1], []).append((bits, entry[2]))
			else:
				raise ValueError(f"Unknown entry type: {entry[1]}")
		
		# insert unconnected option explicitly
		for bits, con_entry in config_data["connection"].items():
			con_entry[1].insert(0, ((False, )*len(bits), UNCONNECTED_NAME))
		
		config_data_list.append(config_data)
	
	colbufctrl_map = get_colbufctrl_data(ic, inner_tiles)
	
	lut_io_kinds, lut_io_tiles = get_lut_io(inner_segs)
	
	indent = "\t"
	level = 0
	#chip_file.write("net_names = (\n")
	#for name in name_list:
	#	chip_file.write(f"\t'{name}',\n")
	#chip_file.write(")\n\n")
	
	chip_file.write("seg_kinds = ")
	write_iterable_iterable(chip_file, seg_kinds, 5, level, indent, True)
	chip_file.write("\n\n")
	
	chip_file.write("drv_kinds = ")
	write_iterable_iterable(chip_file, drv_kinds, 20, level, indent, True)
	chip_file.write("\n\n")
	
	chip_file.write("seg_tile_map = ")
	write_dict_iterable(chip_file, seg_tile_map, 12, level, indent)
	chip_file.write("\n\n")
	
	chip_file.write("config_kinds = (\n")
	level += 1
	for i, config_data in enumerate(config_data_list):
		chip_file.write(f"{indent*level}{{\n")
		level += 1
		for key in config_data:
			chip_file.write(f"{indent*level}'{key}': ")
			if key == "connection":
				cons = config_data[key]
				chip_file.write("{\n")
				for bits in sorted(cons):
					con_entry = cons[bits]
					chip_file.write(f"{indent*(level+1)}{bits}: ('{con_entry[0]}', ")
					write_iterable(chip_file, con_entry[1], 1, level+1, indent)
					chip_file.write(f"),\n")
				
				chip_file.write(f"{indent*level}}}")
			elif key == "lut":
				write_iterable_iterable(chip_file, config_data[key], 4, level, indent, True)
			else:
				write_iterable(chip_file, config_data[key], 8, level, indent)
			chip_file.write(",\n")
		level -= 1
		chip_file.write(f"{indent*level}}}, # {i}\n")
	level -= 1
	chip_file.write(")\n\n")
	
	chip_file.write("config_tile_map = ")
	write_dict_iterable(chip_file, config_tile_map, 12, level, indent)
	chip_file.write("\n\n")
	
	chip_file.write("colbufctrl_tile_map = ")
	write_dict_iterable(chip_file, colbufctrl_map, 12, level, indent)
	chip_file.write("\n\n")
	
	chip_file.write("lut_io_kinds = ")
	write_iterable_iterable(chip_file, lut_io_kinds, 1, level, indent)
	chip_file.write("\n\n")
	
	chip_file.write("lut_io_tiles = ")
	write_iterable_iterable(chip_file, lut_io_tiles, 12, level, indent)
	chip_file.write("\n\n")

if __name__ == "__main__":
	with open("chip_database.py", "w") as chip_file:
		write_chip_data(chip_file)
