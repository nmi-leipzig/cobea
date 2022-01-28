from typing import Iterable

from domain.interfaces import UniqueID

class SimpleUID(UniqueID):
	def __init__(self):
		self._counter = 0
	
	def get_id(self) -> int:
		uid = self._counter
		self._counter += 1
		return uid
	
	def exclude(self, ids: Iterable[int]) -> None:
		self._counter = max(self._counter, max(ids)+1)
