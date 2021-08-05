import os
import random
import sys
import unittest
import subprocess

from typing import Iterable, Tuple

sys.path.append("/usr/local/bin")
import icebox

import adapters.icecraft as icecraft
from adapters.icecraft import IcecraftBitPosition, RAMMode

from .common import create_bits, SEND_BRAM_META

class IcecraftStormConfigTest(unittest.TestCase):
	target_cls = icecraft.IcecraftStormConfig
	
	def setUp(self):
		self.config_meta = {s.mode: s for s in SEND_BRAM_META}
	
	def test_create_empty(self):
		config = self.target_cls.create_empty()
	
	def test_create_from_filename(self):
		config = self.target_cls.create_from_filename(self.config_meta[RAMMode.RAM_256x16].asc_filename)
	
	def test_get_ram_values(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = self.target_cls.create_from_filename(current.asc_filename)
				
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
				config = self.target_cls.create_from_filename(current.asc_filename)
				
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
				config = self.target_cls.create_from_filename(current.asc_filename)
				
				expected_ic = icebox.iceconfig()
				expected_ic.read_file(current.asc_filename)
				
				tmp_filename = f"tmp.test_write_asc.{mode.name}.asc"
				config.write_asc(tmp_filename)
				
				ic = icebox.iceconfig()
				ic.read_file(tmp_filename)
				
				os.remove(tmp_filename)
				
				self.check_configuration(expected_ic, ic)
	
	def test_write_bitstream(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = self.target_cls.create_from_filename(current.asc_filename)
				
				expected_ic = icebox.iceconfig()
				expected_ic.read_file(current.asc_filename)
				
				tmp_bin = f"tmp.test_write_bitstream.{mode.name}.bin"
				tmp_asc = f"tmp.test_write_bitstream.{mode.name}.asc"
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
	
	def test_get_bitstream(self):
		for mode, current in self.config_meta.items():
			with self.subTest(mode=mode):
				config = self.target_cls.create_from_filename(current.asc_filename)
				
				expected_ic = icebox.iceconfig()
				expected_ic.read_file(current.asc_filename)
				
				tmp_bin = f"tmp.test_get_bitstream.{mode.name}.bin"
				tmp_asc = f"tmp.test_get_bitstream.{mode.name}.asc"
				
				res = config.get_bitstream()
				
				with open(tmp_bin, "wb") as bin_file:
					bin_file.write(res)
				
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
		
	
	def test_get_bit(self):
		with self.subTest(desc="Empty"):
			dut = self.target_cls.create_empty()
			
			for bit in [IcecraftBitPosition(16, 17, 4, 5), IcecraftBitPosition(0, 1, 14, 17)]:
				res = dut.get_bit(bit)
				self.assertFalse(res)
		
		for current in self.config_meta.values():
			with self.subTest(asc=current.asc_filename):
				dut = self.target_cls.create_from_filename(current.asc_filename)
				for tile, group_map in current.known_bits.items():
					# append 0 in max to avoid "TypeError: 'int' object is not iterable" if list is empty
					index_limit = max(18, *[max(g)+1 for g in group_map.values()], 0)
					group_limit = max(16, *group_map, 0)
					for grp in range(group_limit):
						for idx in range(index_limit):
							bit = IcecraftBitPosition(tile.x, tile.y, grp, idx)
							exp = current.bit_value(bit)
							
							res = dut.get_bit(bit)
							
							self.assertEqual(exp, res)
	
	def check_initial_bit_values(self, bram_meta, bits, dut):
		exp = tuple(bram_meta.bit_value(b) for b in bits)
		res = dut.get_multi_bits(bits)
		self.assertEqual(exp, res)
		
		# check sorted
		sort = sorted(zip(bits, exp))
		sort_bits = tuple(b for b, _ in sort)
		sort_exp = tuple(e for _, e in sort)
		sort_res = dut.get_multi_bits(sort_bits)
		self.assertEqual(sort_exp, sort_res)
	
	def test_get_multi_bits(self):
		with self.subTest(desc="Empty"):
			dut = self.target_cls.create_empty()
			
			for bits in [(IcecraftBitPosition(16, 17, 4, 5), ), create_bits(0, 1, [(2, 3), (14, 17), (0, 0)])]:
				res = dut.get_multi_bits(bits)
				self.assertEqual((False, )*len(bits), res)
		
		for current in self.config_meta.values():
			with self.subTest(asc=current.asc_filename):
				dut = self.target_cls.create_from_filename(current.asc_filename)
				limits = {t:[
					max(16, *gm, 0),
					max(18, *[max(g)+1 for g in gm.values()], 0)
				] for t, gm in current.known_bits.items()}
				
				for bit_count in [1, 2, 5, 8]:
					for rounds in range(5):
						# from single tile
						tile = random.choice(list(limits.keys()))
						bits = create_bits(
							tile.x,
							tile.y,
							[(
								random.randint(0, limits[tile][0]-1),
								random.randint(0, limits[tile][1]-1),
							) for i in range(bit_count)]
						)
						self.check_initial_bit_values(current, bits, dut)
						
						# from multiple tiles
						bits = tuple(IcecraftBitPosition(
							t.x,
							t.y,
							random.randint(0, limits[t][0]-1),
							random.randint(0, limits[t][1]-1),
						) for t in random.choices(list(limits.keys()), k=bit_count))
						self.check_initial_bit_values(current, bits, dut)
	
	def test_set_bit(self):
		set_seq = (
			(IcecraftBitPosition(16, 17, 4, 5), False),
			(IcecraftBitPosition(16, 17, 4, 5), True),
			(IcecraftBitPosition(16, 17, 4, 5), False),
		)
		dut = self.target_cls.create_empty()
		
		for bit, value in set_seq:
			dut.set_bit(bit, value)
			
			res = dut.get_bit(bit)
			self.assertEqual(value, res)
	
	def test_set_multi_bits(self):
		bits_1 = create_bits(4, 5, [(9, 6)])
		bits_2 = create_bits(16, 17, [(12, 45), (0, 0)])
		set_seq = (
			(bits_1, (False, )),
			(bits_1, (True, )),
			(bits_1, (False, )),
			(bits_2, (True, )*2),
			(bits_2, (False, )*2),
			(bits_2, (False, True)),
		)
		
		dut = self.target_cls.create_empty()
		
		for bits, values in set_seq:
			dut.set_multi_bits(bits, values)
			
			res = dut.get_multi_bits(bits)
			self.assertEqual(values, res)
			
			# values should not depend on order
			res = dut.get_multi_bits(tuple(reversed(bits)))
			self.assertEqual(tuple(reversed(values)), res)
	
	@staticmethod
	def extract_ones(asc_filename: str, coordinates: Iterable[Tuple[int, int]]) -> list:
		ic = icebox.iceconfig()
		ic.read_file(asc_filename)
		ones = []
		for x, y in coordinates:
			tile_data = ic.tile(x, y)
			tile_ones = []
			ones.append([x, y, tile_ones])
			for group, group_data in enumerate(tile_data):
				group_ones = [i for i, v in enumerate(group_data) if v=="1"]
				if len(group_ones):
					tile_ones.append([group, group_ones])
		
		return ones

class IcecraftRawConfigTest(IcecraftStormConfigTest):
	target_cls = icecraft.IcecraftRawConfig

