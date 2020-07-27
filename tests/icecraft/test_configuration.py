import os
import sys
import unittest
import subprocess

sys.path.append("/usr/local/bin")
import icebox

import adapters.icecraft as icecraft

from .common import SEND_BRAM_META

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

