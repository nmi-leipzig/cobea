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
from .chip_data import get_config_items, get_net_data, get_colbufctrl, ConfigDictType
from .chip_data_utils import NetData, SegEntryType, SegType
from .config_item import ConfigItem, ConnectionItem, IndexedItem

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
		
		net_relations = NetRelation.from_net_data_iter(raw_nets, tiles)
		net_map = NetRelation.create_net_map(net_relations)
		
		self._choose_nets(net_relations, net_map, request)
		
		
		
		
		cbc_coords = self.get_colbufctrl_coordinates(net_map, tiles)
		cbc_conf = self.get_colbufctrl_config(cbc_coords)
		
		return IcecraftRep([], [], cbc_conf, tuple(sorted(request.output_lutffs)))
	
	@staticmethod
	def carry_in_set_net(config_map: Mapping[TilePosition, ConfigDictType], raw_nets: List[NetData]) -> None:
		"""Replace CarryInSet tile ConfigItem with a dummy net that  can be connected to carry_in_mux"""
		for tile, conf in config_map.items():
			try:
				index_list = [i for i, c in enumerate(conf["tile"]) if c.kind == "CarryInSet"]
			except KeyError:
				# no tile config items
				continue
			
			if len(index_list) > 1:
				raise ValueError(f"Multiple CarryInSet entries for tile {tile}: {index_list}")
			
			try:
				index = index_list[0]
			except IndexError:
				# no CarryInSet
				continue
			
			carry_set_item = conf["tile"][index]
			conf["tile"] = conf["tile"][:index] + conf["tile"][index+1:]
			
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
			conf["connection"] += (con_item, )
		
	
	@classmethod
	def _choose_nets(cls, net_relations: Iterable[NetRelation], net_map: Mapping[NetId, NetRelation], request: RequestObject) -> None:
		# exclude exclude nets
		for regex_str in request.exclude_nets:
			cond_func = cls.create_regex_condition(regex_str)
			cls.set_available(net_relations, False, cond_func)
		# exclude all nets with driver outside of tiles
		cls.set_available(net_relations, False, lambda n: n.has_external_driver)
		
		# include include nets
		for regex_str in request.include_nets:
			cond_func = cls.create_regex_condition(regex_str)
			cls.set_available(net_relations, True, cond_func)
		
		# include joint input nets
		for name in request.joint_input_nets:
			cls.set_available(net_relations, True, lambda n: any([name==e for _, _, e in n.segment]))
		
		# include lone input nets
		for net_pos in request.lone_input_nets:
			seg = (net_pos.x, net_pos.y, net_pos.net)
			net_map[seg].available = True
	
	@staticmethod
	def tiles_from_rectangle(x_min: int, y_min: int, x_max: int, y_max: int) -> List[TilePosition]:
		return [TilePosition(x, y) for x in range(x_min, x_max+1) for y in range(y_min, y_max+1)]
	
	@staticmethod
	def set_available(net_relations: Iterable[NetRelation], value: bool, cond: Callable[[NetRelation], bool]) -> None:
		for net_rel in net_relations:
			if net_rel.available == value:
				continue
			
			if cond(net_rel):
				net_rel.available = value
	
	@staticmethod
	def create_regex_condition(regex_str: str) -> Callable[[NetRelation], bool]:
		pat = re.compile(regex_str)
		
		def func(net_rel: NetRelation) -> bool:
			for seg in net_rel.segment:
				if pat.match(seg[2]):
					return True
			return False
		
		return func
	
	@staticmethod
	def get_colbufctrl_coordinates(net_map: Mapping[NetId, NetRelation], tiles: Iterable[TilePosition]) -> List[IcecraftColBufCtrl]:
		coords = set()
		for index in range(8):
			net_tiles = []
			for tile_pos in tiles:
				net_rel = net_map[(*tile_pos, f"glb_netwk_{index}")]
				if net_rel.available:
					net_tiles.append(tile_pos)
			
			cbc_tiles = get_colbufctrl(net_tiles)
			coords.update([IcecraftColBufCtrl(t, index) for t in cbc_tiles])
		
		return sorted(coords)
	
	@staticmethod
	def get_colbufctrl_config(coords: Iterable[IcecraftColBufCtrl]) -> List[IndexedItem]:
		cbc_conf = []
		for cbc_coord in coords:
			item_dict = get_config_items(cbc_coord.tile)
			cbc_conf.append(item_dict["ColBufCtrl"][cbc_coord.z])
		return cbc_conf
	
	@classmethod
	def create_genes(
		cls,
		net_relations: Iterable[NetRelation],
		config_map: Mapping[TilePosition, ConfigDictType],
		used_function: Callable[[NetRelation], bool],
		lut_functions: Iterable[LUTFunction],
		net_map: Mapping[NetId, NetRelation] = None
	) -> Tuple[List[Gene], List[Gene], List[int]]:
		"""returns const_genes, genes and gene_section_lengths"""
		if net_map is None:
			net_map = NetRelation.create_net_map(net_relations)
		
		const_genes = []
		genes = []
		sec_len=[]
		
		def add_gene(gene):
			if len(gene.alleles) > 1:
				genes.append(gene)
			elif len(gene.alleles) == 1:
				const_genes.append(gene)
			else:
				raise Exception("Gene without alleles")
		
		# sort nets
		unused_nets = []
		ext_drv_nets = []
		multi_drv_nets = []
		single_tile_nets = []
		for net_rel in net_relations:
			if not net_rel.available:
				continue
			
			if net_rel.hard_driven:
				continue
			
			if len(list(net_rel.iter_src_grps())) == 0:
				continue
			
			drv_tiles = list(net_rel.iter_drv_tiles())
			
			if len(drv_tiles) == 0:
				continue
			
			if not used_function(net_rel):
				unused_nets.append(net_rel)
				continue
			
			if net_rel.has_external_driver:
				ext_drv_nets.append(net_rel)
				continue
			
			if len(drv_tiles) > 1:
				multi_drv_nets.append(net_rel)
				continue
			
			single_tile_nets.append(net_rel)
		
		const_genes = [cls.create_unused_gene_from_net(n, f"unused {n.segment[0]}") for n in unused_nets]
		
		const_genes.extend(cls.create_unused_gene_from_net(e, f"externally driven {e.segment[0]}") for e in ext_drv_nets)
		
		for net_rel in multi_drv_nets:
			src_grps = list(net_rel.iter_src_grps())
			bits, alleles = cls.alleles_from_src_grps(src_grps, used_function)
			tmp_gene = Gene(
				bits,
				alleles,
				f"multitile driver {net_rel.segment[0]}"
			)
			
			add_gene(tmp_gene)
		# first gene section: nets having potential drivers in multiple nets
		if len(genes) > 0:
			sec_len.append(len(genes))
		
		single_const_genes, single_genes, single_sec_len = cls.create_tile_genes(
			single_tile_nets,
			config_map,
			used_function,
			lut_functions,
			net_map
		)
		const_genes.extend(single_const_genes)
		genes.extend(single_genes)
		sec_len.extend(single_sec_len)
		
		return const_genes, genes, sec_len
	
	@classmethod
	def create_unused_gene(cls, src_grps: Sequence[SourceGroup], desc: Union[str, None]=None) -> Gene:
		if desc is None:
			desc = "not driven"
		bits = cls.bits_of_src_grps(src_grps)
		if len(bits) == 0:
			raise ValueError("No bits in unused gene")
		return Gene(
			bits,
			AlleleList([Allele((False, )*len(bits), "not driven")]),
			desc
		)
	
	@classmethod
	def create_unused_gene_from_net(cls, net_rel: NetRelation, desc: Union[str, None]=None) -> Gene:
		src_grps = list(net_rel.iter_src_grps())
		return cls.create_unused_gene(src_grps, desc)
	
	@classmethod
	def create_tile_genes(
		cls,
		single_tile_nets: Iterable[NetRelation],
		config_map: Mapping[TilePosition, ConfigDictType],
		used_function: Callable[[NetRelation], bool],
		lut_functions: Iterable[LUTFunction],
		net_map: Mapping[NetId, NetRelation]
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
			
		
		# sort nets by tile
		single_tile_map = {}
		for net in single_tile_nets:
			if net.multiple_drv_tiles:
				raise ValueError("net with multiple driver tiles can't be handled as tile genes")
			tile = next(net.iter_drv_tiles())
			single_tile_map.setdefault(tile, []).append(net)
		
		# find all tiles
		tiles = set(single_tile_map)
		tiles.update(config_map)
		
		for tile in sorted(tiles):
			prev_len = len(genes)
			# tile confs
			for tile_conf in empty_if_missing(config_map[tile], "tile"):
				if tile_conf.kind in ("NegClk", ):
					tmp_gene = cls.create_all_allele_gene(tile_conf)
				else:
					raise ValueError(f"Unsupported tile config '{tile_conf.kind}'")
				
				add_gene(tmp_gene)
			
			# LUTs
			for lut_conf_iter in empty_if_missing(config_map[tile], "lut"):
				for lut_conf in lut_conf_iter:
					if lut_conf.kind in ("DffEnable", "Set_NoReset", "AsyncSetReset"):
						tmp_gene = cls.create_all_allele_gene(
							lut_conf,
							f"tile ({tile.x}, {tile.y}) LUT {lut_conf.index} {lut_conf.kind}"
						)
					elif lut_conf.kind == "TruthTable":
						used_inputs = []
						for in_index in range(4):
							try:
								in_net = net_map[(tile.x, tile.y, f"lutff_{lut_conf.index}/in_{in_index}")]
							except KeyError:
								#TODO: warning
								continue
							
							if in_net.available and used_function(in_net):
								used_inputs.append(in_index)
						
						unused_inputs = [i for i in range(4) if i not in used_inputs]
						if len(lut_functions) == 0:
							# no restrictions regarding functions
							alleles = AllelePow(4, unused_inputs)
						else:
							values_list = []
							desc_list = []
							for func_enum in lut_functions:
								values = cls.lut_function_to_truth_table(func_enum, used_inputs)
								try:
									index = values_list.index(values)
									desc_list[index] += f", {func_enum.name}"
								except ValueError:
									values_list.append(values)
									desc_list.append(func_enum.name)
								
							ordered = sorted(zip(values_list, desc_list), key=lambda e: e[0])
							alleles = AlleleList([Allele(v, d) for v, d in ordered])
							
						tmp_gene = Gene(
							lut_conf.bits,
							alleles,
							f"tile ({tile.x}, {tile.y}) LUT {lut_conf.index} {lut_conf.kind}"
						)
						
					elif lut_conf.kind in ("CarryEnable"):
						continue
					else:
						raise ValueError(f"Unsupported lut config '{lut_conf.kind}'")
					
					add_gene(tmp_gene)
			
			# connections that only belong to this tile
			for net in empty_if_missing(single_tile_map, tile):
				if net.hard_driven:
					continue
				
				src_grps = list(net.iter_src_grps())
				if len(src_grps) == 0:
					continue
				
				if net.available and used_function(net) and not net.has_external_driver:
					bits, alleles = cls.alleles_from_src_grps(src_grps, used_function)
					tmp_gene = Gene(
						bits,
						alleles,
						f"tile ({tile.x}, {tile.y}) driver {net.segment[0][2]}"
					)
				else:
					tmp_gene = cls.create_unused_gene(src_grps, f"tile ({tile.x}, {tile.y}) {net.segment[0][2]} not driven")
				
				add_gene(tmp_gene)
			
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
	
	@staticmethod
	def bits_of_src_grps(src_grps: Iterable[SourceGroup]) -> Tuple[IcecraftBitPosition, ...]:
		all_bits = tuple()
		for sg in src_grps:
			all_bits += sg.bits
		
		return all_bits
	
	@classmethod
	def alleles_from_src_grps(cls, src_grps: Sequence[SourceGroup], used_function: Callable[[NetRelation], bool]) -> Tuple[Tuple[IcecraftBitPosition, ...], AlleleList]:
		if len(src_grps) < 1:
			raise ValueError("Can't create  alleles without at least one SourceGroup")
		
		all_bits = cls.bits_of_src_grps(src_grps)
		width = len(all_bits)
		
		alleles = []
		alleles.append(Allele((False, )*width, "not driven"))
		
		# add available and used sources for each SourceGroup
		# while bits from other SourceGroups remain False
		suffix_len = 0
		for src_grp in reversed(src_grps): # reverse to get values closer to sorted order
			for src, vals in zip(src_grp.iter_srcs(), src_grp.iter_values()):
				if not src.available or not used_function(src):
					continue
				allele = Allele(
					(False, )*(width-len(vals)-suffix_len) + vals + (False, )*suffix_len,
					""
				)
				alleles.append(allele)
			
			suffix_len += len(src_grp.bits)
		
		return all_bits, AlleleList(alleles)
	
	@staticmethod
	def lut_function_to_truth_table(lut_function: LUTFunction, used_inputs: Iterable[int]) -> Tuple[bool, ...]:
		if lut_function == LUTFunction.CONST_0:
			return (False, )*16
		elif lut_function == LUTFunction.CONST_1:
			return (True, )*16
		
		if lut_function == LUTFunction.AND:
			func = lambda x: all(x)
		elif lut_function == LUTFunction.NAND:
			func = lambda x: not all(x)
		elif lut_function == LUTFunction.OR:
			func = lambda x: any(x)
		elif lut_function == LUTFunction.NOR:
			func = lambda x: not any(x)
		elif lut_function == LUTFunction.PARITY:
			func = lambda x: x.count(1) % 2 == 1
		else:
			raise ValueError("Unsupported LUT function '{}'".format(lut_function))
		
		values = []
		for i in range(16):
			in_values = [(i>>j)&1 for j in used_inputs]
			value = func(in_values)
			values.append(value)
		return tuple(values)
		
	
