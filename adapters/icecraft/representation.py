import re
from typing import Sequence, Mapping, List, Tuple, Iterable, Callable, Union
from dataclasses import dataclass
from contextlib import contextmanager
from collections import defaultdict

from domain.interfaces import Representation, RepresentationGenerator
from domain.model import TargetConfiguration, Gene, Chromosome
from domain.request_model import RequestObject, Parameter
from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow

from .misc import TilePosition, IcecraftLUTPosition, IcecraftColBufCtrl, IcecraftNetPosition, LUTFunction, IcecraftBitPosition
from .chip_data import get_config_items, get_net_data, get_colbufctrl, ConfigAssemblage
from .chip_data_utils import NetData, SegEntryType, SegType
from .config_item import ConfigItem, ConnectionItem, IndexedItem
from .inter_rep import InterRep, Vertex, Edge, VertexDesig, EdgeDesig

NetId = SegEntryType

# name of the dummy net representing CarryInSet
CARRY_ONE_IN = "carry_one_in"

class NetRelation:
	"""Represent a nets context and relations to other nets and configrations"""
	def __init__(self, net_data: NetData, inner_tiles: Iterable[TilePosition]=[]) -> None:
		self._net_data = net_data
		self._available = True
		
		# check for external drivers
		self._has_external_driver = False
		drv_tile_set = set()
		for drv_index in net_data.drivers:
			drv_tile = TilePosition(*net_data.segment[drv_index][:2])
			drv_tile_set.add(drv_tile)
			if drv_tile not in inner_tiles:
				self._has_external_driver = True
		
		self._drv_tiles = sorted(drv_tile_set)
		
		self._multi_drv_tiles = self.multiple_driver_tiles_in_net_data(net_data)
		
		self.fixed = not self.hard_driven
		# source groups that have this net as destination
		self._src_grp_list = []
		# number of viable sources
		self._has_viable_src = False
		# source groups that have this net as source
		self._dst_grp_list = []
		# index of this net in the source of the source group
		self._dst_indices = []
	
	@contextmanager
	def guard_viable_src(self):
		# known inconsistency: loops (that should only occur in spans) remain
		# vaiable if there once was a viable source even when thaat source
		# is removed
		pre = self.is_viable_src
		yield
		if pre != self.is_viable_src:
			self._propagate_valid_src()
	
	def _propagate_valid_src(self):
		for dst in self.iter_dsts():
			dst.update_has_viable_src()
	
	@property
	def net_data(self) -> NetData:
		return self._net_data
	
	@property
	def segment(self) -> SegType:
		return self._net_data.segment
	
	@property
	def hard_driven(self) -> bool:
		return self._net_data.hard_driven
	
	@property
	def drivers(self) -> Tuple[int, ...]:
		return self._net_data.drivers
	
	@property
	def has_external_driver(self) -> bool:
		return self._has_external_driver
	
	@property
	def available(self) -> bool:
		return self._available
	
	@available.setter
	def available(self, value: bool) -> None:
		with self.guard_viable_src():
			self._available = value
	
	@property
	def has_viable_src(self) -> bool:
		return self._has_viable_src
	
	def update_has_viable_src(self) -> None:
		with self.guard_viable_src():
			found = False
			for src_grp in self._src_grp_list:
				if found:
					break
				for src in src_grp.src_list:
					if src.is_viable_src:
						found = True
						break
			
			self._has_viable_src = found
	
	@property
	def is_viable_src(self) -> bool:
		return self.available and (self.hard_driven or self.has_external_driver or self.has_viable_src)
	
	def iter_src_grps(self) -> Iterable["SourceGroup"]:
		yield from self._src_grp_list
	
	def add_src_grp(self, src_grp: "SourceGroup") -> None:
		self._src_grp_list.append(src_grp)
		self.update_has_viable_src()
	
	def iter_drv_tiles(self) -> Iterable[TilePosition]:
		yield from self._drv_tiles
	
	@property
	def multiple_drv_tiles(self):
		"""return True if at least two drivers are in different tiles"""
		return self._multi_drv_tiles
	
	def multiple_src_tiles(self):
		"""return True iff at least two source are in different tiles
		
		checks only currently available scr_grps, while multiple_drv_tiles checks all possible drivers
		"""
		tile = None
		for src_grp in self.iter_src_grps():
			if tile is None:
				tile = src_grp.tile
			elif tile != src_grp.tile:
				return True
		
		return False
	
	def iter_dsts(self) -> Iterable["NetRelation"]:
		for dst_grp in self._dst_grp_list:
			yield dst_grp.dst
	
	def iter_dst_grps(self) -> Iterable["SourceGroup"]:
		yield from self._dst_grp_list
	
	def iter_dst_indices(self) -> Iterable[int]:
		"""index for this NetRelation in the list of sources of the destination SourceGroup"""
		yield from self._dst_indices
	
	def add_dst(self, dst_grp: "SourceGroup", dst_index: int) -> None:
		self._dst_grp_list.append(dst_grp)
		self._dst_indices.append(dst_index)
	
	def __repr__(self) -> str:
		return f"NetRelation({repr(self._net_data)})"
	
	@classmethod
	def from_net_data_iter(cls, net_data_iter: Iterable[NetData], inner_tiles: Iterable[TilePosition]) -> List["NetRelation"]:
		"""create NetRelation instances"""
		return [cls(d, inner_tiles) for d in net_data_iter]
	
	@staticmethod
	def create_net_map(net_relations: Iterable["NetRelation"]) -> Mapping[NetId, "NetRelation"]:
		"""put NetRelation instances in a dictionary NetId -> NetRelation"""
		return {net_id: net_rel for net_rel in net_relations for net_id in net_rel.segment}
	
	@staticmethod
	def multiple_driver_tiles_in_net_data(net_data: NetData) -> bool:
		prev_pos = None
		for index in net_data.drivers:
			pos = net_data.segment[index][:2]
			if prev_pos is None:
				prev_pos = pos
			elif prev_pos != pos:
				return True
		
		return False
	

class SourceGroup:
	"""Group of sources for a destination, controlled by the same bits"""
	def __init__(self, config_item: ConnectionItem, dst: NetRelation, src_list: Tuple[NetRelation, ...]) -> None:
		self._config_item = config_item
		self._dst = dst
		self._src_list = src_list
		# assumption: all bits of the config item come from the same tile
		self._tile = config_item.bits[0].tile
		assert all([self.tile == b.tile for b in config_item.bits]), f"Not all bits in same tile {config_item.bits}"
	
	@property
	def tile(self) -> TilePosition:
		return self._tile
	
	@property
	def config_item(self) -> ConnectionItem:
		return self._config_item
	
	@property
	def bits(self) -> Tuple[IcecraftBitPosition, ...]:
		return self._config_item.bits
	
	@property
	def dst(self) -> NetRelation:
		return self._dst
	
	@property
	def src_list(self) -> Tuple[NetRelation, ...]:
		return self._src_list
	
	def iter_srcs(self) -> Iterable[NetRelation]:
		yield from self._src_list
	
	# iterate over bit values for sources
	def iter_values(self) -> Iterable[Tuple[bool, ...]]:
		yield from self._config_item.values
	
	def __repr__(self) -> str:
		bit_str = "".join([f"({b.group}, {b.index}), " for b in self.config_item.bits])
		return f"SourceGroup(tile=({self.tile.x}, {self.tile.y}), bits=({bit_str}), dst={repr(self.dst)})"
	
	@classmethod
	def populate_net_relations(cls, net_map: Mapping[NetId, NetRelation], con_configs: Iterable[ConnectionItem]) -> List["SourceGroup"]:
		src_grp_list = []
		for item in con_configs:
			# create source group
			tile_pos = item.bits[0].tile
			dst = net_map[(*tile_pos, item.dst_net)]
			src_list = tuple(net_map[(*tile_pos, s)] for s in item.src_nets)
			
			src_grp = cls(item, dst, src_list)
			
			# add source group to net relations
			dst.add_src_grp(src_grp)
			#dst.src_grp_list.append(src_grp)
			for i, net_rel in enumerate(src_list):
				net_rel.add_dst(src_grp, i)
				#net_rel.dst_grp_list.append(src_grp)
				#net_rel.dst_indices.append(i)
			
			src_grp_list.append(src_grp)
		
		return src_grp_list


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
	- unused -> ressource will not be used have a fixed, neutral genotype and phneotype, e.g bits 
	will be constantly set to neutral (as a general rule to 0); described by (the negation of) 
	a used function constructed from the request
	"""
	def __init__(self) -> None:
		self._parameters = {"__call__": [
			Parameter("x_min", int),
			Parameter("y_min", int),
			Parameter("x_max", int),
			Parameter("y_max", int),
			Parameter("exclude_nets", str, multiple=True),
			Parameter("include_nets", str, multiple=True),
			Parameter("output_lutffs", IcecraftLUTPosition, multiple=True),
			Parameter("joint_input_nets", str, default=[], multiple=True),
			Parameter("lone_input_nets", IcecraftNetPosition, default=[], multiple=True),
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
		
		self._choose_nets(rep, request)
		
		self.set_lut_functions(rep, request.lut_functions)
		
		#TODO: set used flag
		
		
		cbc_coords = self.get_colbufctrl_coordinates(rep)
		cbc_conf = self.get_colbufctrl_config(cbc_coords)
		
		return IcecraftRep([], [], cbc_conf, tuple(sorted(request.output_lutffs)))
	
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
	def _choose_nets(cls, rep: InterRep, request: RequestObject) -> None:
		# exclude exclude nets
		for regex_str in request.exclude_nets:
			cond_func = cls.create_regex_condition_vertex(regex_str)
			cls.set_available_vertex(rep, cond_func, False)
		# exclude all nets with external drivers
		cls.set_available_vertex(rep, lambda v: v.ext_src, False)
		
		# include include nets
		for regex_str in request.include_nets:
			cond_func = cls.create_regex_condition_vertex(regex_str)
			cls.set_available_vertex(rep, cond_func, True)
		
		# include joint input nets
		for name in request.joint_input_nets:
			cls.set_available_vertex(rep, lambda v: any([name==d.name for d in v.desigs]), True)
		
		# include lone input nets
		for net_pos in request.lone_input_nets:
			desig = VertexDesig.from_net_position(net_pos)
			try:
				vtx = rep.get_vertex(desig)
			except KeyError:
				raise ValueError(f"Requested input net {net_pos} not found")
			vtx.available = True
	
	@staticmethod
	def set_lut_functions(rep: InterRep, lut_functions: Iterable[LUTFunction]) -> None:
		for vtx in rep.iter_lut_vertices():
			vtx.functions = list(lut_functions)
	
	@staticmethod
	def tiles_from_rectangle(x_min: int, y_min: int, x_max: int, y_max: int) -> List[TilePosition]:
		return [TilePosition(x, y) for x in range(x_min, x_max+1) for y in range(y_min, y_max+1)]
	
	@staticmethod
	def set_available_vertex(rep: InterRep, cond: Callable[[Vertex], bool], value: bool = False) -> None:
		for vertex in rep.iter_vertices():
			if vertex.available == value:
				continue
			
			if cond(vertex):
				vertex.available = value
	
	@staticmethod
	def set_available_edge(rep: InterRep, cond: Callable[[Edge], bool], value: bool = False) -> None:
		for edge in rep.iter_edges():
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
		sec_len=[]
		
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
		sec_len=[]
		
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
	
