from dataclasses import dataclass, fields
from operator import attrgetter, itemgetter
from typing import Any, Dict, List
from unittest import TestCase


from adapters.hdf5_sink import chain_funcs, MetaEntry, ParamAim
from applications.discern_frequency.hdf5_desc import add_meta, HDF5Desc, pa_gen

from ..common import check_func_eq

class HDF5DescTest(TestCase):
	def check_param_aim(self, a, b):
		check_func_eq(self, a.alter, b.alter)
		for cur_field in fields(ParamAim):
			if cur_field.name == "alter":
				continue
			
			self.assertEqual(getattr(a, cur_field.name), getattr(b, cur_field.name))
	
	def test_pa_gen(self):
		@dataclass
		class PATC:
			desc: str
			gen_name: str
			req_names: List[str]
			kwargs: Dict[str, Any]
			exp: ParamAim
		
		cases = [
			PATC("no kwargs", "habitat", ["in"], {}, ParamAim(["in"], "uint8", "habitat", "/", False, tuple())),
			PATC("all kwargs", "habitat", ["over", "out"], {
				"alter": itemgetter(1), "compress": "lzf", "comp_opt": 3, "shuffle": True
			}, ParamAim(["over", "out"], "uint8", "habitat", "/", False, tuple(), itemgetter(1), "lzf", 3, True)),
			PATC("override type", "habitat", ["in"], {"data_type": "uint16"}, ParamAim(
				["in"], "uint16", "habitat", "/", False, tuple()
			)),
			PATC("override shape", "habitat", ["in"], {"shape": (6, )}, ParamAim(
				["in"], "uint8", "habitat", "/", False, (6, )
			)),
			PATC("override type and shape", "habitat", ["in"], {"data_type": "uint16", "shape": (6, )}, ParamAim(
				["in"], "uint16", "habitat", "/", False, (6, )
			)),
			PATC("override alter", "habitat", ["in"], {"alter": chain_funcs([itemgetter(8), attrgetter("abc")])},
				ParamAim(["in"], "uint8", "habitat", "/", False, tuple(), 
					alter=chain_funcs([itemgetter(8), attrgetter("abc")])
				)
			),
		]
		
		for tc in cases:
			with self.subTest(desc=tc.desc):
				res = pa_gen(tc.gen_name, tc.req_names, **tc.kwargs)
				self.check_param_aim(tc.exp, res)
	
	#def test_with_sink
	
	def test_add_meta(self):
		metadata = {}
		value = "my desc"
		add_meta(metadata, "habitat.desc", value)
		
		self.assertEqual(1, len(metadata))
		self.assertIn("habitat", metadata)
		self.assertEqual([MetaEntry("description", value, str)], metadata["habitat"])
	
	def test_add_meta_error(self):
		metadata = {}
		with self.assertRaises(ValueError):
			add_meta(metadata, "habitat", b"123")
