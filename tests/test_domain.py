#!/usr/bin/env python3

import unittest.mock as mock
import sys

import unittest

from domain import model
import domain.interfaces as interfaces
import domain.use_cases as use_cases
from domain.request_model import RequestObject

import tests.mocks as mocks
from tests.test_request_model import check_parameter_user

class MeasureTest(unittest.TestCase):
	def test_call(self):
		input_data = model.InputData([2, 3, 4])
		output_data = model.OutputData([12, 13, 14])
		
		mock_manager = mocks.MockTargetManager()
		mock_meter = mocks.MockMeter(output_data)
		
		measure_case = use_cases.Measure(mock_manager, mock_meter)
		req = RequestObject()
		#req["input_data"] = input_data
		req["serial_number"] = None
		res_data = measure_case(req)
		
		self.assertEqual(output_data, res_data)
	
	def test_parameter_user(self):
		mock_manager = mocks.MockTargetManager()
		output_data = model.OutputData([12, 13, 14])
		mock_meter = mocks.MockMeter(output_data)
		
		measure_case = use_cases.Measure(mock_manager, mock_meter)
		check_parameter_user(self, measure_case)

class FitnessFunctionTest(unittest.TestCase):
	class MockLibrary(interfaces.FitnessFunctionLibrary):
		def __init__(self):
			self.function = mock.MagicMock()
			self.function.return_value = 1.2
		
		def get_fitness_function(self, identifier: str) -> interfaces.FitnessFunction:
			return self.function
	
	def setUp(self):
		self.mock_lib = self.MockLibrary()
	
	def test_creation(self):
		ff_lib = self.mock_lib
		identifier = "my_ff"
		fitness_function = ff_lib.get_fitness_function(identifier)
		
		self.assertEqual(self.mock_lib.function, fitness_function)
	
	def test_call(self):
		ff_lib = self.mock_lib
		fitness_function = ff_lib.get_fitness_function("my_ff")
		
		input_data = model.InputData([2, 3, 4])
		output_data = model.OutputData([12, 13, 14])
		
		fitness_function(input_data, output_data)
		self.mock_lib.function.assert_called_once_with(input_data, output_data)
	

class ChromosomeTest(unittest.TestCase):
	def test_creation(self):
		chromo = model.Chromosome(2, (1, 2, 3))
	
	def test_getitem(self):
		allele_indices = (1, 2, 3)
		chromo = model.Chromosome(2, allele_indices)
		for i, a in enumerate(allele_indices):
			self.assertEqual(a, chromo[i])
