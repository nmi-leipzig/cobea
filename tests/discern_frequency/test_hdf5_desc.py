from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Dict, List
from unittest import TestCase


from adapters.hdf5_sink import ParamAim
from applications.discern_frequency.hdf5_desc import HDF5Desc, pa_gen


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
