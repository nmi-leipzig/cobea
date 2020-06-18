#!/usr/bin/env python3

import unittest.mock as mock
import sys

import unittest

from adapters.scipy_functions import SciPyFunctions
from adapters.scipy_preprocessing import SciPyPreprocessing
import domain.model as model
import domain.interfaces as interfaces
import domain.use_cases as use_cases

class SciPyFunctionsTest(unittest.TestCase):
	def setUp(self):
		pass
	
	def test_creation(self):
		spf = SciPyFunctions()
	
	def test_get_implementation(self):
		spf = SciPyFunctions()
		res = spf.get_implementation("pearsons_correlation")
		
		self.assertEqual(SciPyFunctions.pearsons_correlation, res)
	
	def test_use_case_creation(self):
		spf = SciPyFunctions()
		create_case = use_cases.CreateFitnessFunction(spf)
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
		spf = SciPyFunctions()
		create_case = use_cases.CreateFitnessFunction(spf)
		fitness_function = create_case(use_cases.RequestObject(
			identifier = "pearsons_correlation",
			description = "Pearson Correlation by SciPy"
		))
		
		test_in = model.InputData((10, 45, 23, 53))
		test_out = model.OutputData((2, 1, 7, 3))
		
		expected = SciPyFunctions.pearsons_correlation(test_in, test_out)
		res = fitness_function(test_in, test_out)
		self.assertEqual(expected, res)

class SciPyPreprocessingTest(unittest.TestCase):
	def get_example_request(self):
		return use_cases.RequestObject(
			identifier = "select",
			description = "select [3:5]",
			start = 3,
			end = 5
		)
	
	def check_example(self, func):
		org_in = model.InputData(range(10))
		org_out = model.OutputData(range(10,20))
		
		res_in, res_out = func(org_in, org_out)
		
		self.assertEqual(org_in[3:5], res_in)
		self.assertEqual(org_out[3:5], res_out)
		
		self.assertTrue(isinstance(res_in, model.InputData))
		self.assertTrue(isinstance(res_out, model.OutputData))
	
	def test_creation(self):
		spp = SciPyPreprocessing()
	
	def test_get_implementation(self):
		spp = SciPyPreprocessing()
		
		res = spp.get_implementation(self.get_example_request())
		self.check_example(res)
	
	def test_create_use_case(self):
		spp = SciPyPreprocessing()
		use_case = use_cases.CreatePreprocessing(spp)
		req = self.get_example_request()
		
		res = use_case(req)
		self.assertEqual(req.identifier, res.identifier)
		self.assertEqual(req.description, res.description)
		self.check_example(res)
