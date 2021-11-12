import struct

from typing import Mapping, Iterable

from domain.interfaces import Driver, TargetDevice
from domain.model import InputData
from domain.request_model import ResponseObject, RequestObject, Parameter


class EmbedDriver(Driver):
	"""Write data directly to a target device to drive a measurement
	
	The target device can differ from call to call and is passed as parameter in the request.
	"""
	
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
	
	def drive(self, request: RequestObject) -> ResponseObject:
		self.write_data(request.driver_dev, request.driver_data, request.driver_format)
		return ResponseObject()
	
	def clean_up(self, request: RequestObject) -> ResponseObject:
		return ResponseObject()

	@staticmethod
	def write_data(driver_dev: TargetDevice, data: InputData, format_str: str) -> None:
		for value in data:
			raw = struct.pack(format_str, value)
			
			driver_dev.write_bytes(raw)


class FixedEmbedDriver(EmbedDriver):
	"""Write data directly to the same target device to drive a measurement
	
	In difference to EmbedDriver, the target device the same for all calls and is passed to the constructor.
	"""
	
	def __init__(self, driver_dev: TargetDevice, driver_format: str="B") -> None:
		self._driver_dev = driver_dev
		self._driver_format = driver_format
	
	def drive(self, request: RequestObject) -> ResponseObject:
		self.write_data(self._driver_dev, request.driver_data, self._driver_format)
		return ResponseObject()
