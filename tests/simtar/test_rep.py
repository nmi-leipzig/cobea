from unittest import TestCase
from unittest.mock import MagicMock

from adapters.simtar.config import SimtarConfig
from adapters.simtar.pos import SimtarBitPos
from adapters.simtar.rep import SimtarRep, SimtarRepGen
from domain.model import Chromosome
from domain.request_model import RequestObject

from ..common import check_parameter_user


class SimtarRepTest(TestCase):
	def setUp(self):
		self.count = 17
	
	def all_bits(self, config):
		return [config.get_bit(SimtarBitPos(i)) for i in range(self.count)]
	
	def test_create_empty(self):
		dut = SimtarRep([], [])
	
	def create(self, always_active=True):
		gen = SimtarRepGen()
		req = RequestObject(always_active=always_active)
		res = gen(req)
		
		return res.representation
	
	def test_create(self):
		dut = self.create(False)
	
	def test_create_active(self):
		dut = self.create(True)
	
	def test_prepare_config(self):
		dut = self.create(True)
		config = SimtarConfig()
		
		dut.prepare_config(config)
		
		self.assertTrue(config.get_bit(SimtarBitPos(16)))
	
	def test_decode(self):
		test_data = [ # allele index list, expected bits
			((0, 0), [False]*17),
			((0, 1), [False]*16+[True]),
		]
		
		dut = self.create(False)
		config = SimtarConfig()
		for i, (indices, exp_list) in enumerate(test_data):
			chromo = Chromosome(i, indices)
			dut.decode(config, chromo)
			res = self.all_bits(config)
			
			self.assertEqual(exp_list, res)
	
	def test_iter_genes(self):
		mock_genes = [MagicMock for _ in range(3)]
		dut = SimtarRep(mock_genes, [])
		
		for exp, res in zip(mock_genes, dut.iter_genes()):
			self.assertEqual(exp, res)


class SimtarRepGenTest(TestCase):
	def test_parameter_user(self):
		dut = SimtarRepGen()
		check_parameter_user(self, dut)
	
	def test_call(self):
		dut = SimtarRepGen()
		
		with self.subTest(desc="always active"):
			req = RequestObject(always_active=True)
			res = dut(req)
			self.assertIn("representation", res)
			rep = res.representation
			
			genes = [g for g in rep.iter_genes()]
			self.assertEqual(1, len(genes))
			for i in range(16):
				self.assertEqual(i, genes[0].bit_positions[i])
		
		with self.subTest(desc="not always active"):
			req = RequestObject(always_active=False)
			res = dut(req)
			self.assertIn("representation", res)
			rep = res.representation
			
			genes = [g for g in rep.iter_genes()]
			self.assertEqual(2, len(genes))
			for i in range(16):
				self.assertEqual(i, genes[0].bit_positions[i])
			
			self.assertEqual((16, ), genes[1].bit_positions)
