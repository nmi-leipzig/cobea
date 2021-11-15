from unittest import TestCase

from applications.discern_frequency.action import FreqSumFF
from domain.model import InputData, OutputData
from domain.request_model import ResponseObject, RequestObject


class FreqSumFFTest(TestCase):
	def test_create(self):
		dut = FreqSumFF(5, 5)
	
	def test_compute(self):
		test_cases = [# combination index, measurement, expected result
			(0, [255*256]*5+[0]*5, 1.0691833355591607), # 0b0000011111
			(251, [61461.492]*5+[0]*5, 1), # 0b1111100000
			(65, [10000]*10, 0.0010807097233555662), # 0b100110011
			(65, [3, 4, 3, 0, 5, 2, 1, 0, 2, 1], 3.6140597599635693e-05), # 0b100110011
		]
		
		dut = FreqSumFF(5, 5)
		for comb_idx, data, exp in test_cases:
			with self.subTest(comb_idx=comb_idx, exp=exp):
				req = RequestObject(driver_data = InputData([comb_idx]), measurement=OutputData(data))
				res = dut.compute(req)
				self.assertAlmostEqual(exp, res.fit, 15)
	
	def test_compute_error(self):
		test_cases = [# combination index, measurement, expected error
			(0, [], ValueError),
			(251, [61461.492]*6+[0]*5, ValueError),
			(65, [1]*9, ValueError),
		]
		
		dut = FreqSumFF(5, 5)
		for comb_idx, data, exp in test_cases:
			with self.subTest(comb_idx=comb_idx, exp=exp):
				req = RequestObject(driver_data = InputData([comb_idx]), measurement=OutputData(data))
				with self.assertRaises(exp):
					res = dut.compute(req)
				
		
