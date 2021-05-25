"""Dummies that do nothing"""

from typing import Any

from domain.data_sink import DataSink, DoneReq
from domain.interfaces import Driver, Meter
from domain.model import OutputData
from domain.request_model import RequestObject

class DummyDataSink(DataSink):
	def write_metadata(self, name: str, data: Any, data_type: type, multiple=False) -> None:
		pass
	
	def write_request(self, req_data: DoneReq) -> None:
		pass

class DummyDriver(Driver):
	@property
	def parameters(self):
		return {"drive": [], "clean_up": []}
	
	def drive(self, request: RequestObject) -> None:
		pass
	
	def clean_up(self, request: RequestObject) -> None:
		pass

class DummyMeter(Meter):
	@property
	def parameters(self):
		return {"prepare": [], "measure": []}
	
	def prepare(self, request: RequestObject) -> None:
		pass
	
	def measure(self, request: RequestObject) -> OutputData:
		return OutputData()
