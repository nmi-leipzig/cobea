import random

from typing import Any, Sequence, Union

from domain.interfaces import PRNG

class BuiltInPRNG(PRNG):
	def __init__(self, seed: Union[None, int, float, str, bytes, bytearray]=None) -> Any:
		self._rng = random.Random(seed)
	
	def get_state(self) -> Any:
		return self._rng.getstate()
	
	def randint(self, a: int, b: int) -> int:
		return self._rng.randint(a, b)
	
	def shuffle(self, a: Sequence) -> None:
		self._rng.shuffle(a)
