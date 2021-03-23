import unittest

from domain.request_model import RequestObject
from domain.use_cases import CreatePosTrans
from adapters.icecraft.position_transformation import IcecraftPosTransLibrary
from adapters.icecraft.misc import IcecraftPosition

class TestIcecraftPosTransLibrary(unittest.TestCase):
	def test_creation(self):
		ptl = IcecraftPosTransLibrary()
	
	def test_use_case_creation(self):
		ptl = IcecraftPosTransLibrary()
		uc = CreatePosTrans(ptl)
	
	def test_expand_rectangle(self):
		dut = IcecraftPosTransLibrary.expand_rectangle
		
		self.check_expand_rectangle(dut)
	
	def test_expand_rectangle_req(self):
		ptl = IcecraftPosTransLibrary()
		
		req = RequestObject()
		req["identifier"] = "expand_rectangle"
		dut = ptl.get_implementation(req)
		
		self.check_expand_rectangle(dut)
	
	def test_use_case(self):
		ptl = IcecraftPosTransLibrary()
		uc = CreatePosTrans(ptl)
		
		req = RequestObject()
		req["identifier"] = "expand_rectangle"
		req["description"] = "from corners to all tiles in rectangle"
		
		dut = uc(req)
		
		self.check_expand_rectangle(dut)
	
	def check_expand_rectangle(self, dut):
		test_data = (
			((2, 2, 2, 2), [(2, 2)]), # single tile
			((3, 5, 7, 5), [(3, 5), (4, 5), (5, 5), (6, 5), (7, 5)]), # row
			((7, 9, 7, 13), [(7, 9), (7, 10), (7, 11), (7, 12), (7, 13)]), # colum
			((4, 6, 5, 7), [(4, 6), (4, 7), (5, 6), (5, 7)]), # no inner tile
			((5, 8, 7, 10), [(5, 8), (5, 9), (5, 10), (6, 8), (6, 9), (6, 10), (7, 8), (7, 9), (7, 10)]), # inner tile
		)
		
		for rect, raw_exp in test_data:
			exp = [IcecraftPosition(*t) for t in raw_exp]
			res = dut([IcecraftPosition(*rect[:2]), IcecraftPosition(*rect[2:4])])
			res_set = set(res)
			
			# no duplicates
			self.assertEqual(len(res), len(res_set))
			
			# correct tiles
			self.assertEqual(set(exp), res_set)
	
		
