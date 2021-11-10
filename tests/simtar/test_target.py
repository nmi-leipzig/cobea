from unittest import TestCase

from adapters.simtar.config import SimtarConfig
from adapters.simtar.pos import SimtarBitPos
from adapters.simtar.target import SimtarDev

class SimtarDevTest(TestCase):
	def test_create(self):
		dut = SimtarDev()
	
	def test_sn(self):
		dut1 = SimtarDev()
		dut2 = SimtarDev()
		
		self.assertNotEqual(dut1.serial_number, dut2.serial_number)
	
	def test_configure(self):
		config = SimtarConfig([True]*17)
		dut = SimtarDev()
		dut.configure(config)
	
	def test_read_bytes(self):
		test_data = [ # config data, expected value
			([True]*17, b"\x01"),
			([False]*17, b"\xff"),
			([False]*16+[True], b"\x00"),
		]
		
		dut = SimtarDev()
		for data, exp in test_data:
			with self.subTest(data=data):
				config = SimtarConfig(data)
				dut.configure(config)
				res = dut.read_bytes(1)
				
				self.assertEqual(exp, res)
	
	def test_write_bytes(self):
		test_data = [ # config data, expected values
			([True]*17, [b"\x01"]*16),
			([False]*17, [b"\xff"]*16),
			([False]*16+[True], [b"\x00"]*16),
			([True]*6+[False]*10+[True], [b"\x01"]*6+[b"\x00"]*10)
		]
		
		dut = SimtarDev()
		for data, exp_list in test_data:
			with self.subTest(data=data):
				config = SimtarConfig(data)
				dut.configure(config)
				for i, exp in enumerate(exp_list):
					res = dut.write_bytes(bytes([i]))
					self.assertEqual(1, res)
					
					val = dut.read_bytes(1)
					self.assertEqual(exp, val)
