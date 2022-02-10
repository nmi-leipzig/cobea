from typing import Iterable, List, Optional

from domain.data_sink import DataSink
from domain.interfaces import PopulationInit
from domain.interfaces import PRNG, Representation, UniqueID
from domain.model import Chromosome
from domain.request_model import RequestObject
from domain.use_cases import RandomChromo

class RandomPop(PopulationInit):
	"""Initialize population randomly"""
	def __init__(self, rep: Representation, uid_gen: UniqueID, prng: PRNG, data_sink: Optional[DataSink]=None) -> None:
		self._init_uc = RandomChromo(prng, rep, uid_gen, data_sink)
	
	def init_pop(self, pop_size: int) -> List[Chromosome]:
		return [self._init_uc(RequestObject()).chromosome for _ in range(pop_size)]

class GivenPop(PopulationInit):
	"""Initialize population with predefined population"""
	def __init__(self, given_pop: Iterable[Chromosome]) -> None:
		self._given = list(given_pop)	
	
	def init_pop(self, pop_size: int) -> List[Chromosome]:
		if pop_size != len(self._given):
			raise ValueError(f"requested {pop_size}, but given are {len(self._given)}")
		return list(self._given)
