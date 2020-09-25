from typing import Sequence, Mapping, List, Tuple, Iterable
from dataclasses import dataclass

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
	def __init__(self, net_data: NetData) -> None:
		self._net_data = net_data
		self.available = True
		self.fixed = not self.hard_driven
		# source groups that have this net as destination
		self.src_grp_list = []
		# source groups that have this net as source
		self.dst_grp_list = []
		# index of this net in the source of the source group
		self.dst_indices = []
	
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
	
	def __repr__(self) -> str:
		return f"NetRelation({repr(self._net_data)})"

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
		]}
	
	@property
	def parameters(self) -> Mapping[str, Parameter]:
		return self._parameters
	
	def __call__(self, request: RequestObject) -> IcecraftRep:
		tiles = self.tiles_from_rectangle(request.x_min, request.y_min, request.x_max, request.y_max)
		
		raw_nets = get_net_data(tiles)
		net_relations = [NetRelation(n) for n in raw_nets]
		net_map = self.net_map_from_net_relations(net_relations)
		
		config_map = {t: get_config_items(t) for t in tiles}
		
		return IcecraftRep([], [], [], tuple(sorted(request.output_lutffs)))
	
	@staticmethod
	def tiles_from_rectangle(x_min: int, y_min: int, x_max: int, y_max: int) -> List[TilePosition]:
		return [TilePosition(x, y) for x in range(x_min, x_max+1) for y in range(y_min, y_max+1)]
	
	@staticmethod
	def net_map_from_net_relations(net_relations: Iterable[NetData]) -> Mapping[NetId, NetRelation]:
		net_map = {}
		for net_rel in net_relations:
			for net_id in net_rel.segment:
				net_map[net_id] = net_rel
		
		return net_map
	
	@staticmethod
	def populate_source_groups(net_map: Mapping[NetId, NetRelation], con_configs: Iterable[ConnectionItem]) -> List[SourceGroup]:
		src_grp_list = []
		for item in con_configs:
			# create source group
			tile_pos = item.bits[0].tile
			dst = net_map[(*tile_pos, item.dst_net)]
			src_list = tuple(net_map[(*tile_pos, s)] for s in item.src_nets)
			
			src_grp = SourceGroup(item, dst, src_list)
			
			# add source group to net relations
			dst.src_grp_list.append(src_grp)
			for i, net_rel in enumerate(src_list):
				net_rel.dst_grp_list.append(src_grp)
				net_rel.dst_indices.append(i)
			
			src_grp_list.append(src_grp)
		
		return src_grp_list

