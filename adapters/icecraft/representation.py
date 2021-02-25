import re
from typing import Sequence, Mapping, List, Tuple, Iterable, Callable, Union
from dataclasses import dataclass
from contextlib import contextmanager
from collections import defaultdict

from domain.interfaces import Representation, RepresentationGenerator
from domain.model import TargetConfiguration, Gene, Chromosome
from domain.request_model import RequestObject, Parameter
from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow

from .misc import TilePosition, IcecraftLUTPosition, IcecraftColBufCtrl, \
	IcecraftNetPosition, LUTFunction, IcecraftBitPosition, \
	IcecraftResource, TILE_ALL, TILE_ALL_LOGIC
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
		
		self._choose_resources(rep, request, tiles)
		
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
	
	@classmethod
	def set_vertex_resources(
		cls,
		rep: InterRep,
		resources: Iterable[IcecraftResource],
		special_map: Mapping[int, List[TilePosition]],
		value: bool
	) -> None:
		for resc in resources:
			if resc.x in special_map or resc.y in special_map:
				if resc.x != resc.y:
					raise IcecraftInputError(f"{resc.x}!={resc.y}, only identical special values supported")
				possible_tiles = special_map[resc.x]
			else:
				possible_tiles = [resc.tile]
			
			cond_func = cls.create_regex_condition_vertex(resc.name)
			for tile in possible_tiles:
				cls.set_available_vertex(rep.get_vertices_of_tile(tile), cond_func, value)
		
	
	@classmethod
	def _choose_resources(cls, rep: InterRep, request: RequestObject, tiles: Iterable[TilePosition]) -> None:
		"""Set available flag of resources according to a request
		
		tiles specifies which tiles the wildcars TILE_ALL and TILE_ALL_LOGIC are applied to
		"""
		# sort by special values for tile coordinates
		special_map = {}
		special_map[TILE_ALL] = list(tiles)
		# at the moment only logic tiles are supported so they are the same
		special_map[TILE_ALL_LOGIC] = special_map[TILE_ALL]
		
		# exclude exclude resources
		cls.set_vertex_resources(rep, request.exclude_resources, special_map, False)
		
		# exclude all nets with external drivers
		cls.set_available_vertex(rep.iter_vertices(), lambda v: v.ext_src, False)
		
		# include include resources
		cls.set_vertex_resources(rep, request.include_resources, special_map, True)
	
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
	def create_regex_condition_vertex(regex_str: str) -> Callable[[Vertex], bool]:
		pat = re.compile(regex_str)
		
		def func(vtx: Vertex) -> bool:
			for desig in vtx.desigs:
				if pat.match(desig.name):
					return True
			return False
		
		return func
	
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
	
