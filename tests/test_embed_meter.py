from unittest import TestCase, skipIf
from unittest.mock import MagicMock
import random
import struct

from adapters.dummies import DummyDriver
from adapters.embed_meter import EmbedMeter
from adapters.icecraft.configuration import IcecraftRawConfig, IcecraftStormConfig, block_size_from_mode
from adapters.icecraft.target import IcecraftManager
from domain.request_model import RequestObject
from domain.use_cases import Measure

from .common import check_parameter_user
from .icecraft.common import SEND_BRAM_META, FORMAT_DICT
from .mocks import MockTargetDevice

class EmbedMeterTest(TestCase):
	def setUp(self):
		self.req_list = []
		for prefix in [bytes(), b"hello"]:
			for output_format in ["B", "<H"]:
				for output_count in [0, 1, 2, 3, 4]:
					self.req_list.append(RequestObject(
						prefix = prefix,
						output_count = output_count,
						output_format = output_format,
						retry = 0,
					))
	
	def test_creation(self):
		dut = EmbedMeter()
	
	def test_prepare(self):
		dut = EmbedMeter()
		for req in self.req_list:
			with self.subTest(req=req):
				req["meter_dev"] = MagicMock()
				exp = RequestObject(req)
				dut.prepare(req)
				
				for var in ["prefix", "output_count", "output_format"]:
					self.assertEqual(exp[var], req[var])
				
				self.assertEqual(0, len(exp.meter_dev.method_calls))
	
	def test_measure(self):
		dut = EmbedMeter()
		
		for req in self.req_list:
			with self.subTest(req=req):
				exp_data, ret_data = self.create_data(req)
				
				req["meter_dev"] = MockTargetDevice(read_data=ret_data)
				
				res = dut.measure(req)
				
				self.assertEqual(exp_data, list(res))
	
	@staticmethod
	def create_data(req):
		max_data = pow(256, struct.calcsize(req.output_format)) - 1
		exp_data = [random.randint(0, max_data) for _ in range(req.output_count)]
		ret_data = req.prefix + b"".join(struct.pack(req.output_format, d) for d in exp_data)
		
		return exp_data, ret_data
	
	def test_fail_prefix(self):
		dut = EmbedMeter()
		
		for req in self.req_list:
			if not len(req.prefix):
				continue
			
			with self.subTest(req=req):
				exp_data, ret_data = self.create_data(req)
				ret_data = bytes([(ret_data[0]+1)%256]) + ret_data[1:]
				
				req["meter_dev"] = MockTargetDevice(read_data=ret_data)
				
				with self.assertRaises(AssertionError):
					res = dut.measure(req)
				
	
	def test_use_case(self):
		dut = EmbedMeter()
		
		measure_case = Measure(DummyDriver(), dut)
		
		for req in self.req_list:
			with self.subTest(req=req):
				exp_data, ret_data = self.create_data(req)
				
				req["meter_dev"] = MockTargetDevice(read_data=ret_data)
				
				res = measure_case(req)
				
				self.assertEqual(exp_data, list(res))
	
	@skipIf(IcecraftManager.device_present(), "no hardware")
	def test_with_hardware(self):
		dut = EmbedMeter()
		
		man = IcecraftManager()
		device = man.acquire()
		
		for send_meta in SEND_BRAM_META:
			with self.subTest(mode=send_meta.mode):
				config = IcecraftRawConfig.create_from_file(send_meta.asc_filename)
				device.configure(config)
				
				count = block_size_from_mode(send_meta.mode)
				
				req = RequestObject(
					prefix = b"",
					output_count = count, #len(send_meta.initial_data),
					output_format = FORMAT_DICT[send_meta.mode],
					meter_dev = device,
				)
				
				res = dut.measure(req)
				
				self.assertEqual(send_meta.initial_data+[0]*(count-len(send_meta.initial_data)), list(res))
		
		man.release(device)
	
	def test_parameter_user(self):
		dut = EmbedMeter()
		check_parameter_user(self, dut)
