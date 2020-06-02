#!/usr/bin/env python3

import unittest.mock as mock
import sys

import unittest

from adapters.scipy_functions import SciPyFunctions
import domain.model as model
import domain.interfaces as interfaces
import domain.use_cases as use_cases

class SciPyFunctionsTest(unittest.TestCase):
	def setUp(self):
		pass
	
	def test_creation(self):
		scp = SciPyFunctions()
	
	def test_get_implementation(self):
		scp = SciPyFunctions()
		res = scp.get_implementation("pearsons_correlation")
		
		self.assertEqual(SciPyFunctions.pearsons_correlation, res)
	
	def test_use_case_creation(self):
		scp = SciPyFunctions()
		create_case = use_cases.CreateFitnessFunction(scp)
		req = use_cases.RequestObject()
		identifier = "pearsons_correlation"
		description = "Pearson Correlation by SciPy"
		req["identifier"] = identifier
		req["description"] = description
		fitness_function = create_case(req)
		
		self.assertEqual(identifier, fitness_function.identifier)
		self.assertEqual(description, fitness_function.description)
		self.assertEqual(SciPyFunctions.pearsons_correlation, fitness_function.implementation)
	
	def test_function(self):
		scp = SciPyFunctions()
		create_case = use_cases.CreateFitnessFunction(scp)
		fitness_function = create_case(use_cases.RequestObject(
			identifier = "pearsons_correlation",
			description = "Pearson Correlation by SciPy"
		))
		
		test_in = model.TestInput((10, 45, 23, 53))
		test_out = model.TestOutput((2, 1, 7, 3))
		
		expected = SciPyFunctions.pearsons_correlation(test_in, test_out)
		res = fitness_function(test_in, test_out)
		self.assertEqual(expected, res)
