import random

from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from deap import tools
from deap import creator
from deap import base
from deap import algorithms

from domain.interfaces import EvoAlgo, InputData, PRNG, Representation, UniqueID
from domain.model import Chromosome
from domain.request_model import RequestObject
from domain.use_cases import GenChromo, Measure, RandomChromo

creator.create("SimpleFit", base.Fitness, weights=(1.0, ))

@dataclass
class Individual:
	chromo: Chromosome
	fitness: creator.SimpleFit=field(default_factory=creator.SimpleFit, init=False)
	
	def __len__(self) -> int:
		return len(self.chromo.allele_indices)
	
	def __getitem__(self, index: int) -> int:
		return self.chromo.allele_indices[index]
	
	@classmethod
	def wrap_alteration(cls, func, in_count, chromo_gen: GenChromo) -> Callable[..., Tuple["Individual", ...]]:
		
		def wrapped_func(*args, **kwargs) -> Tuple["Individual", ...]:
			res = func(*[list(args[i].chromo.allele_indices) for i in range(in_count)], *args[in_count:], **kwargs)
			
			chromos = []
			req = RequestObject()
			for allele_indices in res:
				req["allele_indices"] = allele_indices
				chromos.append(chromo_gen(req))
			return tuple(Individual(c) for c in chromos)
		
		return wrapped_func

class SimpleEA(EvoAlgo):
	def __init__(self, rep: Representation, measure_uc: Measure, uid_gen: UniqueID, prng: PRNG) -> None:
		self._rep = rep
		self._measure_uc = measure_uc
		self._init_uc = RandomChromo(prng, rep, uid_gen)
		self._chromo_gen = GenChromo(uid_gen)
	
	def run(self) -> None:
		# create toolbox
		toolbox = self.create_toolbox()
		# create population
		pop = self._init_pop(10)
		# run
		algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.1, ngen=5)
		
	
	def _init_pop(self, count) -> List[Individual]:
		return [Individual(self._init_uc(RequestObject())) for _ in range(count)]
	
	def _evaluate(self, i) -> Tuple[int]:
		driver_req = RequestObject(
			driver_data = InputData([0]),
		)
		data = self._measure_uc(driver_req)
		return (sum(i)+sum(data), )
	
	def create_toolbox(self) -> base.Toolbox:
		#creator.create("TestFit", base.Fitness, weights=(1.0,))
		#creator.create("Chromo", list, fitness=creator.TestFit)
		
		toolbox = base.Toolbox()
		
		#toolbox.register("rand_bool", random.randint, 0, 1)
		#toolbox.register("init_individual", tools.initRepeat, creator.Chromo, toolbox.rand_bool, 20)
		#toolbox.register("init_pop", tools.initRepeat, list, toolbox.init_individual)
		
		toolbox.register("mate", Individual.wrap_alteration(tools.cxTwoPoint, 2, self._chromo_gen))
		toolbox.register(
			"mutate",
			Individual.wrap_alteration(tools.mutUniformInt, 1, self._chromo_gen),
			low=0, up=[len(g.alleles)-1 for g in self._rep.iter_genes()], indpb=0.05)
		toolbox.register("select", tools.selTournament, tournsize=3)
		toolbox.register("evaluate", self._evaluate)
		
		return toolbox
