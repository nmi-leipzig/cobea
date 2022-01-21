import h5py
import inspect
import multiprocessing as mp
import numpy as np
import os

from collections import OrderedDict
from dataclasses import dataclass
from functools import partial
from operator import abs, add, attrgetter, itemgetter, neg
from unittest import TestCase
from typing import Any, Iterable, List, Mapping, NamedTuple, Tuple

from adapters.hdf5_sink import compose, HDF5Sink, IgnoreValue, noop, ParamAim
from domain.allele_sequence import Allele, AlleleAll, AlleleList, AllelePow
from domain.base_structures import BitPos
from domain.model import Gene

@dataclass
class SimpleBitPos(BitPos):
	x: int
	y: int
	i: int
	
	def to_ints(self) -> Tuple[int, ...]:
		return (self.x, self.y, self.i)
	
	@classmethod
	def from_ints(cls, ints: Iterable[Tuple[int, int, int]]):
		return tuple(cls(*i) for i in ints)

class FuncTest(TestCase):
	def assertFunc(self, exp, dut):
		"""assert equality of functions
		
		This is impossible in general (halting problem), so only the names and classe are checked.
		Furthermore, partial with func=compose is checked recursively.
		"""
		if inspect.isfunction(exp):
			self.assertTrue(inspect.isfunction(dut))
			self.assertEqual(exp.__name__, dut.__name__)
		else:
			self.assertFalse(inspect.isfunction(dut))
			self.assertEqual(exp.__class__, dut.__class__)
			self.assertEqual(exp.__doc__, dut.__doc__)
			if exp.__class__.__name__ == "partial" and inspect.isfunction(exp.func) and exp.func.__name__ == "compose":
				# args
				self.assertEqual(len(exp.args), len(dut.args))
				for ea, da in zip(exp.args, dut.args):
					self.assertEqual(len(ea), len(da))
					for ef, af in zip(ea, fa):
						self.assertFunc(ef, af)
				
				# kwargs
				self.assertEqual(set(exp.keywords), set(dut.keywords))
				for key in exp.keywords:
					if key == "funcs":
						self.assertEqual(len(exp.keywords[key]), len(dut.keywords[key]))
						for ef, af in zip(exp.keywords[key], dut.keywords[key]):
							self.assertFunc(ef, af)
						
						continue
					self.assertEqual(exp.keywords[key], dut.keywords[key])
	
	def test_meta_assertFunc(self):
		# desc, a, b, res
		func1 = compose
		ig1 = itemgetter(0)
		tc_data = [
			("same itemgetter", ig1, ig1, True),
			("same func", func1, func1, True),
			("eq itemgetter", itemgetter(3), itemgetter(3), True),
			(
				"eq partial",
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), list]),
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), list]),
				True
			),
			("different func", compose, noop, False),
			("different non func", itemgetter(4), partial, False),
			("func vs non func", compose, itemgetter(5), False),
			(
				"different partial",
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), list]),
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), tuple]),
				False
			),
		]
		for desc, a, b, res in tc_data:
			with self.subTest(desc=desc):
				if res:
					self.assertFunc(a, b)
					self.assertFunc(b, a)
				else:
					with self.assertRaises(AssertionError):
						self.assertFunc(a, b)
					with self.assertRaises(AssertionError):
						self.assertFunc(b, a)
	
	def test_noop(self):
		for exp in [1, 2, None, "str"]:
			with self.subTest(exp=exp):
				res = noop(exp)
				self.assertEqual(exp, res)
	
	def test_compose(self):
		tc_data = [# desc, funcs, x_list, res_list
			("empty", [], [7, -3], [7, -3]),
			("single", [neg], [7, -3], [-7, 3]),
			("order 1", [abs, neg], [7, -3], [-7, -3]),
			("order 2", [neg, abs], [7, -3], [7, 3]),
			("partial", [partial(add, 4)], [7, -3], [11, 1]),
			#("lambda", [lambda a: a*a], [7, -3], [49, 9]), # fails in multiprocessing
		]
		for desc, funcs, x_list, res_list in tc_data:
			with self.subTest(desc=desc):
				for x, exp in zip(x_list, res_list):
					res = compose(x, funcs)
					self.assertEqual(exp, res)
		
		# test multiprocessing
		ctx = mp.get_context("spawn")
		for desc, funcs, x_list, res_list in tc_data:
			with self.subTest(desc="mp: "+desc):
				for x, exp in zip(x_list, res_list):
					p_func = partial(compose, funcs=funcs)
					pro = ctx.Process(target=self.exec_compose, args=(p_func, x, exp))
					pro.start()
					pro.join()
					self.assertEqual(pro.exitcode, 0)

	
	@staticmethod
	def exec_compose(p_func, x, exp):
		res = p_func(x)
		if exp != res:
			raise AssertionError()

class HDF5SinkTest(TestCase):
	def check_hdf5(self, filename, exp_attrs, exp_data):
		with h5py.File(filename, "r") as h5_file:
			# check attributes
			for entity_name, attr_dict in exp_attrs.items():
				self.assertIn(entity_name, h5_file)
				entity = h5_file[entity_name]
				
				for name, value in attr_dict.items():
					self.assertIn(name, entity.attrs)
					
					#self.assertEqual(entity.attrs[name], value)
					self.compare_np(entity.attrs[name], value)
				
				for name in entity.attrs:
					self.assertIn(name, attr_dict)
			
			
			# check data
			for ds_name, exp_data in exp_data.items():
				self.assertIn(ds_name, h5_file)
				ds = h5_file[ds_name]
				self.compare_np(exp_data, ds)
				
	
	def compare_np(self, a, b):
		if type(a) == np.ndarray:
			self.assertTrue(np.allclose(a, b))
		else:
			self.assertEqual(a, b)
	
	def setUp(self):
		self.filename = "tmp.test.h5"
	
	def tearDown(self):
		try:
			os.remove(self.filename)
		except FileNotFoundError:
			pass
	
	def test_creation(self):
		dut = HDF5Sink({}, filename=self.filename, mode="w")
	
	def test_write(self):
		class WriteData(NamedTuple):
			desc: str
			write_map: Mapping[str, List[ParamAim]]
			write_data: List[Tuple[str, Mapping[str, Any]]]
			exp_attrs: Mapping[str, Mapping[str, Any]]
			exp_data: Mapping[str, Any]
		
		def alter_str(x):
			if not isinstance(x[0], str):
				raise IgnoreValue()
			return x[0]
		
		def alter_int(x):
			if not isinstance(x[0], int):
				raise IgnoreValue()
			return x[0]
		
		test_data = [
			WriteData("all empty", {}, [], {}, {}),
			WriteData(
				"attr",
				{"src1": [ParamAim(["d1"], None, "d1.0"), ParamAim(["d3"], "uint8", "d3")]},
				[("src1", {"d1": [1, 2, 3], "d2": 5, "d3": None})],
				{"/": {"d1.0": ([1, 2, 3]), "d3": h5py.Empty("uint8")}},
				{}
			),
			WriteData(
				"dataset",
				{"src1": [ParamAim(["d1"], "uint8", "d1.0", as_attr=False, shape=(3, ))]},
				[("src1", {"d1": [1, 2, 3]}), ("src1", {"d1": [0, 0, 0]})],
				{},
				{"d1.0": np.array([[1, 2, 3], [0, 0, 0]])}
			),
			WriteData(
				"ignore value",
				{"src7": [
					ParamAim(["var"], None, "my_str", "v", alter=alter_str),
					ParamAim(["var"], None, "my_int", "v", alter=alter_int),
				]},
				[("src7", {"var": 235}), ("src7", {"var": "hi"})],
				{"v": {"my_str": "hi", "my_int": 235}},
				{}
			),
			WriteData(
				"dataset attr",
				OrderedDict({
					"attr_setter": [ParamAim(["meta"], None, "meta_int", "ds")],
					"data_setter": [ParamAim(["data"], "uint8", "ds", as_attr=False)]
				}),
				[("attr_setter", {"meta": 7}), ("data_setter", {"data": 23}), ("data_setter", {"data": 47})],
				{"ds": {"meta_int": 7}},
				{"ds": np.array([23, 47])}
			),
			WriteData(
				"multiple dataset entries",
				{"mde": [ParamAim(["data"], "uint8", "md", as_attr=False)]},
				[("mde", {"data": 8}), ("mde", {"data": [8, 9]})],
				{},
				{"md": np.array([8, 8, 9])}
			),
			WriteData(
				"create_gene_aims",
				{"dna": HDF5Sink.create_gene_aims("genes", 3, h5_path="my_genes")},
				[("dna", {"genes": [
					Gene(
						SimpleBitPos.from_ints([(105, 238, 198), (148, 46, 11), (141, 158, 195), (130, 151, 70)]),
						AlleleAll(4),
						"AlleleAll gene"
					),
					Gene(
						SimpleBitPos.from_ints([(77, 79, 195), (77, 80, 195)]),
						AlleleList([Allele((False, False), "neutral"), Allele((False, True), "on")]),
						"AlleleList gene"
					),
					Gene(
						SimpleBitPos.from_ints([(247, 181, 71), (247, 181, 154), (247, 181, 198)]),
						AllelePow(3, [1]),
						"AllelePow gene"
					),
				]})],
				{
					"my_genes/gene_00000": {
						"description": "AlleleAll gene",
						"bits": [[105, 238, 198], [148, 46, 11], [141, 158, 195], [130, 151, 70]],
						"allele_type": "AlleleAll",
					},
					"my_genes/gene_00001": {
						"description": "AlleleList gene",
						"bits": [[77, 79, 195], [77, 80, 195]],
						"allele_type": "AlleleList",
						"alleles": [[False, False], [False, True]],
					},
					"my_genes/gene_00002": {
						"description": "AllelePow gene",
						"bits": [[247, 181, 71], [247, 181, 154], [247, 181, 198]],
						"allele_type": "AllelePow",
						"input_count": 3,
						"unused_inputs": [1],
					}
				},
				{}
			),
		]
		
		for td in test_data:
			with self.subTest(desc=td.desc):
				dut = HDF5Sink(td.write_map, filename=self.filename, mode="w")
				with dut:
					for src, data_dict in td.write_data:
						dut.write(src, data_dict)
				
				self.check_hdf5(self.filename, td.exp_attrs, td.exp_data)
