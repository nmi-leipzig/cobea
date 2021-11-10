from unittest import TestCase

from adapters.simtar.pos import SimtarBitPos


class SimtarBitPosTest(TestCase):
	def test_creation(self):
		dut = SimtarBitPos(8)
	
	def test_value(self):
		dut = SimtarBitPos(52)
		self.assertEqual(52, dut)
	
	def test_to_ints(self):
		val = 17
		dut = SimtarBitPos(val)
		res = dut.to_ints()
		
		self.assertIsInstance(res, tuple)
		self.assertEqual(1, len(res))
		self.assertEqual(val, res[0])
	
	def test_add(self):
		s1 = SimtarBitPos(5)
		s2 = SimtarBitPos(3)
		dut = SimtarBitPos(s1 + s2)
		
		self.assertIsInstance(dut, SimtarBitPos)
		self.assertEqual(dut, 8)
