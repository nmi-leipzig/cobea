from typing import Sequence, Mapping, List, Tuple, Iterable
from dataclasses import dataclass
from contextlib import contextmanager

from domain.interfaces import Representation, RepresentationGenerator
from domain.model import TargetConfiguration, Gene, Chromosome
from domain.request_model import RequestObject, Parameter

from .misc import TilePosition, IcecraftLUTPosition, IcecraftColBufCtrl, IcecraftNetPosition, LUTFunction
from .chip_data import get_config_items, get_net_data
from .chip_data_utils import NetData, SegEntryType, SegType
from .config_item import ConnectionItem

NetId = SegEntryType

class NetRelation:
	"""Represent a nets context and relations to other nets and configrations"""
	def __init__(self, net_data: NetData, inner_tiles: Iterable[TilePosition]=[]) -> None:
		self._net_data = net_data
		self._available = True
		
		# check for external drivers
		self._has_external_driver = False
		for drv_index in net_data.drivers:
			drv_tile = TilePosition(*net_data.segment[drv_index][:2])
			if drv_tile not in inner_tiles:
				self._has_external_driver = True
				break
		
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
		for dst in self.iter_dst():
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
	
	def iter_dst(self) -> Iterable["NetRelation"]:
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
	def net_map_from_net_data(cls, net_data_iter: Iterable[NetData], inner_tiles: Iterable[TilePosition]) -> Mapping[NetId, "NetRelation"]:
		"""create NetRelation instances and put them in a dictionary NetId -> NetRelation"""
		net_map = {}
		for net_data in net_data_iter:
			net_rel = cls(net_data, inner_tiles)
			for net_id in net_rel.segment:
				net_map[net_id] = net_rel
		
		return net_map
	

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
	def dst(self) -> NetRelation:
		return self._dst
	
	@property
	def src_list(self) -> Tuple[NetRelation, ...]:
		return self._src_list
	
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
	colbufctrl: Sequence[IcecraftColBufCtrl]
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
		
		raw_nets = get_net_data(tiles)
		#net_relations = [NetRelation(n) for n in raw_nets]
		net_map = NetRelation.net_map_from_net_data(raw_nets, tiles)
		
		config_map = {t: get_config_items(t) for t in tiles}
		
		return IcecraftRep([], [], [], tuple(sorted(request.output_lutffs)))
	
	@staticmethod
	def tiles_from_rectangle(x_min: int, y_min: int, x_max: int, y_max: int) -> List[TilePosition]:
		return [TilePosition(x, y) for x in range(x_min, x_max+1) for y in range(y_min, y_max+1)]
	
