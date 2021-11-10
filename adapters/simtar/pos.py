from typing import Tuple

from domain.base_structures import BitPos


class SimtarBitPos(int, BitPos):
	def to_ints(self) -> Tuple[int, ...]:
		return (self, )
