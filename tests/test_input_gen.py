from unittest import TestCase

from adapters.input_gen import RandIntGen, SeqGen
from domain.interfaces import PRNG
from domain.model import InputData
from domain.request_model import RequestObject

from .common import check_parameter_user
from .mocks import MockRandInt

class SeqGenTest(TestCase):
	def test_create(self):
		dut = SeqGen([InputData([8])])
	
	def test_generate(self):
		for length in range(1, 5):
			with self.subTest(length=length):
				seq = [InputData([i]) for i in range(length)]
				dut = SeqGen(seq)
				
				for i in range(length*3):
					res = dut.generate(RequestObject())
					self.assertEqual(seq[i%length], res.driver_data)
	
	def test_parameter_user(self):
		dut = SeqGen([InputData([8])])
		check_parameter_user(self, dut)


class RandIntGenTest(TestCase):
	def create_dut(self, int_list=[8], min_int=None, max_int=None):
		if min_int is None:
			min_int = min(int_list)
		if max_int is None:
			max_int = max(int_list)
		
		prng = MockRandInt(int_list)
		return RandIntGen(prng, min_int, max_int)
	
	def test_create(self):
		dut = self.create_dut([8], 0, 16)
	
	def test_generate(self):
		test_cases = [
			([1, 2, 3], 1, 3),
			(list(range(10)), 0, 9),
			([-2, 30, 0], -50, 50),
		]
		
		for int_list, min_int, max_int in test_cases:
			with self.subTest(int_list=int_list):
				dut = self.create_dut(int_list, min_int, max_int)
				for exp in int_list:
					res = dut.generate(RequestObject())
					self.assertIsInstance(res.driver_data, InputData)
					self.assertEqual(exp, res.driver_data[0])
	
	def test_parameter_user(self):
		dut = self.create_dut()
		check_parameter_user(self, dut)
