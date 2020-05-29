#!/usr/bin/env python3

import unittest.mock as mock
import sys

import unittest

from domain import model
import domain.interfaces as interfaces
import domain.use_cases as use_cases

class FitnessFunctionTest(unittest.TestCase):
	class MockLibrary(interfaces.FitnessFunctionLibrary):
		def __init__(self):
			self.function = mock.MagicMock()
			self.function.return_value = 1.2
		
		def get_implementation(self, identifier: str) -> model.FitnessFunctionImpl:
			return self.function
	
	def setUp(self):
		self.mock_lib = self.MockLibrary()
	
	def test_creation(self):
		create_case = use_cases.CreateFitnessFunction(self.mock_lib)
		identifier = "my_ff"
		description = "my very own fitness function"
		fitness_function = create_case(identifier, description)
		
		self.assertEqual(identifier, fitness_function.identifier)
		self.assertEqual(description, fitness_function.description)
		self.assertEqual(self.mock_lib.function, fitness_function.implementation)
	
	def test_call(self):
		create_case = use_cases.CreateFitnessFunction(self.mock_lib)
		fitness_function = create_case("my_ff", "my very own fitness function")
		
		test_input = model.TestInput([2, 3, 4])
		test_output = model.TestOutput([12, 13, 14])
		
		fitness_function(test_input, test_output)
		self.mock_lib.function.assert_called_once_with(test_input, test_output)
