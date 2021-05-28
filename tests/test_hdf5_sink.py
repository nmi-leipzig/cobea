import h5py
import numpy as np
import os
import unittest

from typing import Any, List, Mapping, NamedTuple, Tuple

from adapters.hdf5_sink import HDF5Sink, IgnoreValue, ParamAim

class HDF5SinkTest(unittest.TestCase):
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
		dut = HDF5Sink({}, self.filename)
	
	def test_write(self):
		class WriteData(NamedTuple):
			desc: str
			write_map: Mapping[str, List[ParamAim]]
			write_data: List[Tuple[str, Mapping[str, Any]]]
			exp_attrs: Mapping[str, Mapping[str, Any]]
			exp_data: Mapping[str, Any]
		
		def alter_str(x):
			if not isinstance(x, str):
				raise IgnoreValue()
			return x
		
		def alter_int(x):
			if not isinstance(x, int):
				raise IgnoreValue()
			return x
		
		test_data = [
			WriteData("all empty", {}, [], {}, {}),
			WriteData(
				"attr",
				{"src1": [ParamAim("d1", None, "d1.0")]},
				[("src1", {"d1": [1, 2, 3], "d2": 5})],
				{"/": {"d1.0": ([1, 2, 3])}},
				{}
			),
			WriteData(
				"dataset",
				{"src1": [ParamAim("d1", "uint8", "d1.0", as_attr=False, shape=(3, ))]},
				[("src1", {"d1": [1, 2, 3]}), ("src1", {"d1": [0, 0, 0]})],
				{},
				{"d1.0": np.array([[1, 2, 3], [0, 0, 0]])}
			),
			WriteData(
				"ignore value",
				{"src7": [
					ParamAim("var", None, "my_str", "v", alter=alter_str),
					ParamAim("var", None, "my_int", "v", alter=alter_int),
				]},
				[("src7", {"var": 235}), ("src7", {"var": "hi"})],
				{"v": {"my_str": "hi", "my_int": 235}},
				{}
			),
		]
		
		for td in test_data:
			with self.subTest(desc=td.desc):
				dut = HDF5Sink(td.write_map, self.filename)
				with dut:
					for src, data_dict in td.write_data:
						dut.write(src, data_dict)
				
				self.check_hdf5(self.filename, td.exp_attrs, td.exp_data)
