"""Basic strutructures that even entitites depend on."""

from abc import ABC, abstractmethod
from typing import Tuple

class BitPos(ABC):
	"""Position of a bit."""
	@abstractmethod
	def to_ints(self) -> Tuple[int, ...]:
		raise NotImplementedError()
