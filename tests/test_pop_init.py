from unittest import TestCase

from adapters.pop_init import RandomPop
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
