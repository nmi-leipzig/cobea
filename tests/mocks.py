from typing import Any, Union, Mapping, Iterable

from domain.interfaces import TargetDevice, TargetConfiguration, TargetManager, Meter
from domain.model import OutputData
from domain.request_model import RequestObject, Parameter


class MockTargetDevice(TargetDevice):
	def __init__(self, serial_number="9555", hardware_type="S6C7"):
		self._serial_number = serial_number
		self._hardware_type = hardware_type
	
	@property
	def serial_number(self) -> str:
		return self._serial_number
	
	@property
	def hardware_type(self) -> str:
		return self._hardware_type
	
	def configure(self, configuration: TargetConfiguration) -> None:
		pass
	
	def read_bytes(self, size: int) -> bytes:
		return bytes((7,))*size
	
	def write_bytes(self, data: bytes) -> int:
		return len(data)

class MockTargetManager(TargetManager):
	def __init__(self, size=1):
		hardware_type = "S6C7"
		self.devices = {s: MockTargetDevice(s, hardware_type) for s in range(size)}
		self.available = set(self.devices)
	
	def acquire(self, serial_number: Union[str, None]) -> TargetDevice:
		if serial_number is None:
			serial_number = self.available.pop()
		else:
			self.available.remove(serial_number)
		
		return self.devices[serial_number]
	
	def release(self, target: TargetDevice) -> None:
		assert target.serial_number in self.devices
		self.available.add(target.serial_number)

class MockMeter(Meter):
	def __init__(self, output_data: OutputData):
		self.output_data = output_data
	
	def __call__(self, target: TargetDevice, request: RequestObject) -> OutputData:
		return self.output_data
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"__call__": []}
	
