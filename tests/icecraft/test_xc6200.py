import unittest
import re
import itertools

from dataclasses import dataclass, field
from typing import NamedTuple, List, NewType, Tuple, Union, Mapping
from queue import SimpleQueue

from domain.model import Gene
from domain.request_model import RequestObject
from adapters.icecraft.config_item import ConfigItem
from adapters.icecraft.inter_rep import InterRep, VertexDesig, EdgeDesig, Vertex, LUTVertex, Edge
from adapters.icecraft.xc6200 import XC6200Direction, XC6200Port, XC6200RepGen
from adapters.icecraft.misc import IcecraftPosition, IcecraftBitPosition, IcecraftResource,\
IcecraftResCon, TILE_ALL, TILE_ALL_LOGIC, IcecraftGeneConstraint
from adapters.icecraft.chip_data import get_config_items, get_net_data
from adapters.icecraft.chip_data_utils import UNCONNECTED_NAME
from adapters.icecraft.position_transformation import IcecraftPosTransLibrary

PartMeaning = NewType("PartMeaning", Union[Tuple[bool, ...], Tuple[str, str], None])
AlleleMeaning = NewType("AlleleMeaning", List[PartMeaning])
GeneMeaning = NewType("GeneMeaning", List[AlleleMeaning])

@dataclass
class TTIndex:
	gene_index: int
	config_pos: int

@dataclass
class SrcIndex(TTIndex):
	allele_index: int
	src_net_index: int

@dataclass
class DstIndex:
	gene_index: int
	config_pos_list: List[int]

@dataclass
class TileData:
	tile: IcecraftPosition
	genes: List[Gene] = field(default_factory=list)
	tile_meaning: List[GeneMeaning] = field(default_factory=list)
	src_map: Mapping[str, List[SrcIndex]] = field(default_factory=dict)
	dst_map: Mapping[str, DstIndex] = field(default_factory=dict)
	tt_map: Mapping[int, TTIndex] = field(default_factory=dict)
	gene_index_configs_map: List[List[ConfigItem]] = field(default_factory=list)

class NoOutMapError(Exception):
	pass

class TestXC6200Direction(unittest.TestCase):
	def test_opposite_consistency(self):
		for dut in XC6200Direction:
			if dut == XC6200Direction.f:
				continue
			
			with self.subTest(desc=f"{dut}"):
				self.assertEqual(dut, dut.opposite().opposite())

class TestXC6200(unittest.TestCase):
	
	def find_configs_and_meaning(self, tile_data):
		# requires: tile, genes
		# sets: tile_meaning, src_map, dst_map, tt_map
		
		
		# get all configs for tiles
		config_assem = get_config_items(tile_data.tile)
		
		bit_config_map = {b: c for c in config_assem.connection for b in c.bits}
		for ll in config_assem.lut:
			for l in ll:
				for b in l.bits:
					bit_config_map[b] = l
		
		for t in config_assem.tile:
			for b in t.bits:
				bit_config_map[b] = t
		
		for gene_index, gene in enumerate(tile_data.genes):
			# find config items and map the bits
			bit_gene_pos_map = {b: i for i, b in enumerate(gene.bit_positions)}
			configs = []
			tile_data.gene_index_configs_map.append(configs)
			gene_pos_conf_pos_map = [None]*len(gene.bit_positions)
			
			while len(bit_gene_pos_map) > 0:
				bit = next(iter(bit_gene_pos_map))
				config = bit_config_map[bit]
				config_pos = len(configs)
				configs.append(config)
				
				if config.kind == "connection":
					dst_name = config.dst_net
					
					try:
						entry = tile_data.dst_map[dst_name]
						self.assertEqual(gene_index, entry.gene_index)
						entry.config_pos_list.append(config_pos)
					except KeyError:
						tile_data.dst_map[dst_name] = DstIndex(gene_index, [config_pos])
				elif config.kind == "TruthTable":
					self.assertNotIn(config.index, tile_data.tt_map)
					
					tile_data.tt_map[config.index] = TTIndex(gene_index, config_pos)
				
				for i, b in enumerate(config.bits):
					gene_pos_conf_pos_map[bit_gene_pos_map[b]] = (config_pos, i)
					
					del bit_gene_pos_map[b]
					del bit_config_map[b]
			
			# find meaning of alleles from configs
			gene_meaning = []
			tile_data.tile_meaning.append(gene_meaning)
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
						
						tile_data.src_map.setdefault(src_name, []).append(SrcIndex(gene_index, config_pos, allele_index, src_index))
						allele_meaning.append((src_name, dst_name))
					elif config.kind == "TruthTable":
						allele_meaning.append(allele_vals)
					else:
						# ignore, but keep absolute index of meaning and configs in sync
						allele_meaning.append(None)
				
				gene_meaning.append(allele_meaning)
		
		self.check_dst_src_map(tile_data)
	
	def check_dst_src_map(self, tile_data):
		# check dst map
		for dst, dst_index in tile_data.dst_map.items():
			# compare to config
			configs = tile_data.gene_index_configs_map[dst_index.gene_index]
			for config_pos in dst_index.config_pos_list:
				self.assertEqual(dst, configs[config_pos].dst_net)
				
				# compare to meaning
				for allele_meaning in tile_data.tile_meaning[dst_index.gene_index]:
					meaning = allele_meaning[config_pos]
					self.assertEqual(dst, meaning[1])
			
		
		# check src map
		for src, src_index_list in tile_data.src_map.items():
			for src_index in src_index_list:
				# compare to meaning
				meaning = tile_data.tile_meaning[src_index.gene_index][src_index.allele_index][src_index.config_pos]
				self.assertEqual(src, meaning[0])
				
				# compare to config
				config = tile_data.gene_index_configs_map[src_index.gene_index][src_index.config_pos]
				self.assertEqual(src, config.src_nets[src_index.src_net_index])
	
	def find_out_map(self, tile_data):
		all_sigs = ["top", "lft", "bot", "rgt", "f"]
		sig_index_map = {s: i for i, s in enumerate(all_sigs)}
		# detect mapping
		neigh_map = {}
		for src_name in tile_data.src_map:
			res = re.match(r"neigh_op_(?P<direction>\w+)_(?P<lut_index>\d)", src_name)
			if res:
				direc = res.group("direction")
				lut_index = res.group("lut_index")
				if direc in neigh_map:
					raise NoOutMapError(f"found '{direc}' multiple times in {tile_data.tile}")
				neigh_map[direc] = int(lut_index)
		
		out_map = {}
		for neigh_dir, lut_index in neigh_map.items():
			neigh_index = sig_index_map[neigh_dir]
			loc_dir = all_sigs[(neigh_index+2)%4]
			out_map[loc_dir] = lut_index
		
		# f_out
		# every output should have one input from the function unit
		# this should be a LUT output
		try:
			lut_index = next(iter(out_map.values()))
		except StopIteration as si:
			raise NoOutMapError(f"Empty out map for {tile_data.tile}") from si
		
		todo_nets = {f"lutff_{lut_index}/in_{i}" for i in range(4)}
		# rememeber already processed nets to avoid recalculation and loops
		done_nets = {UNCONNECTED_NAME}
		f_indices = []
		while len(todo_nets) > 0:
			cur_net = todo_nets.pop()
			if cur_net in done_nets:
				continue
			done_nets.add(cur_net)
			
			res = re.match(r"lutff_(?P<index>\d)/(c|l)?out", cur_net)
			if res:
				# found lut output -> assume function unit
				f_indices.append(int(res.group("index")))
			else:
				# trace sources of this net
				try:
					dst_index = tile_data.dst_map[cur_net]
				except KeyError:
					# no sources specified
					continue
				
				# add all possible sources to the stack
				for allele_meaning in tile_data.tile_meaning[dst_index.gene_index]:
					for config_pos in dst_index.config_pos_list:
						src_net, dst_net = allele_meaning[config_pos]
						self.assertEqual(cur_net, dst_net)
						
						todo_nets.add(src_net)
				
		if len(f_indices) < 1:
			raise NoOutMapError(f"function unit not found in {tile_data.tile}")
		elif len(f_indices) > 1:
			raise NoOutMapError(f"multiple candiates for function unit found in {tile_data.tile}")
		
		out_map["f"] = f_indices[0]
		
		if len(out_map.values()) != len(set(out_map.values())):
			raise NoOutMapError(f"Mapping inputs to outputs is not one-to-one in tile {tile_data.tile}")
		
		return out_map
	
	@classmethod
	def get_lut_value(cls, lut_index, src_state, tt_state, value_map):
		pass
		# trace inputs
		in_value = 0
		for i in range(4):
			cur_net = f"lutff_{lut_index}/in_{i}"
			while True:
				try:
					part_value = value_map[cur_net]
					break
				except KeyError:
					pass
				
				try:
					cur_net = src_state[cur_net]
				except KeyError:
					res = re.match(r"lutff_(?P<lut_index>)/(l)?out", cur_net)
					if not res:
						raise
					part_value = cls.get_lut_value(int(res.group("lut_index")), src_state, tt_state, value_map)
			if part_value:
				in_value |= 1 << i
		
		return tt_state[lut_index][in_value]
	
	#def test_meta_get_lut_value(self):
	#	# constant 0
	#	# constant 1
	#	# simple and
	#	# concatenated LUTs
	#	pass
	
	@staticmethod
	def simple_function_unit(x1: bool, x2: bool, x3: bool, y2: int, y3: int, q: bool=False):
		"""Compute the value for a simplified function unit
		
		- Q is assumed as constant (default False)
		"""
		if y2 < 2:
			y2_out = x2
		else:
			y2_out = q
		
		if y2 % 2 == 1:
			y2_out = not y2_out
		
		if y3 < 2:
			y3_out = x3
		else:
			y3_out = q
		
		if y3 % 2 == 1:
			y3_out = not y3_out
		
		if x1:
			return y2_out
		else:
			return y3_out
	
	@staticmethod
	def switch_direction(direction):
		directions = ["top", "lft", "bot", "rgt"]
		cur_index = directions.index(direction)
		op_index = (cur_index+2)%4
		return directions[op_index]
	
	def check_xc6200_representation(self, rep):
		# out_map is map from output of XC6200 cell to (LUT) indices
		
		# sort genes by tile
		tile_map = {}
		for gene in itertools.chain(rep.genes, rep.constant):
			tile = gene.bit_positions[0].tile
			# genes spanning multiple tiles are not supported
			self.assertTrue(all(b.tile==tile for b in gene.bit_positions))
			
			tile_map.setdefault(tile, TileData(tile)).genes.append(gene)
		
		# assume all tiles have the same out_map -> detect mapping by checking which neigh_op nets are used
		all_sigs = ["top", "lft", "bot", "rgt", "f"]
		out_map = {}
		for tile_data in tile_map.values():
			self.find_configs_and_meaning(tile_data)
			try:
				tmp_out_map = self.find_out_map(tile_data)
			except NoOutMapError as nome:
				self.fail(f"No put map for {tile_data.tile}")
			
			# check out map
			for sig in all_sigs:
				# check signal in tmp out map
				try:
					lut_index = tmp_out_map[sig]
				except KeyError:
					# only allowable at boarders
					# detection is done by incoming signals -> detect if tile that should create the signal is there 
					if sig == "f":
						self.fail(f"no function unit in {tile_data.tile}")
					elif sig == "top":
						neigh_offset = (0, -1)
					elif sig == "bot":
						neigh_offset = (0, 1)
					elif sig == "lft":
						neigh_offset = (1, 0)
					elif sig == "rgt":
						neigh_offset = (-1, 0)
					
					neigh_pos = IcecraftPosition(tile_data.tile.x+neigh_offset[0], tile_data.tile.y+neigh_offset[1])
					self.assertNotIn(neigh_pos, tile_map.keys(), f"no {sig} signal in {tile_data.tile} despite neighbor available")
					continue
				
				# check index consistency
				try:
					exp_index = out_map[sig]
				except KeyError:
					out_map[sig] = lut_index
					continue
				
				self.assertEqual(exp_index, lut_index)
			
		self.assertEqual(set(all_sigs), set(out_map))
		
		#print(f"detected out map: {out_map}")
		
		for tile_data in tile_map.values():
			for dir_index, direction in enumerate(all_sigs[:4]):
				# trace back the inputs of the LUT and collect relevant genes/meanings
				lut_index = out_map[direction]
				relevant_gene_indices = list()
				relevant_gene_indices.append(tile_data.tt_map[lut_index].gene_index)
				
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
						self.assertEqual(out_map[self.switch_direction(neigh_dir)], neigh_lut)
					elif re.match(r"lutff_(\d)/(c|l)?out", cur_net):
						other_lut = int(cur_net[6])
						# assume that another LUT output as input can only be the function unit
						self.assertEqual(out_map["f"], other_lut, "inconsistent f LUT")
					else:
						# simple net -> find source
						dst_index = tile_data.dst_map[cur_net]
						
						relevant_gene_indices.append(dst_index.gene_index)
						# add all possible sources to the stack
						for allele_meaning in tile_data.tile_meaning[dst_index.gene_index]:
							for config_pos in dst_index.config_pos_list:
								src_net, dst_net = allele_meaning[config_pos]
								self.assertEqual(cur_net, dst_net)
								
								net_stack.append(src_net)
				#print([tile_meaning[i] for i in relevant_gene_indices])
				
				# for all allele combinations check the behaviour of the LUT output with respect to the inputs
				src_list = [f"neigh_op_{d}_{out_map[self.switch_direction(d)]}" for d in all_sigs[:4]]
				src_list.append(f"lutff_{out_map['f']}/out")
				out_comb_map = {"INV": []}
				
				for comb_index, allele_comb in enumerate(itertools.product(*[tile_data.tile_meaning[i] for i in relevant_gene_indices])):
					assert len(allele_comb) == len(relevant_gene_indices)
					# create truth table and connection state according to the allele combination
					tt_state = {}
					src_state = {}
					for allele_meaning, gene_index in zip(allele_comb, relevant_gene_indices):
						configs = tile_data.gene_index_configs_map[gene_index]
						assert len(allele_meaning) == len(configs)
						for meaning, config in zip(allele_meaning, configs):
							if config.kind == "connection":
								src, dst = meaning
								if dst in src_state:
									# don't overwrite with unconnected
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
					
					matches = [True]*len(src_list)
					for src_values in itertools.product([False, True], repeat=len(src_list)):
						src_val_map = {s: v for s, v in zip(src_list, src_values)}
						# compute LUT output
						tt_index = 0
						for in_index in range(4):
							dst = f"lutff_{lut_index}/in_{in_index}"
							src = con_state[dst]
							# KeyError from here -> source that should have no influence
							try:
								val = src_val_map[src]
							except KeyError:
								if src == UNCONNECTED_NAME:
									val = False
								else:
									raise
							if val:
								tt_index |= 1 << in_index
						lut_val = tt_state[lut_index][tt_index]
						# compare LUT output to sources
						matches = [m and (lut_val == s) for m, s in zip(matches, src_values)]
					self.assertGreaterEqual(1, sum(matches))
					try:
						match_index = matches.index(True)
						out_comb_map.setdefault(all_sigs[match_index], []).append(comb_index)#src_list[match_index])
					except ValueError:
						out_comb_map["INV"].append(comb_index)
				
				# all inputs included, except the same direction
				self.assertNotIn(direction, out_comb_map, f"should not be in {direction}")
				# check number of combinations that lead to a certain state
				comb_count = None
				inv_count = 0
				for sig in all_sigs:
					if sig == direction:
						continue
					if sig not in out_comb_map:
						if sig == "f":
							self.fail(f"no function unit input for {direction} in {tile_data.tile}")
						elif sig == "top":
							neigh_offset = (0, 1)
						elif sig == "bot":
							neigh_offset = (0, -1)
						elif sig == "lft":
							neigh_offset = (-1, 0)
						elif sig == "rgt":
							neigh_offset = (1, 0)
						
						neigh_pos = IcecraftPosition(tile_data.tile.x+neigh_offset[0], tile_data.tile.y+neigh_offset[1])
						self.assertNotIn(neigh_pos, tile_map.keys(), f"no {sig} input for {direction} in {tile_data.tile} despite neighbor available\n{out_comb_map}\n{[len(g.alleles) for g in tile_data.genes]}")
						
						inv_count += 1
					else:
						if comb_count is None:
							comb_count = len(out_comb_map[sig])
						else:
							self.assertEqual(comb_count, len(out_comb_map[sig]))
				# at least f should be present -> comb_count is not None
				self.assertEqual(comb_count*inv_count, len(out_comb_map["INV"]))
			
			# check function unit
			avail_in = [d for d in all_sigs[:4] if f"neigh_op_{d}_{out_map[self.switch_direction(d)]}" in tile_data.src_map]
			#for neigh, x_off, y_off in [("top", 0, 1), ("lft", -1, 0), ("bot", 0, -1), ("rgt", 1, 0)]:
			#	if IcecraftPosition(tile_data.tile.x+x_off, tile_data.tile.y+y_off) in tile_map:
			#		avail_in.append(neigh)
			
			#print(avail_in)
			# map inputs
			ice40_map = {d: f"neigh_op_{d}_{out_map[self.switch_direction(d)]}" for d in all_sigs[:4]}
			xc6200_map = {
				"north": f"neigh_op_bot_{out_map['top']}",
				"south": f"neigh_op_top_{out_map['bot']}",
				"east": f"neigh_op_lft_{out_map['rgt']}",
				"west": f"neigh_op_rgt_{out_map['lft']}",
			}
			
			# find relevant genes
			lut_index = out_map["f"]
			relevant_gene_indices = list()
			
			net_stack = [f"lutff_{lut_index}/out"]
			done_nets = {f"neigh_op_{d}_{out_map[self.switch_direction(d)]}" for d in avail_in}
			done_nets.add(UNCONNECTED_NAME)
			while len(net_stack) > 0:
				cur_net = net_stack.pop()
				if cur_net in done_nets:
					continue
				done_nets.add(cur_net)
				
				if re.match(r"lutff_(\d)/(c|l)?out", cur_net):
					other_lut = int(cur_net[6])
					relevant_gene_indices.append(tile_data.tt_map[other_lut].gene_index)
					net_stack.extend(f"lutff_{other_lut}/in_{i}" for i in range(4))
				else:
					# simple net -> find source
					dst_index = tile_data.dst_map[cur_net]
					
					relevant_gene_indices.append(dst_index.gene_index)
					# add all possible sources to the stack
					for allele_meaning in tile_data.tile_meaning[dst_index.gene_index]:
						for config_pos in dst_index.config_pos_list:
							src_net, dst_net = allele_meaning[config_pos]
							self.assertEqual(cur_net, dst_net)
							
							net_stack.append(src_net)
			#print(relevant_gene_indices)
			
			# compute output of representational function unit dependent on the input signals for every allele combination
			output_comb_map = {}
			for comb_index, allele_comb in enumerate(itertools.product(*[tile_data.tile_meaning[i] for i in relevant_gene_indices])):
				# get current state
				tt_state = {}
				src_state = {}
				for allele_meaning, gene_index in zip(allele_comb, relevant_gene_indices):
					configs = tile_data.gene_index_configs_map[gene_index]
					assert len(allele_meaning) == len(configs)
					for meaning, config in zip(allele_meaning, configs):
						if config.kind == "connection":
							src, dst = meaning
							if dst in src_state:
								# don't overwrite with unconnected
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
				
				output_list = []
				for values in itertools.product((False, True), repeat=len(avail_in)):
					value_map = {f"neigh_op_{d}_{out_map[self.switch_direction(d)]}": v for d, v in zip(avail_in, values)}
					value_map[UNCONNECTED_NAME] = False
					
					output = self.get_lut_value(out_map["f"], src_state, tt_state, value_map)
					
					output_list.append(output)
				
				output_comb_map.setdefault(tuple(output_list), []).append(comb_index)
			#print(output_comb_map)
			
			output_xc_map = {o: [] for o in output_comb_map}
			# compute output of XC6200 function unit dependent on the input for every mux combination and match to representation
			for comb_index, (x1_mux, x2_mux, x3_mux, y2, y3) in enumerate(itertools.product(range(4), repeat=5)):
				values = [None]*16
				output_list = []
				for values in itertools.product((False, True), repeat=len(avail_in)):
					# unavailable inputs are set to False by default
					mux = [False]*4
					for sig, val in zip(avail_in, values):
						mux[all_sigs.index(sig)] = val
					
					output = self.simple_function_unit(*[mux[i] for i in (x1_mux, x2_mux, x3_mux)], y2, y3)
					
					output_list.append(output)
				
				output_tuple = tuple(output_list)
				self.assertIn(output_tuple, output_xc_map)
				output_xc_map[output_tuple].append(comb_index)
			
			#print(output_xc_map)
			for output, comb_list in output_xc_map.items():
				self.assertNotEqual(0, len(comb_list), f"unrequired output pattern {output}")
			
	
	def test_xc6200_structure(self):
		x_min, x_max = (2, 4)
		y_min, y_max = (2, 4)
		
		dut = XC6200RepGen()
		with self.subTest(desc="no in ports"):
			req = RequestObject(in_ports=[])
			req["tiles"] = IcecraftPosTransLibrary.expand_rectangle([IcecraftPosition(x_min, y_min), IcecraftPosition(x_max, y_max)])
			
			res = dut(req)
			
			self.check_xc6200_representation(res)
		
		with self.subTest(desc="in port"):
			req.in_ports.append(XC6200Port(IcecraftPosition(2, 3), XC6200Direction["lft"]))
			
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
	
	@unittest.skip("experimental, takes a long(!) time")
	def test_simple_xc6200(self):
		x = 16
		y = 17
		mid_tile = IcecraftPosition(x, y)
		top_tile = IcecraftPosition(x, y+1)
		lft_tile = IcecraftPosition(x-1, y)
		bot_tile = IcecraftPosition(x, y-1)
		rgt_tile = IcecraftPosition(x+1, y)
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
	
	def test_get_neighbor(self):
		tile = IcecraftPosition(2, 2)
		test_cases = {
			XC6200Direction.top: IcecraftPosition(2, 3),
			XC6200Direction.lft: IcecraftPosition(1, 2),
			XC6200Direction.bot: IcecraftPosition(2, 1),
			XC6200Direction.rgt: IcecraftPosition(3, 2),
		}
		
		for direction, exp in test_cases.items():
			res = XC6200RepGen.get_neighbor(tile, direction)
			
			self.assertEqual(exp, res)
