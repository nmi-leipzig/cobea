import struct
import time

from serial import Serial
from serial.tools.list_ports import comports
from types import TracebackType
from typing import Iterable, Mapping, Optional, Type

from domain.interfaces import Driver, IdentifiableHW, InputData, Meter, OutputData
from domain.request_model import Parameter, ResponseObject, RequestObject

class MCUDrvMtr(Driver, Meter, IdentifiableHW):
	def __init__(self, serial_number: str, return_count: int, return_format: str="B", init_size: int=0,
		baudrate: int=500000) -> None:
		
		self._return_count = return_count
		self._return_format = return_format
		self._init_size = init_size
		self._baudrate = baudrate
		self._arduino_sn = serial_number
		self._arduino = None
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {
			"drive": [
				Parameter("driver_data", InputData),
				Parameter("driver_format", str, default="B"),
			],
			"clean_up": [],
			"prepare": [],
			"measure": [],
		}
	
	@property
	def serial_number(self) -> str:
		return self._arduino_sn
	
	@property
	def hardware_type(self) -> str:
		return "Arduino"
	
	def __enter__(self) -> "MCUDrvMtr":
		ports = comports()
		arduino_ports = [p for p in ports if p.serial_number==self._arduino_sn]
		device = arduino_ports[0].device
		
		self._arduino = Serial(port=device, baudrate=self._baudrate)
		self._arduino.__enter__()
		self._arduino.reset_input_buffer()
		self._arduino.reset_output_buffer()
		
		# Arduino reboots on connecting serial -> wait till reboot is done
		time.sleep(2)
		
		self._arduino.read(self._init_size)
		
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
		pass
	
	def drive(self, request: RequestObject) -> ResponseObject:
		for value in request.driver_data:
			raw = struct.pack(request.driver_format, value)
			
			self._arduino.write(raw)
		return ResponseObject()
	
	def measure(self, request: RequestObject) -> OutputData:
		res = []
		chunk_size = struct.calcsize(self._return_format)
		for _ in range(self._return_count):
			raw_data = self._arduino.read(chunk_size)
			res.extend(struct.unpack(self._return_format, raw_data))
		
		return OutputData(res)
	
	def clean_up(self, request: RequestObject) -> ResponseObject:
		return ResponseObject()
