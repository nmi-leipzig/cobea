from typing import Iterable, Mapping

from domain.interfaces import InputGen, PRNG
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


class RandIntGen(InputGen):
	"""Input generator that creates a random integer"""
	
	def __init__(self, prng: PRNG, min_int: int, max_int: int) -> None:
		self._prng = prng
		self._min_int = min_int
		self._max_int = max_int
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"generate": []}
	
	def generate(self, request: RequestObject) -> ResponseObject:
		val = self._prng.randint(self._min_int, self._max_int)
		return ResponseObject(driver_data=val)
