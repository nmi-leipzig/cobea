import random
import struct

from typing import NamedTuple, List
import os

from unittest import TestCase, skipIf
from unittest.mock import MagicMock

from adapters.dummies import DummyMeter
from adapters.embed_driver import EmbedDriver
from adapters.embed_meter import EmbedMeter
from adapters.icecraft.configuration import IcecraftRawConfig
from adapters.icecraft.target import IcecraftManager
from domain.model import InputData
from domain.use_cases import Measure
from domain.request_model import RequestObject

from .common import check_parameter_user, TEST_DATA_DIR
from .mocks import MockTargetDevice

class EmbedDriverTest(TestCase):
	class EDTC(NamedTuple):
		fmt: str
		exp_data: bytes
		driver_data: List[int]
	
	def setUp(self):
		self.tc_list = []
		for fmt in ["B", "<H"]:
			exp_data = bytes([random.getrandbits(8) for _ in range(20*struct.calcsize(fmt))])
			driver_data = InputData(d[0] for d in struct.iter_unpack(fmt, exp_data))
			self.tc_list.append(self.EDTC(fmt, exp_data, driver_data))
	
	def test_creation(self):
		dut = EmbedDriver()
	
	def test_drive(self):
		dut = EmbedDriver()
		
		for tc in self.tc_list:
			with self.subTest(fmt=tc.fmt):
				dev = MockTargetDevice()
				req = RequestObject(
					driver_data = tc.driver_data,
					driver_format = tc.fmt,
					driver_dev = dev,
				)
				
				dut.drive(req)
				
				self.assertEqual(tc.exp_data, dev.written)
	
	def test_clean_up(self):
		dut = EmbedDriver()
		mock_req = MagicMock()
		
		dut.clean_up(mock_req)
		
		self.assertEqual(0, len(mock_req.mock_calls))
		self.assertEqual(0, len(mock_req.method_calls))
	
	def test_write_data(self):
		for tc in self.tc_list:
			with self.subTest(fmt=tc.fmt):
				dev = MockTargetDevice()
				
				EmbedDriver.write_data(dev, tc.driver_data, tc.fmt)
				
				self.assertEqual(tc.exp_data, dev.written)
	
	def test_use_case(self):
		dut = EmbedDriver()
		
		measure_case = Measure(dut, DummyMeter())
		
		for tc in self.tc_list:
			with self.subTest(fmt=tc.fmt):
				dev = MockTargetDevice()
				req = RequestObject(
					driver_data = tc.driver_data,
					driver_format = tc.fmt,
					driver_dev = dev,
					retry = 0,
				)
				
				measure_case(req)
				
				self.assertEqual(tc.exp_data, dev.written)
		
	
	@skipIf(IcecraftManager.device_present(), "no hardware")
	def test_with_hardware(self):
		man = IcecraftManager()
		
		dut = EmbedDriver()
		meter = EmbedMeter()
		config = IcecraftRawConfig.create_from_file(os.path.join(TEST_DATA_DIR, "echo_fpga.asc"))
		
		for tc in self.tc_list:
			with self.subTest(fmt=tc.fmt):
				dev = man.acquire()
				
				dev.configure(config)
				
				driver_req = RequestObject(
					driver_data = tc.driver_data,
					driver_format = tc.fmt,
					driver_dev = dev,
				)
				
				meter_req = RequestObject(
					prefix = b"",
					output_count = len(tc.driver_data),
					output_format = tc.fmt,
					meter_dev = dev,
				)
				
				meter.prepare(meter_req)
				dut.drive(driver_req)
				res = meter.measure(meter_req)
				
				self.assertEqual(tc.driver_data, res)
				
				man.release(dev)
	
	def test_parameter_user(self):
		dut = EmbedDriver()
		check_parameter_user(self, dut)
