#!/usr/bin/env python3

import unittest.mock as mock
import sys

import unittest

from domain.model import InputData, OutputData
from domain.use_cases import Measure
from domain.request_model import RequestObject

from ..mocks import MockTargetManager, MockMeter
from ..common import check_parameter_user

class MeasureTest(unittest.TestCase):
	def test_call(self):
		input_data = InputData([2, 3, 4])
		output_data = OutputData([12, 13, 14])
		
		mock_manager = MockTargetManager()
		mock_meter = MockMeter(output_data)
		
		measure_case = Measure(mock_manager, mock_meter)
		req = RequestObject()
		#req["input_data"] = input_data
		req["serial_number"] = None
		res_data = measure_case(req)
		
		self.assertEqual(output_data, res_data)
	
	def test_parameter_user(self):
		mock_manager = MockTargetManager()
		output_data = OutputData([12, 13, 14])
		mock_meter = MockMeter(output_data)
		
		measure_case = Measure(mock_manager, mock_meter)
		check_parameter_user(self, measure_case)
