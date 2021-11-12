from unittest import TestCase

from adapters.input_gen import SeqGen
from domain.model import InputData
from domain.request_model import RequestObject

from .common import check_parameter_user


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
