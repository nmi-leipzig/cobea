from typing import List, Optional

from domain.data_sink import DataSink
from domain.interfaces import PopulationInit
from domain.interfaces import PRNG, Representation, UniqueID
from domain.model import Chromosome
from domain.request_model import RequestObject
from domain.use_cases import RandomChromo

class RandomPop(PopulationInit):
	def __init__(self, rep: Representation, uid_gen: UniqueID, prng: PRNG, data_sink: Optional[DataSink]=None) -> None:
		self._init_uc = RandomChromo(prng, rep, uid_gen, data_sink)
	
	def init_pop(self, pop_size: int) -> List[Chromosome]:
		return [self._init_uc(RequestObject()).chromosome for _ in range(pop_size)]
