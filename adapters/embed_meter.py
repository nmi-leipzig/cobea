import struct
from typing import Mapping, Iterable

from domain.interfaces import TargetDevice, Meter
from domain.model import OutputData
from domain.request_model import Parameter, RequestObject, ResponseObject


class EmbedMeter(Meter):
	"""Read measurement data directly from a target device.
	
	The target device can differ from call to call and is passed as parameter in the request.
	"""
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {
			"prepare": [],
			"measure": [
				Parameter("prefix", bytes, default=bytes()),
				Parameter("output_count", int),
				Parameter("output_format", str),
				Parameter("meter_dev", TargetDevice),
			]
		}
	
	def prepare(self, request: RequestObject) -> ResponseObject:
		return ResponseObject()
	
	def measure(self, request: RequestObject) -> ResponseObject:
		return self.read_all(request.meter_dev, request.output_count, request.output_format, request.prefix)
	
	@classmethod
	def read_all(cls, meter_dev: TargetDevice, out_count: int, out_format: str, prefix: bytes):
		# receive prefix
		cls.read_prefix(meter_dev, prefix)
		
		# receive output data
		data = cls.read_data(meter_dev, out_count, out_format)
		return ResponseObject(measurement=OutputData(data))
	
	@staticmethod
	def read_prefix(meter_dev: TargetDevice, prefix: bytes) -> None:
		if len(prefix):
			pre = meter_dev.read_bytes(len(prefix))
			assert pre == prefix
	
	@staticmethod
	def read_data(meter_dev: TargetDevice, count: int, format_str: str) -> list:
		size = struct.calcsize(format_str)
		data = []
		
		for _ in range(count):
			raw = meter_dev.read_bytes(size)
			if len(raw) < size:
				raise IOError()
			
			value = struct.unpack(format_str, raw)[0]
			data.append(value)
		
		return data
	

class FixedEmbedMeter(EmbedMeter):
	"""Read measurement data directly from a constant target device.
	
	In difference to EmbedMeter, the target device the same for all calls and is passed to the constructor.
	"""
	
	def __init__(self, meter_dev: TargetDevice, out_count: int, out_format: str="B", prefix: bytes=bytes()) -> None:
		self._meter_dev = meter_dev
		self._out_count = out_count
		self._out_format = out_format
		self._prefix = prefix
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"prepare": [], "measure": []}
	
	def measure(self, request: RequestObject) -> ResponseObject:
		return self.read_all(self._meter_dev, self._out_count, self._out_format, self._prefix)
	
