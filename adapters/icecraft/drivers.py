from typing import Mapping

from adapters.icecraft.configuration import block_size_from_mode
from domain.interfaces import TargetConfiguration, TargetDevice, Driver
from domain.model import InputData, OutputData
from domain.request_model import ResponseObject, RequestObject, Parameter

from .misc import IcecraftPosition, RAMMode


class IcecraftRAMDriver(Driver):
	"""Embed driver data in BRAM of icecraft device and configure it"""
	
	def __init__(self) -> None:
		self._parameters = {"drive": [
			Parameter("configuration", TargetConfiguration),
			Parameter("ram_mode", RAMMode),
			Parameter("input_data", InputData),
			Parameter("ram_blocks", IcecraftPosition, multiple=True),
			Parameter("driver_dev", TargetDevice),
		], "clean_up": []}
	
	@property
	def parameters(self) -> Mapping[str, Parameter]:
		return self._parameters
	
	def drive(self, request: RequestObject) -> ResponseObject:
		device = request.driver_dev
		# embed input data in ram
		config = request.configuration
		block_size = block_size_from_mode(request.ram_mode)
		start = 0
		block_index = 0
		while start < len(request.input_data):
			config.set_ram_values(
				request.ram_blocks[block_index],
				0,
				request.input_data[start:start+block_size],
				request.ram_mode
			)
			block_index += 1
			start += block_size
		
		# flash configuration
		device.configure(config)

		return ResponseObject()

	def clean_up(self, request: RequestObject) -> ResponseObject:
		return ResponseObject()
