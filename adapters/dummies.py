"""Dummies that do nothing"""

from domain.interfaces import Driver, Meter
from domain.model import OutputData
from domain.request_model import RequestObject

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
