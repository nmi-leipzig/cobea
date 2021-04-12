import struct

from typing import Mapping, Iterable

from domain.interfaces import Driver, TargetDevice
from domain.model import InputData
from domain.request_model import RequestObject, Parameter

class EmbedDriver(Driver):
	"""Write data directly to a target device to drive a measurement"""
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {
			"drive": [
				Parameter("driver_data", InputData),
				Parameter("driver_format", str, default="B"),
				Parameter("driver_dev", TargetDevice),
			],
			"clean_up": [],
		}
	
	def drive(self, request: RequestObject) -> None:
		self.write_data(request.driver_dev, request.driver_data, request.driver_format)
	
	def clean_up(self, request: RequestObject) -> None:
		pass
	
	@staticmethod
	def write_data(driver_dev: TargetDevice, data: InputData, format_str: str) -> None:
		for value in data:
			raw = struct.pack(format_str, value)
			
			driver_dev.write_bytes(raw)
