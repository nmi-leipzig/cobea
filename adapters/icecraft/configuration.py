import os
import sys
from io import StringIO, BytesIO
from typing import Iterable, List, Tuple, Sequence

sys.path.append("/usr/local/bin")
import icebox

from .ice_board import BRAMMode, Configuration, FPGABoard, TilePosition, Bit

from domain.base_structures import BitPos
from domain.interfaces import TargetConfiguration

from .misc import RAMMode, IcecraftPosition

def value_length_from_mode(mode: RAMMode) -> int:
	return 16 // (1 << mode)

def block_size_from_mode(mode: RAMMode) -> int:
	return 4096//value_length_from_mode(mode)

class IcecraftRawConfig(TargetConfiguration):
	mode_map = {
		RAMMode.RAM_256x16: BRAMMode.BRAM_256x16,
		RAMMode.RAM_512x8: BRAMMode.BRAM_512x8,
		RAMMode.RAM_1024x4: BRAMMode.BRAM_1024x4,
		RAMMode.RAM_2048x2: BRAMMode.BRAM_2048x2,
	}
	
	def __init__(self, raw_config: Configuration) -> None:
		self._raw_config = raw_config
	
	def to_text(self) -> str:
		with StringIO() as sio:
			self._raw_config.write_asc(sio)
			return sio.getvalue()
	
	def set_bit(self, bit: BitPos, value: bool) -> None:
		self._raw_config.set_bit(bit.x, bit.y, bit.group, bit.index, value)
	
	def get_bit(self, bit: BitPos) -> bool:
		return self._raw_config.get_bit(bit.x, bit.y, bit.group, bit.index)
	
	def write_asc(self, asc_name: str) -> None:
		with open(asc_name, "w") as asc_file:
			self._raw_config.write_asc(asc_file)
	
	def write_bitstream(self, bitstream_name: str) -> None:
		with open(bitstream_name, "wb") as bin_file:
			self._raw_config.write_bin(bin_file)
	
	def get_bitstream(self) -> bytes:
		with BytesIO() as bin_file:
			self._raw_config.write_bin(bin_file)
			bitstream = bin_file.getvalue()
		return bitstream
	
	def set_ram_values(self, ram_block: IcecraftPosition, address: int, values: Iterable[int], mode: RAMMode=RAMMode.RAM_512x8) -> None:
		raw_mode = self.mode_map[mode]
		self._raw_config.set_bram_values(TilePosition(ram_block.x, ram_block.y), values, address, raw_mode)
	
	def get_ram_values(self, ram_block: IcecraftPosition, address: int, count: int=1, mode: RAMMode=RAMMode.RAM_512x8) -> List[int]:
		raw_mode = self.mode_map[mode]
		return self._raw_config.get_bram_values(TilePosition(ram_block.x, ram_block.y), address, count, raw_mode)
	
	@classmethod
	def create_from_file(cls, asc_filename: str) -> "IcecraftRawConfig":
		raw_config = Configuration.create_from_asc(asc_filename)
		return cls(raw_config)
	
	@classmethod
	def create_empty(cls) -> "IcecraftRawConfig":
		raw_config = Configuration.create_blank("8k")
		
		return cls(raw_config)

class IcecraftStormConfig(TargetConfiguration):
	def __init__(self, ice_conf) -> None:
		self._ice_conf = ice_conf
	
	def to_text(self) -> str:
		# ice_config always opens a file to write asc to
		# so the asc text has to be written to a file before reading its content immediately
		# NamedTemporaryFile isn't used as it it may not be possible for ice_config to open it
		tmp_key = "".join(random.choice("0123456789abcdef") for _ in range(6))
		asc_name = f"tmp.to_text.{random.randrange(16**6):06x}.asc"
		self.write_asc(asc_name)
		
		with open(asc_name, "r") as asc_file:
			asc_text = asc_file.read()
		
		os.remove(asc_name)
		
		return asc_text
	
	def set_bit(self, bit: BitPos, value: bool) -> None:
		tile_bits = self._ice_conf.tile(bit.x, bit.y)
		grp_str = tile_bits[bit.group]
		
		if value:
			str_value = '1'
		else:
			str_value = '0'
		
		new_grp_str = grp_str[0:bit.index] + str_value + grp_str[bit.index+1:]
		
		tile_bits[bit.group] = new_grp_str
	
	def get_bit(self, bit: BitPos) -> bool:
		tile_bits = self._ice_conf.tile(bit.x, bit.y)
		return tile_bits[bit.group][bit.index] == '1'
	
	def write_asc(self, asc_name: str) -> None:
		self._ice_conf.write_file(asc_name)
	
	def write_bitstream(self, bitstream_name: str) -> None:
		asc_name = bitstream_name + ".asc"
		self.write_asc(asc_name)
		FPGABoard.pack_bitstream(asc_name, bitstream_name)
		os.remove(asc_name)
	
	def get_bitstream(self) -> bytes:
		bin_filename = "tmp.get_bitstream.bin"
		
		self.write_bitstream(bin_filename)
		
		with open(bin_filename, "rb") as bin_file:
			bitstream = bin_file.read()
		
		os.remove(bin_filename)
		
		return bitstream
	
	def set_ram_values(self, ram_block: IcecraftPosition, address: int, values: Iterable[int], mode: RAMMode=RAMMode.RAM_512x8) -> None:
		ram_strings = self._ice_conf.ram_data.setdefault((ram_block.x, ram_block.y), ["0"*64]*16)
		for value in values:
			self.set_in_ram_strings(ram_strings, address, value, mode)
			address += 1
	
	def get_ram_values(self, ram_block: IcecraftPosition, address: int, count: int=1, mode: RAMMode=RAMMode.RAM_512x8) -> List[int]:
		ram_strings = self._ice_conf.ram_data.setdefault((ram_block.x, ram_block.y), ["0"*64]*16)
		values = []
		for tmp_address in range(address, address+count):
			value = self.get_from_ram_strings(ram_strings, tmp_address, mode)
			values.append(value)
		
		return values
	
	@staticmethod
	def split_address(address: int) -> Tuple[int, int, int]:
		index = address % 256
		offset = address // 256
		col_index = index % 16
		row_index = index // 16
		
		return row_index, col_index, offset
	
	@classmethod
	def get_from_ram_strings(cls, ram_strings: Sequence[str], address: int, mode: RAMMode=RAMMode.RAM_512x8) -> int:
		value_len = value_length_from_mode(mode)
		row_index, col_index, offset = cls.split_address(address)
		
		l = len(ram_strings[row_index])
		
		str_word = ram_strings[row_index][l-4*(col_index+1):l-4*col_index]
		int_word = int(str_word, 16)
		
		if value_len == 16:
			return int_word
		
		step = 16 // value_len
		int_word >>= offset
		mask = 1
		value = 0
		for i in range(value_len):
			value |= mask & int_word
			mask <<= 1
			int_word >>= step - 1
		
		return value
	
	@classmethod
	def set_in_ram_strings(cls, ram_strings: Sequence[str], address: int, value: int, mode: RAMMode=RAMMode.RAM_512x8) -> None:
		value_len = value_length_from_mode(mode)
		row_index, col_index, offset = cls.split_address(address)
		
		assert value >= 0, "Value has to be non negative."
		assert value < pow(2, value_len), f"Value {value} too large for bit length {value_len}."
		
		str_row = ram_strings[row_index]
		
		l = len(ram_strings[row_index])
		
		if value_len == 16:
			new_int_word = value
		else:
			str_word = ram_strings[row_index][l-4*(col_index+1):l-4*col_index]
			int_word = int(str_word, 16)
			
			step = 16 // value_len
			new_int_word = int_word
			mask = 1 << offset
			value <<= offset
			for i in range(value_len):
				new_int_word = (new_int_word & (0xFFFF ^ mask)) | (mask & value)
				
				mask <<= step
				value <<= step - 1
		
		new_str_word = "{:04x}".format(new_int_word)
		assert len(new_str_word) == 4, f"Word in hex has to have 4 characters, not {len(new_str_word)}."
		ram_strings[row_index] = str_row[:l-4*(col_index+1)] + new_str_word + str_row[l-4*col_index:]
	
	@classmethod
	def create_from_file(cls, asc_filename: str) -> "IcecraftStormConfig":
		ic = icebox.iceconfig()
		ic.read_file(asc_filename)
		
		return cls(ic)
	
	@classmethod
	def create_empty(cls) -> "IcecraftStormConfig":
		ic = icebox.iceconfig()
		ic.setup_empty_8k()
		
		return cls(ic)


