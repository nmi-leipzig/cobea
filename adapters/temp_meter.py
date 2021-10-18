import struct

from serial import Serial
from serial.tools.list_ports import comports
import time
from types import TracebackType
from typing import Iterable, Mapping, Optional, Type

from domain.interfaces import IdentifiableHW, Meter
from domain.model import OutputData
from domain.request_model import Parameter, RequestObject, ResponseObject


class TempMeterError(Exception):
	"""Raised when an error occurs in the operation of the temp meter"""
	pass

class TempMeter(Meter, IdentifiableHW):
	"""Read Temperature from Arduino with DS18B20 sensor"""
	def __init__(self, baudrate: int=500000, arduino_sn: Optional[str]=None) -> None:
		self._baudrate = baudrate
		self._arduino = None
		self._arduino_sn = arduino_sn
		self._ds18b20_sn = None
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {
			"prepare": [],
			"measure": [],
		}
	
	@property
	def serial_number(self) -> str:
		return self._arduino_sn
	
	@property
	def hardware_type(self) -> str:
		return "Arduino"
	
	@property
	def sensor_serial_number(self) -> str:
		return self._ds18b20_sn
	
	@property
	def sensor_type(self) -> str:
		return "DS18B20"
	
	def __enter__(self) -> "TempMeter":
		ports = comports()
		if self._arduino_sn is None:
			arduino_ports = [p for p in ports if p.manufacturer and p.manufacturer.startswith("Arduino")]
			try:
				self._arduino_sn = arduino_ports[0].serial_number
				device = arduino_ports[0].device
			except IndexError:
				raise TempMeterError(f"no temperature reader found found") from None
		else:
			arduino_ports = [p for p in ports if p.serial_number==self._arduino_sn]
			try:
				device = arduino_ports[0].device
			except IndexError:
				raise TempMeterError(f"no hardware with serial number {self._arduino_sn} found") from None
		
		self._arduino = Serial(port=device, baudrate=self._baudrate)
		self._arduino.__enter__()
		self._arduino.reset_input_buffer()
		self._arduino.reset_output_buffer()
		
		# Arduino reboots on connecting serial -> wait till reboot is done
		time.sleep(2)
		
		self._arduino.write(b"i")
		sn_data = self._arduino.read(8)
		sn_int = struct.unpack("<Q", sn_data)[0]
		if sn_int == 0:
			raise TempMeterError("No temperature sensor found")
		self._ds18b20_sn = f"{sn_int:016x}"
		
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		self._arduino.__exit__(exc_type, exc_value, exc_traceback)
		
		self._arduino = None
		return False
	
	def prepare(self, request: RequestObject) -> ResponseObject:
		# write temperature request
		self._arduino.write(b"s")
		return ResponseObject()
	
	def measure(self, request: RequestObject) -> OutputData:
		data = self._arduino.read(2)
		raw_temp = struct.unpack("<h", data)[0]
		
		return OutputData([raw_temp/128])
