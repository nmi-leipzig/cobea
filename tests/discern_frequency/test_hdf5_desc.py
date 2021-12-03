from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Dict, List
from unittest import TestCase


from adapters.hdf5_sink import MetaEntry, ParamAim
from applications.discern_frequency.hdf5_desc import add_meta, HDF5Desc, pa_gen


class TestHDF5Desc(TestCase):
	def test_pa_gen(self):
		@dataclass
		class PATC:
			desc: str
			gen_name: str
			req_names: List[str]
			kwargs: Dict[str, Any]
			exp: ParamAim
		
		func = itemgetter(1)
		
		cases = [
			PATC("no kwargs", "habitat", ["in"], {}, ParamAim(["in"], "uint8", "habitat", "/", False, tuple())),
			PATC("all kwargs", "habitat", ["over", "out"], {
				"alter": func, "compress": "lzf", "comp_opt": 3, "shuffle": True
			}, ParamAim(["over", "out"], "uint8", "habitat", "/", False, tuple(), func, "lzf", 3, True)),
		]
		
		for tc in cases:
			with self.subTest(desc=tc.desc):
				res = pa_gen(tc.gen_name, tc.req_names, **tc.kwargs)
				self.assertEqual(tc.exp, res)
	
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
