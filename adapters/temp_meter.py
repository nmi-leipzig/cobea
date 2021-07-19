import struct

from serial import Serial
from serial.tools.list_ports import comports
import time
from types import TracebackType
from typing import Iterable, Mapping, Optional, Type

from domain.interfaces import IdentifiableHW, Meter
from domain.model import OutputData
from domain.request_model import Parameter, RequestObject

class TempMeter(Meter, IdentifiableHW):
	"""Read Temperature from Arduino with DS18B20 sensor"""
	def __init__(self, baudrate=500000)-> None:
		self._baudrate = baudrate
		self._arduino = None
		self._arduino_sn = None
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
		arduino_ports = [p for p in ports if p.manufacturer and p.manufacturer.startswith("Arduino")]
		self._arduino_sn = arduino_ports[0].serial_number
		self._arduino = Serial(port=arduino_ports[0].device, baudrate=self._baudrate)
		self._arduino.__enter__()
		self._arduino.reset_input_buffer()
		self._arduino.reset_output_buffer()
		
		# Arduino reboots on connecting serial -> wait till reboot is done
		time.sleep(2)
		
		self._arduino.write(b"i")
		sn_data = self._arduino.read(8)
		sn_int = struct.unpack("<Q", sn)[0]
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
	
	def prepare(self, request: RequestObject) -> None:
		# write temperature request
		self._arduino.write(b"s")
	
	def measure(self, request: RequestObject) -> OutputData:
		data = self._arduino.read(2)
		raw_temp = struct.unpack("<h", data)[0]
		
		return OutputData([raw_temp/128])
