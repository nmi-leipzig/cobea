#!/usr/bin/env python3

import random
import sys
import unittest
import unittest.mock as mock

from dataclasses import dataclass
from typing import Callable, List, Optional

from adapters.dummies import DummyDriver
from adapters.embed_driver import FixedEmbedDriver
from adapters.embed_meter import EmbedMeter
from adapters.fitness import ReduceFF
from adapters.input_gen import SeqGen
from adapters.simtar import SimtarBitPos, SimtarConfig, SimtarDev, SimtarRepGen
from domain.allele_sequence import Allele, AlleleList, AlleleAll, AllelePow
from domain.interfaces import Driver, FitnessFunction, InputGen, MeasureTimeout, Meter, Representation, TargetConfiguration, TargetDevice
from domain.model import Chromosome, InputData, OutputData, Gene
from domain.use_cases import DecTarget, GenChromo, Measure, MeasureFitness, RandomChromo
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
		req = RequestObject(retry=0)
		#req["input_data"] = input_data
		
		res_data = measure_case(req).measurement
		
		self.assertEqual(exp_prep, mock_meter.prep_count)
		self.assertEqual(output_data, res_data)
	
	def test_retry(self):
		output_data = OutputData([12, 13, 14])
		
		def run_measure(retry, fail_count):
			mock_meter = MockMeter(output_data, fail_count=fail_count)
			driver = DummyDriver()
			measure_case = Measure(driver, mock_meter)
			req = RequestObject(retry=retry)
			
			return measure_case(req).measurement
		
		for retry in range(5):
			for fail_count in range(retry+1):
				res = run_measure(retry, fail_count)
			
			for fail_count in range(retry+1, 10):
				with self.assertRaises(MeasureTimeout):
					res = run_measure(retry, fail_count)
	
	def test_parameter_user(self):
		output_data = OutputData([12, 13, 14])
		mock_meter = MockMeter(output_data)
		driver = DummyDriver()
		
		measure_case = Measure(driver, mock_meter)
		check_parameter_user(self, measure_case)


class DecTargetTest(unittest.TestCase):
	def setUp(self):
		gen = SimtarRepGen()
		req = RequestObject(always_active=True)
		self.rep = gen(req).representation
		self.habitat = SimtarConfig()
		self.rep.prepare_config(self.habitat)
		self.target = SimtarDev()
		self.dut = DecTarget(self.rep, self.habitat, self.target)
	
	def all_outputs(self):
		outputs = []
		for i in range(16):
			self.target.write_bytes(bytes([i]))
			outputs.append(self.target.read_bytes(1))
		return outputs
	
	def test_create(self):
		# nothing to do as dut is created in setUp
		pass
	
	def test_call(self):
		req = RequestObject(chromosome=Chromosome(0, (0, )))
		res = self.dut(req)
		
		# check target
		outputs = self.all_outputs()
		self.assertEqual([b"\x00"]*16, outputs)
		
		# check config in response
		values = [res.configuration.get_bit(SimtarBitPos(i)) for i in range(17)]
		self.assertEqual([False]*16+[True], values)
	
	def test_modification_leak(self):
		# alteration to the returned configuration should not alter the habitat
		req1 = RequestObject(chromosome=Chromosome(0, (0, )))
		res1 = self.dut(req1)
		before = self.all_outputs()
		
		# reset active flag
		# dut is configured as always active, the Chromosome can't change that
		# but a direct manipulation of the habitat can
		res1.configuration.set_bit(SimtarBitPos(16), False)
		
		req2 = RequestObject(chromosome=Chromosome(0, (0, )))
		res2 = self.dut(req2)
		after = self.all_outputs()
		
		# all outputs would be b'\xff' if active bit was also reset in the habitat
		self.assertEqual(before, after)
	
	def test_parameter_user(self):
		check_parameter_user(self, self.dut)


class MeasureFitnessTest(unittest.TestCase):
	@dataclass
	class MFData:
		dut: MeasureFitness = None
		rep: Representation = None
		habitat: TargetConfiguration = None
		target: TargetDevice = None
		dec_uc: DecTarget = None
		drv: Driver = None
		mtr: Meter = None
		mea_uc: Measure = None
		ff: FitnessFunction = None
		uc_req: RequestObject = None # prepared request for call to MeasureFitness
		prep: Callable[[OutputData], OutputData] = None
		drv_list: List[InputData] = None
		gen: Optional[InputGen] = None
	
	def create_dut(self, use_gen):
		res = self.MFData()
		# dec
		gen = SimtarRepGen()
		req = RequestObject(always_active=True)
		res.rep = gen(req).representation
		res.habitat = SimtarConfig()
		res.rep.prepare_config(res.habitat)
		
		res.target = SimtarDev()
		res.dec_uc = DecTarget(res.rep, res.habitat, res.target)
		
		# Measure
		res.drv = FixedEmbedDriver(res.target, "B")
		res.mtr = EmbedMeter()
		res.mea_uc = Measure(res.drv, res.mtr)
		
		#FitnessFunction
		res.ff = ReduceFF(lambda a, b: a+b)
		
		# prepare request
		res.uc_req = RequestObject(
			prefix = bytes(),
			output_count = 1,
			output_format = "B",
			meter_dev = res.target,
		)
		
		#InputGen
		res.drv_list = [InputData([i]) for i in range(16)]
		if use_gen:
			res.gen = SeqGen(res.drv_list)
		
		res.prep = lambda a: OutputData([float(v) for v in a])
		res.dut = MeasureFitness(res.dec_uc, res.mea_uc, res.ff, res.gen, prep=res.prep)
		
		return res
	
	def test_call(self):
		for use_gen in [False, True]:
			with self.subTest(use_input_gen=use_gen):
				dut_data = self.create_dut(use_gen)
				allele_index = 50
				chromo = Chromosome(2, [allele_index])
				tt = next(dut_data.rep.iter_genes()).alleles[allele_index].values
				req = dut_data.uc_req
				req["chromosome"] = chromo
				for i, exp in enumerate(tt):
					if not use_gen:
						req["driver_data"] = dut_data.drv_list[i]
					
					res = dut_data.dut(req)
					self.assertEqual(exp, res.fitness==1, f"{i}: {res}, {tt}")
	
	def test_parameter_user(self):
		dut_data = self.create_dut(False)
		check_parameter_user(self, dut_data.dut)


class GenChromoTest(unittest.TestCase):
	def setUp(self):
		self.id_list = [3, 4, 28, 0, 10]
		self.mock_id = MockUniqueID(self.id_list)
	
	def test_call(self):
		allele_indices_list = [[j*j for j in range(i+1)] for i in range(len(self.id_list))]
		
		dut = GenChromo(self.mock_id)
		
		for exp_id, exp_indices in zip(self.id_list, allele_indices_list):
			res = dut(RequestObject(allele_indices=exp_indices)).chromosome
			
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
			res = dut(RequestObject()).chromosome
			
			self.assertEqual(exp_id, res.identifier)
			self.assertEqual(self.int_list[i*gene_count:(i+1)*gene_count], list(res.allele_indices))
	
	def test_parameter_user(self):
		dut = RandomChromo(self.mock_prng, self.mock_rep, self.mock_id)
		
		check_parameter_user(self, dut)
