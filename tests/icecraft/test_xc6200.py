import unittest
import re
import itertools

from dataclasses import dataclass
from typing import NamedTuple, List
from queue import SimpleQueue

from domain.request_model import RequestObject
from adapters.icecraft.inter_rep import InterRep, VertexDesig, EdgeDesig, Vertex, LUTVertex, Edge
from adapters.icecraft.representation import IcecraftRepGen
from adapters.icecraft.misc import TilePosition, IcecraftBitPosition, IcecraftResource, IcecraftResCon, TILE_ALL, TILE_ALL_LOGIC, IcecraftGeneConstraint
from adapters.icecraft.chip_data import get_config_items, get_net_data
from adapters.icecraft.chip_data_utils import UNCONNECTED_NAME

class TestXC6200(unittest.TestCase):
	
	def check_xc6200_representation(self, rep):
		# out_map is map from output of XC6200 cell to (LUT) indices
		
		# sort genes by tile
		tile_gene_map = {}
		for gene in itertools.chain(rep.genes, rep.constant):
			if len(gene.alleles) == 1 and not any(gene.alleles[0].values):
				# only neutral allele
				continue
			
			tile = gene.bit_positions[0].tile
			# genes spanning multiple tiles are not supported
			self.assertTrue(all(b.tile==tile for b in gene.bit_positions))
			
			tile_gene_map.setdefault(tile, []).append(gene)
		
		# assume all tiles have the same out_map -> detect mapping by checking which neigh_op nets are used
		#config_map = {t: get_config_items(t) for t in tiles}
		
		tile_meaning_map = {}
		for tile, genes in tile_gene_map.items():
			# get all configs for tiles
			config_assem = get_config_items(tile)
			
			bit_config_map = {b: c for c in config_assem.connection for b in c.bits}
			for ll in config_assem.lut:
				for l in ll:
					for b in l.bits:
						bit_config_map[b] = l
			
			for t in config_assem.tile:
				for b in t.bits:
					bit_config_map[b] = t
			
			dst_map = {}
			src_map = {}
			tt_map = {}
			
			tile_meaning = []
			tile_meaning_map[tile] = tile_meaning
			gene_index_configs_map = []
			for gene_index, gene in enumerate(genes):
				# find config items and map the bits
				bit_gene_pos_map = {b: i for i, b in enumerate(gene.bit_positions)}
				configs = []
				gene_index_configs_map.append(configs)
				gene_pos_conf_pos_map = [None]*len(gene.bit_positions)
				
				while len(bit_gene_pos_map) > 0:
					bit = next(iter(bit_gene_pos_map))
					config = bit_config_map[bit]
					config_pos = len(configs)
					configs.append(config)
					
					if config.kind == "connection":
						dst_name = config.dst_net
						
						try:
							entry = dst_map[dst_name]
							self.assertEqual(gene_index, entry[0])
							entry[1].append(config_pos)
						except KeyError:
							dst_map[dst_name] = (gene_index, [config_pos])
					elif config.kind == "TruthTable":
						self.assertNotIn(config.index, tt_map)
						
						tt_map[config.index] = (gene_index, config_pos)
					
					for i, b in enumerate(config.bits):
						gene_pos_conf_pos_map[bit_gene_pos_map[b]] = (config_pos, i)
						
						del bit_gene_pos_map[b]
						del bit_config_map[b]
				
				# find meaning of alleles from configs
				gene_meaning = []
				tile_meaning.append(gene_meaning)
				for allele_index, allele in enumerate(gene.alleles):
					# extract values from allele
					vals = [[None]*len(c.bits) for c in configs]
					for gene_pos, (conf_index, conf_pos) in enumerate(gene_pos_conf_pos_map):
						vals[conf_index][conf_pos] = allele.values[gene_pos]
					
					allele_meaning = []
					# lookup meaning in configs
					for config_pos, (config, allele_vals) in enumerate(zip(configs, vals)):
						if config.kind == "connection":
							dst_name = config.dst_net
							
							try:
								src_index = config.values.index(tuple(allele_vals))
							except ValueError:
								self.fail(f"{allele_vals} missing for {config.bits}")
							
							src_name = config.src_nets[src_index]
							
							src_map.setdefault(src_name, []).append((gene_index, config_pos, allele_index))
							allele_meaning.append((src_name, dst_name))
						elif config.kind == "TruthTable":
							allele_meaning.append(allele_vals)
						else:
							# ignore, but keep absolute index of meaning and configs in sync
							allele_meaning.append(None)
					
					gene_meaning.append(allele_meaning)
				
			all_sigs = ["top", "lft", "bot", "rgt", "f"]
			# detect mapping
			neigh_map = {}
			for src_name in src_map:
				res = re.match(r"neigh_op_(?P<direction>\w+)_(?P<lut_index>\d)", src_name)
				if res:
					direc = res.group("direction")
					lut_index = res.group("lut_index")
					self.assertNotIn(direc, neigh_map)
					neigh_map[direc] = int(lut_index)
			
			if 4 != len(neigh_map):
				print(f"not enough inputs for tile {tile}")
				continue
			out_map = {}
			for neigh_index, neigh_dir in enumerate(all_sigs[:4]):
				loc_dir = all_sigs[(neigh_index+2)%4]
				out_map[loc_dir] = neigh_map[neigh_dir]
			
			self.assertEqual(4, len(set(out_map.values())), f"couldn't match inputs to outputs in tile {tile}")
			
			f_out = None
			for dir_index, direction in enumerate(all_sigs[:4]):
				# trace back the inputs of the LUT and collect relevant genes/meanings
				lut_index = out_map[direction]
				relevant_gene_indices = list()
				relevant_gene_indices.append(tt_map[lut_index][0])
				
				net_stack = [f"lutff_{lut_index}/in_{i}" for i in range(4)]
				done_nets = {UNCONNECTED_NAME}
				while len(net_stack) > 0:
					cur_net = net_stack.pop()
					if cur_net in done_nets:
						continue
					done_nets.add(cur_net)
					if re.match(r"neigh_op_(\w+)_(\d)", cur_net):
						neigh_dir = cur_net[9:12]
						neigh_lut = int(cur_net[13])
						self.assertIn(neigh_dir, neigh_map)
						self.assertEqual(neigh_map[neigh_dir], neigh_lut)
					elif re.match(r"lutff_(\d)/(c|l)?out", cur_net):
						other_lut = int(cur_net[6])
						# assume that another LUT output as input can only be the function unit
						if f_out is None:
							f_out = other_lut
						self.assertEqual(f_out, other_lut, "inconsistent f LUT")
					else:
						# simple net -> find source
						gene_index, config_pos_list = dst_map[cur_net]
						
						relevant_gene_indices.append(gene_index)
						# add all possible sources to the stack
						for allele_meaning in tile_meaning[gene_index]:
							for config_pos in config_pos_list:
								src_net, dst_net = allele_meaning[config_pos]
								self.assertEqual(cur_net, dst_net)
								
								net_stack.append(src_net)
				#print([tile_meaning[i] for i in relevant_gene_indices])
				
				# for all allele combinations check the behaviour of the LUT output with respect to the inputs
				src_list = [f"neigh_op_{d}_{neigh_map[d]}" for d in all_sigs[:4]]
				src_list.append(f"lutff_{f_out}/out")
				out_comb_map = {}
				for comb_index, allele_comb in enumerate(itertools.product(*[tile_meaning[i] for i in relevant_gene_indices])):
					assert len(allele_comb) == len(relevant_gene_indices)
					# create truth table and connection state according to the allele combination
					tt_state = {}
					src_state = {}
					for allele_meaning, gene_index in zip(allele_comb, relevant_gene_indices):
						configs = gene_index_configs_map[gene_index]
						assert len(allele_meaning) == len(configs)
						for meaning, config in zip(allele_meaning, configs):
							if config.kind == "connection":
								src, dst = meaning
								if dst in src_state:
									if src == UNCONNECTED_NAME:
										continue
									# only unconnected can be overwritten
									self.assertEqual(UNCONNECTED_NAME, src_state[dst])
								
								src_state[dst] = src
								
							elif config.kind == "TruthTable":
								self.assertNotIn(config.index, tt_state)
								tt_state[config.index] = meaning
							else:
								pass
					todo_stack = [(d, s) for d, s in src_state.items()]
					con_state = dict(src_state)
					while len(todo_stack) > 0:
						dst, src = todo_stack.pop()
						try:
							src_src = con_state[src]
						except KeyError:
							# no source for source -> done
							continue
						con_state[dst] = src_src
						todo_stack.append((dst, src_src))
					#print(con_state)
					matches = [True]*len(src_list)
					for src_values in itertools.product([False, True], repeat=len(src_list)):
						src_val_map = {s: v for s, v in zip(src_list, src_values)}
						# compute LUT output
						tt_index = 0
						for in_index in range(4):
							dst = f"lutff_{lut_index}/in_{in_index}"
							src = con_state[dst]
							# KeyError from here -> source that should have no influence
							val = src_val_map[src]
							if val:
								tt_index |= 1 << in_index
						lut_val = tt_state[lut_index][tt_index]
						# compare LUT output to sources
						matches = [m and (lut_val == s) for m, s in zip(matches, src_values)]
					self.assertEqual(1, sum(matches))
					match_index = matches.index(True)
					out_comb_map.setdefault(all_sigs[match_index], []).append(src_list[match_index])#comb_index)
				
				# all inputs included, except the same direction
				self.assertNotIn(direction, out_comb_map, f"should not be in {direction}")
				# check number of combinations that lead to a certain state
				comb_count = None
				for sig in all_sigs:
					if sig == direction:
						continue
					self.assertIn(sig, out_comb_map)
					if comb_count is None:
						comb_count = len(out_comb_map[sig])
					else:
						self.assertEqual(comb_count, len(out_comb_map[sig]))
				
			
			# check function unit
			# check connection options
			for out_i, out_sig in enumerate(all_sigs[:4]):
				for in_sig in all_sigs:
					if in_sig == all_sigs[(out_i+2)%5]:
						continue
	
	def test_xc6200_structure(self):
		dut = IcecraftRepGen()
		req = RequestObject()
		req["x_min"] = 2
		req["y_min"] = 2
		req["x_max"] = 4
		req["y_max"] = 4
		req["exclude_resources"] = [IcecraftResource.from_coords(TILE_ALL, TILE_ALL, n) for n in ("NET#sp4", "NET#sp12", "NET#glb_netwk", "LUT#5", "LUT#6", "LUT#7")]
		req["include_resources"] = []
		req["exclude_connections"] = [IcecraftResCon.from_coords(TILE_ALL, TILE_ALL, "", "")]
		req["include_connections"] = [IcecraftResCon.from_coords(TILE_ALL, TILE_ALL, f"NET#{s}$", f"NET#{d}$") for s, d in [
			("neigh_op_bot_1", "local_g0_1"), ("neigh_op_bot_1", "local_g1_1"), ("neigh_op_lft_4", "local_g0_4"),
			("neigh_op_rgt_2", "local_g3_2"), ("neigh_op_top_3", "local_g1_3"), ("lutff_0/out", "local_g1_0"),
			("local_g0_1", "lutff_0/in_1"), ("local_g0_1", "lutff_4/in_1"), ("local_g0_4", "lutff_0/in_0"),
			("local_g0_4", "lutff_1/in_3"), ("local_g0_4", "lutff_3/in_1"), ("local_g0_4", "lutff_4/in_0"),
			("local_g1_0", "lutff_1/in_0"), ("local_g1_0", "lutff_2/in_1"), ("local_g1_0", "lutff_3/in_0"),
			("local_g1_0", "lutff_4/in_3"), ("local_g1_1", "lutff_1/in_1"), ("local_g1_1", "lutff_2/in_2"),
			("local_g1_3", "lutff_0/in_2"), ("local_g1_3", "lutff_2/in_0"), ("local_g1_3", "lutff_3/in_3"),
			("local_g1_3", "lutff_4/in_2"), ("local_g3_2", "lutff_0/in_3"), ("local_g3_2", "lutff_1/in_2"),
			("local_g3_2", "lutff_2/in_3"), ("local_g3_2", "lutff_3/in_2")
		]] + [
			IcecraftResCon.from_coords(TILE_ALL, TILE_ALL, f"NET#lutff_{l}/in_{i}$", f"LUT#{l}$") for l in range(5) for i in range(4)
		] + [
			IcecraftResCon.from_coords(TILE_ALL, TILE_ALL, f"LUT#{l}$", f"NET#lutff_{l}/out") for l in range(5)
		]
		req["output_lutffs"] = []
		req["lut_functions"] = []
		req["gene_constraints"] = [
			IcecraftGeneConstraint(
				tuple(IcecraftBitPosition.from_coords(TILE_ALL_LOGIC, TILE_ALL_LOGIC, *c) for c in b),
				tuple(
					tuple((s & (1<<i)) > 0 for s in range(16)) for i in range(4)
				)
			) for b in [
				(
					(2, 40), (3, 40), (3, 41), (2, 41), (2, 42), (3, 42), (3, 43), (2, 43),
					(2, 39), (3, 39), (3, 38), (2, 38), (2, 37), (3, 37), (3, 36), (2, 36)
				),
				(
					(4, 40), (5, 40), (5, 41), (4, 41), (4, 42), (5, 42), (5, 43), (4, 43),
					(4, 39), (5, 39), (5, 38), (4, 38), (4, 37), (5, 37), (5, 36), (4, 36)
				),
				(
					(6, 40), (7, 40), (7, 41), (6, 41), (6, 42), (7, 42), (7, 43), (6, 43),
					(6, 39), (7, 39), (7, 38), (6, 38), (6, 37), (7, 37), (7, 36), (6, 36)
				),
				(
					(8, 40), (9, 40), (9, 41), (8, 41), (8, 42), (9, 42), (9, 43), (8, 43),
					(8, 39), (9, 39), (9, 38), (8, 38), (8, 37), (9, 37), (9, 36), (8, 36)
				)
			]
		] + [# truth table LUT 0
			IcecraftGeneConstraint(
				tuple(IcecraftBitPosition.from_coords(TILE_ALL_LOGIC, TILE_ALL_LOGIC, *c) for c in [
					(0, 40), (1, 40), (1, 41), (0, 41), (0, 42), (1, 42), (1, 43), (0, 43),
					(0, 39), (1, 39), (1, 38), (0, 38), (0, 37), (1, 37), (1, 36), (0, 36)
				]),
				(
					(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
					(False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, True),
					(False, False, False, False, False, False, False, False, False, False, True, True, False, False, True, True),
					(False, False, False, False, False, False, False, False, False, True, False, True, False, True, False, True),
					(False, False, False, False, False, False, False, False, True, False, True, False, True, False, True, False),
					(False, False, False, False, False, False, False, False, True, True, False, False, True, True, False, False),
					(False, False, False, False, False, False, False, False, True, True, True, True, False, False, False, False),
					(False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True),
					(False, False, False, False, False, False, True, True, False, False, False, False, False, False, True, True),
					(False, False, False, False, False, False, True, True, True, True, False, False, True, True, True, True),
					(False, False, False, False, False, False, True, True, True, True, True, True, False, False, True, True),
					(False, False, False, False, False, True, False, True, False, False, False, False, False, True, False, True),
					(False, False, False, False, False, True, False, True, True, False, True, False, True, True, True, True),
					(False, False, False, False, False, True, False, True, True, True, True, True, False, True, False, True),
					(False, False, False, False, True, False, True, False, False, False, False, False, True, False, True, False),
					(False, False, False, False, True, False, True, False, False, True, False, True, True, True, True, True),
					(False, False, False, False, True, False, True, False, True, True, True, True, True, False, True, False),
					(False, False, False, False, True, True, False, False, False, False, False, False, True, True, False, False),
					(False, False, False, False, True, True, False, False, False, False, True, True, True, True, True, True),
					(False, False, False, False, True, True, False, False, True, True, True, True, True, True, False, False),
					(False, False, False, False, True, True, True, True, False, False, False, False, False, False, False, False),
					(False, False, False, False, True, True, True, True, False, False, False, False, True, True, True, True),
					(False, False, False, False, True, True, True, True, False, False, True, True, False, False, True, True),
					(False, False, False, False, True, True, True, True, False, True, False, True, False, True, False, True),
					(False, False, False, False, True, True, True, True, True, False, True, False, True, False, True, False),
					(False, False, False, False, True, True, True, True, True, True, False, False, True, True, False, False),
					(False, False, False, False, True, True, True, True, True, True, True, True, False, False, False, False),
					(False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True),
					(False, False, False, True, False, False, False, True, False, False, False, True, False, False, False, True),
					(False, False, False, True, False, False, False, True, True, False, True, True, True, False, True, True),
					(False, False, False, True, False, False, False, True, True, True, False, True, True, True, False, True),
					(False, False, False, True, True, False, True, True, False, False, False, True, True, False, True, True),
					(False, False, False, True, True, True, False, True, False, False, False, True, True, True, False, True),
					(False, False, True, False, False, False, True, False, False, False, True, False, False, False, True, False),
					(False, False, True, False, False, False, True, False, False, True, True, True, False, True, True, True),
					(False, False, True, False, False, False, True, False, True, True, True, False, True, True, True, False),
					(False, False, True, False, False, True, True, True, False, False, True, False, False, True, True, True),
					(False, False, True, False, True, True, True, False, False, False, True, False, True, True, True, False),
					(False, False, True, True, False, False, False, False, False, False, True, True, False, False, False, False),
					(False, False, True, True, False, False, False, False, False, False, True, True, True, True, True, True),
					(False, False, True, True, False, False, False, False, True, True, True, True, True, True, False, False),
					(False, False, True, True, False, False, True, True, False, False, False, False, False, False, False, False),
					(False, False, True, True, False, False, True, True, False, False, False, False, True, True, True, True),
					(False, False, True, True, False, False, True, True, False, False, True, True, False, False, True, True),
					(False, False, True, True, False, False, True, True, False, True, False, True, False, True, False, True),
					(False, False, True, True, False, False, True, True, True, False, True, False, True, False, True, False),
					(False, False, True, True, False, False, True, True, True, True, False, False, True, True, False, False),
					(False, False, True, True, False, False, True, True, True, True, True, True, False, False, False, False),
					(False, False, True, True, False, False, True, True, True, True, True, True, True, True, True, True),
					(False, False, True, True, False, True, False, True, False, False, True, True, False, True, False, True),
					(False, False, True, True, True, False, True, False, False, False, True, True, True, False, True, False),
					(False, False, True, True, True, True, False, False, False, False, True, True, True, True, False, False),
					(False, False, True, True, True, True, True, True, False, False, False, False, True, True, False, False),
					(False, False, True, True, True, True, True, True, False, False, True, True, False, False, False, False),
					(False, False, True, True, True, True, True, True, False, False, True, True, True, True, True, True),
					(False, True, False, False, False, True, False, False, False, True, False, False, False, True, False, False),
					(False, True, False, False, False, True, False, False, False, True, True, True, False, True, True, True),
					(False, True, False, False, False, True, False, False, True, True, True, False, True, True, True, False),
					(False, True, False, False, False, True, True, True, False, True, False, False, False, True, True, True),
					(False, True, False, False, True, True, True, False, False, True, False, False, True, True, True, False),
					(False, True, False, True, False, False, False, False, False, True, False, True, False, False, False, False),
					(False, True, False, True, False, False, False, False, False, True, False, True, True, True, True, True),
					(False, True, False, True, False, False, False, False, True, True, True, True, True, False, True, False),
					(False, True, False, True, False, False, True, True, False, True, False, True, False, False, True, True),
					(False, True, False, True, False, True, False, True, False, False, False, False, False, False, False, False),
					(False, True, False, True, False, True, False, True, False, False, False, False, True, True, True, True),
					(False, True, False, True, False, True, False, True, False, False, True, True, False, False, True, True),
					(False, True, False, True, False, True, False, True, False, True, False, True, False, True, False, True),
					(False, True, False, True, False, True, False, True, True, False, True, False, True, False, True, False),
					(False, True, False, True, False, True, False, True, True, True, False, False, True, True, False, False),
					(False, True, False, True, False, True, False, True, True, True, True, True, False, False, False, False),
					(False, True, False, True, False, True, False, True, True, True, True, True, True, True, True, True),
					(False, True, False, True, True, False, True, False, False, True, False, True, True, False, True, False),
					(False, True, False, True, True, True, False, False, False, True, False, True, True, True, False, False),
					(False, True, False, True, True, True, True, True, False, False, False, False, True, False, True, False),
					(False, True, False, True, True, True, True, True, False, True, False, True, False, False, False, False),
					(False, True, False, True, True, True, True, True, False, True, False, True, True, True, True, True),
					(False, True, True, False, False, True, True, False, False, True, True, False, False, True, True, False),
					(False, True, True, True, False, False, True, False, False, True, True, True, False, False, True, False),
					(False, True, True, True, False, True, False, False, False, True, True, True, False, True, False, False),
					(False, True, True, True, False, True, True, True, False, False, True, False, False, False, True, False),
					(False, True, True, True, False, True, True, True, False, True, False, False, False, True, False, False),
					(False, True, True, True, False, True, True, True, False, True, True, True, False, True, True, True),
					(True, False, False, False, True, False, False, False, True, False, False, False, True, False, False, False),
					(True, False, False, False, True, False, False, False, True, False, True, True, True, False, True, True),
					(True, False, False, False, True, False, False, False, True, True, False, True, True, True, False, True),
					(True, False, False, False, True, False, True, True, True, False, False, False, True, False, True, True),
					(True, False, False, False, True, True, False, True, True, False, False, False, True, True, False, True),
					(True, False, False, True, True, False, False, True, True, False, False, True, True, False, False, True),
					(True, False, True, False, False, False, False, False, True, False, True, False, False, False, False, False),
					(True, False, True, False, False, False, False, False, True, False, True, False, True, True, True, True),
					(True, False, True, False, False, False, False, False, True, True, True, True, False, True, False, True),
					(True, False, True, False, False, False, True, True, True, False, True, False, False, False, True, True),
					(True, False, True, False, False, True, False, True, True, False, True, False, False, True, False, True),
					(True, False, True, False, True, False, True, False, False, False, False, False, False, False, False, False),
					(True, False, True, False, True, False, True, False, False, False, False, False, True, True, True, True),
					(True, False, True, False, True, False, True, False, False, False, True, True, False, False, True, True),
					(True, False, True, False, True, False, True, False, False, True, False, True, False, True, False, True),
					(True, False, True, False, True, False, True, False, True, False, True, False, True, False, True, False),
					(True, False, True, False, True, False, True, False, True, True, False, False, True, True, False, False),
					(True, False, True, False, True, False, True, False, True, True, True, True, False, False, False, False),
					(True, False, True, False, True, False, True, False, True, True, True, True, True, True, True, True),
					(True, False, True, False, True, True, False, False, True, False, True, False, True, True, False, False),
					(True, False, True, False, True, True, True, True, False, False, False, False, False, True, False, True),
					(True, False, True, False, True, True, True, True, True, False, True, False, False, False, False, False),
					(True, False, True, False, True, True, True, True, True, False, True, False, True, True, True, True),
					(True, False, True, True, False, False, False, True, True, False, True, True, False, False, False, True),
					(True, False, True, True, True, False, False, False, True, False, True, True, True, False, False, False),
					(True, False, True, True, True, False, True, True, False, False, False, True, False, False, False, True),
					(True, False, True, True, True, False, True, True, True, False, False, False, True, False, False, False),
					(True, False, True, True, True, False, True, True, True, False, True, True, True, False, True, True),
					(True, True, False, False, False, False, False, False, True, True, False, False, False, False, False, False),
					(True, True, False, False, False, False, False, False, True, True, False, False, True, True, True, True),
					(True, True, False, False, False, False, False, False, True, True, True, True, False, False, True, True),
					(True, True, False, False, False, False, True, True, True, True, False, False, False, False, True, True),
					(True, True, False, False, False, True, False, True, True, True, False, False, False, True, False, True),
					(True, True, False, False, True, False, True, False, True, True, False, False, True, False, True, False),
					(True, True, False, False, True, True, False, False, False, False, False, False, False, False, False, False),
					(True, True, False, False, True, True, False, False, False, False, False, False, True, True, True, True),
					(True, True, False, False, True, True, False, False, False, False, True, True, False, False, True, True),
					(True, True, False, False, True, True, False, False, False, True, False, True, False, True, False, True),
					(True, True, False, False, True, True, False, False, True, False, True, False, True, False, True, False),
					(True, True, False, False, True, True, False, False, True, True, False, False, True, True, False, False),
					(True, True, False, False, True, True, False, False, True, True, True, True, False, False, False, False),
					(True, True, False, False, True, True, False, False, True, True, True, True, True, True, True, True),
					(True, True, False, False, True, True, True, True, False, False, False, False, False, False, True, True),
					(True, True, False, False, True, True, True, True, True, True, False, False, False, False, False, False),
					(True, True, False, False, True, True, True, True, True, True, False, False, True, True, True, True),
					(True, True, False, True, False, False, False, True, True, True, False, True, False, False, False, True),
					(True, True, False, True, True, False, False, False, True, True, False, True, True, False, False, False),
					(True, True, False, True, True, True, False, True, False, False, False, True, False, False, False, True),
					(True, True, False, True, True, True, False, True, True, False, False, False, True, False, False, False),
					(True, True, False, True, True, True, False, True, True, True, False, True, True, True, False, True),
					(True, True, True, False, False, False, True, False, True, True, True, False, False, False, True, False),
					(True, True, True, False, False, True, False, False, True, True, True, False, False, True, False, False),
					(True, True, True, False, True, True, True, False, False, False, True, False, False, False, True, False),
					(True, True, True, False, True, True, True, False, False, True, False, False, False, True, False, False),
					(True, True, True, False, True, True, True, False, True, True, True, False, True, True, True, False),
					(True, True, True, True, False, False, False, False, False, False, False, False, False, False, False, False),
					(True, True, True, True, False, False, False, False, False, False, False, False, True, True, True, True),
					(True, True, True, True, False, False, False, False, False, False, True, True, False, False, True, True),
					(True, True, True, True, False, False, False, False, False, True, False, True, False, True, False, True),
					(True, True, True, True, False, False, False, False, True, False, True, False, True, False, True, False),
					(True, True, True, True, False, False, False, False, True, True, False, False, True, True, False, False),
					(True, True, True, True, False, False, False, False, True, True, True, True, False, False, False, False),
					(True, True, True, True, False, False, False, False, True, True, True, True, True, True, True, True),
					(True, True, True, True, False, False, True, True, False, False, False, False, False, False, True, True),
					(True, True, True, True, False, False, True, True, True, True, False, False, False, False, False, False),
					(True, True, True, True, False, False, True, True, True, True, True, True, False, False, True, True),
					(True, True, True, True, False, True, False, True, False, False, False, False, False, True, False, True),
					(True, True, True, True, False, True, False, True, True, False, True, False, False, False, False, False),
					(True, True, True, True, False, True, False, True, True, True, True, True, False, True, False, True),
					(True, True, True, True, True, False, True, False, False, False, False, False, True, False, True, False),
					(True, True, True, True, True, False, True, False, False, True, False, True, False, False, False, False),
					(True, True, True, True, True, False, True, False, True, True, True, True, True, False, True, False),
					(True, True, True, True, True, True, False, False, False, False, False, False, True, True, False, False),
					(True, True, True, True, True, True, False, False, False, False, True, True, False, False, False, False),
					(True, True, True, True, True, True, False, False, True, True, True, True, True, True, False, False),
					(True, True, True, True, True, True, True, True, False, False, False, False, False, False, False, False),
					(True, True, True, True, True, True, True, True, False, False, False, False, True, True, True, True),
					(True, True, True, True, True, True, True, True, False, False, True, True, False, False, True, True),
					(True, True, True, True, True, True, True, True, False, True, False, True, False, True, False, True),
					(True, True, True, True, True, True, True, True, True, False, True, False, True, False, True, False),
					(True, True, True, True, True, True, True, True, True, True, False, False, True, True, False, False),
					(True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False),
					(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
				)
			)
		]
		
		res = dut(req)
		
		self.check_xc6200_representation(res)
	
	@staticmethod
	def find_routes(need, rep):
		src_vtx = rep.get_vertex(need.src)
		dst_vtx = rep.get_vertex(need.dst)
		routes = []
		
		@dataclass
		class RouteTask:
			vtx: Vertex
			path: List[EdgeDesig]
		
		visited = set()
		fifo = SimpleQueue()
		fifo.put(RouteTask(src_vtx, []))
		while not fifo.empty():
			task = fifo.get()
			if task.vtx == dst_vtx:
				routes.append(task.path)
				continue
			
			if task.vtx.desigs[0] in visited:
				# already seen -> cycles not interesting
				continue
			
			# no spans
			if re.match(r"NET#sp", task.vtx.desigs[0].name):
				continue
			
			visited.add(task.vtx.desigs[0])
			
			for edge in task.vtx.iter_out_edges():
				new_path = list(task.path)
				new_path.append(edge.desig)
				new_task = RouteTask(edge.dst, new_path)
				fifo.put(new_task)
		
		return routes
	
	@classmethod
	def create_routes(cls, needs, rep):
		res_dict = {}
		for need in needs:
			res = cls.find_routes(need, rep)
			res_dict[need] = res
		
		return res_dict
	
	#@unittest.skip("experimental, takes a long(!) time")
	def test_simple_xc6200(self):
		x = 16
		y = 17
		mid_tile = TilePosition(x, y)
		top_tile = TilePosition(x, y+1)
		lft_tile = TilePosition(x-1, y)
		bot_tile = TilePosition(x, y-1)
		rgt_tile = TilePosition(x+1, y)
		tiles = [mid_tile, lft_tile, rgt_tile, top_tile, bot_tile]
		
		config_map = {t: get_config_items(t) for t in tiles}
		
		raw_nets = get_net_data(tiles)
		rep = InterRep(raw_nets, config_map)
		
		class LUTPlacement(NamedTuple):
			func: int
			top_out: int
			lft_out: int
			bot_out: int
			rgt_out: int
		
		def lut_out_desig(tile, lut_index):
			return VertexDesig.from_net_name(tile, f"lutff_{lut_index}/out")
		
		@dataclass(frozen=True)
		class ConNeed(EdgeDesig):
			def __post_init__(self):
				pass
			
			def __repr__(self):
				return f"({self.src.tile.x}, {self.src.tile.y}) {self.src.name} -> ({self.dst.tile.x}, {self.dst.tile.y}) {self.dst.name}"
			
			@classmethod
			def from_lut_src(cls, src_tile, src_index, dst):
				src = lut_out_desig(src_tile, src_index)
				return cls(src, dst)
		
		all_needs = []
		for src_tile in [mid_tile, top_tile, lft_tile, bot_tile, rgt_tile]:
			for src_index in range(8):
				src = lut_out_desig(src_tile, src_index)
				for dst_index in range(8):
					dst = VertexDesig.from_lut_index(mid_tile, dst_index)
					all_needs.append(ConNeed(src, dst))
		
		all_routes = self.create_routes(all_needs, rep)
		#for need, routes in all_routes.items():
		#	print(f"{need}:")
		#	for i, route in enumerate(routes):
		#		s = "=".join(f"({e.src.tile.x}, {e.src.tile.y}) {e.src.name} -> {e.dst.name}" for e in route)
		#		print(f"{i}: {s}")
		
		@dataclass
		class RoutingTask:
			grp_index: int
			need_index: int
			route_index: int
			to_clear: List[EdgeDesig]
			grp_routes: List[List[EdgeDesig]]
		
		solutions = {}
		for c, raw_indices in enumerate(itertools.permutations(range(8), 5)):
			print(f"{c}/{8*7*6*5*4}")
			plmt = LUTPlacement(*raw_indices)
			# create connection requirements
			
			# split in need groups; inside a need group are options,
			# i.e. only one will be relaized, so they can share incompatible
			# configurations, while between need groups only compatible
			# configurations can be shared
			need_grps = []
			top_in = lut_out_desig(top_tile, plmt.bot_out)
			lft_in = lut_out_desig(lft_tile, plmt.rgt_out)
			bot_in = lut_out_desig(bot_tile, plmt.top_out)
			rgt_in = lut_out_desig(rgt_tile, plmt.lft_out)
			f_out = lut_out_desig(mid_tile, plmt.func)
			# f -> all at same time -> all in own need group
			f_desig = VertexDesig.from_lut_index(mid_tile, plmt.func)
			need_grps.extend([[ConNeed(s, f_desig)] for s in [top_in, lft_in, bot_in, rgt_in]])
			#for i, ng in enumerate(need_grps):
			#	print(f"grp {i}")
			#	for n in ng:
			#		print(f"{n}")
			#		for r in all_routes[n]:
			#			print(r)
			#return
			
			top_desig = VertexDesig.from_lut_index(mid_tile, plmt.top_out)
			need_grps.append([ConNeed(s, top_desig) for s in [f_out, lft_in, bot_in, rgt_in]])
			
			lft_desig = VertexDesig.from_lut_index(mid_tile, plmt.lft_out)
			need_grps.append([ConNeed(s, lft_desig) for s in [f_out, top_in, bot_in, rgt_in]])
			
			bot_desig = VertexDesig.from_lut_index(mid_tile, plmt.bot_out)
			need_grps.append([ConNeed(s, bot_desig) for s in [f_out, top_in, lft_in, rgt_in]])
			
			rgt_desig = VertexDesig.from_lut_index(mid_tile, plmt.rgt_out)
			need_grps.append([ConNeed(s, rgt_desig) for s in [f_out, top_in, lft_in, bot_in]])
			
			# estimate upper limit of combinations
			limit = 1
			for ng in need_grps:
				for n in ng:
					limit *= len(all_routes[n])
			print(f"at most {limit}")
			routings = []
			
			stack = [RoutingTask(0, 0, 0, [], [])]
			cur_routing = []
			#pdb.set_trace()
			while len(stack) > 0:
				task = stack.pop()
				#print(len(stack))
				#print(cur_routing)
				# clean up
				if task.to_clear:
					for ed in task.to_clear:
						edge = rep.get_edge(ed)
						assert not edge.available
						edge.available = True
					cur_routing.pop()
					continue
				
				if task.grp_index == len(need_grps):
					# solution found
					print(f"found for {plmt}")
					routings.append(list(cur_routing))
					break
					#continue
				
				need_grp = need_grps[task.grp_index]
				if task.need_index == len(need_grp):
					# need grp done
					#print(f"need grp {task.grp_index} done")
					cur_routing.append(task.grp_routes)
					# set bits in rep
					set_set = set()
					for route in task.grp_routes:
						for ed in route:
							edge = rep.get_edge(ed)
							if edge.available:
								set_set.add(ed)
								edge.available = False
					#enable resetting
					stack.append(RoutingTask(
						task.grp_index,
						0,
						0,
						list(set_set),
						[]
					))
					# continue with next need grp
					stack.append(RoutingTask(
						task.grp_index+1,
						0,
						0,
						[],
						[]
					))
					continue
				
				need = need_grp[task.need_index]
				routes = all_routes[need]
				route_index = task.route_index
				# search for possible route
				while route_index < len(routes):
					valid = True
					for ed in routes[route_index]:
						edge = rep.get_edge(ed)
						if isinstance(edge.dst, LUTVertex):
							
							continue
						not_avail = [e for e in edge.dst.iter_in_edges() if not e.available]
						# more than one edeg not available -> multi options for other need group
						# one edge not available -> fixed connection, bad if not the dame connection is required
						if (len(not_avail) > 1) or (len(not_avail) == 1 and not_avail[0] != edge):
							valid = False
							#print(f"fail for {ed}")
							break
					if valid:
						break
					
					route_index += 1
				
				if route_index == len(routes):
					# no more routes to try
					#print(f"nothing more for grp {task.grp_index}, need {task.need_index}")
					continue
				
				# continue later with next route ...
				stack.append(RoutingTask(
					task.grp_index,
					task.need_index,
					route_index+1,
					[],
					task.grp_routes
				))
				# ... but first go to next need
				stack.append(RoutingTask(
					task.grp_index,
					task.need_index+1,
					0,
					[],
					task.grp_routes+[routes[route_index]]
				))
			
			if len(routings) > 0:
				solutions[plmt] = routings
		
		self.assertTrue(solutions)
		print(f"{len(solutions)} found:")
		for plmt, routings in solutions.items():
			print(f"{plmt}: {len(routings)}")
	
