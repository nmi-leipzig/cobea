#!/usr/bin/env python3

import random
import sys
import unittest
import unittest.mock as mock

from adapters.dummies import DummyDriver
from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow
from domain.model import InputData, OutputData, Gene
from domain.use_cases import Measure, GenChromo, RandomChromo
from domain.request_model import RequestObject

from ..mocks import MockTargetManager, MockMeter, MockUniqueID, MockRandInt, MockRepresentation, MockBitPos
from ..common import check_parameter_user

class MeasureTest(unittest.TestCase):
	def test_call(self):
		input_data = InputData([2, 3, 4])
		output_data = OutputData([12, 13, 14])
		
		mock_meter = MockMeter(output_data)
		exp_prep = mock_meter.prep_count + 1
		
		driver = DummyDriver()
		
		measure_case = Measure(driver, mock_meter)
		req = RequestObject()
		#req["input_data"] = input_data
		
		res_data = measure_case(req)
		
		self.assertEqual(exp_prep, mock_meter.prep_count)
		self.assertEqual(output_data, res_data)
	
	def test_parameter_user(self):
		output_data = OutputData([12, 13, 14])
		mock_meter = MockMeter(output_data)
		driver = DummyDriver()
		
		measure_case = Measure(driver, mock_meter)
		check_parameter_user(self, measure_case)

class GenChromoTest(unittest.TestCase):
	def setUp(self):
		self.id_list = [3, 4, 28, 0, 10]
		self.mock_id =  MockUniqueID(self.id_list)
	
	def test_call(self):
		allele_indices_list = [[j*j for j in range(i+1)] for i in range(len(self.id_list))]
		
		dut = GenChromo(self.mock_id)
		
		for exp_id, exp_indices in zip(self.id_list, allele_indices_list):
			res = dut(RequestObject(allele_indices=exp_indices))
			
			self.assertEqual(exp_id, res.identifier)
			self.assertEqual(exp_indices, list(res.allele_indices))
	
	def test_parameter_user(self):
		dut = GenChromo(self.mock_id)
		
		check_parameter_user(self, dut)

class RandomChromoTest(unittest.TestCase):
	def setUp(self):
		self.id_list = [3, 4, 28, 0, 10]
		self.mock_id =  MockUniqueID(self.id_list)
		
		max_len = 5
		all_list = []
		list_list = []
		pow_list = []
		for l in range(1, max_len+1):
			all_list.append(Gene(tuple(MockBitPos(l*100+j) for j in range(l)), AlleleAll(l), ""))
			list_list.append(Gene(
				tuple(MockBitPos(l*1000+j) for j in range(l)),
				AlleleList([Allele((False, )*l, ""), Allele((True, )*l, "")]),
				""
			))
			pow_list.append(Gene(tuple(MockBitPos(l*10000+j) for j in range(l)), AllelePow(l, []), ""))
		
		gene_list = all_list + list_list + pow_list
		self.mock_rep = MockRepresentation(gene_list)
		
		int_list = [0]*len(gene_list)
		int_list.extend([len(g.alleles)-1 for g in gene_list])
		for _ in range(len(self.id_list)-2):
			int_list.extend([random.randint(0, len(g.alleles)-1) for g in gene_list])
		
		self.int_list = int_list
		self.mock_prng = MockRandInt(int_list)
	
	def test_call(self):
		gene_count = len(list(self.mock_rep.iter_genes()))
		dut = RandomChromo(self.mock_prng, self.mock_rep, self.mock_id)
		
		for i, exp_id in enumerate(self.id_list):
			res = dut(RequestObject())
			
			self.assertEqual(exp_id, res.identifier)
			self.assertEqual(self.int_list[i*gene_count:(i+1)*gene_count], list(res.allele_indices))
	
	def test_parameter_user(self):
		dut = RandomChromo(self.mock_prng, self.mock_rep, self.mock_id)
		
		check_parameter_user(self, dut)
