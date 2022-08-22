"""Intermediate representation of a FPGA structure

The intermediate representation is created from chip database entries.
Afterwards it is modified to fit the specific requirements of  the
current request (e.g. available nets and connections between them).

The final used representation is created from this intermediate
representation. This is necessary as the final usage of the
representation has different requirements (easy storage, simple access)
than the during the creation of the representation (easy modification).

The basic idea is to have a directed graph with potential connections
between nets as edges and configurable elements as vertices (e.g. group of
all bits that define the driver of a net, a LUT). The configurable
elements define how the output is derived from the input (e.g. by
selecting an input).

Multiedges are possible, if a net has two different names that both can
drive the same net.
"""

from dataclasses import dataclass, field
from functools import total_ordering
from typing import Iterable, Union, Any, Mapping, Tuple, List, Dict, Callable, NewType, ClassVar

from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow
from domain.model import Gene

from adapters.icecraft.chip_data import ConfigAssemblage
from adapters.icecraft.chip_data_utils import NetData, ElementInterface, SegEntryType, UNCONNECTED_NAME
from adapters.icecraft.config_item import ConnectionItem, IndexedItem
from adapters.icecraft.misc import IcecraftNetPosition, IcecraftLUTPosition, IcecraftPosition, IcecraftBitPosition, LUTFunction, IcecraftSatisfiabilityError

VertexPosition = NewType("VertexPosition", Union[IcecraftNetPosition, IcecraftLUTPosition])

SEPARATOR = "#"

@dataclass(frozen=True, order=True)
class VertexDesig:
	"""Wrapper to make IcecraftNetPosition and IcecraftLUTPosition comparable"""
	tile: IcecraftPosition
	name: str
	
	@staticmethod
	def canonical_net_name(net_name: str) -> str:
		return f"NET{SEPARATOR}{net_name}"
	
	@staticmethod
	def canonical_lut_name(lut_index: int) -> str:
		return f"LUT{SEPARATOR}{lut_index}"
	
	@classmethod
	def from_net_name(cls, tile: IcecraftPosition, net_name: str) -> "VertexDesig":
		return cls(tile, cls.canonical_net_name(net_name))
	
	@classmethod
	def from_lut_index(cls, tile: IcecraftPosition, lut_index: int) -> "VertexDesig":
		return cls(tile, cls.canonical_lut_name(lut_index))
	
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
		return cls.from_net_name(IcecraftPosition(*seg[:2]), seg[2])

@dataclass(frozen=True, order=True)
class EdgeDesig:
	src: VertexDesig
	dst: VertexDesig
	
	def __post_init__(self):
		assert self.src.tile == self.dst.tile, "src and dst are not in the same tile"
	
	@classmethod
	def net_to_net(cls, tile: IcecraftPosition, src_name: str, dst_name: str) -> "EdgeDesig":
		src = VertexDesig.from_net_name(tile, src_name)
		dst = VertexDesig.from_net_name(tile, dst_name)
		return cls(src, dst)
	
	@classmethod
	def net_to_lut(cls, tile: IcecraftPosition, src_name: str, dst_index: int) -> "EdgeDesig":
		src = VertexDesig.from_net_name(tile, src_name)
		dst = VertexDesig.from_lut_index(tile, dst_index)
		return cls(src, dst)
	
	@classmethod
	def lut_to_net(cls, tile: IcecraftPosition, src_index: int, dst_name: str) -> "EdgeDesig":
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
	def driver_tiles(self) -> Tuple[IcecraftPosition, ...]:
		return tuple(sorted(set(self.desigs[i].tile for i in self.drivers)))
	
	@property
	def bit_count(self) -> int:
		raise NotImplementedError()
	
	def get_bit_tuples(self) -> List[Tuple[IcecraftBitPosition, ...]]:
		raise NotImplementedError()
	
	def get_genes(self, desc: Union[str, None]=None) -> List[Gene]:
		raise NotImplementedError()
	
	def neutral_alleles(self) -> List[AlleleList]:
		raise NotImplementedError()

@dataclass
class PartConf:
	"""specific bits with specific values, i.e. part of a configuration"""
	bits: Tuple[IcecraftBitPosition, ...]
	values: Tuple[bool, ...]

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
			if src_net == UNCONNECTED_NAME and self.rep.has_edge(edge_desig):
				# connection to UNCONNECTED net is enabled by multiple source groups
				# -> don't add edge more than once
				continue
			self.rep.add_edge(edge_desig)
		
		src_grp = SourceGroup(con_item.bits, dst_desig, srcs)
		self.src_grps.append(src_grp)
		
		self.rep.register_bits(src_grp.bits, self)
	
	def __post_init__(self) -> None:
		assert len(self.desigs) > 0
	
	@property
	def bit_count(self) -> int:
		return sum(len(s.bits) for s in self.src_grps)
	
	def get_bit_tuples(self) -> List[Tuple[IcecraftBitPosition, ...]]:
		if len(self.src_grps) == 0:
			return []
		else:
			return [tuple(b for sg in self.src_grps for b in sg.bits)]
	
	def get_edge_config(self, edge_desig: EdgeDesig) -> PartConf:
		"""get bits and their values to configure a certain edge as connection
		
		The number of bits and values may be 0 in case the connection is hardwired.
		
		The goal is to provide the necessary data to check if a connection is established by a configuration. Using this
		data to create or alter configurations may lead to invalid configurations (see below).
		
		Only the relevant bits to set the edge as connection are returned. Other bits (from other source groups), that
		may have to be set to UNCONNECTED are not returned. Therefore relying only on the return value to configure
		connections may lead to invalid configurations taht can damage the device (short circuit).
		"""
		if self.configurable:
			for src_grp in self.src_grps:
				try:
					vals = src_grp.srcs[edge_desig]
				except KeyError:
					continue
				
				return PartConf(src_grp.bits, vals)
		else:
			# hard wired -> just check if the edge is available
			for edge in self.in_edges:
				if edge.desig == edge_desig:
					return PartConf(tuple(), tuple())
			
		raise ValueError(f"Edge {edge_desig} not foun in {self.desigs[0]}")
	
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
			
			allele_seq = self.neutral_alleles()[0]
		else:
			def usable_in_edge(edge):
				return all((edge.available, edge.used, edge.src.available, edge.src.used))
			
			alleles = []
			edge_map = {e.desig: e for e in self.in_edges}
			
			# prepare unconnected option and connected options
			no_uncon = []
			uncon_list = []
			uncon_edge_list = []
			uncon_name = VertexDesig.canonical_net_name(UNCONNECTED_NAME)
			options_list = []
			for sg_index, src_grp in enumerate(self.src_grps):
				options = []
				uncon_vals = None
				uncon_edge = None
				
				for edge_desig, vals in sorted(src_grp.srcs.items(), key=lambda i: i[1]):
					if edge_desig.src.name == uncon_name:
						uncon_vals = vals
						uncon_edge = edge_map[edge_desig]
						# handle unconnected option explicitly, away from the other options
						continue
					
					options.append((edge_map[edge_desig], vals))
				
				options_list.append(options)
				
				uncon_list.append(uncon_vals)
				uncon_edge_list.append(uncon_edge)
				if uncon_vals is None:
					no_uncon.append(sg_index)
			
			if len(no_uncon) > 0:
				raise IcecraftSatisfiabilityError(f"Can't create genes as {len(no_uncon)} have to be connected at the same time")
				# for len(no_uncon)=1 it could be recovered by setting all other option to empty list
				# but that case is currently not required and causes just more complexity
			
			if all(usable_in_edge(e) for e in uncon_edge_list):
				alleles.append(Allele(sum(uncon_list, tuple()), "unconnected"))
			
			# add available and used sources for each SourceGroup
			# while bits from other SourceGroups remain False
			for sg_index, options in reversed(list(enumerate(options_list))): # reverse to get values closer to sorted order
				for edge, vals in options:
					if not usable_in_edge(edge):
						continue
					allele = Allele(
						sum(uncon_list[:sg_index], tuple()) + vals + sum(uncon_list[sg_index+1:], tuple()),
						edge.desig.src.name
					)
					alleles.append(allele)
					
					assert len(allele.values)==bit_count
			
			allele_seq = AlleleList(alleles)
		
		return [Gene(all_bits, allele_seq, base_desc+desc)]
	
	def neutral_alleles(self) -> List[AlleleList]:
		neutral_vals_list = []
		for src_grp in self.src_grps:
			desig = EdgeDesig(VertexDesig.from_net_name(src_grp.dst.tile, UNCONNECTED_NAME), src_grp.dst)
			try:
				vals = src_grp.srcs[desig]
			except KeyError as ke:
				raise IcecraftSatisfiabilityError("UNCONNECTED option missing for neutral allele") from ke
			neutral_vals_list.append(vals)
		
		return [AlleleList([Allele(tuple(s for v in neutral_vals_list for s in v), "neutral")])]
	
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
	index_name_map: ClassVar[Dict[str, int]] = {i: n for i, n in enumerate(names)}
	
	def __post_init__(self) -> None:
		tile = self.dff_enable[0].tile
		assert all(tile==b.tile for b in self.dff_enable)
		assert all(tile==b.tile for b in self.set_no_reset)
		assert all(tile==b.tile for b in self.async_set_reset)
		assert all(tile==b.tile for b in self.truth_table)
	
	def as_tuple(self) -> Tuple[Tuple[IcecraftBitPosition, ...], ...]:
		"""return fields as tuple
		
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
	lut_index: int
	lut_bits: LUTBits
	functions: List[LUTFunction] = field(default_factory=list, init=False)
	# carry enable is separate from lut_bits as it is set dynamically if needed, not by genes
	carry_enable: Tuple[IcecraftBitPosition, ...]
	# override fields that are the same for all LUTs
	# set init=False to avoid TypeError: non-default argument follows default argument
	configurable: bool = field(default=True, init=False)
	drivers: Tuple[int, ...] = field(default=(0, ), init=False)
	
	def __post_init__(self) -> None:
		assert len(self.desigs) == 1
		assert int(self.desig.name.split(SEPARATOR)[-1]) == self.lut_index
		tile = self.desig.tile
		# LUTBits asserts that all tiles are the same, so only check one
		assert self.lut_bits.dff_enable[0].tile == tile
		assert all(b.tile==tile for b in self.carry_enable)
		
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
	def desig(self) -> VertexDesig:
		return self.desigs[0]
	
	@property
	def bit_count(self) -> int:
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
			
			allele_seqs = {n: a for n, a in zip(LUTBits.names, self.neutral_alleles())}
		else:
			allele_seqs = {
				"DffEnable": AlleleAll(len(self.lut_bits.dff_enable)),
				"Set_NoReset": AlleleAll(len(self.lut_bits.set_no_reset)),
				"AsyncSetReset": AlleleAll(len(self.lut_bits.async_set_reset))
			}
			
			# truth table
			if len(self.functions) == 0:
				unused_inputs = [i for i, e in enumerate(self.in_edges) if not (e.available and e.used and e.src.available and e.src.used)]
				allele_seqs["TruthTable"] = AllelePow(len(self.in_edges), unused_inputs)
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
				allele_seqs["TruthTable"] = alleles
		
		genes = [Gene(b, allele_seqs[n], f"{base_desc} {n}{desc}") for b, n in zip(self.lut_bits.as_tuple(), LUTBits.names)]
		return genes
	
	def neutral_alleles(self) -> List[AlleleList]:
		return [AlleleList([Allele((False, )*len(b), "neutral")]) for b in self.lut_bits.as_tuple()]
	
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
		carry_enable = [i.bits for i in config_items if i.kind=="CarryEnable"][0]
		return cls(rep, (desig, ), lut_index, lut_bits, carry_enable)

class InterRep:
	def __init__(self, net_data_iter: Iterable[NetData], config_map: Mapping[IcecraftPosition, ConfigAssemblage]) -> None:
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
		
		assert not self.has_edge(desig)
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
	
	def get_vertices_of_tile(self, tile: IcecraftPosition) -> List[Vertex]:
		try:
			return self._tile_vertex_map[tile]
		except KeyError:
			# no vertices for this tile -> no entry
			return []
	
	def get_edges_of_tile(self, tile: IcecraftPosition) -> List[Edge]:
		try:
			return self._tile_edge_map[tile]
		except KeyError:
			# no edges for this tile -> no entry
			return []
	
	def has_edge(self, desig: EdgeDesig) -> bool:
		return desig in self._edge_map
	
	def iter_vertices(self) -> Iterable[Vertex]:
		yield from self._vertices
	
	def iter_edges(self) -> Iterable[Edge]:
		yield from self._edge_map.values()
	
	def iter_lut_vertices(self) -> Iterable[LUTVertex]:
		for v in self.iter_vertices():
			if isinstance(v, LUTVertex):
				yield v
				
