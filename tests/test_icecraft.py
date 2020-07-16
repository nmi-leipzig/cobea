import os
import sys
import unittest.mock as mock
from dataclasses import dataclass
from typing import List
import unittest
import subprocess
import json
import random

sys.path.append("/usr/local/bin")
import icebox

from domain import model
import domain.interfaces as interfaces
import domain.use_cases as use_cases
from domain.request_model import RequestObject
import adapters.icecraft_target as icecraft

from tests.test_request_model import check_parameter_user

TEST_DATA_DIR = __file__ + ".data"

@dataclass
class SendBRAMMeta:
	mode: str
	asc_filename: str
	ram_block: icecraft.TilePosition
	initial_data: List[int]
	mask: int
	
	def __post_init__(self):
		self.ram_block = icecraft.TilePosition(*self.ram_block)
		self.asc_filename = os.path.join(TEST_DATA_DIR, self.asc_filename)

with open(os.path.join(TEST_DATA_DIR, "send_all_bram.json"), "r") as json_file:
	SEND_BRAM_META = tuple([SendBRAMMeta(*s) for s in json.load(json_file)])

class IcecraftStormConfigTest(unittest.TestCase):
	def setUp(self):
		self.config_meta = {s.mode: s for s in SEND_BRAM_META}
	
	def test_create_empty(self):
		config = icecraft.IcecraftStormConfig.create_empty()
	
	def test_create_from_file(self):
		config = icecraft.IcecraftStormConfig.create_from_file(self.config_meta["256x16"].asc_filename)
	
	def test_get_ram_values(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = icecraft.IcecraftStormConfig.create_from_file(current.asc_filename)
				
				# read single
				for address, expected in enumerate(current.initial_data):
					value = config.get_ram_values(current.ram_block, address, 1, mode)
					self.assertEqual(expected, value[0])
				
				# read all
				values = config.get_ram_values(current.ram_block, 0, len(current.initial_data), mode)
				self.assertEqual(current.initial_data, values)
	
	def test_set_ram_values(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = icecraft.IcecraftStormConfig.create_from_file(current.asc_filename)
				
				expected = list(current.initial_data)
				# write single
				for address, old_value in enumerate(current.initial_data):
					new_value = current.mask ^ old_value
					config.set_ram_values(current.ram_block, address, [new_value], mode)
					expected[address] = new_value
					values = config.get_ram_values(current.ram_block, 0, len(current.initial_data), mode)
					self.assertEqual(expected, values)
				
				# write all
				config.set_ram_values(current.ram_block, 0, current.initial_data, mode)
				values = config.get_ram_values(current.ram_block, 0, len(current.initial_data), mode)
				self.assertEqual(current.initial_data, values)
	
	def check_configuration(self, expected_config, config):
		# compare two icebox configurations
		for value_name in ("device", "warmboot"):
			expected_value = getattr(expected_config, value_name)
			given_value = getattr(config, value_name)
			self.assertEqual(expected_value, given_value, f"Expected {value_name} to be {expected_value}, but was {given_value}.")
		
		for col_name in ("logic_tiles", "io_tiles", "ramb_tiles", "ramt_tiles", "ram_data", "ipcon_tiles", "symbols", "extra_bits", "dsp_tiles"):
			expected_col = getattr(expected_config, col_name)
			given_col = getattr(config, col_name)
			self.assertEqual(expected_col, given_col, f"Contents of {col_name} differ from expected values:")
	
	def test_write_asc(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = icecraft.IcecraftStormConfig.create_from_file(current.asc_filename)
				
				expected_ic = icebox.iceconfig()
				expected_ic.read_file(current.asc_filename)
				
				tmp_filename = f"tmp.test_write_asc.{mode}.asc"
				config.write_asc(tmp_filename)
				
				ic = icebox.iceconfig()
				ic.read_file(tmp_filename)
				
				os.remove(tmp_filename)
				
				self.check_configuration(expected_ic, ic)
	
	def test_write_bitstream(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = icecraft.IcecraftStormConfig.create_from_file(current.asc_filename)
				
				expected_ic = icebox.iceconfig()
				expected_ic.read_file(current.asc_filename)
				
				tmp_bin = f"tmp.test_write_bitstream.{mode}.bin"
				tmp_asc = f"tmp.test_write_bitstream.{mode}.asc"
				config.write_bitstream(tmp_bin)
				
				subprocess.run(
					["iceunpack", tmp_bin, tmp_asc],
					stdin=subprocess.DEVNULL,
					stderr=subprocess.STDOUT,
					#text=True, # only from Python version 3.7 on
					universal_newlines=True
				)
				
				ic = icebox.iceconfig()
				ic.read_file(tmp_asc)
				
				os.remove(tmp_bin)
				os.remove(tmp_asc)
				
				self.check_configuration(expected_ic, ic)
		

class IcecraftDeviceTest(unittest.TestCase):
	def get_configured_device(self, asc_filename):
		fpga = icecraft.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		config = icecraft.IcecraftStormConfig.create_from_file(asc_filename)
		device.configure(config)
		
		return device
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_creation(self):
		fpga = icecraft.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_serial_number(self):
		fpga = icecraft.FPGABoard.get_suitable_board()
		exp_sn = fpga.serial_number
		device = icecraft.IcecraftDevice(fpga)
		sn = device.serial_number
		self.assertEqual(exp_sn, sn)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_hardware_type(self):
		fpga = icecraft.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		exp_ht = icecraft.HX8K_BOARD
		ht = device.hardware_type
		self.assertEqual(exp_ht, ht)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_configure(self):
		device = self.get_configured_device(SEND_BRAM_META[0].asc_filename)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_read_bytes(self):
		meta = next(s for s in SEND_BRAM_META if s.mode=="512x8")
		device = self.get_configured_device(meta.asc_filename)
		
		exp_values = bytes(meta.initial_data)
		values = device.read_bytes(len(exp_values))
		self.assertEqual(exp_values, values)
		
		device.close()
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
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
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_no_double_acquire(self):
		manager = icecraft.IcecraftManager()
		device = manager.acquire()
		with self.assertRaises(ValueError):
			device2 = manager.acquire(serial_number=device.serial_number)
	
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_no_double_release(self):
		manager = icecraft.IcecraftManager()
		device = manager.acquire()
		manager.release(device)
		with self.assertRaises(KeyError):
			manager.release(device)
	

class IcecraftEmbedMeterTest(unittest.TestCase):
	@unittest.skipIf(len(icecraft.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_call(self):
		format_dict = {"256x16": "<H", "512x8": "B", "1024x4": "B", "2048x2": "B"}
		meter = icecraft.IcecraftEmbedMeter()
		fpga = icecraft.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		
		for send_meta in SEND_BRAM_META:
			with self.subTest(mode=send_meta.mode):
				config = icecraft.IcecraftStormConfig.create_from_file(send_meta.asc_filename)
				# address 0 is always 0, even if init values tries to define it otherwise
				data = model.InputData([
					random.randint(0, send_meta.mask) for _ in range(config.block_size_from_mode(send_meta.mode))
				])
				req = RequestObject()
				req["configuration"] = config
				req["ram_mode"] = send_meta.mode
				req["ram_blocks"] = [send_meta.ram_block]
				req["input_data"] = data
				req["prefix"] = None
				req["output_count"] = len(data)
				req["output_format"] = format_dict[req.ram_mode]
				
				output = meter(device, req)
				self.assertEqual(data, output)
		
		device.close()
	
	def test_parameter_user(self):
		meter = icecraft.IcecraftEmbedMeter()
		check_parameter_user(self, meter)
