import random
import unittest

import adapters.icecraft as icecraft
from domain import model
from domain.request_model import RequestObject

from ..common import check_parameter_user

from .common import SEND_BRAM_META

class IcecraftEmbedMeterTest(unittest.TestCase):
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_call(self):
		format_dict = {"256x16": "<H", "512x8": "B", "1024x4": "B", "2048x2": "B"}
		meter = icecraft.IcecraftEmbedMeter()
		fpga = icecraft.target.FPGABoard.get_suitable_board()
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
