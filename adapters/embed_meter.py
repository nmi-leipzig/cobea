import struct
from typing import Mapping, Iterable

from domain.interfaces import TargetDevice, Meter
from domain.model import OutputData
from domain.request_model import Parameter, RequestObject

class EmbedMeter(Meter):
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
	
	def prepare(self, request: RequestObject) -> None:
		pass
	
	def measure(self, request: RequestObject) -> OutputData:
		# receive prefix
		if len(request.prefix):
			pre = request.meter_dev.read_bytes(len(request.prefix))
			assert pre == request.prefix
		
		# receive output data
		data = self.read_data(request.meter_dev, request.output_count, request.output_format)
		return OutputData(data)
	
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
	