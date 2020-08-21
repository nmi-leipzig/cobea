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

def get_conf_data(ic, tiles):
	conf_kinds = []
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
		
		conf_kind = tuple(sorted(conf_set))
		try:
			conf_kind_index = conf_kind_map[conf_kind]
		except KeyError:
			conf_kind_index = len(conf_kinds)
			conf_kinds.append(conf_kind)
			conf_kind_map[conf_kind] = conf_kind_index
		
		conf_tile_map.setdefault(conf_kind_index, list()).append(tile_pos)
	
	return conf_kinds, conf_tile_map

def get_net_conf_data(ic, tile_map, seg_kinds, conf_kinds, conf_tile_map):
	conf_kind_map = {c: i for i, c in enumerate(conf_kinds)}
	for tile_pos in sorted(tile_map):
		# get rquested nets
		nets = set(seg_kinds[s][r][2] for s, r in tile_map[tile_pos])
		print(nets)
		tile_db = ic.tile_db(*tile_pos)
		

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
	
	conf_kinds, conf_tile_map = get_conf_data(ic, inner_tiles)
	
	#TODO: find routing info in outer tiles
	io_tile_map = {k: v for k, v in tile_map.items() if k[0] in (0, 33) or k[1] in (0, 33)}
	
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
