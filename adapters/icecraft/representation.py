import re
from typing import Sequence, Mapping, List, Tuple, Iterable, Callable, Union, Set, NamedTuple
from dataclasses import dataclass
from contextlib import contextmanager
from collections import defaultdict

from domain.interfaces import Representation, RepresentationGenerator
from domain.model import TargetConfiguration, Gene, Chromosome
from domain.request_model import RequestObject, Parameter
from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow

from .misc import TilePosition, IcecraftLUTPosition, IcecraftColBufCtrl, \
	IcecraftNetPosition, LUTFunction, IcecraftBitPosition, \
	IcecraftResource, IcecraftResCon, TILE_ALL, TILE_ALL_LOGIC, \
	IcecraftInputError, IcecraftGeneConstraint
from .chip_data import get_config_items, get_net_data, get_colbufctrl, ConfigAssemblage
from .chip_data_utils import NetData, SegEntryType, SegType
from .config_item import ConfigItem, ConnectionItem, IndexedItem
from .inter_rep import InterRep, Vertex, Edge, VertexDesig, EdgeDesig

NetId = SegEntryType

# name of the dummy net representing CarryInSet
CARRY_ONE_IN = "carry_one_in"

@dataclass
class IcecraftRep(Representation):
	genes: Sequence[Gene]
	# constant genes, i.e. with exactly one allele
	constant: Sequence[Gene]
	#colbufctrl
	colbufctrl: Sequence[IndexedItem]
	# output_lutffs
	output: Sequence[IcecraftLUTPosition]
	
	def prepare_config(self, config: TargetConfiguration) -> None:
		# set constant bits
		# set ColBufCtrl for global network input
		pass
	
	def decode(self, config: TargetConfiguration, chromo: Chromosome) -> None:
		pass
	

class IcecraftRepGen(RepresentationGenerator):
	"""Generate a representation for ice40 FPGAs
	
	The information about the FPGA ressources (nets, connections, LUTs) is transformed to internal 
	data structures, a request is parsed to select which ressources belong to the phenotype and 
	therefore should be represented in the genotype.
	
	A coarse selection is done by selcting the tiles, by default all resoources in the selected tiles are represented.
	Ressources can be excluded in two ways:
	- not available -> ressource doesn't belong to the genotype nor the phenotype and is not 
	configured, i.e. bits will not be set; described by the request
	- unused -> ressource will not be used have a fixed, neutral genotype and phenotype, e.g bits 
	will be constantly set to neutral (as a general rule to 0); described by (the negation of) 
	a used function constructed from the request
	"""
	def __init__(self) -> None:
		self._parameters = {"__call__": [
			Parameter("x_min", int),
			Parameter("y_min", int),
			Parameter("x_max", int),
			Parameter("y_max", int),
			Parameter("exclude_resources", IcecraftResource, default=[], multiple=True),
			Parameter("include_resources", IcecraftResource, default=[], multiple=True),
			Parameter("exclude_connections", IcecraftResCon, default=[], multiple=True),
			Parameter("include_connections", IcecraftResCon, default=[], multiple=True),
			Parameter("output_lutffs", IcecraftLUTPosition, multiple=True),
			Parameter("lut_functions", LUTFunction, default=[], multiple=True),
			Parameter("prune_no_viable_src", bool, default=False),
		]}
	
	@property
	def parameters(self) -> Mapping[str, Parameter]:
		return self._parameters
	
	def __call__(self, request: RequestObject) -> IcecraftRep:
		tiles = self.tiles_from_rectangle(request.x_min, request.y_min, request.x_max, request.y_max)
		
		config_map = {t: get_config_items(t) for t in tiles}
		
		raw_nets = get_net_data(tiles)
		self.carry_in_set_net(config_map, raw_nets)
		
		rep = InterRep(raw_nets, config_map)
		
		self.set_external_source(rep, tiles)
		
		special_map = self.create_special_map(tiles)
		self._choose_resources(rep, request, special_map)
		self._choose_connections(rep, request, special_map)
		
		self.set_lut_functions(rep, request.lut_functions)
		
		#TODO: set used flag
		
		const_genes, genes, sec_len = self.create_genes(rep, config_map)
		
		cbc_coords = self.get_colbufctrl_coordinates(rep)
		cbc_conf = self.get_colbufctrl_config(cbc_coords)
		
		return IcecraftRep(const_genes, genes, cbc_conf, tuple(sorted(request.output_lutffs)))
	
	@staticmethod
	def carry_in_set_net(config_map: Mapping[TilePosition, ConfigAssemblage], raw_nets: List[NetData]) -> None:
		"""Replace CarryInSet tile ConfigItem with a dummy net that can be connected to carry_in_mux"""
		for tile, conf in config_map.items():
			index_list = [i for i, c in enumerate(conf.tile) if c.kind == "CarryInSet"]
			
			if len(index_list) > 1:
				raise ValueError(f"Multiple CarryInSet entries for tile {tile}: {index_list}")
			
			try:
				index = index_list[0]
			except IndexError:
				# no CarryInSet
				continue
			
			carry_set_item = conf.tile[index]
			conf.tile = conf.tile[:index] + conf.tile[index+1:]
			
			raw_nets.append(NetData(
				((*tile, CARRY_ONE_IN), ),
				True,
				(0, )
			))
			con_item = ConnectionItem(
				carry_set_item.bits,
				"connection",
				"carry_in_mux",
				((True, ), ),
				(CARRY_ONE_IN, )
			)
			conf.connection += (con_item, )
		
	
	@staticmethod
	def set_external_source(rep: InterRep, tiles: List[TilePosition]) -> None:
		for vtx in rep.iter_vertices():
			drv_tiles = [vtx.desigs[i].tile for i in vtx.drivers]
			vtx.ext_src = any(t not in tiles for t in drv_tiles)
	
	@staticmethod
	def tiles_from_resource_tile(resc_tile: TilePosition, special_map: Mapping[int, List[TilePosition]]) -> List[TilePosition]:
		"""Get tiles that match the tile of a resource
		
		The resource tile may include special values while the returned tiles don't.
		"""
		if resc_tile.x in special_map or resc_tile.y in special_map:
			if resc_tile.x != resc_tile.y:
				raise IcecraftInputError(f"{resc_tile.x}!={resc_tile.y}, only identical special values supported")
			tiles = special_map[resc_tile.x]
		else:
			tiles = [resc_tile]
		
		return tiles
	
	@classmethod
	def set_vertex_resources(
		cls,
		rep: InterRep,
		resources: Iterable[IcecraftResource],
		special_map: Mapping[int, List[TilePosition]],
		value: bool
	) -> None:
		for resc in resources:
			possible_tiles = cls.tiles_from_resource_tile(resc.tile, special_map)
			cond_func = cls.create_regex_condition_vertex(resc.name, possible_tiles)
			
			for tile in possible_tiles:
				cls.set_available_vertex(rep.get_vertices_of_tile(tile), cond_func, value)
	
	@classmethod
	def set_edge_resources(
		cls,
		rep: InterRep,
		resccons: Iterable[IcecraftResCon],
		special_map: Mapping[int, List[TilePosition]],
		value: bool
	) -> None:
		for resccon in resccons:
			possible_tiles = cls.tiles_from_resource_tile(resccon.tile, special_map)
			cond_func = cls.create_regex_condition_edge(resccon.src_name, resccon.dst_name, possible_tiles)
			
			for tile in possible_tiles:
				cls.set_available_edge(rep.get_edges_of_tile(tile), cond_func, value)
	
	@staticmethod
	def create_special_map(tiles: Iterable[TilePosition]) -> Mapping[int, List[TilePosition]]:
		# sort by special values for tile coordinates
		special_map = {}
		special_map[TILE_ALL] = list(tiles)
		# at the moment only logic tiles are supported so they are the same
		special_map[TILE_ALL_LOGIC] = special_map[TILE_ALL]
		
		return special_map
	
	@classmethod
	def _choose_resources(cls, rep: InterRep, request: RequestObject, special_map: Mapping[int, List[TilePosition]]) -> None:
		"""Set available flag of resources according to a request
		
		tiles specifies which tiles the wildcars TILE_ALL and TILE_ALL_LOGIC are applied to
		"""
		# exclude exclude resources
		cls.set_vertex_resources(rep, request.exclude_resources, special_map, False)
		
		# exclude all nets with external drivers
		cls.set_available_vertex(rep.iter_vertices(), lambda v: v.ext_src, False)
		
		# include include resources
		cls.set_vertex_resources(rep, request.include_resources, special_map, True)
	
	@classmethod
	def _choose_connections(cls, rep: InterRep, request: RequestObject, special_map: Mapping[int, List[TilePosition]]) -> None:
		"""Set available flag of connections between resources according to a request"""
		# exclude exclude connections
		cls.set_edge_resources(rep, request.exclude_connections, special_map, False)
		
		# include include connections
		cls.set_edge_resources(rep, request.include_connections, special_map, True)
	
	@staticmethod
	def set_lut_functions(rep: InterRep, lut_functions: Iterable[LUTFunction]) -> None:
		for vtx in rep.iter_lut_vertices():
			vtx.functions = list(lut_functions)
	
	@staticmethod
	def tiles_from_rectangle(x_min: int, y_min: int, x_max: int, y_max: int) -> List[TilePosition]:
		return [TilePosition(x, y) for x in range(x_min, x_max+1) for y in range(y_min, y_max+1)]
	
	@staticmethod
	def set_available_vertex(vertex_iter: Iterable[Vertex], cond: Callable[[Vertex], bool], value: bool = False) -> None:
		for vertex in vertex_iter:
			if vertex.available == value:
				continue
			
			if cond(vertex):
				vertex.available = value
	
	@staticmethod
	def set_available_edge(edge_iter: Iterable[Edge], cond: Callable[[Edge], bool], value: bool = False) -> None:
		for edge in edge_iter:
			if edge.available == value:
				continue
			
			if cond(edge):
				edge.available = value
	
	@staticmethod
	def create_regex_condition_vertex(regex_str: str, tiles: Iterable[TilePosition]) -> Callable[[Vertex], bool]:
		pat = re.compile(regex_str)
		tile_set = set(tiles)
		
		def func(vtx: Vertex) -> bool:
			for desig in vtx.desigs:
				if desig.tile in tile_set and pat.match(desig.name):
					return True
			return False
		
		return func
	
	@staticmethod
	def create_regex_condition_edge(src_regex: str, dst_regex: str, tiles: Iterable[TilePosition]) -> Callable[[Edge], bool]:
		src_pat = re.compile(src_regex)
		dst_pat = re.compile(dst_regex)
		tile_set = set(tiles)
		
		def func(edge: Edge) -> bool:
			desig = edge.desig
			return desig.src.tile in tile_set and src_pat.match(desig.src.name) is not None and dst_pat.match(desig.dst.name) is not None
		
		return func
	
	@classmethod
	def apply_gene_constraints(cls, genes: List[Gene], constraint_iter: Iterable[IcecraftGeneConstraint]) -> int:
		"""
		
		Every bit can only be defined once, even if the multiple definition are compatible.
		
		position:
		restraint of allesles only -> same position
		reorder bits only -> same position
		combination -> delete original genes, append siper gene
		
		return number of super genes
		"""
		class BitOrigin(NamedTuple):
			gene_pos: int
			bit_pos : int
		
		bit_org_gene_map = {b: g for g in genes for b in g.bit_positions}
		bits_org_list_pos = {g.bit_positions: i for i, g in enumerate(genes)}
		del_list = []
		super_count = 0
		for constraint in constraint_iter:
			# find mapping from constraint bits to gene bits
			bit_index_map = {b:i for i, b in enumerate(constraint.bits)}
			pos_origin_map = [None]*len(constraint.bits)
			org_gene_list = []
			while len(bit_index_map) > 0:
				next_bit = next(iter(bit_index_map.keys()))
				
				try:
					org_gene = bit_org_gene_map[next_bit]
				except KeyError as ke:
					raise IcecraftInputError(f"bit {next_bit} not found; not defined or used twice") from ke
				
				gene_pos = len(org_gene_list)
				org_gene_list.append(org_gene)
				for bit_pos, bit in enumerate(org_gene.bit_positions):
					try:
						index = bit_index_map[bit]
						del bit_index_map[bit]
					except KeyError as ke:
						raise IcecraftInputError(f"bits {org_gene.bit_positions} of single gene only partially included in constraint or included twice")
					
					pos_origin_map[index] = BitOrigin(gene_pos, bit_pos)
					
					try:
						del bit_org_gene_map[bit]
					except KeyError as ke:
						raise IcecraftInputError(f"bit {bit} not found; not defined or used twice") from ke
			
			assert all(o is not None for o in pos_origin_map)
			
			# check values of alleles
			#TODO: construct comments
			for val in constraint.values:
				assert len(val) == len(pos_origin_map)
				
				# reset every time to avoid covering unset values by using values from previous runs
				values_list = [[None]*len(g.bit_positions) for g in org_gene_list]
				
				for bit_org, cur_val in zip(pos_origin_map, val):
					values_list[bit_org.gene_pos][bit_org.bit_pos] = cur_val
				
				for gene, org_val in zip(org_gene_list, values_list):
					assert all(v is not None for v in org_val)
					
					try:
						i = gene.alleles.values_index(org_val)
					except ValueError as ve:
						raise IcecraftInputError(f"invalid values for {gene.bit_positions}") from ve
			
			# construct gene
			cstr_gene = Gene(constraint.bits, AlleleList([Allele(v, "") for v in constraint.values]), "constraint")
			
			if len(org_gene_list) == 1:
				# replace existing gene
				index = bits_org_list_pos[org_gene_list[0].bit_positions]
				genes[index] = cstr_gene
			else:
				genes.append(cstr_gene)
				super_count += 1
				# delete used genes
				# do it later to not mess up indices in bits_org_list_pos
				del_list.extend([bits_org_list_pos[o.bit_positions] for o in org_gene_list])
		
		assert len(set(del_list)) == len(del_list), "double entries in del list"
		
		for d in sorted(del_list, reverse=True):
			genes.pop(d)
			
		return super_count
	
	@staticmethod
	def get_colbufctrl_coordinates(rep: InterRep) -> List[IcecraftColBufCtrl]:
		coords = set()
		for index in range(8):
			# global network is the same for every tile -> doesn't matter which one
			desig = VertexDesig.from_seg_entry((1, 1, f"glb_netwk_{index}"))
			try:
				glb_vtx = rep.get_vertex(desig)
			except KeyError:
				# global net not found -> no need for ColBufCtrl
				continue
			
			if not glb_vtx.available:
				continue
			
			# tiles from out edges
			# in edges are not relevant as far as seen in valid bitstreams
			glb_tiles = set(e.desig.src.tile for e in glb_vtx.iter_out_edges() if e.available and e.dst.available)
			
			cbc_tiles = get_colbufctrl(glb_tiles)
			coords.update([IcecraftColBufCtrl(t, index) for t in cbc_tiles])
		
		return sorted(coords)
	
	@staticmethod
	def get_colbufctrl_config(coords: Iterable[IcecraftColBufCtrl]) -> List[IndexedItem]:
		cbc_conf = []
		for cbc_coord in coords:
			item_assemblage = get_config_items(cbc_coord.tile)
			cbc_conf.append(item_assemblage.col_buf_ctrl[cbc_coord.z])
		return cbc_conf
	
	@classmethod
	def create_genes(
		cls,
		rep: InterRep,
		config_map: Mapping[TilePosition, ConfigAssemblage]
	) -> Tuple[List[Gene], List[Gene], List[int]]:
		"""returns const_genes, genes and gene_section_lengths"""
		
		const_genes = []
		genes = []
		sec_len = []
		
		def add_genes(gene_iter):
			for gene in gene_iter:
				if len(gene.alleles) > 1:
					genes.append(gene)
				elif len(gene.alleles) == 1:
					const_genes.append(gene)
				else:
					raise Exception("Gene without alleles")
		
		# sort vertices
		unused_vertices = []
		ext_drv_vertices = []
		multi_drv_vertices = []
		single_tile_vertices = []
		for vtx in rep.iter_vertices():
			if not vtx.available:
				continue
			
			# no explicit check for configurable as configurable == False -> bit_count == 0
			if vtx.bit_count == 0:
				continue
			
			if len(vtx.driver_tiles) == 0:
				continue
			
			if not vtx.used:
				unused_vertices.append(vtx)
				continue
			
			if vtx.ext_src:
				ext_drv_vertices.append(vtx)
				continue
			
			if len(vtx.driver_tiles) > 1:
				multi_drv_vertices.append(vtx)
				continue
			
			single_tile_vertices.append(vtx)
		
		const_genes = []
		for vtx in unused_vertices+ext_drv_vertices:
			tmp_genes = vtx.get_genes()
			assert all(len(g.alleles) == 1 for g in tmp_genes)
			const_genes.extend(tmp_genes)
		
		for vtx in multi_drv_vertices:
			tmp_genes = vtx.get_genes()
			add_genes(tmp_genes)
		
		# first gene section: nets having potential drivers in multiple nets
		if len(genes) > 0:
			sec_len.append(len(genes))
		
		single_const_genes, single_genes, single_sec_len = cls.create_tile_genes(
			single_tile_vertices,
			config_map,
		)
		const_genes.extend(single_const_genes)
		genes.extend(single_genes)
		sec_len.extend(single_sec_len)
		
		return const_genes, genes, sec_len
	
	@classmethod
	def create_tile_genes(
		cls,
		single_tile_vertices: Iterable[Vertex],
		config_map: Mapping[TilePosition, ConfigAssemblage]
	) -> Tuple[List[Gene], List[Gene], List[int]]:
		"""returns const_genes, genes and gene_section_lengths"""
		const_genes = []
		genes = []
		sec_len = []
		
		def empty_if_missing(dictionary, key):
			try:
				return dictionary[key]
			except KeyError:
				return []
		
		def add_gene(gene):
			if len(gene.alleles) > 1:
				genes.append(gene)
			elif len(gene.alleles) == 1:
				const_genes.append(gene)
			else:
				raise Exception("Gene without alleles")
		
		# sort vertices by tile
		single_tile_map = {}
		for vtx in single_tile_vertices:
			if len(vtx.driver_tiles) > 1:
				raise ValueError("vertex with multiple driver tiles can't be handled as tile genes")
			tile = vtx.driver_tiles[0]
			single_tile_map.setdefault(tile, []).append(vtx)
		
		# find all tiles
		tiles = set(single_tile_map)
		tiles.update(config_map)
		
		for tile in sorted(tiles):
			prev_len = len(genes)
			# tile confs
			for tile_conf in config_map[tile].tile:
				if tile_conf.kind in ("NegClk", ):
					tmp_gene = cls.create_all_allele_gene(tile_conf)
				else:
					raise ValueError(f"Unsupported tile config '{tile_conf.kind}'")
				
				add_gene(tmp_gene)
			
			# vertices that only belong to this tile
			for vtx in empty_if_missing(single_tile_map, tile):
				tmp_genes = vtx.get_genes()
				for gene in tmp_genes:
					add_gene(gene)
			
			new_count = len(genes) - prev_len
			if new_count > 0:
				sec_len.append(new_count)
		
		return const_genes, genes, sec_len
	
	@staticmethod
	def create_all_allele_gene(item: ConfigItem, desc: str=None) -> Gene:
		"""create gene from ConfigItem with all possible alleles"""
		if desc is None:
			desc = f"tile ({item.bits[0].x}, {item.bits[0].y}) {item.kind}"
		return Gene(
			item.bits,
			AlleleAll(len(item.bits)),
			desc
		)
	
