import struct
from typing import Mapping

from domain.interfaces import TargetConfiguration, TargetDevice, Meter
from domain.model import InputData, OutputData
from domain.request_model import RequestObject, Parameter

from .misc import IcecraftPosition

class IcecraftEmbedMeter(Meter):
	"""Measure icecraft target by embedding the input data in ram"""
	
	def __init__(self) -> None:
		self._parameters = {"__call__": [
			Parameter("configuration", TargetConfiguration),
			Parameter("ram_mode", str),
			Parameter("input_data", InputData),
			Parameter("ram_blocks", IcecraftPosition, multiple=True),
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
	
	def measure(self, target: TargetDevice, request: RequestObject) -> OutputData:
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


