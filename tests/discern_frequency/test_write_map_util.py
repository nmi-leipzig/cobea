from unittest import TestCase

from applications.discern_frequency.write_map_util import fixed_prefix

class WriteMapUtilTest(TestCase):
	def test_fixed_prefix(self):
		test_data = [# test input, exp
			("", ""),
			("/", "/"),
			("mapping/carry_data/carry_data_{}", "mapping/carry_data"),
			("/mapping/carry_data/carry_data_{}", "/mapping/carry_data"),
			("/mapping_{}/carry_data/carry_data_{}", ""),
			("mapping_{}/carry_data/carry_data_{}", ""),
		]
		
		for data, exp in test_data:
			with self.subTest(data=data):
				res = fixed_prefix(data)
				self.assertEqual(exp, res)
	
