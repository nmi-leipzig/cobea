"""Intermediate representation of a FPGA structure

The intermediate representation is created from chip database entries.
Afterwards it is modified to fit the specific requirements of  the
current request (e.g. available nets and connections between them).

The final used representation is created from this intermediate
representation. This is necessary as the final usage of the
representation has different requirements (easy storage, simple access)
than the during the creation of the representation (easy modification).

The basic idea is to have a directed graph with potential connections
between nets as edges configurabel elements as vertices (e.g. group of
all bits that define the driver of a net, a LUT). The configurable
elements define how the output id derived from the input (e.g. by
selecting an input).

Multiedges are possible, if a net has two different names that both can
drive the same net.
"""

from dataclasses import dataclass, field
from functools import total_ordering
from typing import Iterable, Union, Any, Mapping, Tuple, List, Dict

from .chip_data import ConfigAssemblage
from .chip_data_utils import NetData, ElementInterface
from .config_item import ConnectionItem, IndexedItem
from .misc import IcecraftNetPosition, IcecraftLUTPosition, TilePosition, IcecraftBitPosition

@total_ordering
@dataclass(frozen=True, order=False)
class VertexDesig:
	"""Wrapper to make IcecraftNetPosition and IcecraftLUTPosition comparable"""
	position: Union[IcecraftNetPosition, IcecraftLUTPosition]
	
	def __lt__(self, other: Any) -> bool:
		try:
			return self.position < other.position
		except TypeError:
			# compare IcecraftNetPosition and IcecraftLUTPosition
			if isinstance(self.position, IcecraftLUTPosition):
				# IcecraftLUTPosition is smallest
				return True
			elif isinstance(other.position, IcecraftLUTPosition):
				return False
			else:
				# chould not occur: position is not the same type, both are not IcecraftLUTPosition
				# and there are only 2 possible types
				return NotImplemented
		except AttributeError:
			return NotImplemented
	
	@property
	def tile(self):
		return self.position.tile
	
	@classmethod
	def from_net_name(cls, tile: TilePosition, net_name: str) -> "VertexDesig":
		net_pos = IcecraftNetPosition(tile, net_name)
		return cls(net_pos)
	
	@classmethod
	def from_lut_index(cls, tile: TilePosition, lut_index: int) -> "VertexDesig":
		lut_pos = IcecraftLUTPosition(tile, lut_index)
		return cls(lut_pos)

@dataclass(frozen=True, order=True)
class EdgeDesig:
	src: VertexDesig
	dst: VertexDesig
	
	def __post_init__(self):
		assert self.src.tile == self.dst.tile, "src and dst are not in the same tile"

@dataclass
class InterElement:
	rep: "InterRep"

@dataclass
class SourceGroup:
	bits: Tuple[IcecraftBitPosition, ...]
	dst: VertexDesig
	srcs: Mapping[EdgeDesig, Tuple[bool, ...]]
	
	def __post_init__(self) -> None:
		for b in self.bits:
			assert b.tile == self.dst.tile
		for s, v in self.srcs.items():
			assert s.dst == self.dst
			assert len(v) == len(self.bits)

@dataclass
class EdgeData:
	available: bool = field(default=True, init=False)

@dataclass
class Vertex(InterElement):
	available: bool = field(default=True, init=False)
	in_data: Dict[EdgeDesig, EdgeData] = field(default_factory=dict, init=False)
	out_edges: List[EdgeDesig] = field(default_factory=list, init=False)
	ext_src: bool = field(default=False, init=False)
	
	def add_edge(self, edge: EdgeDesig, incoming: bool) -> None:
		if incoming:
			self.in_data[edge] = EdgeData()
		else:
			self.out_edges.append(edge)
	
	def get_in_data(self, edge: EdgeDesig) -> EdgeData:
		return self.in_data[edge]
	
	def iter_in_edges(self) -> Iterable[EdgeDesig]:
		yield from self.in_data.keys()
	
	def iter_out_edges(self) -> Iterable[EdgeDesig]:
		yield from self.out_edges

@dataclass
class ConVertex(Vertex):
	desigs: Tuple[VertexDesig, ...]
	hard_driven: bool
	drivers: Tuple[int, ...]
	src_grps: List[SourceGroup] = field(default_factory=list, init=False)
	
	def add_src_grp(self, con_item: ConnectionItem) -> None:
		dst = VertexDesig(IcecraftNetPosition(con_item.bits[0].tile, con_item.dst_net))
		assert dst in self.desigs, "Wrong dst for ConnectionItem "
		
		srcs = {}
		for value, src_net in zip(con_item.values, con_item.src_nets):
			src = VertexDesig(IcecraftNetPosition(dst.tile, src_net))
			edge = EdgeDesig(src, dst)
			srcs[edge] = value
			self.rep.add_edge(edge)
		
		src_grp = SourceGroup(con_item.bits, dst, srcs)
		self.src_grps.append(src_grp)
	
	@classmethod
	def from_net_data(cls, rep: "InterRep", raw: NetData) -> "ConVertex":
		desigs = tuple(VertexDesig(IcecraftNetPosition.from_coords(*s)) for s in raw.segment)
		return cls(rep, desigs, raw.hard_driven, raw.drivers)

@dataclass
class LUTVertex(Vertex):
	desig: VertexDesig
	truth_table_bits: Tuple[IcecraftBitPosition, ...]
	inputs: List[EdgeDesig] = field(default_factory=list) # an ordered representation of the LUT inputs is required (in edges are unordered)
	
	def __post_init__(self):
		tile = self.desig.tile
		for b in self.truth_table_bits:
			assert b.tile == tile
	
	def connect(self, lut_con: ElementInterface) -> None:
		for in_net in lut_con.in_nets:
			src = VertexDesig(IcecraftNetPosition.from_coords(*in_net))
			in_edge = EdgeDesig(src, self.desig)
			self.rep.add_edge(in_edge)
			self.inputs.append(in_edge)
		
		for out_net in lut_con.out_nets:
			dst = VertexDesig(IcecraftNetPosition.from_coords(*out_net))
			out_edge = EdgeDesig(self.desig, dst)
			self.rep.add_edge(out_edge)
	
	@property
	def desigs(self):
		return (self.desig, )
	
	@classmethod
	def from_truth_table(cls, rep: "InterRep", tt_config: IndexedItem) -> "LUTVertex":
		if tt_config.kind != "TruthTable":
			raise ValueError(f"Need config kind 'TruthTable', got {tt_config.kind}")
		tile = tt_config.bits[0].tile
		desig = VertexDesig(IcecraftLUTPosition(tile, tt_config.index))
		return cls(rep, desig, tt_config.bits)

class InterRep:
	def __init__(self, net_data_iter: Iterable[NetData], config_map: Mapping[TilePosition, ConfigAssemblage]) -> None:
		self._vertices = []
		self._vertex_map = {}
		self._edges = []
		
		for raw_net in net_data_iter:
			self._add_con_vertex(raw_net)
		
		for tile, config_assem in config_map.items():
			# add LUT vertices
			for lut_grp in config_assem.lut:
				for lut_config in lut_grp:
					if lut_config.kind != "TruthTable":
						continue
					
					self._add_lut_vertex(lut_config)
			
		# TODO: CARRY_ONE_IN, RAM and D_IN
		# add configs
	
	def _add_vertex(self, vertex: Vertex) -> None:
		self._vertices.append(vertex)
		for des in vertex.desigs:
			self._vertex_map[des] = vertex
	
	def _add_con_vertex(self, raw_net: NetData) -> None:
		vertex = ConVertex.from_net_data(self, raw_net)
		self._add_vertex(vertex)
	
	def _add_lut_vertex(self, tt_config: IndexedItem) -> None:
		vertex = LUTVertex.from_truth_table(self, tt_config)
		self._add_vertex(vertex)
	
	def add_edge(self, edge: EdgeDesig) -> None:
		src = self.get_vertex(edge.src)
		src.add_edge(edge, False)
		
		dst = self.get_vertex(edge.dst)
		dst.add_edge(edge, True)
		
		self._edges.append(edge)
	
	def get_vertex(self, desig: VertexDesig) -> Vertex:
		return self._vertex_map[desig]
	
	def iter_vertices(self) -> Iterable[Vertex]:
		yield from self._vertices
	
	def iter_edges(self) -> Iterable[EdgeDesig]:
		yield from self._edges
