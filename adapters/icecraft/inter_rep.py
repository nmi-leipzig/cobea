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
from typing import Iterable, Union, Any, Mapping, Tuple, List, Dict, Callable, NewType

from .chip_data import ConfigAssemblage
from .chip_data_utils import NetData, ElementInterface, SegEntryType
from .config_item import ConnectionItem, IndexedItem
from .misc import IcecraftNetPosition, IcecraftLUTPosition, TilePosition, IcecraftBitPosition

VertexPosition = NewType("VertexPosition", Union[IcecraftNetPosition, IcecraftLUTPosition])

SEPARATOR = "#"

@dataclass(frozen=True, order=True)
class VertexDesig:
	"""Wrapper to make IcecraftNetPosition and IcecraftLUTPosition comparable"""
	tile: TilePosition
	name: str
	
	@classmethod
	def from_net_name(cls, tile: TilePosition, net_name: str) -> "VertexDesig":
		return cls(tile, f"NET{SEPARATOR}{net_name}")
	
	@classmethod
	def from_lut_index(cls, tile: TilePosition, lut_index: int) -> "VertexDesig":
		return cls(tile, f"LUT{SEPARATOR}{lut_index}")
	
	@classmethod
	def from_net_position(cls, net_pos: IcecraftNetPosition) -> "VertexDesig":
		return cls.from_net_name(net_pos.tile, net_pos.name)
	
	@classmethod
	def from_lut_position(cls, lut_pos: IcecraftLUTPosition) -> "VertexDesig":
		return cls.from_lut_index(lut_pos.tile, lut_pos.z)
	
	@classmethod
	def from_vertex_position(cls, vtx_pos: VertexPosition) -> "VertexDesig":
		if isinstance(vtx_pos, IcecraftNetPosition):
			return cls.from_net_position(vtx_pos)
		elif isinstance(vtx_pos, IcecraftLUTPosition):
			return cls.from_lut_position(vtx_pos)
		
		raise NotImplementedError()
	
	@classmethod
	def from_seg_entry(cls, seg: SegEntryType) -> "VertexDesig":
		return cls.from_net_name(TilePosition(*seg[:2]), seg[2])

@dataclass(frozen=True, order=True)
class EdgeDesig:
	src: VertexDesig
	dst: VertexDesig
	
	def __post_init__(self):
		assert self.src.tile == self.dst.tile, "src and dst are not in the same tile"

@dataclass
class InterElement:
	rep: "InterRep"
	available: bool = field(default=True, init=False)

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
class Edge(InterElement):
	desig: EdgeDesig
	
	@property
	def src(self) -> "Vertex":
		return self.rep.get_vertex(self.desig.src)
	
	@property
	def dst(self) -> "Vertex":
		return self.rep.get_vertex(self.desig.dst)

@dataclass
class Vertex(InterElement):
	in_edges: List[Edge] = field(default_factory=list, init=False)
	out_edges: List[Edge] = field(default_factory=list, init=False)
	ext_src: bool = field(default=False, init=False)
	desigs: Tuple[VertexDesig, ...]
	hard_driven: bool
	drivers: Tuple[int, ...]
	
	def add_edge(self, edge: Edge, incoming: bool) -> None:
		if incoming:
			self.in_edges.append(edge)
		else:
			self.out_edges.append(edge)
	
	def iter_in_edges(self) -> Iterable[Edge]:
		yield from self.in_edges
	
	def iter_out_edges(self) -> Iterable[Edge]:
		yield from self.out_edges
	

@dataclass
class ConVertex(Vertex):
	src_grps: List[SourceGroup] = field(default_factory=list, init=False)
	
	def add_src_grp(self, con_item: ConnectionItem) -> None:
		dst_desig = VertexDesig.from_net_name(con_item.bits[0].tile, con_item.dst_net)
		assert dst_desig in self.desigs, "Wrong dst for ConnectionItem "
		
		srcs = {}
		for value, src_net in zip(con_item.values, con_item.src_nets):
			src_desig = VertexDesig.from_net_name(dst_desig.tile, src_net)
			edge_desig = EdgeDesig(src_desig, dst_desig)
			srcs[edge_desig] = value
			self.rep.add_edge(edge_desig)
		
		src_grp = SourceGroup(con_item.bits, dst_desig, srcs)
		self.src_grps.append(src_grp)
	
	@classmethod
	def from_net_data(cls, rep: "InterRep", raw: NetData) -> "ConVertex":
		desigs = tuple(VertexDesig.from_seg_entry(s) for s in raw.segment)
		return cls(rep, desigs, raw.hard_driven, raw.drivers)

@dataclass
class LUTVertex(Vertex):
	truth_table_bits: Tuple[IcecraftBitPosition, ...]
	# override fields that are the same for all LUTs
	# set init=False to avoid TypeError: non-default argument follows default argument
	hard_driven: bool = field(default=True, init=False)
	drivers: Tuple[int, ...] = field(default=(0, ), init=False)
	
	def __post_init__(self):
		tile = self.desig.tile
		for b in self.truth_table_bits:
			assert b.tile == tile
		assert len(self.desigs) == 1
	
	def connect(self, lut_con: ElementInterface) -> None:
		for in_net in lut_con.in_nets:
			src = VertexDesig.from_seg_entry(in_net)
			in_edge = EdgeDesig(src, self.desig)
			self.rep.add_edge(in_edge)
		
		for out_net in lut_con.out_nets:
			dst = VertexDesig.from_seg_entry(out_net)
			out_edge = EdgeDesig(self.desig, dst)
			self.rep.add_edge(out_edge)
	
	@property
	def desig(self):
		return self.desigs[0]
	
	@classmethod
	def from_truth_table(cls, rep: "InterRep", tt_config: IndexedItem) -> "LUTVertex":
		if tt_config.kind != "TruthTable":
			raise ValueError(f"Need config kind 'TruthTable', got {tt_config.kind}")
		tile = tt_config.bits[0].tile
		desig = VertexDesig.from_lut_index(tile, tt_config.index)
		return cls(rep, (desig, ), tt_config.bits)

class InterRep:
	def __init__(self, net_data_iter: Iterable[NetData], config_map: Mapping[TilePosition, ConfigAssemblage]) -> None:
		self._vertices = []
		self._vertex_map = {}
		self._edge_map = {}
		
		for raw_net in net_data_iter:
			self._add_con_vertex(raw_net)
		
		for tile, config_assem in config_map.items():
			# add LUT vertices
			for lut_grp in config_assem.lut:
				for lut_config in lut_grp:
					if lut_config.kind != "TruthTable":
						continue
					
					self._add_lut_vertex(lut_config)
			
			# connect LUTs
			for lut_index, single_lut in enumerate(config_assem.lut_io):
				desig = VertexDesig.from_lut_index(tile, lut_index)
				vertex = self.get_vertex(desig)
				vertex.connect(single_lut)
			
			# add connection configs
			for config_item in config_assem.connection:
				desig = VertexDesig.from_net_name(tile, config_item.dst_net)
				vertex = self.get_vertex(desig)
				vertex.add_src_grp(config_item)
		# TODO: CARRY_ONE_IN, RAM and D_IN
		
	
	def _add_vertex(self, vertex: Vertex) -> None:
		self._vertices.append(vertex)
		for des in vertex.desigs:
			self._vertex_map[des] = vertex
	
	def _add_con_vertex(self, raw_net: NetData) -> ConVertex:
		vertex = ConVertex.from_net_data(self, raw_net)
		self._add_vertex(vertex)
		return vertex
	
	def _add_lut_vertex(self, tt_config: IndexedItem) -> LUTVertex:
		vertex = LUTVertex.from_truth_table(self, tt_config)
		self._add_vertex(vertex)
		return vertex
	
	def add_edge(self, desig: EdgeDesig) -> Edge:
		edge = Edge(self, desig)
		
		edge.src.add_edge(edge, False)
		edge.dst.add_edge(edge, True)
		
		self._edge_map[desig] = edge
		
		return edge
	
	def get_vertex(self, desig: VertexDesig) -> Vertex:
		return self._vertex_map[desig]
	
	def get_edge(self, desig: EdgeDesig) -> Edge:
		return self._edge_map[desig]
	
	def iter_vertices(self) -> Iterable[Vertex]:
		yield from self._vertices
	
	def iter_edges(self) -> Iterable[Edge]:
		yield from self._edge_map.values()
	
