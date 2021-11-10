from domain.base_structures import BitPos
from domain.interfaces import TargetConfiguration

class SimtarConfig(TargetConfiguration):
	BIT_COUNT = 17
	
	def __init__(self, data=None) -> None:
		if data is None:
			self._bits = [None]*self.BIT_COUNT
		else:
			self._bits = [data[i] for i in range(self.BIT_COUNT)]
	
	def set_bit(self, bit: BitPos, value: bool) -> None:
		self._bits[bit] = value
	
	def get_bit(self, bit: BitPos) -> bool:
		return self._bits[bit]
	
	def to_text(self) -> str:
		return "".join(["1" if b else "0" for b in self._bits])
	
	@classmethod
	def from_text(cls, text: str) -> "SimtarConfig":
		data = [d=="1" for d in text]
		return SimtarConfig(data)
