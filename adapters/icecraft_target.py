import os
import sys
import random
import struct
from io import StringIO
from typing import Union, NamedTuple, Mapping, Iterable, Sequence, Tuple, List

sys.path.append("/usr/local/bin")
import icebox

sys.path.append(
	os.path.join(
		os.path.dirname(
			os.path.dirname(
				os.path.dirname(os.path.abspath(__file__))
			)
		),
		"components",
		"board"
	)
	
)

from fpga_board import FPGABoard
from fpga_manager import FPGAManager

from domain.interfaces import TargetDevice, Meter, TargetManager
from domain.model import TargetConfiguration, InputData, OutputData
from domain.request_model import RequestObject, Parameter

HX8K_BOARD = "ICE40HX8K-B-EVN"

class TilePosition(NamedTuple):
	x: int
	y: int

class IcecraftStormConfig(TargetConfiguration):
	def __init__(self, ice_conf) -> None:
		self._ice_conf = ice_conf
	
	def to_text(self) -> str:
		# ice_config always opens a file to write asc to
		# so the asc text has to be written to a file before reading its content immediately
		# NamedTemporaryFile isn't used as it it may not be possible for ice_config to open it
		tmp_key = "".join(random.choice("0123456789abcdef") for _ in range(6))
		asc_name = f"tmp.to_text.{hex(random)}.asc"
		self.write_asc(asc_name)
		
		with open(asc_name, "r") as asc_file:
			asc_text = asc_file.read()
		
		os.remove(asc_name)
		
		return asc_text
	
	def write_asc(self, asc_name: str) -> None:
		self._ice_conf.write_file(asc_name)
	
	def write_bitstream(self, bitstream_name: str) -> None:
		asc_name = bitstream_name + ".asc"
		self.write_asc(asc_name)
		FPGABoard.pack_bitstream(asc_name, bitstream_name)
		os.remove(asc_name)
	
	def set_ram_values(self, ram_block: TilePosition, address: int, values: Iterable[int], mode: str="512x8") -> None:
		ram_strings = self._ice_conf.ram_data.setdefault(ram_block, ["0"*64]*16)
		for value in values:
			self.set_in_ram_strings(ram_strings, address, value, mode)
			address += 1
	
	def get_ram_values(self, ram_block: TilePosition, address: int, count: int=1, mode: str="512x8") -> List[int]:
		ram_strings = self._ice_conf.ram_data.setdefault(ram_block, ["0"*64]*16)
		values = []
		for tmp_address in range(address, address+count):
			value = self.get_from_ram_strings(ram_strings, tmp_address, mode)
			values.append(value)
		
		return values
	
	@classmethod
	def block_size_from_mode(cls, mode: str) -> int:
		return 4096//cls.value_length_from_mode(mode)
	
	@staticmethod
	def value_length_from_mode(mode: str) -> int:
		if (mode == 0) or (mode == "256x16"):
			return 16
		elif (mode == 1) or (mode == "512x8"):
			return 8
		elif (mode == 2) or (mode == "1024x4"):
			return 4
		elif (mode == 3) or (mode == "2048x2"):
			return 2
		else:
			raise ValueError(f"Invalid mode: {mode}")
	
	@staticmethod
	def split_address(address: int) -> Tuple[int, int, int]:
		index = address % 256
		offset = address // 256
		col_index = index % 16
		row_index = index // 16
		
		return row_index, col_index, offset
	
	@classmethod
	def get_from_ram_strings(cls, ram_strings: Sequence[str], address: int, mode: str="512x8") -> int:
		value_len = cls.value_length_from_mode(mode)
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
	def set_in_ram_strings(cls, ram_strings: Sequence[str], address: int, value: int, mode: str="512x8") -> None:
		value_len = cls.value_length_from_mode(mode)
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

class IcecraftDevice(TargetDevice):
	"""ice device"""
	
	def __init__(self, device: FPGABoard) -> None:
		self._device = device
	
	@property
	def serial_number(self) -> str:
		return self._device.serial_number
	
	@property
	def hardware_type(self) -> str:
		return HX8K_BOARD
	
	def close(self) -> None:
		self._device.close()
	
	def configure(self, configuration: TargetConfiguration) -> None:
		# just use the configuration as if it was for the correct device
		
		base_name = "gen_tmp"
		asc_name = f"{base_name}.asc"
		bitstream_name = f"{base_name}.bin"
		# write asc
		configuration.write_asc(asc_name)
		# pack asc to bin
		self._device.pack_bitstream(asc_name, bitstream_name)
		
		# flash
		self._device.flash_bitstream(bitstream_name)
		
		# remove asc and bin file
		os.remove(bitstream_name)
		os.remove(asc_name)
	
	def read_bytes(self, size: int) -> bytes:
		return self._device.uart.read(size)
	
	def write_bytes(self, data: bytes) -> int:
		return self._device.uart.write(data)

class IcecraftManager(TargetManager):
	"""simple management of icecraft devices without concurrency"""
	
	def __init__(self) -> None:
		self._in_use = set()
	
	def acquire(self, serial_number: Union[str, None] = None) -> TargetDevice:
		if serial_number is None:
			device = FPGABoard.get_suitable_board(black_list=self._in_use)
			serial_number = device.serial_number
		else:
			if serial_number in self._in_use:
				raise ValueError(f"FPGA with serial number {serial_number} already in use")
			device = FPGABoard(serial_number)
		
		self._in_use.add(serial_number)
		
		return IcecraftDevice(device)
	
	def release(self, target: TargetDevice) -> None:
		self._in_use.remove(target.serial_number)
		target.close()

class MultiIcecraftManager(TargetManager):
	"""management of ice devices in multiprocessing environments"""
	
	def __init__(self) -> None:
		self._fpga_manager = FPGAManager.create_manager()
	
	def acquire(self, serial_number: Union[str, None]) -> TargetDevice:
		raise NotImplementedError()
	
	def release(self, target: TargetDevice) -> None:
		raise NotImplementedError()

class IcecraftEmbedMeter(Meter):
	"""Measure icecraft target by embedding the input data in ram"""
	
	def __init__(self) -> None:
		self._parameters = {"__call__": [
			Parameter("configuration", TargetConfiguration),
			Parameter("ram_mode", str),
			Parameter("input_data", InputData),
			Parameter("ram_blocks", TilePosition),
			Parameter("prefix", bytes, default=None),
			Parameter("output_count", int),
			Parameter("output_format", str),
		]}
	
	@property
	def parameters(self) -> Mapping[str, Parameter]:
		return self._parameters
	
	@staticmethod
	def read_data(target: TargetDevice, count: int, format_str: str) -> list:
		size = struct.calcsize(format_str)
		data = []
		
		for _ in range(count):
			raw = target.read_bytes(size)
			value = struct.unpack(format_str, raw)[0]
			data.append(value)
		
		return data
	
	def __call__(self, target: TargetDevice, request: RequestObject) -> OutputData:
		# embed input data in ram
		config = request.configuration
		block_size = config.block_size_from_mode(request.ram_mode)
		start = 0
		block_index = 0
		while start < len(request.input_data):
			config.set_ram_values(
				#config.ram_coordinates(request.ram_blocks[block_index]),
				request.ram_blocks[block_index],
				0,
				request.input_data[start:start+block_size],
				request.ram_mode
			)
			block_index += 1
			start += block_size
		
		# flash configuration
		target.configure(config)
		
		# receive prefix
		if request.prefix is not None:
			pre = target.read_bytes(len(request.prefix))
			assert pre == request.prefix
		
		# receive output data
		data = self.read_data(target, request.output_count, request.output_format)
		return OutputData(data)

