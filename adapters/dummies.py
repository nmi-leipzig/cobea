"""Dummies that do nothing"""

from types import TracebackType
from typing import Any, Mapping, Optional, Type

from domain.data_sink import DataSink
from domain.interfaces import Driver, Meter
from domain.model import OutputData
from domain.request_model import RequestObject

class DummyDataSink(DataSink):
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		pass
	
	def __enter__(self) -> "DummyDataSink":
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
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
