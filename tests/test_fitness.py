from unittest import TestCase

from adapters.fitness import ReduceFF
from domain.model import InputData, OutputData
from domain.request_model import RequestObject


class ReduceFFTest(TestCase):
	def test_create(self):
		dut = ReduceFF(lambda a, b: b)
	
	def test_sum(self):
		dut = ReduceFF(lambda a, b: a+b)
		data = OutputData([2, 6, 8])
		req = RequestObject(driver_data=InputData(), measurement=data)
		res = dut.compute(req)
		
		self.assertEqual(sum(data), res.fitness)
		
