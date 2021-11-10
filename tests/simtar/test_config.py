import random

from unittest import TestCase

from adapters.simtar.config import SimtarConfig
from adapters.simtar.pos import SimtarBitPos


class SimtarConfigTest(TestCase):
	def setUp(self):
		self.count = 17
		self.test_data = [[False]*self.count, [True]*self.count, [False]*9+[True]*8]
	
	def all_bits(self, dut):
		return [dut.get_bit(SimtarBitPos(i)) for i in range(self.count)]
	
	def test_create(self):
		dut = SimtarConfig()
	
	def test_initial_data(self):
		for data in self.test_data:
			with self.subTest(data=data):
				dut = SimtarConfig(data)
				
				self.assertEqual(data, self.all_bits(dut))
	
	def test_text(self):
		for data in self.test_data:
			with self.subTest(data=data):
				dut = SimtarConfig(data)
				text = dut.to_text()
				res = SimtarConfig.from_text(text)
				
				self.assertEqual(data, self.all_bits(res))
	
	def test_get_bit(self):
		for data in self.test_data:
			with self.subTest(data=data):
				dut = SimtarConfig(data)
				for i in range(self.count):
					res = dut.get_bit(SimtarBitPos(i))
					self.assertEqual(data[i], res)
	
	def test_set_bit(self):
		ref = [None]*self.count
		dut = SimtarConfig(ref)
		for data in self.test_data:
			indices = [i for i in range(self.count)]
			random.shuffle(indices)
			with self.subTest(data=data, indices=indices):
				for i in indices:
					val = data[i]
					ref[i] = val
					dut.set_bit(SimtarBitPos(i), val)
					
					self.assertEqual(ref, self.all_bits(dut))
