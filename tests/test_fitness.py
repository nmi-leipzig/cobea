from unittest import TestCase

from adapters.fitness import ReduceFF
from domain.model import InputData, OutputData
from domain.request_model import RequestObject

from tests.common import check_parameter_user


class ReduceFFTest(TestCase):
	def test_create(self):
		dut = ReduceFF(lambda a, b: b)
	
	def test_sum(self):
		dut = ReduceFF(lambda a, b: a+b)
		data = OutputData([2, 6, 8])
		req = RequestObject(driver_data=InputData(), measurement=data)
		res = dut.compute(req)
		
		self.assertEqual(sum(data), res.fitness)
	
	def test_parameter_user(self):
		dut = ReduceFF(lambda a, b: b)
		check_parameter_user(self, dut)
