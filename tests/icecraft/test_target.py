import os
import unittest

import adapters.icecraft as icecraft
from adapters.icecraft import RAMMode

from .common import SEND_BRAM_META, TEST_DATA_DIR

class IcecraftDeviceTest(unittest.TestCase):
	def get_configured_device(self, asc_filename):
		fpga = icecraft.target.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		config = icecraft.IcecraftStormConfig.create_from_file(asc_filename)
		device.configure(config)
		
		return device
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_creation(self):
		fpga = icecraft.target.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_serial_number(self):
		fpga = icecraft.target.FPGABoard.get_suitable_board()
		exp_sn = fpga.serial_number
		device = icecraft.IcecraftDevice(fpga)
		sn = device.serial_number
		self.assertEqual(exp_sn, sn)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_hardware_type(self):
		fpga = icecraft.target.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		exp_ht = icecraft.HX8K_BOARD
		ht = device.hardware_type
		self.assertEqual(exp_ht, ht)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_configure(self):
		device = self.get_configured_device(SEND_BRAM_META[0].asc_filename)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_read_bytes(self):
		meta = next(s for s in SEND_BRAM_META if s.mode==RAMMode.RAM_512x8)
		device = self.get_configured_device(meta.asc_filename)
		
		exp_values = bytes(meta.initial_data)
		values = device.read_bytes(len(exp_values))
		self.assertEqual(exp_values, values)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_write_bytes(self):
		asc_filename = os.path.join(TEST_DATA_DIR, "echo.asc")
		
		device = self.get_configured_device(asc_filename)
		for data in (bytes([0]), bytes([1]), bytes([255, 0])):
			device.write_bytes(data)
			recv = device.read_bytes(len(data))
			
			self.assertEqual(data, recv)
			#print(data, recv)
		
		device.close()
	

class IcecraftManagerTest(unittest.TestCase):
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_no_double_acquire(self):
		manager = icecraft.IcecraftManager()
		device = manager.acquire()
		with self.assertRaises(ValueError):
			device2 = manager.acquire(serial_number=device.serial_number)
	
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_no_double_release(self):
		manager = icecraft.IcecraftManager()
		device = manager.acquire()
		manager.release(device)
		with self.assertRaises(KeyError):
			manager.release(device)
	
