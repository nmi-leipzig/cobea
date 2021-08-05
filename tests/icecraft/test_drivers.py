import unittest
import random
from copy import deepcopy
from unittest.mock import MagicMock
from typing import NamedTuple

from adapters.dummies import DummyMeter
from adapters.icecraft.drivers import IcecraftRAMDriver
from adapters.icecraft.configuration import IcecraftRawConfig, block_size_from_mode
from adapters.icecraft.misc import RAMMode, IcecraftPosition
from adapters.icecraft.target import IcecraftManager
from adapters.embed_meter import EmbedMeter
from domain.model import InputData
from domain.request_model import RequestObject
from domain.use_cases import Measure

from .common import SEND_BRAM_META, FORMAT_DICT

from ..common import check_parameter_user
from ..mocks import MockTargetDevice

class IcecraftRAMDriverTest(unittest.TestCase):
	def test_creation(self):
		dut = IcecraftRAMDriver()
	
	def create_request_and_exp(self):
		exp = RequestObject(
			configuration = IcecraftRawConfig.create_empty(),
			ram_mode = RAMMode.RAM_512x8,
			#TODO: random values
			data = [0xFF]*512,
			block = IcecraftPosition(8, 27),
			driver_dev = MockTargetDevice(),
		)
		req = RequestObject(
			configuration = exp.configuration,
			ram_mode = exp.ram_mode,
			input_data = InputData(exp.data),
			ram_blocks = [exp.block],
			driver_dev = exp.driver_dev,
		)
		
		return req, exp
	
	def test_drive(self):
		req, exp = self.create_request_and_exp()
		
		dut = IcecraftRAMDriver()
		dut.drive(req)
		
		self.assertEqual(exp.data, exp.configuration.get_ram_values(exp.block, 0, len(exp.data), exp.ram_mode))
		self.assertEqual((exp.configuration.to_text(), ), exp.driver_dev.configured)
	
	def test_clean_up(self):
		config = IcecraftRawConfig.create_empty()
		target_mock = MagicMock()
		exp_txt = config.to_text()
		
		req = RequestObject(configuration=config, driver_dev=target_mock)
		
		dut = IcecraftRAMDriver()
		
		dut.clean_up(req)
		
		self.assertEqual(exp_txt, req.configuration.to_text())
		self.assertEqual(0, len(target_mock.method_calls))
	
	def test_use_case(self):
		req, exp = self.create_request_and_exp()
		
		dut = IcecraftRAMDriver()
		
		measure_case = Measure(dut, DummyMeter())
		
		res = measure_case(req)
		
		self.assertEqual(exp.data, exp.configuration.get_ram_values(exp.block, 0, len(exp.data), exp.ram_mode))
		self.assertEqual((exp.configuration.to_text(), ), exp.driver_dev.configured)
	
	@unittest.skipIf(IcecraftManager.device_present(), "no hardware")
	def test_with_hardware(self):
		man = IcecraftManager()
		device = man.acquire()
		meter = EmbedMeter()
		dut = IcecraftRAMDriver()
		
		for send_meta in SEND_BRAM_META:
			with self.subTest(mode=send_meta.mode):
				config = IcecraftRawConfig.create_from_filename(send_meta.asc_filename)
				# the BRAM needs some time to be functional after power up
				# else the first read (most of the time address 0) returns always 0
				data = InputData([
					random.randint(0, send_meta.mask) for _ in range(block_size_from_mode(send_meta.mode))
				])
				req = RequestObject()
				req["configuration"] = config
				req["ram_mode"] = send_meta.mode
				req["ram_blocks"] = [send_meta.ram_block]
				req["input_data"] = data
				req["driver_dev"] = device
				
				read_req = RequestObject(
					prefix = b"",
					output_count = len(data),
					output_format = FORMAT_DICT[req.ram_mode],
					meter_dev = device,
				)
				
				meter.prepare(read_req)
				dut.drive(req)
				
				output = meter.measure(read_req)
				
				self.assertEqual(data, output)
		
		man.release(device)
	
	def test_parameter_user(self):
		dut = IcecraftRAMDriver()
		check_parameter_user(self, dut)
