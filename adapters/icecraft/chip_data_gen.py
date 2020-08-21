#!/usr/bin/env python3

import sys
import re

sys.path.append("/usr/local/bin")
import icebox

def get_inner_tiles(ic):
	inner_tiles = set()
	for x in range(1, ic.max_x):
		for y in range(1, ic.max_y):
			if ic.tile(x, y) is None:
				continue
			inner_tiles.add((x, y))
	return inner_tiles

def get_segments(ic, tiles):
	all_segments_set = ic.group_segments(tiles, connect_gb=False)
	
	# list
	all_segments = sorted(all_segments_set)
	
	return all_segments

def get_seg_kinds(all_segments):
	# kinds of segments
	seg_kinds = []
	# mapping seg_kind -> index
	seg_kind_map = {}
	# mapping (x, y) -> list of (seg_kind, role)
	tile_map = {}
	
	for seg_group in all_segments:
		# generate seg_kind
		sorted_seg_group = sorted(seg_group)
		base = sorted_seg_group[0]
		
		seg_kind = tuple([(x-base[0], y-base[1], r) for x, y, r in sorted_seg_group])
		
		try:
			seg_kind_index = seg_kind_map[seg_kind]
		except KeyError:
			seg_kind_index = len(seg_kinds)
			seg_kinds.append(seg_kind)
			seg_kind_map[seg_kind] = seg_kind_index
		
		for role, entry in enumerate(sorted_seg_group):
			tile_id = (entry[0], entry[1])
			#if tile_id not in inner_tiles:
			#	continue
			# create relative segements
			tile_map.setdefault(tile_id, set()).add((seg_kind_index, role))
	
	return seg_kinds, tile_map

def add_conf_set(conf_kind_list, conf_kind_map, conf_tile_map, tile_pos, conf_set):
	conf_kind = tuple(sorted(conf_set))
	try:
		conf_kind_index = conf_kind_map[conf_kind]
	except KeyError:
		conf_kind_index = len(conf_kind_list)
		conf_kind_list.append(conf_kind)
		conf_kind_map[conf_kind] = conf_kind_index
	
	conf_tile_map.setdefault(conf_kind_index, list()).append(tile_pos)

def get_conf_data(ic, tiles):
	conf_kind_list = []
	conf_kind_map = {}
	conf_tile_map = {}
	
	for tile_pos in sorted(tiles):
		tile_db = ic.tile_db(*tile_pos)
		
		conf_set = set()
		for entry in tile_db:
			if not ic.tile_has_entry(*tile_pos, entry):
				print("Tile ({},{}) has no entry {}".format(*tile_pos, entry))
				continue
			
			conf_set.add((tuple(entry[0]), *entry[1:]))
		
		add_conf_set(conf_kind_list, conf_kind_map, conf_tile_map, tile_pos, conf_set)
	
	return conf_kind_list, conf_tile_map

def get_net_conf_data(ic, tile_map, seg_kinds, conf_kind_list, conf_tile_map):
	conf_kind_map = {c: i for i, c in enumerate(conf_kind_list)}
	for tile_pos in sorted(tile_map):
		# get rquested nets
		nets = set(seg_kinds[s][r][2] for s, r in tile_map[tile_pos])
		#print(f"{tile_pos} ({len(nets)}): {list(nets)[:5]}")
		tile_db = ic.tile_db(*tile_pos)
		
		conf_set = set()
		for entry in tile_db:
			# important for io tiles as the spans differ between left/right and top/bottom
			if not ic.tile_has_entry(*tile_pos, entry):
				#print(f"Tile {tile_pos} has no entry {entry}")
				continue
			
			if entry[1] not in ("buffer", "routing"):
				continue
			
			if entry[3] not in nets:
				continue
			
			conf_set.add((tuple(entry[0]), *entry[1:]))
		
		add_conf_set(conf_kind_list, conf_kind_map, conf_tile_map, tile_pos, conf_set)

def sort_net_data(seg_kinds, tile_map):
	# sort seg_kinds
	sorted_indices = sorted(range(len(seg_kinds)), key=lambda i: seg_kinds[i])
	srt_seg_kinds = [seg_kinds[i] for i in sorted_indices]
	# update tile_map
	index_map = {o: n for n, o in enumerate(sorted_indices)}
	srt_tile_map = {}
	for tile_id in tile_map:
		srt_tile_map[tile_id] = [(index_map[s], r) for s, r in tile_map[tile_id]]
	
	return srt_seg_kinds, srt_tile_map

def get_nets_for_tile(seg_kinds, tile_pos, seg_indices):
	nets = []
	for seg_index, role in seg_indices:
		seg_kind = seg_kinds[seg_index]
		x_off = tile_pos[0] - seg_kind[role][0]
		y_off = tile_pos[1] - seg_kind[role][1]
		net = tuple((x+x_off, y+y_off, n) for x, y, n in seg_kind)
		nets.append(net)
	
	return nets

def split_bit_values(bit_comb):
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

def write_chip_data(chip_file):
	ic = icebox.iceconfig()
	ic.setup_empty_8k()
	
	inner_tiles = get_inner_tiles(ic)
	inner_segs = get_segments(ic, inner_tiles)
	seg_kinds, tile_map = get_seg_kinds(inner_segs)
	seg_kinds, tile_map = sort_net_data(seg_kinds, tile_map)
	#for tile_pos in tile_map:
	#	if tile_pos[0] in (0, 33) or tile_pos[1] in (0, 33):
	#		print(f"{tile_pos}: {len(tile_map[tile_pos])}")
	#		#print(tile_map[tile_pos])
	
	name_set = {n for s in seg_kinds for x, y, n in s}
	name_list = sorted(name_set)
	name_map = {n: i for i, n in enumerate(name_list)}
	
	conf_kind_list, conf_tile_map = get_conf_data(ic, inner_tiles)
	
	#TODO: find routing info in outer tiles
	io_tile_map = {k: v for k, v in tile_map.items() if k[0] in (0, 33) or k[1] in (0, 33)}
	o = len(conf_kind_list)
	get_net_conf_data(ic, io_tile_map, seg_kinds, conf_kind_list, conf_tile_map)
	#print(f"new: {o}-{len(conf_kind_list)-1}:\n{conf_kind_list[o:]}")
	
	conf_data_list = []
	for conf_kind in conf_kind_list:
		conf_data = {}
		for entry in conf_kind:
			bits, values = split_bit_values(entry[0])
			
			if entry[1] in ("routing", "buffer"):
				# [0] -> bits
				# [1] -> type
				# [2] -> source
				# [3] -> destination
				conf_data.setdefault("connection", {}).setdefault(bits, (entry[3], []))[1].append((values, entry[2]))
			elif entry[1] in ("CarryInSet", "NegClk"):
				conf_data.setdefault("tile", []).append((bits, entry[1]))
			elif entry[1] == "ColBufCtrl":
				net_name = entry[2]
				res = re.match(r"glb_netwk_(?P<index>\d+)$", net_name)
				index = int(res.group("index"))
				
				conf_data.setdefault("ColBufCtrl", [None]*8)[index] = bits
			elif entry[1].startswith("LC_"):
				lut_index = int(entry[1][3:])
				tmp_bits = []
				
				for index, kind in ((8, "CarryEnable"), (9, "DffEnable"), (18, "Set_NoReset"), (19, "AsyncSetReset")):
					tmp_bits.append(([bits[index]], kind))
				
				tmp_bits.append((
					# order bits so index is equal to binary i_3 i_2 i_1 i_0
					tuple([bits[i] for i in (4, 14, 15, 5, 6, 16, 17, 7, 3, 13, 12, 2, 1, 11, 10, 0)]),
					"TruthTable",
				))
				
				conf_data.setdefault("lut", [None]*8)[lut_index] = tmp_bits
			elif entry[1] in ("RamConfig", "RamCascade"):
				conf_data.setdefault(entry[1], []).append((bits, entry[2]))
			else:
				raise ValueError(f"Unknown entry type: {entry[1]}")
		conf_data_list.append(conf_data)
	
	#chip_file.write("net_names = (\n")
	#for name in name_list:
	#	chip_file.write(f"\t'{name}',\n")
	#chip_file.write(")\n\n")
	
	chip_file.write("segment_kinds = [\n")
	for i, seg_group in enumerate(seg_kinds):
		per_line = 5
		#segment_group = tuple((x, y, name_map[n] ) for x, y, n in seg_group)
		segment_group = seg_group
		if len(segment_group) <= per_line:
			chip_file.write(f"\t{segment_group}, # {i}\n")
		else:
			chip_file.write("\t(\n")
			
			for j in range(0, len(segment_group), per_line):
				chip_file.write("\t\t")
				for k, seg in enumerate(segment_group[j:j+per_line]):
					chip_file.write(f"{seg},")
					if k < per_line - 1:
						chip_file.write(" ")
				chip_file.write("\n")
			chip_file.write(f"\t), # {i}\n")
	chip_file.write("]\n\n")
	
	chip_file.write("tile_map = {\n")
	for key in sorted(tile_map.keys()):
		chip_file.write("\t{}: {},\n".format(key, tuple(sorted(tile_map[key]))))
	chip_file.write("}\n\n")
	

if __name__ == "__main__":
	with open("chip_data.py", "w") as chip_file:
		write_chip_data(chip_file)
