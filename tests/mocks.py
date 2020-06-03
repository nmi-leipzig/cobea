from typing import Any, Union

import domain.interfaces as interfaces
import domain.model as model
from domain.request_model import RequestObject


class MockTargetDevice(interfaces.TargetDevice):
	def __init__(self, serial_number="9555", hardware_type="S6C7"):
		self._serial_number = serial_number
		self._hardware_type = hardware_type
	
	@property
	def serial_number(self) -> str:
		return self._serial_number
	
	@property
	def hardware_type(self) -> str:
		return self._hardware_type
	
	def configure(self, configuration: model.TargetConfiguration) -> None:
		pass
	
	def read_bytes(self, size: int) -> bytes:
		return bytes((7,))*size
	
	def write_bytes(self, data: bytes) -> int:
		return len(data)

class MockTargetManager(interfaces.TargetManager):
	def __init__(self, size=1):
		hardware_type = "S6C7"
		self.devices = {s: MockTargetDevice(s, hardware_type) for s in range(size)}
		self.available = set(self.devices)
	
	def acquire(self, serial_number: Union[str, None]) -> interfaces.TargetDevice:
		if serial_number is None:
			serial_number = self.available.pop()
		else:
			self.available.remove(serial_number)
		
		return self.devices[serial_number]
	
	def release(self, target: interfaces.TargetDevice) -> None:
		assert target.serial_number in self.devices
		self.available.add(target.serial_number)

class MockMeter(interfaces.Meter):
	def __init__(self, output_data: model.OutputData):
		self.output_data = output_data
	
	def __call__(self, target: interfaces.TargetDevice, request: RequestObject) -> model.OutputData:
		return self.output_data
