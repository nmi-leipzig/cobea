from unittest import TestCase

from adapters.pop_init import GivenPop, RandomPop
from adapters.prng import BuiltInPRNG
from adapters.simtar import SimtarRepGen
from adapters.unique_id import SimpleUID
from domain.model import Chromosome
from domain.request_model import  RequestObject

class RandomPopTest(TestCase):
	def create_dut(self):
		gen = SimtarRepGen()
		req = RequestObject(always_active=True)
		rep = gen(req).representation
		
		prng = BuiltInPRNG()
		suid = SimpleUID()
		dut = RandomPop(rep, suid, prng)
		
		return dut
	
	def test_creation(self):
		self.create_dut()
	
	def test_init_pop(self):
		dut = self.create_dut()
		
		res = dut.init_pop(7)
		
		self.assertEqual(7, len(res))
		for chromo in res:
			self.assertIsInstance(chromo, Chromosome)

class GivenPopTest(TestCase):
	def create_dut(self):
		chromo_list = [
			Chromosome(23, (1, 2, 3)),
			Chromosome(42, (0, 7, 11)),
			Chromosome(1, (12, 3, 1)),
			Chromosome(274, (9, 1, 9)),
		]
		
		dut = GivenPop(chromo_list)
		
		return chromo_list, dut
	
	def test_creation(self):
		self.create_dut()
	
	def test_init_pop(self):
		exp, dut = self.create_dut()
		
		with self.subTest(desc="normal call"):
			res = dut.init_pop(len(exp))
			
			self.assertEqual(exp, res)
		
		for length in [0, len(exp)-1, len(exp)+1]:
			with self.subTest(desc=f"invalid length {length}"), self.assertRaises(ValueError):
				res = dut.init_pop(length)
