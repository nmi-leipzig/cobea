import random
import unittest

import adapters.icecraft as icecraft
from adapters.icecraft import RAMMode
from adapters.icecraft.configuration import block_size_from_mode
from domain import model
from domain.request_model import RequestObject

from tests.common import check_parameter_user

from tests.icecraft.common import SEND_BRAM_META

class IcecraftEmbedMeterTest(unittest.TestCase):
	@unittest.skipIf(len(icecraft.target.FPGABoard.get_suitable_serial_numbers()) < 1, "no hardware")
	def test_call(self):
		format_dict = {
			RAMMode.RAM_256x16: "<H",
			RAMMode.RAM_512x8: "B",
			RAMMode.RAM_1024x4: "B",
			RAMMode.RAM_2048x2: "B"
		}
		meter = icecraft.IcecraftEmbedMeter()
		fpga = icecraft.target.FPGABoard.get_suitable_board()
		device = icecraft.IcecraftDevice(fpga)
		
		for send_meta in SEND_BRAM_META:
			with self.subTest(mode=send_meta.mode):
				config = icecraft.IcecraftStormConfig.create_from_filename(send_meta.asc_filename)
				# the BRAM needs some time to be functional after power up
				# else the first read (most of the time address 0) returns always 0
				data = model.InputData([
					random.randint(0, send_meta.mask) for _ in range(block_size_from_mode(send_meta.mode))
				])
				req = RequestObject()
				req["configuration"] = config
				req["ram_mode"] = send_meta.mode
				req["ram_blocks"] = [send_meta.ram_block]
				req["input_data"] = data
				req["prefix"] = None
				req["output_count"] = len(data)
				req["output_format"] = format_dict[req.ram_mode]
				req["target"] = device
				
				output = meter.measure(req).measurement
				self.assertEqual(data, output)
		
		device.close()
	
	def test_parameter_user(self):
		meter = icecraft.IcecraftEmbedMeter()
		check_parameter_user(self, meter)
