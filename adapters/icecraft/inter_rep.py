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
from typing import Iterable, Union, Any, Mapping, Tuple, List, Dict, Callable, NewType, ClassVar

from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow
from domain.model import Gene

from .chip_data import ConfigAssemblage
from .chip_data_utils import NetData, ElementInterface, SegEntryType
from .config_item import ConnectionItem, IndexedItem
from .misc import IcecraftNetPosition, IcecraftLUTPosition, TilePosition, IcecraftBitPosition, LUTFunction

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
	
	@classmethod
	def net_to_net(cls, tile: TilePosition, src_name: str, dst_name: str) -> "EdgeDesig":
		src = VertexDesig.from_net_name(tile, src_name)
		dst = VertexDesig.from_net_name(tile, dst_name)
		return cls(src, dst)
	
	@classmethod
	def net_to_lut(cls, tile: TilePosition, src_name: str, dst_index: int) -> "EdgeDesig":
		src = VertexDesig.from_net_name(tile, src_name)
		dst = VertexDesig.from_lut_index(tile, dst_index)
		return cls(src, dst)
	
	@classmethod
	def lut_to_net(cls, tile: TilePosition, src_index: int, dst_name: str) -> "EdgeDesig":
		src = VertexDesig.from_lut_index(tile, src_index)
		dst = VertexDesig.from_net_name(tile, dst_name)
		return cls(src, dst)

@dataclass
class InterElement:
	rep: "InterRep"
	available: bool = field(default=True, init=False)
	used: bool = field(default=True, init=False)

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
	# not configurable -> bit_count == 0, but not the other way around
	# e.g. for ConVertex with external source
	configurable: bool
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
	
	@property
	def driver_tiles(self) -> Tuple[TilePosition, ...]:
		return tuple(sorted(set(self.desigs[i].tile for i in self.drivers)))
	
	@property
	def bit_count(self) -> int:
		raise NotImplementedError()
	
	def get_bit_tuples(self) -> List[Tuple[IcecraftBitPosition, ...]]:
		raise NotImplementedError()
	
	def get_genes(self, desc: Union[str, None]=None) -> List[Gene]:
		raise NotImplementedError()
	
	@staticmethod
	def neutral_alleles(bit_count: int) -> AlleleList:
		return AlleleList([Allele((False, )*bit_count, "neutral")])

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
		
		self.rep.register_bits(src_grp.bits, self)
	
	def __post_init__(self):
		assert len(self.desigs) > 0
	
	@property
	def bit_count(self):
		return sum(len(s.bits) for s in self.src_grps)
	
	def get_bit_tuples(self) -> List[Tuple[IcecraftBitPosition, ...]]:
		if len(self.src_grps) == 0:
			return []
		else:
			return [tuple(b for sg in self.src_grps for b in sg.bits)]
	
	def get_genes(self, desc: str="") -> List[Gene]:
		if not self.available:
			return []
		
		if desc != "":
			desc = " " + desc
		
		desig = self.desigs[0]
		base_desc = f"({desig.tile.x}, {desig.tile.y}) {desig.name}"
		
		all_bits = tuple(b for sg in self.src_grps for b in sg.bits)
		bit_count = len(all_bits)
		if bit_count == 0:
			return []
		
		if self.ext_src or not self.used:
			if self.ext_src:
				base_desc += " external source"
			else:
				base_desc += " unused"
			
			allele_seq = self.neutral_alleles(bit_count)
		else:
			alleles = [Allele((False, )*bit_count, "not driven")]
			edge_map = {e.desig: e for e in self.in_edges}
			# add available and used sources for each SourceGroup
			# while bits from other SourceGroups remain False
			suffix_len = 0
			for src_grp in reversed(self.src_grps): # reverse to get values closer to sorted order
				for edge_desig, vals in sorted(src_grp.srcs.items(), key=lambda i: i[1]):
					edge = edge_map[edge_desig]
					if not all((edge.available, edge.used, edge.src.available, edge.src.used)):
						continue
					allele = Allele(
						(False, )*(bit_count-len(vals)-suffix_len) + vals + (False, )*suffix_len,
						edge.desig.src.name
					)
					alleles.append(allele)
				
				suffix_len += len(src_grp.bits)
			
			assert suffix_len==bit_count
			
			allele_seq = AlleleList(alleles)
		
		return [Gene(all_bits, allele_seq, base_desc+desc)]
	
	@classmethod
	def from_net_data(cls, rep: "InterRep", raw: NetData) -> "ConVertex":
		desigs = tuple(VertexDesig.from_seg_entry(s) for s in raw.segment)
		return cls(rep, desigs, not raw.hard_driven, raw.drivers)

@dataclass
class LUTBits:
	dff_enable: Tuple[IcecraftBitPosition, ...]
	set_no_reset: Tuple[IcecraftBitPosition, ...]
	async_set_reset: Tuple[IcecraftBitPosition, ...]
	truth_table: Tuple[IcecraftBitPosition, ...]
	names: ClassVar[Tuple[str, ...]] = ("DffEnable", "Set_NoReset", "AsyncSetReset", "TruthTable")
	
	def __post_init__(self):
		tile = self.dff_enable[0].tile
		assert all(tile==b.tile for b in self.dff_enable)
		assert all(tile==b.tile for b in self.set_no_reset)
		assert all(tile==b.tile for b in self.async_set_reset)
		assert all(tile==b.tile for b in self.truth_table)
	
	def as_tuple(self) -> Tuple[Tuple[IcecraftBitPosition, ...], ...]:
		"""return fileds as tuple
		
		difference to dataclasses.astuple: not recursive,
		i.e. IcecraftBitPosition is not converted to tuple
		"""
		return (self.dff_enable, self.set_no_reset, self.async_set_reset, self.truth_table)
	
	@classmethod
	def from_config_items(cls, config_items: Iterable[IndexedItem]) -> "LUTBits":
		order = {n: i for i, n in enumerate(cls.names)}
		args = [None]*len(order)
		for item in config_items:
			try:
				index = order[item.kind]
			except KeyError:
				continue
			args[index] = item.bits
		
		assert all(a is not None for a in args)
		
		return cls(*args)

@dataclass
class LUTVertex(Vertex):
	lut_bits: LUTBits
	functions: List[LUTFunction] = field(default_factory=list, init=False)
	# override fields that are the same for all LUTs
	# set init=False to avoid TypeError: non-default argument follows default argument
	configurable: bool = field(default=True, init=False)
	drivers: Tuple[int, ...] = field(default=(0, ), init=False)
	
	def __post_init__(self):
		assert len(self.desigs) == 1
		tile = self.desig.tile
		# LUTBits asserts that all tiles are the same, so only check one
		assert self.lut_bits.dff_enable[0].tile == tile
		
		for bits in self.lut_bits.as_tuple():
			self.rep.register_bits(bits, self)
	
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
	
	@property
	def bit_count(self):
		return sum(len(b) for b in self.lut_bits.as_tuple())
	
	def get_bit_tuples(self) -> List[Tuple[IcecraftBitPosition, ...]]:
		return list(self.lut_bits.as_tuple())
	
	def get_genes(self, desc: str="") -> List[Gene]:
		if not self.available:
			return []
		
		if desc != "":
			desc = " " + desc
		
		base_desc = f"({self.desig.tile.x}, {self.desig.tile.y}) {self.desig.name}"
		
		if self.ext_src or not self.used:
			if self.ext_src:
				base_desc += " external source"
			else:
				base_desc += " unused"
			
			allele_seqs = [self.neutral_alleles(len(b)) for b in self.lut_bits.as_tuple()]
		else:
			allele_seqs = [AlleleAll(len(b)) for b in self.lut_bits.as_tuple()[:3]]
			
			# truth table
			if len(self.functions) == 0:
				unused_inputs = [i for i, e in enumerate(self.in_edges) if not (e.available and e.used and e.src.available and e.src.used)]
				allele_seqs.append(AllelePow(len(self.in_edges), unused_inputs))
			else:
				used_inputs = [i for i, e in enumerate(self.in_edges) if (e.available and e.used and e.src.available and e.src.used)]
				values_list = []
				desc_list = []
				for func_enum in self.functions:
					values = self.lut_function_to_truth_table(func_enum, len(self.in_edges), used_inputs)
					try:
						index = values_list.index(values)
						desc_list[index] += f", {func_enum.name}"
					except ValueError:
						values_list.append(values)
						desc_list.append(func_enum.name)
					
				ordered = sorted(zip(values_list, desc_list), key=lambda e: e[0])
				alleles = AlleleList([Allele(v, d) for v, d in ordered])
				allele_seqs.append(alleles)
		
		genes = [Gene(b, a, f"{base_desc} {n}{desc}") for b, a, n in zip(self.lut_bits.as_tuple(), allele_seqs, LUTBits.names)]
		return genes
	
	@staticmethod
	def lut_function_to_truth_table(lut_function: LUTFunction, input_count: int, used_inputs: Iterable[int]) -> Tuple[bool, ...]:
		assert all(u<input_count for u in used_inputs)
		assert all(used_inputs[i]<used_inputs[i+1] for i in range(len(used_inputs)-1))
		
		combinations = pow(2, input_count)
		
		if lut_function == LUTFunction.CONST_0:
			return (False, )*combinations
		elif lut_function == LUTFunction.CONST_1:
			return (True, )*combinations
		
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
		for i in range(combinations):
			in_values = [(i>>j)&1 for j in used_inputs]
			value = func(in_values)
			values.append(value)
		return tuple(values)
	
	@classmethod
	def from_config_items(cls, rep: "InterRep", config_items: Iterable[IndexedItem]) -> "LUTVertex":
		lut_index = config_items[0].index
		assert all(c.index==lut_index for c in config_items)
		lut_bits = LUTBits.from_config_items(config_items)
		tile = lut_bits.truth_table[0].tile
		desig = VertexDesig.from_lut_index(tile, lut_index)
		return cls(rep, (desig, ), lut_bits)

class InterRep:
	def __init__(self, net_data_iter: Iterable[NetData], config_map: Mapping[TilePosition, ConfigAssemblage]) -> None:
		self._vertices = []
		self._vertex_map = {}
		self._tile_vertex_map = {}
		self._edge_map = {}
		self._tile_edge_map = {}
		self._bit_map = {}
		
		for raw_net in net_data_iter:
			self._add_con_vertex(raw_net)
		
		for tile, config_assem in config_map.items():
			# add LUT vertices
			for lut_grp in config_assem.lut:
				self._add_lut_vertex(lut_grp)
			
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
		# TODO: RAM and D_IN
		
	
	def _add_vertex(self, vertex: Vertex) -> None:
		self._vertices.append(vertex)
		tiles = set()
		for des in vertex.desigs:
			assert des not in self._vertex_map
			self._vertex_map[des] = vertex
			tiles.add(des.tile)
		
		for tile in tiles:
			self._tile_vertex_map.setdefault(tile, []).append(vertex)
	
	def _add_con_vertex(self, raw_net: NetData) -> ConVertex:
		vertex = ConVertex.from_net_data(self, raw_net)
		self._add_vertex(vertex)
		return vertex
	
	def _add_lut_vertex(self, config_items: Iterable[IndexedItem]) -> LUTVertex:
		vertex = LUTVertex.from_config_items(self, config_items)
		self._add_vertex(vertex)
		return vertex
	
	def add_edge(self, desig: EdgeDesig) -> Edge:
		edge = Edge(self, desig)
		
		edge.src.add_edge(edge, False)
		edge.dst.add_edge(edge, True)
		
		assert desig not in self._edge_map
		self._edge_map[desig] = edge
		
		self._tile_edge_map.setdefault(desig.dst.tile, []).append(edge)
		
		return edge
	
	def register_bits(self, bits: Iterable[IcecraftBitPosition], vertex: Vertex) -> None:
		for bit in bits:
			assert bit not in self._bit_map
			self._bit_map[bit] = vertex
	
	def get_vertex(self, desig: VertexDesig) -> Vertex:
		return self._vertex_map[desig]
	
	def get_edge(self, desig: EdgeDesig) -> Edge:
		return self._edge_map[desig]
	
	def get_vertex_for_bit(self, bit: IcecraftBitPosition) -> Vertex:
		return self._bit_map[bit]
	
	def get_vertices_of_tile(self, tile: TilePosition) -> List[Vertex]:
		try:
			return self._tile_vertex_map[tile]
		except KeyError:
			# no vertices for this tile -> no entry
			return []
	
	def get_edges_of_tile(self, tile: TilePosition) -> List[Edge]:
		try:
			return self._tile_edge_map[tile]
		except KeyError:
			# no edges for this tile -> no entry
			return []
	
	def iter_vertices(self) -> Iterable[Vertex]:
		yield from self._vertices
	
	def iter_edges(self) -> Iterable[Edge]:
		yield from self._edge_map.values()
	
	def iter_lut_vertices(self) -> Iterable[LUTVertex]:
		for v in self.iter_vertices():
			if isinstance(v, LUTVertex):
				yield v
				
