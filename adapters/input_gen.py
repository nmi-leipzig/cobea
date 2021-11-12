from typing import Iterable, Mapping

from domain.interfaces import InputGen
from domain.request_model import Parameter, ResponseObject, RequestObject
from domain.model import InputData


class SeqGen(InputGen):
	"""Input generator that cycles a list of values"""
	
	def __init__(self, seq: Iterable[InputData]) -> None:
		self._seq = list(seq)
		self._index = 0
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"generate": []}
	
	def generate(self, request: RequestObject) -> ResponseObject:
		val = self._seq[self._index]
		self._index = (self._index + 1) % len(self._seq)
		return ResponseObject(driver_data=val)
