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

class IcecraftBitPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = icecraft.IcecraftBitPosition(icecraft.TilePosition(1, 2), 3, 4)
	
	def check_values(self, dut, x, y, group, index):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(group, dut.group)
		self.assertEqual(index, dut.index)
	
	def test_values(self):
		x = 3
		y = 4
		group = 5
		index = 6
		
		dut = icecraft.IcecraftBitPosition(icecraft.TilePosition(x, y), group, index)
		self.check_values(dut, x, y, group, index)
	
	def test_from_coords(self):
		x = 3
		y = 4
		group = 5
		index = 6
		
		dut = icecraft.IcecraftBitPosition.from_coords(x, y, group, index)
		self.check_values(dut, x, y, group, index)
		

class IcecraftLUTPositionTest(unittest.TestCase):
	dut_cls = icecraft.IcecraftLUTPosition
	
	def test_creation(self):
		dut = self.dut_cls(icecraft.TilePosition(1, 2), 3)
	
	def check_values(self, dut, x, y, z):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(z, dut.z)
	
	def test_values(self):
		x = 3
		y = 4
		z = 5
		
		dut = self.dut_cls(icecraft.TilePosition(x, y), z)
		self.check_values(dut, x, y, z)
	
	def test_from_coords(self):
		x = 3
		y = 4
		z = 5
		
		dut = self.dut_cls.from_coords(x, y, z)
		self.check_values(dut, x, y, z)
	


class IcecraftColBufCtrlTest(IcecraftLUTPositionTest):
	dut_cls = icecraft.IcecraftColBufCtrl

class IcecraftNetPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = icecraft.IcecraftNetPosition(icecraft.TilePosition(1, 2), "test_net")
	
	def check_values(self, dut, x, y, net):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(net, dut.net)
	
	def test_values(self):
		x = 3
		y = 4
		net = "test_net"
		
		dut = icecraft.IcecraftNetPosition(icecraft.TilePosition(x, y), net)
		self.check_values(dut, x, y, net)
	
	def test_from_coords(self):
		x = 3
		y = 4
		net = "test_net"
		
		dut = icecraft.IcecraftNetPosition.from_coords(x, y, net)
		self.check_values(dut, x, y, net)
		

class IcecraftStormConfigTest(unittest.TestCase):
	target_cls = icecraft.IcecraftStormConfig
	
	def setUp(self):
		self.config_meta = {s.mode: s for s in SEND_BRAM_META}
	
	def test_create_empty(self):
		config = self.target_cls.create_empty()
	
	def test_create_from_file(self):
		config = self.target_cls.create_from_file(self.config_meta["256x16"].asc_filename)
	
	def test_get_ram_values(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = self.target_cls.create_from_file(current.asc_filename)
				
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
				config = self.target_cls.create_from_file(current.asc_filename)
				
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
	
	def check_config_dict(self, a, b):
		for key in a:
			if key in b:
				self.assertEqual(a[key], b[key])
			else:
				for s in a[key]:
					try:
						i = int(s, 16)
						self.assertEqual(0, i)
					except ValueError:
						self.fail(f"entry for {key} not in both dicts is {s}")
	
	def check_configuration(self, expected_config, config):
		# compare two icebox configurations
		for value_name in ("device", "warmboot"):
			expected_value = getattr(expected_config, value_name)
			given_value = getattr(config, value_name)
			self.assertEqual(expected_value, given_value, f"Expected {value_name} to be {expected_value}, but was {given_value}.")
		
		for col_name in ("logic_tiles", "io_tiles", "ramb_tiles", "ramt_tiles", "ram_data", "ipcon_tiles", "symbols", "extra_bits", "dsp_tiles"):
			expected_col = getattr(expected_config, col_name)
			given_col = getattr(config, col_name)
			
			if isinstance(expected_col, dict):
				self.check_config_dict(expected_col, given_col)
				self.check_config_dict(given_col, expected_col)
			else:
				self.assertEqual(expected_col, given_col, f"Contents of {col_name} differ from expected values:")
	
	def test_write_asc(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = self.target_cls.create_from_file(current.asc_filename)
				
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
				config = self.target_cls.create_from_file(current.asc_filename)
				
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
		
class IcecraftRawConfigTest(IcecraftStormConfigTest):
	target_cls = icecraft.IcecraftRawConfig

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

class IcecraftRepGenTest(unittest.TestCase):
	def test_creation(self):
		dut = icecraft.IcecraftRepGen()
	
	def test_call(self):
		dut = icecraft.IcecraftRepGen()
		req = RequestObject()
		req["x_min"] = 2
		req["y_min"] = 2
		req["x_max"] = 2
		req["y_max"] = 2
		req["exclude_nets"] = ["sp4", "sp12", "glb_netwk"]
		req["include_nets"] = []
		req["output_lutffs"] = [icecraft.IcecraftLUTPosition.from_coords(2, 2, 2)]
		req["joint_input_nets"] = []
		req["lone_input_nets"] = []
		req["lut_functions"] = [icecraft.LUTFunction.NAND, icecraft.LUTFunction.AND]
		
		dut(req)
	
	def parse_gene(self, raw_gene, desc=""):
		tile = icecraft.TilePosition(*raw_gene[0])
		
		bit_pos = []
		for raw_bit in raw_gene[1]:
			bit_pos.append(icecraft.IcecraftBitPosition(tile, *raw_bit))
		
		raw_alleles = raw_gene[2]
		if raw_alleles == []:
			alleles = model.AlleleAll(len(bit_pos))
		else:
			tmp_alleles = []
			for j, raw_allele in enumerate(raw_alleles):
				tmp_alleles.append(model.Allele(raw_allele, f"allele {j}"))
			
			alleles = model.AlleleList(tmp_alleles)
		
		return model.Gene(bit_pos, alleles, desc)
	
	def test_correct_rep(self):
		with open(os.path.join(TEST_DATA_DIR, "rep_creation.json"), "r") as json_file:
			raw_test_data = json.load(json_file)
		dut = icecraft.IcecraftRepGen()
		
		for raw_test in raw_test_data:
			with self.subTest():
				# read test data and create request
				req = RequestObject()
				req["x_min"] = raw_test[0]
				req["y_min"] = raw_test[1]
				req["x_max"] = raw_test[2]
				req["y_max"] = raw_test[3]
				req["exclude_nets"] = [v for v, d in raw_test[4]]
				req["include_nets"] = [v for v, d in raw_test[5]]
				output = [icecraft.IcecraftLUTPosition.from_coords(*c) for c in raw_test[6]]
				req["output_lutffs"] = list(output)
				req["joint_input_nets"] = raw_test[7]
				req["lone_input_nets"] = raw_test[8]
				req["lut_functions"] = [icecraft.LUTFunction[s] for s in raw_test[9]]
				
				genes = []
				
				for i, raw_gene in enumerate(raw_test[10]):
					genes.append(self.parse_gene(raw_gene, f"gene {i}"))
				
				const_bits = []
				for i, raw_const in enumerate(raw_test[11]):
					const_bits.append(self.parse_gene(raw_const, f"const {i}"))
				
				used_colbufctrl = []
				for raw_ctrl in raw_test[12]:
					used_colbufctrl.append(icecraft.IcecraftColBufCtrl.from_coords(*raw_ctrl))
				
				# call DUT
				rep = dut(req)
				
				# check representation
				#self.assertEqual(set(genes), set(rep.genes))
				#self.assertEqual(set(const_bits), set(constant))
				self.assertEqual(set(used_colbufctrl), set(rep.colbufctrl))
				self.assertEqual(set(output), set(rep.output))
				
		
	
	def test_parameter_user(self):
		rep_gen = icecraft.IcecraftRepGen()
		check_parameter_user(self, rep_gen)
