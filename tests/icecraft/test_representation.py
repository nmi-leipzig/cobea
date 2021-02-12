import unittest
import re
import copy
import itertools
import pdb
from typing import NamedTuple, Iterable, List, Mapping, Callable, Tuple, Union, Dict
from enum import Enum, auto
from dataclasses import dataclass, field

import adapters.icecraft as icecraft
from adapters.icecraft import TilePosition, IcecraftBitPosition, IcecraftNetPosition, IcecraftColBufCtrl, LUTFunction
from domain.request_model import RequestObject
from domain.model import Gene
from domain.allele_sequence import AlleleList, AlleleAll, AllelePow, Allele
from adapters.icecraft.chip_data import ConfigAssemblage, get_config_items, get_net_data
from adapters.icecraft.chip_data_utils import NetData, ElementInterface
from adapters.icecraft.config_item import ConnectionItem, IndexedItem, ConfigItem
from adapters.icecraft.inter_rep import InterRep, VertexDesig, EdgeDesig, Vertex

from ..test_request_model import check_parameter_user

from .common import TEST_DATA_DIR, create_bits
from .data.chip_resources import NET_DATA, CON_DATA, LUT_DATA, LUT_CON

class Comparison(Enum):
	DIFFERENT = auto()
	DISORDERED = auto()
	EQUIVALENT = auto()
	IDENTICAL = auto()

class IcecraftRepGenTest(unittest.TestCase):
	def test_creation(self):
		dut = icecraft.IcecraftRepGen()
	
	def test_call(self):
		dut = icecraft.IcecraftRepGen()
		req = RequestObject()
		req["x_min"] = 2
		req["y_min"] = 2
		req["x_max"] = 2
		req["y_max"] = 2
		req["exclude_nets"] = ["sp4", "sp12", "glb_netwk"]
		req["include_nets"] = []
		req["output_lutffs"] = [icecraft.IcecraftLUTPosition.from_coords(2, 2, 2)]
		req["joint_input_nets"] = []
		req["lone_input_nets"] = []
		req["lut_functions"] = [icecraft.LUTFunction.NAND, icecraft.LUTFunction.AND]
		
		dut(req)
	
	def parse_gene(self, raw_gene, desc=""):
		tile = icecraft.TilePosition(*raw_gene[0])
		
		bit_pos = []
		for raw_bit in raw_gene[1]:
			bit_pos.append(icecraft.IcecraftBitPosition(tile, *raw_bit))
		
		raw_alleles = raw_gene[2]
		if raw_alleles == []:
			alleles = model.AlleleAll(len(bit_pos))
		else:
			tmp_alleles = []
			for j, raw_allele in enumerate(raw_alleles):
				tmp_alleles.append(model.Allele(raw_allele, f"allele {j}"))
			
			alleles = model.AlleleList(tmp_alleles)
		
		return model.Gene(tuple(bit_pos), alleles, desc)
	
	@unittest.skip
	def test_correct_rep(self):
		with open(os.path.join(TEST_DATA_DIR, "rep_creation.json"), "r") as json_file:
			raw_test_data = json.load(json_file)
		dut = icecraft.IcecraftRepGen()
		
		for raw_test in raw_test_data:
			with self.subTest():
				# read test data and create request
				req = RequestObject()
				req["x_min"] = raw_test[0]
				req["y_min"] = raw_test[1]
				req["x_max"] = raw_test[2]
				req["y_max"] = raw_test[3]
				req["exclude_nets"] = [v for v, d in raw_test[4]]
				req["include_nets"] = [v for v, d in raw_test[5]]
				output = [icecraft.IcecraftLUTPosition.from_coords(*c) for c in raw_test[6]]
				req["output_lutffs"] = list(output)
				req["joint_input_nets"] = raw_test[7]
				req["lone_input_nets"] = raw_test[8]
				req["lut_functions"] = [icecraft.LUTFunction[s] for s in raw_test[9]]
				
				genes = []
				
				for i, raw_gene in enumerate(raw_test[10]):
					genes.append(self.parse_gene(raw_gene, f"gene {i}"))
				
				const_bits = []
				for i, raw_const in enumerate(raw_test[11]):
					const_bits.append(self.parse_gene(raw_const, f"const {i}"))
				
				used_colbufctrl = []
				for raw_ctrl in raw_test[12]:
					used_colbufctrl.append(icecraft.IcecraftColBufCtrl.from_coords(*raw_ctrl))
				
				# call DUT
				rep = dut(req)
				
				# check representation
				self.assertEqual(set(genes), set(rep.genes))
				self.assertEqual(set(const_bits), set(constant))
				self.assertEqual(set(used_colbufctrl), set(rep.colbufctrl))
				self.assertEqual(set(output), set(rep.output))
				
		
	
	def test_parameter_user(self):
		rep_gen = icecraft.IcecraftRepGen()
		check_parameter_user(self, rep_gen)
	
	def test_tiles_from_rectangle(self):
		test_data = (
			((2, 2, 2, 2), [(2, 2)]), # single tile
			((3, 5, 7, 5), [(3, 5), (4, 5), (5, 5), (6, 5), (7, 5)]), # row
			((7, 9, 7, 13), [(7, 9), (7, 10), (7, 11), (7, 12), (7, 13)]), # colum
			((4, 6, 5, 7), [(4, 6), (4, 7), (5, 6), (5, 7)]), # no inner tile
			((5, 8, 7, 10), [(5, 8), (5, 9), (5, 10), (6, 8), (6, 9), (6, 10), (7, 8), (7, 9), (7, 10)]), # inner tile
		)
		
		for rect, exp in test_data:
			res = icecraft.IcecraftRepGen.tiles_from_rectangle(*rect)
			res_set = set(res)
			
			# no duplicates
			self.assertEqual(len(res), len(res_set))
			
			# correct tiles
			self.assertEqual(set(exp), res_set)
	
	def check_available(self, rep, exp_dict):
		for seg, exp_value in exp_dict.items():
			desig = VertexDesig.from_seg_entry(seg)
			vtx = rep.get_vertex(desig)
			self.assertEqual(exp_value, vtx.available, f"{desig}")
	
	def cond_func(self, vertex):
		for desig in vertex.desigs:
			if re.match(r".*out$", desig.name):
				return True
		return False
	
	def test_set_available_vertex(self):
		all_segs = [n.segment[0] for n in NET_DATA]
		rep = InterRep(NET_DATA, {})
		
		with self.subTest(desc="all to False"):
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: True, False)
			self.check_available(rep, {s: False for s in all_segs})
		
		with self.subTest(desc="all to True"):
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: True, True)
			exp_dict = {s: True for s in all_segs}
			self.check_available(rep, exp_dict)
		
		with self.subTest(desc="no change"):
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: False, False)
			self.check_available(rep, exp_dict)
		
		with self.subTest(desc="regex"):
			# reset
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: True, True)
			
			excluded = [(2, 3, "lut_out"), (0, 3, "right"), (0, 3, "wire_in_1"), (2, 3, "empty_out"), (4, 2, "out"), (7, 0, "out")]
			exp_dict = {s: True if s not in excluded else False for s in all_segs}
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: any(re.match(r".*out$", d.name) for d in x.desigs), False)
			self.check_available(rep, exp_dict)
		
		with self.subTest(desc="regex function"):
			# reset
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: True, True)
			
			icecraft.IcecraftRepGen.set_available_vertex(rep, self.cond_func, False)
			self.check_available(rep, exp_dict)
		
		with self.subTest(desc="external driver"):
			# reset
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: True, True)
			# set ext_src
			for vtx in rep.iter_vertices():
				vtx.ext_src = any(vtx.desigs[i].tile in [(1, 3), (7, 0)] for i in vtx.drivers)
			
			excluded = [(0, 3, "right"), (0, 3, "wire_in_1"), (5, 0, "long_span_4"), (7, 0, "out")]
			exp_dict = {s: True if s not in excluded else False for s in all_segs}
			icecraft.IcecraftRepGen.set_available_vertex(rep, lambda x: x.ext_src, False)
			self.check_available(rep, exp_dict)
			
	
	def check_available_edge(self, rep, exp_dict):
		for desig, exp_value in exp_dict.items():
			edge = rep.get_edge(desig)
			self.assertEqual(exp_value, edge.available, f"{desig}")
	
	def test_set_available_edge(self):
		config_map = {}
		for con_item in CON_DATA:
			config_assem = config_map.setdefault(con_item.bits[0].tile, ConfigAssemblage())
			config_assem.connection += (con_item, )
		
		tile = LUT_DATA[0][0].bits[0].tile
		config_map.setdefault(tile, ConfigAssemblage()).lut = LUT_DATA
		config_map[tile].lut_io = LUT_CON
		
		rep = InterRep(NET_DATA, config_map)
		
		with self.subTest(desc="all to False"):
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: True, False)
			
			exp_dict = {e.desig: False for e in rep.iter_edges()}
			self.check_available_edge(rep, exp_dict)
		
		with self.subTest(desc="all to True"):
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: True, True)
			
			exp_dict = {e.desig: True for e in rep.iter_edges()}
			self.check_available_edge(rep, exp_dict)
		
		with self.subTest(desc="no change"):
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: False, False)
			
			self.check_available_edge(rep, exp_dict)
		
		with self.subTest(desc="regex"):
			# reset
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: True, True)
			
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: any(re.match(r".*span", d.name) for d in e.src.desigs), False)
			
			excluded = [
				EdgeDesig.net_to_net(TilePosition(4, 2), "short_span_2", "short_span_1"),
				EdgeDesig.net_to_net(TilePosition(4, 2), "short_span_1", "short_span_2"),
				EdgeDesig.net_to_net(TilePosition(5, 3), "long_span_2", "long_span_1"),
				EdgeDesig.net_to_net(TilePosition(8, 3), "long_span_3", "long_span_2"),
				EdgeDesig.net_to_net(TilePosition(8, 0), "long_span_4", "long_span_3"),
				EdgeDesig.net_to_net(TilePosition(5, 0), "long_span_1", "long_span_4"),
			]
			exp_dict = {e.desig: True if e.desig not in excluded else False for e in rep.iter_edges()}
			self.check_available_edge(rep, exp_dict)
		
		with self.subTest(desc="external driver of dst"):
			# reset
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: True, True)
			
			for seg in [(2, 3, "internal"), (5, 0, "long_span_1")]:
				desig = VertexDesig.from_seg_entry(seg)
				vtx = rep.get_vertex(desig)
				vtx.ext_src = True
			
			icecraft.IcecraftRepGen.set_available_edge(rep, lambda e: e.dst.ext_src, False)
			
			excluded = [
				EdgeDesig.net_to_net(TilePosition(2, 3), "left",  "internal"),
				EdgeDesig.net_to_net(TilePosition(2, 3), "wire_out",  "internal"),
				EdgeDesig.net_to_net(TilePosition(5, 3), "long_span_2", "long_span_1"),
			]
			exp_dict = {e.desig: True if e.desig not in excluded else False for e in rep.iter_edges()}
			self.check_available_edge(rep, exp_dict)
		
	
	def test_set_external_source(self):
		all_segs = [n.segment[0] for n in NET_DATA]
		test_data = (
			([], {s: True if s!=(2, 3, "empty_out") else False for s in all_segs}, "no tiles"),
			(list(set(TilePosition(*s[:2]) for n in NET_DATA for s in n.segment)), {s: False for s in all_segs}, "all tiles"),
			([TilePosition(2, 3)], {s: True if s not in [
				(2, 3, "internal"), (2, 3, "internal_2"),
				(2, 3, "lut_out"), (2, 3, "empty_out")
			] else False for s in all_segs}, "single driver in"),
			([TilePosition(1, 3)], {s: True if s not in [(0, 3, "right"), (2, 3, "empty_out")] else False for s in all_segs}, "multiple driver one in, one out"),
		)
		for tiles, exp_dict, desc in test_data:
			rep = InterRep(NET_DATA, {})
			with self.subTest(desc=desc):
				icecraft.IcecraftRepGen.set_external_source(rep, tiles)
				for seg, exp in exp_dict.items():
					desig = VertexDesig.from_seg_entry(seg)
					vtx = rep.get_vertex(desig)
					self.assertEqual(exp, vtx.ext_src, f"Wrong for {desig}")
	
	def test_create_regex_condition_vertex(self):
		all_segs = [n.segment[0] for n in NET_DATA]
		test_data = (
			(r"", {s: True for s in all_segs}),
			(r"never_seen", {s: False for s in all_segs}),
			(r"NET#internal", {s: True if s in [(2, 3, "internal"), (2, 3, "internal_2")] else False for s in all_segs}),
			(r".*span_\d", {s: True if s in [
				(4, 2, "short_span_1"), (4, 1, "short_span_2"), (5, 0, "long_span_1"),
				(5, 3, "long_span_2"), (8, 0, "long_span_3"), (5, 0, "long_span_4")
			] else False for s in all_segs})
		)
		
		rep = InterRep(NET_DATA, {})
		
		for regex_str, exp_dict in test_data:
			with self.subTest(regex=regex_str):
				func = icecraft.IcecraftRepGen.create_regex_condition_vertex(regex_str)
				for seg, exp_val in exp_dict.items():
					desig = VertexDesig.from_seg_entry(seg)
					vtx = rep.get_vertex(desig)
					val = func(vtx)
					self.assertEqual(exp_val, val, f"{desig}")
	
	def test_choose_nets(self):
		all_segs = [n.segment[0] for n in NET_DATA]
		ext_drv = {s: True if s in [(0, 3, "right"), (0, 3, "wire_in_1"), (5, 0, "long_span_4"), (7, 0, "out")] else False for s in all_segs}
		
		test_data = (
			("empty parameters, only external driven unavailable", (
				[], [], [], []
			), {s: not v for s, v in ext_drv.items()}),
			("exclude nets", (
				[r".*span"], [], [], []
			), {s: True if s in [(2, 3, "internal"), (2, 3, "internal_2"), (2, 3, "lut_out"), (2, 3, "empty_out"), (4, 2, "out")] else False for s in all_segs}),
			("include nets", (
				[], ["NET#left$"], [], []
			), {s: True if s not in [(0, 3, 'wire_in_1'), (5, 0, 'long_span_4'), (7, 0, 'out')] else False for s in all_segs}),
			("joint_input_nets", (
				[], [], ["NET#left"], []
			), {s: True if s not in [(0, 3, 'wire_in_1'), (5, 0, 'long_span_4'), (7, 0, 'out')] else False for s in all_segs}),
			("lone_input_nets", (
				[], [], [], [IcecraftNetPosition.from_coords(2, 3, "left")]
			), {s: True if s not in [(0, 3, 'wire_in_1'), (5, 0, 'long_span_4'), (7, 0, 'out')] else False for s in all_segs}),
			("complete example", (
				[r".*span"], ["^NET#long_span_\d$"], ["NET#out"], [IcecraftNetPosition.from_coords(2, 3, "left")]
			), {s: True if s not in [(0, 3, 'wire_in_1'), (4, 2, 'short_span_1'), (4, 1, 'short_span_2')] else False for s in all_segs}),
		)
		
		
		with self.subTest(desc="default values of available"):
			rep = InterRep(NET_DATA, {})
			self.check_available(rep, {s: True for s in all_segs})
		
		for desc, in_data, exp_dict in test_data:
			with self.subTest(desc=desc):
				rep = InterRep(NET_DATA, {})
				# set externally driven flag
				for seg, ext_val in ext_drv.items():
					desig = VertexDesig.from_seg_entry(seg)
					vtx = rep.get_vertex(desig)
					vtx.ext_src = ext_val
				
				req = RequestObject()
				req["exclude_nets"], req["include_nets"], req["joint_input_nets"], req["lone_input_nets"] = in_data
				
				icecraft.IcecraftRepGen._choose_nets(rep, req)
				
				self.check_available(rep, exp_dict)
	
	def test_get_colbufctrl_coordinates(self):
		net_data_glb = [NetData(tuple(
			[(0, i, "padin_1")]+[(x, y, f"glb_netwk_{i}") for x in range(1, 33) for y in range(1, 33)]
		), False, (0,)) for i in range(8)]
		available_glb = [True, False, False, False, False, True, False, True]
		
		class DstData(NamedTuple):
			x: int
			y: int
			name: str
			avail: bool
			con: Dict[int, bool]
		
		class CBCData(NamedTuple):
			desc: str
			dsts: List[DstData]
			exp: List[IcecraftColBufCtrl]
		
		test_data = (
			# (description, [(x, y, net_name, is_available), ...], expected_results)
			CBCData("no tile", [], []),
			CBCData(
				"single edge",
				[
					DstData(16, 17, "net_a", True, {0: False, 2: True, 3: False, 5: True}),
					DstData(18, 17, "net_a", False, {0: False, 2: True, 3: False, 5: True}),
				],
				[IcecraftColBufCtrl.from_coords(16, 24, 5)]
			),
			CBCData(
				"RAM tiles",
				[DstData(*t, "net_a", True, {0: False, 2: True, 3: False, 5: True}) for t in ((8, 3), (8, 29), (25, 16), (25, 17))],
				[
					IcecraftColBufCtrl.from_coords(8, 8, 5), IcecraftColBufCtrl.from_coords(8, 25, 5),
					IcecraftColBufCtrl.from_coords(25, 9, 5), IcecraftColBufCtrl.from_coords(25, 24, 5),
				]
			),
			CBCData(
				"RAM tiles unavailable",
				[DstData(*t, "net_a", False, {0: False, 2: True, 3: False, 5: True}) for t in ((8, 3), (8, 29), (25, 16), (25, 17))],
				[]
			),
			CBCData(
				"column",
				[DstData(6, y, "net_a", True, {0: False, 2: True, 3: False, 5: True}) for y in range(10, 17)]
				+[DstData(8, y, "net_a", False, {0: False, 2: True, 3: False, 5: True}) for y in range(10, 17)],
				[IcecraftColBufCtrl.from_coords(6, 9, 5)]
			),
		)
		
		for tc in test_data:
			with self.subTest(desc=tc.desc):
				net_data_dst = [NetData((d[:3],), False, (0, )) for d in tc.dsts]
				available_dst = [d.avail for d in tc.dsts]
				
				rep = InterRep(net_data_glb+net_data_dst, {})
				
				for raw_net, avail in zip(net_data_glb+net_data_dst, available_glb+available_dst):
					desig = VertexDesig.from_seg_entry(raw_net.segment[0])
					vtx = rep.get_vertex(desig)
					vtx.available = avail
				
				for dst_data in tc.dsts:
					for glb_index, edge_avail in dst_data.con.items():
						tile = TilePosition(dst_data.x, dst_data.y)
						src_desig = VertexDesig.from_net_name(tile, f"glb_netwk_{glb_index}")
						dst_desig = VertexDesig.from_net_name(tile, dst_data.name)
						edge = rep.add_edge(EdgeDesig(src_desig, dst_desig))
						edge.available = edge_avail
				
				res = icecraft.IcecraftRepGen.get_colbufctrl_coordinates(rep)
				
				self.assertEqual(tc.exp, res)
		
	
	def test_get_colbufctrl_config(self):
		test_data = (
			(
				[IcecraftColBufCtrl.from_coords(1, 8, 0), IcecraftColBufCtrl.from_coords(13, 9, 4)],
				[
					IndexedItem((IcecraftBitPosition.from_coords(1, 8, 9, 7), ), "ColBufCtrl", 0), 
					IndexedItem((IcecraftBitPosition.from_coords(13, 9, 13, 7), ), "ColBufCtrl", 4), 
				]
			),
			(
				[IcecraftColBufCtrl.from_coords(8, 8, 0), IcecraftColBufCtrl.from_coords(25, 24, 4)],
				[
					IndexedItem((IcecraftBitPosition.from_coords(8, 8, 9, 7), ), "ColBufCtrl", 0), 
					IndexedItem((IcecraftBitPosition.from_coords(25, 24, 13, 7), ), "ColBufCtrl", 4), 
				]
			),
		)
		
		for coords, exp in test_data:
			with self.subTest(coords=coords):
				res = icecraft.IcecraftRepGen.get_colbufctrl_config(coords)
				self.assertEqual(exp, res)
	
	def generic_carry_in_net_test(self, exp_map, exp_nets, config_map, raw_nets):
		in_map = copy.deepcopy(config_map)
		in_nets = list(raw_nets)
		
		icecraft.IcecraftRepGen.carry_in_set_net(in_map, in_nets)
		
		self.assertEqual(exp_map, in_map)
		self.assertEqual(exp_nets, in_nets)
	
	def test_carry_in_set_net(self):
		one_cis_pos = (4, 2)
		no_cis_pos = (8, 3)
		in_nets = list(NET_DATA)
		
		# create config map from connection config
		in_map = {}
		for con_item in CON_DATA:
			tile_configs = in_map.setdefault(con_item.bits[0].tile, ConfigAssemblage())
			tile_configs.connection += (con_item, )
		for x, y in (one_cis_pos, no_cis_pos):
			in_map[(x, y)].tile = (ConfigItem((IcecraftBitPosition.from_coords(x, y, 0, 2), ), "NegClk"), )
		
		exp_map = copy.deepcopy(in_map)
		in_map[one_cis_pos].tile += (ConfigItem((IcecraftBitPosition.from_coords(*one_cis_pos, 1, 50), ), "CarryInSet"), )
		
		exp_map[one_cis_pos].connection += (ConnectionItem(
			(IcecraftBitPosition.from_coords(*one_cis_pos, 1, 50), ),
			"connection", "carry_in_mux", ((True, ), ), (icecraft.representation.CARRY_ONE_IN, )
		), )
		
		exp_nets = list(in_nets)
		exp_nets.append(NetData(((*one_cis_pos, icecraft.representation.CARRY_ONE_IN), ), True, (0, )))
		
		with self.subTest(desc="no and one CarryInSet items and map entries without 'tile' key"):
			self.generic_carry_in_net_test(exp_map, exp_nets, in_map, in_nets)
		
		with self.subTest(desc="two CarryInSet items"):
			in_map[one_cis_pos].tile += (ConfigItem((IcecraftBitPosition.from_coords(*one_cis_pos, 1, 51), ), "CarryInSet"), )
			with self.assertRaises(ValueError):
				self.generic_carry_in_net_test(exp_map, exp_nets, in_map, in_nets)
	
	def transform_to_type(self, raw_data, type_hint):
		from typing import get_type_hints
		
		if hasattr(type_hint, "__origin__"):
			# from typing
			org = type_hint.__origin__
			args = type_hint.__args__
			
			if org == tuple:
				if len(args) == 0:
					return tuple(raw_data)
				
				if len(args) == 2 and args[1] == Ellipsis:
					sub_types = [args[0]]*len(raw_data)
				else:
					sub_types = args
				
				data = []
				for raw, sub in zip(raw_data, sub_types):
					sub_data = self.transform_to_type(raw, sub)
					data.append(sub_data)
				return tuple(data)
			elif org == list:
				if len(args) == 0:
					return list(raw_data)
				
				sub_type = args[0]
				data = []
				for raw in raw_data:
					sub_data = self.transform_to_type(raw, sub_type)
					data.append(sub_data)
				return data
			else:
				raise ValueError(f"Unsupported typing class {type_hint}")
		else:
			sub_types = get_type_hints(type_hint).values()
			
			if len(sub_types) == 0:
				return type_hint(raw_data)
			
			assert len(raw_data) == len(sub_types)
			data = []
			for raw, sub in zip(raw_data, sub_types):
				sub_data = self.transform_to_type(raw, sub)
				data.append(sub_data)
			
			return type_hint(*data)
		
		return None
	
	def compare_allele_seq(self, seq_a, seq_b):
		if seq_a == seq_b:
			return Comparison.IDENTICAL
		
		if len(seq_a) == len(seq_b):
			if set(seq_a) == set(seq_b):
				for a, b in zip(seq_a, seq_b):
					if a != b:
						return Comparison.DISORDERED
				return Comparison.EQUIVALENT
		
		return Comparison.DIFFERENT
	
	@unittest.skip("creates wrong fails")
	def test_create_genes_prev(self):
		# test create_genes with stored results from previous implementation
		# currently the change of the names of nets causes all cases to fail
		# 'my_net_name' -> 'NET#my_net_name'
		class PrevGeneData(NamedTuple):
			tile: Tuple[int, int]
			bits: Tuple[Tuple[int, int], ...]
			values: List[Tuple[bool, ...]]
		
		class GeneData(NamedTuple):
			bits: Tuple[IcecraftBitPosition, ...]
			values: List[Tuple[bool, ...]]
			
			def val_list(self):
				if self.values != []:
					return self.values
				
				return list(itertools.product((False, True), repeat=len(self.bits)))
		
		class MappingCase(NamedTuple):
			x_min: int
			y_min: int
			x_max: int
			y_max: int
			exclude_nets: List[Tuple[str, str]]
			include_nets: List[Tuple[str, str]]
			output_lutffs: List[Tuple[int, int, int]]
			joint_input_nets: List[str]
			lone_input_nets: List[Tuple[int, int, str]]
			lut_functions: List[str]
			genes: List[PrevGeneData]
			const_genes: List[PrevGeneData]
			colbufctrl: List[Tuple[int, int, int]]
		
		def gene_to_data(gene):
			if isinstance(gene.alleles, AlleleAll) or (isinstance(gene.alleles, AllelePow) and len(gene.alleles._unused) == 0):
				values = []
			else:
				if len(gene.alleles) > 1000:
					raise Exception(f"{len(gene.alleles)} alleles in {type(gene.alleles)}")
				values = [a.values for a in gene.alleles]
			
			return GeneData(gene.bit_positions, values)
		
		def prev_to_data(prev_gene_data):
			bits = create_bits(*prev_gene_data.tile, prev_gene_data.bits)
			return GeneData(bits, prev_gene_data.values)
		
		def gen_bit_dict(gene_iter):
			bit_dict = {b: g for g in gene_iter for b in g.bits}
			return bit_dict
		
		def bits_to_str(bits):
			parts = [f"B{b.group}[{b.index}]@({b.x}, {b.y})" for b in bits]
			return f"({', '.join(parts)})"
		
		def sub_values(bits, gene_data):
			indices = [gene_data.bits.index(b) for b in bits]
			values = [tuple(v[i] for i in indices) for v in gene_data.values]
			return values
		
		class MissingComp(NamedTuple):
			gene: GeneData
			missing: List[IcecraftBitPosition] = []
		
		class DiffValueComp(NamedTuple):
			bits: Tuple[IcecraftBitPosition, ...]
			missing: List[Tuple[bool, ...]] = []
			additional: List[Tuple[bool, ...]] = []
			
			@classmethod
			def from_sets(cls, bits, value_set, ref_set):
				return cls(bits, sorted(ref_set-value_set), sorted(value_set-ref_set))
			
			@classmethod
			def from_iters(cls, bits, value_iter, ref_iter):
				return cls.from_sets(bits, set(value_iter), set(ref_iter))
		
		@dataclass
		class GeneComp:
			identical: List[Tuple[IcecraftBitPosition, ...]] = field(default_factory=list)
			subset: Dict[Tuple[IcecraftBitPosition, ...], DiffValueComp] = field(default_factory=dict)
			reordered_bits: Dict[Tuple[IcecraftBitPosition, ...], Tuple[IcecraftBitPosition, ...]] = field(default_factory=dict)
			reordered_values: List[Tuple[IcecraftBitPosition, ...]] = field(default_factory=list)
			different_values: Dict[Tuple[IcecraftBitPosition, ...], DiffValueComp] = field(default_factory=dict)
			partial: Dict[Tuple[IcecraftBitPosition, ...], Tuple[IcecraftBitPosition, ...]] = field(default_factory=dict)
			missing: Dict[IcecraftBitPosition, MissingComp] = field(default_factory=dict)
		
		def compare_genes(gene_data, gene_dict):
			"""compare iterable of a group of GeneData to dict based on another group of GeneData
			
			the first group is seen as "expected" and the second group as to be tested
			e.g. if a gene is in the first group, but not in the second, it is missing
			if a value is not in the first group, but in the second it is additional
			
			compare_genes(a, gen_bit_dict(b)) -> compare_genes(b, gen_bit_dict(a))
			identical -> identical
			subset -> missing or partial
			reordered_bits -> reordered_bits
			reordered_values -> reordered_values
			different_values.missing -> different_values.additional
			different_values.additional -> different_values.missing
			partial -> subset or missing
			missing -> nothing (all bits of gene missing), partial or subset
			"""
			comp_res = GeneComp()
			for r in gene_data:
				#if r not in gene_res_data:
				#	print(f"-: {r[:2]} {str(r[2])[:400]}")
				bit_set = set(r.bits)
				missing_bits = []
				img_genes = []
				while len(bit_set) > 0:
					bit = bit_set.pop()
					try:
						img = gene_dict[bit]
					except KeyError:
						missing_bits.append(bit)
						continue
					
					img_genes.append(img)
					
					bit_set.difference_update(img.bits)
				
				if len(missing_bits) == 0 and len(img_genes) == 1:
					img = img_genes[0]
					if len(img.bits) > len(r.bits):
						#print(f"*{bits_to_str(r.bits)}: subset of {bits_to_str(img.bits)}")
						comp_res.subset[r.bits] = DiffValueComp.from_iters(img.bits, r.val_list(), sub_values(r.bits, img))
					elif img.bits != r.bits:
						#print("f*{bits_to_str(r.bits)}: reordered bits")
						#TODO: take a look at the values
						comp_res.reordered_bits[r.bits] = img.bits
					elif r.values != img.values:
						r_set = set(r.val_list())
						img_set = set(img.val_list())
						if r_set == img_set:
							#print(f"*{bits_to_str(r.bits)}: value order differs")
							comp_res.reordered_values.append(r.bits)
						else:
							#print(f"*{bits_to_str(r.bits)}: values differ ({len(r.values)})")
							#print(f"\t*{len(r_set-img_set)} missing, {len(img_set-r_set)} additional: {str(img_set-r_set)[:100]}")
							comp_res.different_values[r.bits] = DiffValueComp(r.bits, list(r_set-img_set), list(img_set-r_set))
					else:
						comp_res.identical.append(r.bits)
				else:
					#print(f"*{bits_to_str(r.bits)}:")
					#if len(missing_bits) > 0:
					#	print(f"\t-{bits_to_str(sorted(missing_bits))}: bits not found")
					mc = MissingComp(r, missing_bits)
					for mb in missing_bits:
						comp_res.missing[mb] = mc
					
					for img in img_genes:
						img_bits = set(r.bits) & set(img.bits)
						#print(f"\t*{bits_to_str(sorted(img_bits))}: represented in {bits_to_str(img.bits)}")
						comp_res.partial[tuple(img_bits)] = r.bits
			
			return comp_res
		
		import json
		import os
		from pprint import pprint
		
		json_path = os.path.join(TEST_DATA_DIR, "mapping_creation.json")
		with open(json_path, "r") as json_file:
			raw_data = json.load(json_file)
			#print(raw_data)
			#print(get_type_hints(MappingCase))
			data = self.transform_to_type(raw_data, List[MappingCase])
			#print(data)
		
		for i, mc in enumerate(data):#[1:2]):
			with self.subTest(desc=f"mapping case {i}"):
				tiles = icecraft.IcecraftRepGen.tiles_from_rectangle(mc.x_min, mc.y_min, mc.x_max, mc.y_max)
				
				config_map = {t: get_config_items(t) for t in tiles}
				
				raw_nets = get_net_data(tiles)
				icecraft.IcecraftRepGen.carry_in_set_net(config_map, raw_nets)
				
				rep = InterRep(raw_nets, config_map)
				
				req = RequestObject()
				req["x_min"] = mc.x_min
				req["y_min"] = mc.y_min
				req["x_max"] = mc.x_max
				req["y_max"] = mc.y_max
				req["exclude_nets"] = [n for n, _ in mc.exclude_nets]
				req["include_nets"] = [n for n, _ in mc.include_nets]
				req["output_lutffs"] = [icecraft.IcecraftLUTPosition.from_coords(*c) for c in mc.output_lutffs]
				req["joint_input_nets"] = mc.joint_input_nets
				req["lone_input_nets"] = [IcecraftNetPosition.from_coords(*c) for c in mc.lone_input_nets]
				req["lut_functions"] = [icecraft.LUTFunction[n] for n in mc.lut_functions]
				icecraft.IcecraftRepGen._choose_nets(rep, req)
				
				#print(req)
				print(f"available: {sum([v.available for v in rep.iter_vertices()])}")
				#pprint(config_map)
				icecraft.IcecraftRepGen.set_lut_functions(rep, req.lut_functions)
				
				#pdb.set_trace()
				const_res, gene_res, sec_res = icecraft.IcecraftRepGen.create_genes(
					rep,
					config_map
				)
				#pdb.set_trace()
				const_exp_data = [prev_to_data(g) for g in mc.const_genes]
				gene_exp_data = [prev_to_data(g) for g in mc.genes]
				
				exp_gene_dict = gen_bit_dict(const_exp_data)
				exp_gene_dict.update(gen_bit_dict(gene_exp_data))
				
				const_res_data = [gene_to_data(g) for g in const_res]
				#self.assertEqual(mc.const_genes, const_res_data)
				
				gene_res_data = [gene_to_data(g) for g in gene_res]
				#self.assertEqual(sorted(mc.genes), sorted(gene_res_data))
				
				res_gene_dict = gen_bit_dict(const_res_data)
				res_gene_dict.update(gen_bit_dict(gene_res_data))
				
				#print("expected genes in results")
				exp_to_res = compare_genes(gene_exp_data, res_gene_dict)
				
				#print("result genes in expected")
				res_to_exp = compare_genes(gene_res_data, exp_gene_dict)
				
				for bit, mc in res_to_exp.missing.items():
					values = set(sub_values([bit], mc.gene))
					if values != set([(False, )]):
						self.fail(f"Additional meaningful bit: {bit}")
				
				if len(exp_to_res.missing) > 0:
					self.fail(f"{len(exp_to_res.missing)} bits missing in result: {bits_to_str(exp_to_res.missing.keys())}")
				
				for diff in exp_to_res.different_values.values():
					gene = exp_gene_dict[diff.bits[0]]
					# known cases
					raw_bits = tuple((b.group, b.index) for b in diff.bits)
					if (raw_bits, diff.missing, diff.additional) in [
						# the previous implementation automatically cascaded the unused property
						# still there may have been a bug that excludes glb2local_0 despite an global input net available
						(((2, 14), (3, 14), (3, 15), (3, 16), (3, 17)), [], [(False, False, False, False, True)]), # glb2local_0 -> local_g0_4
						(((2, 15), (2, 16), (2, 17), (2, 18), (3, 18)), [], [(False, False, True, False, False)]), # glb2local_1 -> local_g0_5
						(((2, 25), (3, 22), (3, 23), (3, 24), (3, 25)), [], [(False, True, False, False, False)]), # glb2local_2 -> local_g0_6
						(((2, 21), (2, 22), (2, 23), (2, 24), (3, 21)), [], [(False, True, False, False, False)]), # glb2local_3 -> local_g0_7
					]:
						continue
					self.fail(f"{bits_to_str(diff.bits)} values differ:\n\t{len(diff.missing)} missing: {diff.missing}\n\t{len(diff.additional)} additional: {diff.additional}\n\t\t{gene.values}\n\t\t{req}")
				
				#self.assertEqual(len(mc.genes), len(gene_res_data))
	
	def test_create_genes(self):
		class GeneTestCase(NamedTuple):
			desc: str
			rep: InterRep
			config_map: Mapping[TilePosition, ConfigAssemblage] = {}
			exp_const: List[Gene] = []
			exp_genes: List[Gene] = []
			exp_sec: List[int] = []
		
		
		test_cases = []
		
		# carry in set and carry mux
		tile = TilePosition(26, 19)
		net_data = [
			NetData(((*tile, "carry_in_mux"),), False, (0, )),
			NetData(((tile.x, tile.y-1, "lutff_7/cout"), (*tile, "carry_in")), True, (0, )),
			NetData(((*tile, icecraft.representation.CARRY_ONE_IN),), True, (0, )),
		]
		ci_bits = create_bits(*tile, [(1, 49)])
		one_bits = create_bits(*tile, [(1, 50)])
		con_items = [
			ConnectionItem(ci_bits, "connection", "carry_in_mux", ((True, ), ), ("carry_in", )),
			ConnectionItem(one_bits, "connection", "carry_in_mux", ((True, ), ), (icecraft.representation.CARRY_ONE_IN, )),
		]
		config_map = {tile: ConfigAssemblage(connection=tuple(con_items))}
		rep = InterRep(net_data, config_map)
		ec = GeneTestCase(
			"carry mux",
			rep,
			config_map,
			exp_genes = [
				Gene(tuple(ci_bits+one_bits), AlleleList([Allele(v, "") for v in ((False, False), (False, True), (True, False))]), "")
			],
			exp_sec = [1]
		)
		test_cases.append(ec)
		
		# glb2local_1 -> local_g0_5
		(((2, 15), (2, 16), (2, 17), (2, 18), (3, 18)), [], [(False, False, True, False, False)]),
		net_data = [
			NetData(((*tile, "glb2local_1"), ), False, (0, )),
			NetData(((*tile, "local_g0_5"), ), False, (0, )),
		]
		bits = create_bits(*tile, [(2, 15), (2, 16), (2, 17), (2, 18), (3, 18)])
		con_items = [ConnectionItem(bits, "connection", "local_g0_5", ((False, False, True, False, False), ), ("glb2local_1", )),]
		config_map = {tile: ConfigAssemblage(connection=tuple(con_items))}
		rep = InterRep(net_data, config_map)
		ec = GeneTestCase(
			"glb2local_1 -> local_g0_5",
			rep,
			config_map,
			exp_genes = [
				Gene(bits, AlleleList([Allele(v, "") for v in ((False, False, False, False, False), (False, False, True, False, False))]), "")
			],
			exp_sec = [1]
		)
		test_cases.append(ec)
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				#pdb.set_trace()
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_genes(tc.rep, tc.config_map)
				
				self.assertEqual(tc.exp_const, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
	
	def test_create_genes_tile_cases(self):
		# test cases for single tile nets also have to work for more general create_genes function
		st_test_cases = self.generate_tile_genes_test_cases()
		st_exception_cases = self.generate_tile_genes_fail_test_cases()
		
		for tc in st_test_cases:
			with self.subTest(desc=f"single tile case: {tc.desc}"):
				try:
					rep = tc.single_tile_vertices[0].rep
				except IndexError:
					rep = InterRep([], tc.config_map)
				
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_genes(rep, tc.config_map)
				
				for const_gene in tc.exp_const:
					# const genes for external sources are not 
					self.assertIn(const_gene, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
		for tc in st_exception_cases:
			if not tc.general:
				continue
			with self.subTest(desc=f"single tile exception case: {tc.desc}"):
				with self.assertRaises(tc.excep):
					try:
						rep = tc.single_tile_vertices[0].rep
					except IndexError:
						rep = InterRep([], tc.config_map)
					
					icecraft.IcecraftRepGen.create_genes(rep, tc.config_map)
	
	def generate_tile_genes_test_cases(self):
		class TileGenesTestData(NamedTuple):
			desc: str
			single_tile_vertices: List[Vertex] = []
			config_map: Mapping[TilePosition, ConfigAssemblage] = {}
			exp_const: List[Gene] = []
			exp_genes: List[Gene] = []
			exp_sec: List[int] = []
		
		test_cases = []
		
		ec = TileGenesTestData(
			"NegClk",
			config_map = {
				TilePosition(4, 2): ConfigAssemblage(tile=(ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), "NegClk"), )),
				TilePosition(4, 3): ConfigAssemblage(),
			},
			exp_genes = [Gene((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), AlleleAll(1), "")],
			exp_sec = [1]
		)
		test_cases.append(ec)
		
		# LUT test cases
		lut_in_unused = ([], [1], [3], [1, 2], [0, 3], [0, 1, 2], [0, 1, 3], [0, 1, 2, 3])
		def lut_in_profile(vtx):
			for desig in vtx.desigs:
				res = re.match(r"NET#lutff_(\d)/in_(\d)", desig.name)
				if res is not None:
					break
			
			if res is None:
				return True
			
			l = int(res.group(1))
			i = int(res.group(2))
			
			if i in lut_in_unused[l]:
				return False
			else:
				return True
		
		# corresponding to cases in lut_in_unused
		truth_tables_enum = [
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True),
				(False, True, True, False, True, False, False, True, True, False, False, True, False, True, True, False),
				(False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
				(True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, True),
				(False, True, False, True, True, False, True, False, True, False, True, False, False, True, False, True),
				(False, True, False, True, True, True, True, True, True, True, True, True, True, True, True, True),
				(True, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, False, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, True),
				(False, True, True, False, True, False, False, True, False, True, True, False, True, False, False, True),
				(False, True, True, True, True, True, True, True, False, True, True, True, True, True, True, True),
				(True, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, False, True, True, True, True, True, True, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, False, False, False, True, False, True, False, True, False, True),
				(False, True, False, True, False, True, False, True, True, False, True, False, True, False, True, False),
				(False, True, False, True, False, True, False, True, True, True, True, True, True, True, True, True),
				(True, False, True, False, True, False, True, False, False, False, False, False, False, False, False, False),
				(True, True, True, True, True, True, True, True, True, False, True, False, True, False, True, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
				(False, False, False, False, False, False, True, True, False, False, False, False, False, False, True, True),
				(False, False, True, True, True, True, False, False, False, False, True, True, True, True, False, False),
				(False, False, True, True, True, True, True, True, False, False, True, True, True, True, True, True),
				(True, True, False, False, False, False, False, False, True, True, False, False, False, False, False, False),
				(True, True, True, True, True, True, False, False, True, True, True, True, True, True, False, False),
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0
				(False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True), # AND, OR, PARITY
				(True, True, True, True, True, True, True, True, False, False, False, False, False, False, False, False), # NAND, NOR
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0
				(False, False, False, False, True, True, True, True, False, False, False, False, True, True, True, True), # AND, OR, PARITY
				(True, True, True, True, False, False, False, False, True, True, True, True, False, False, False, False), # NAND, NOR
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1
			),
			(
				(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0, OR, NAND, PARITY
				(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1, AND, NOR
			),
		]
		
		lut_conf = []
		exp_genes_no = []
		exp_genes_enum = []
		lut_kinds = ('CarryEnable', 'DffEnable', 'Set_NoReset', 'AsyncSetReset', 'TruthTable')
		for l in range(8):
			raw_bits_list = [
				((0+2*l, 44),),
				((0+2*l, 45),),
				((1+2*l, 44),),
				((1+2*l, 45),),
				(
					(0+2*l, 40), (1+2*l, 40), (1+2*l, 41), (0+2*l, 41),
					(0+2*l, 42), (1+2*l, 42), (1+2*l, 43), (0+2*l, 43),
					(0+2*l, 39), (1+2*l, 39), (1+2*l, 38), (0+2*l, 38),
					(0+2*l, 37), (1+2*l, 37), (1+2*l, 36), (0+2*l, 36)
				)
			]
			bits_list = [create_bits(2, 3, r) for r in raw_bits_list]
			lut_conf.append(tuple(IndexedItem(b, k, l) for b, k in zip(bits_list, lut_kinds)))
			# CarryEnable should not be put in a gene
			# DffEnable, Set_NoReset, AsyncSetReset
			other = [Gene(b, AlleleAll(1), "") for b in bits_list[1:4]]
			exp_genes_no.extend(other)
			exp_genes_enum.extend(other)
			# TruthTable
			exp_genes_no.append(Gene(bits_list[4], AllelePow(4, lut_in_unused[l]), ""))
			exp_genes_enum.append(Gene(bits_list[4], AlleleList([Allele(v, "") for v in truth_tables_enum[l]]), ""))
		
		single_tile_nets = [
			NetData(((2, 3, f"lutff_{l}/in_{i}"), ), False, (0, )) for l in range(8) for i in range(4)
		]
		lut_io = tuple(ElementInterface(tuple((2, 3, f"lutff_{l}/in_{i}") for i in range(4)), tuple()) for l in range(8))
		config_map = {
			TilePosition(2, 3): ConfigAssemblage(lut=tuple(lut_conf), lut_io=lut_io),
			TilePosition(4, 3): ConfigAssemblage(),
		}
		
		rep = InterRep(single_tile_nets, config_map)
		for vtx in rep.iter_vertices():
			vtx.used = lut_in_profile(vtx)
		
		ec = TileGenesTestData(
			"LUT, no function restriction",
			list(rep.iter_vertices()),
			config_map = config_map,
			exp_genes = exp_genes_no,
			exp_sec = [32]
		)
		test_cases.append(ec)
		
		rep = InterRep(single_tile_nets, config_map)
		for vtx in rep.iter_vertices():
			vtx.used = lut_in_profile(vtx)
			try:
				vtx.functions = list(LUTFunction)
			except AttributeError:
				pass
		
		ec = TileGenesTestData(
			"LUT, function restricted",
			list(rep.iter_vertices()),
			config_map = config_map,
			exp_genes = exp_genes_enum,
			exp_sec = [32]
		)
		test_cases.append(ec)
		
		
		org_tile = TilePosition(2, 3)
		def org_name(n):
			# find name of net in org_tile
			for x, y, name in n.segment:
				if org_tile.x == x and org_tile.y == y:
					return name
			raise ValueError("no name in original tile")
		
		net_data_list = []
		net_names = ("unavail", "no_src_grps", "one_src", "one_src_grp", "two_src_grps", "unused")
		for i in range(2):
			net_data_list.extend(NetData(((*org_tile, f"{n}_{i}"), ), False, (0, )) for n in net_names[:3])
			net_data_list.extend(NetData(((1, 1, f"other_{n}_{i}"), (*org_tile, f"{n}_{i}")), False, (1, )) for n in net_names[3:4])
			net_data_list.extend(NetData(((*org_tile, f"{n}_{i}"), ), False, (0, )) for n in net_names[4:])
			# external
			net_data_list.append(NetData(((*org_tile, f"external_{i}"), (3, 4, f"external_{i}")), False, (0, 1)))
			# hard driven
			net_data_list.append(NetData(((*org_tile, f"hard_driven_{i}"), ), True, (0, )))
		
		offset = len(net_data_list)//2
		dst_nets = {org_name(n)[:-2]: n for n in net_data_list[:offset]}
		src_nets = {org_name(n)[:-2]: n for n in net_data_list[offset:]}
		
		gene_data = []
		# bits, dst_name, srcs, del_indices, conf_lengths
		# a tuple describes the data to construct a gene and the original connection item
		# del_indices define indices of srcs that will not be included in the gene
		# conf_lengths define which parts of the bits are included in one connection item
		class RawGene(NamedTuple):
			raw_bits: List[Tuple[int, int]]
			dst_label: str
			src_list: List[Tuple[Tuple[bool, ...], str]]
			del_indices: List[int]
			conf_lengths: List[int]
			create_gene: bool = True
		
		one_src_grp = [
			((False, True), "hard_driven"),
			((True, False), "external"),
			((True, True), "unavail"),
		]
		two_src_grps = [
			((False, False, True),  "external"),
			((False, True, False), "unused"),
			((False, True, True), "hard_driven"),
			((True, False, False), "unavail"),
		]
		gene_data.append(RawGene([(0, 6), (0, 7)], "unavail", one_src_grp, [0, 1, 2], [2], False))
		# no RawGene for no_src_grps
		gene_data.append(RawGene([(2, 6)], "one_src", [((True, ), "external")], [], [1]))
		gene_data.append(RawGene([(3, 6), (3, 7)], "one_src_grp", one_src_grp, [2], [2]))
		gene_data.append(RawGene([(4, 0), (4, 5), (4, 6)], "two_src_grps", two_src_grps, [1, 3], [1, 2]))
		gene_data.append(RawGene([(5, 0), (5, 5), (5, 6)], "unused", two_src_grps, [0, 1, 2, 3], [1, 2]))
		gene_data.append(RawGene([(6, 0), (6, 5), (6, 6)], "external", two_src_grps, [0, 1, 2, 3], [1, 2], False))
		# no RawGene for hard_driven
		
		con_items = []
		exp_const = []
		exp_genes = []
		for gd in gene_data:
			all_bits = create_bits(*org_tile, gd.raw_bits)
			if gd.create_gene:
				alleles = [Allele((False, )*len(all_bits), "")]
				alleles.extend([Allele(v, "") for i, (v, _) in enumerate(gd.src_list) if i not in gd.del_indices])
				gene = Gene(all_bits, AlleleList(alleles), "")
				
				if len(alleles) > 1:
					exp_genes.append(gene)
				else:
					exp_const.append(gene)
			
			dst_net = dst_nets[gd.dst_label]
			dst_name = org_name(dst_net)
			prev = 0
			for l in gd.conf_lengths:
				part_values_list = []
				part_src_list = []
				part_bits = all_bits[prev:prev+l]
				for values, src_label in gd.src_list:
					part_values = values[prev:prev+l]
					if not any(part_values):
						continue
					
					part_values_list.append(part_values)
					
					src_net = src_nets[src_label]
					src_name = org_name(src_net)
					part_src_list.append(src_name)
				
				con_items.append(ConnectionItem(
					part_bits,
					"connection",
					dst_name,
					tuple(part_values_list),
					tuple(part_src_list)
				))
				
				prev += l
		config_map = {org_tile: ConfigAssemblage(connection=tuple(con_items))}
		rep = InterRep(net_data_list, config_map)
		
		for vtx in rep.iter_vertices():
			vtx.used = all(not d.name.startswith("NET#unused") for d in vtx.desigs)
			
			if any(d.name.startswith("NET#unavail") for d in vtx.desigs):
				vtx.available = False
			
			if any(d.name.startswith("NET#external") for d in vtx.desigs):
				vtx.ext_src = True
		
		single_verts = [v for v in rep.iter_vertices() if all(not d.name.startswith("NET#external") for d in v.desigs)]
		
		self.maxDiff = None
		ec = TileGenesTestData(
			"Single tile nets",
			single_tile_vertices = single_verts, 
			config_map = config_map,
			exp_const = exp_const,
			exp_genes = exp_genes,
			exp_sec = [3]
		)
		test_cases.append(ec)
		
		return test_cases
	
	def generate_tile_genes_fail_test_cases(self):
		class TileGenesErrorTestData(NamedTuple):
			desc: str
			excep: Exception
			single_tile_vertices: Iterable[Vertex] = []
			config_map: Mapping[TilePosition, ConfigAssemblage] = {}
			general: bool = True # general error case, i.e. also for create_genes
		
		exception_cases = []
		
		ec = TileGenesErrorTestData(
			"CarryInSet",
			ValueError,
			config_map = {
				TilePosition(4, 2): ConfigAssemblage(tile=(
					ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 2), ), "NegClk"),
					ConfigItem((IcecraftBitPosition.from_coords(4, 2, 0, 3), ), "CarryInSet"),
				))
			},
		)
		exception_cases.append(ec)
		
		org_tile = TilePosition(4, 2)
		other_tile = TilePosition(3, 1)
		net_data_list = [
			NetData(((*other_tile, "dst"), (*org_tile, "dst")), False, (0, 1)),
			NetData(((*other_tile, f"src_1"), ), True, (0, )),
			NetData(((*org_tile, f"src_2"), ), True, (0, )),
		]
		org_con = ConnectionItem(
			create_bits(*other_tile, [(9, 7), (9, 8)]),
			"connection",
			"dst",
			((True, True), ),
			("src_1", )
		)
		other_con = ConnectionItem(
			create_bits(*org_tile, [(4, 5), (4, 6)]),
			"connection",
			"dst",
			((True, True), ),
			("src_2", )
		)
		
		config_map = {
			org_tile: ConfigAssemblage(connection=(org_con, )),
			other_tile: ConfigAssemblage(connection=(other_con, ))
		}
		rep = InterRep(net_data_list, config_map)
		ec = TileGenesErrorTestData(
			"multitile",
			ValueError,
			list(rep.iter_vertices()),
			config_map,
			general = False
		)
		exception_cases.append(ec)
		
		return exception_cases
	
	def create_rep(self, raw_nets, config_map, lut_functions, used_function):
		rep = InterRep(raw_nets, config_map)
		icecraft.IcecraftRepGen.set_lut_functions(rep, lut_functions)
		for vtx in rep.iter_vertices():
			vtx.used = used_function(vtx)
		
		return rep
	
	def test_create_tile_genes(self):
		test_cases = self.generate_tile_genes_test_cases()
		exception_cases = self.generate_tile_genes_fail_test_cases()
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				res_const, res_genes, res_sec = icecraft.IcecraftRepGen.create_tile_genes(tc.single_tile_vertices, tc.config_map)
				
				self.assertEqual(tc.exp_const, res_const)
				self.assertEqual(tc.exp_genes, res_genes)
				self.assertEqual(tc.exp_sec, res_sec)
		
		for tc in exception_cases:
			with self.subTest(desc=tc.desc):
				with self.assertRaises(tc.excep):
					icecraft.IcecraftRepGen.create_tile_genes(tc.single_tile_vertices, tc.config_map)
	
