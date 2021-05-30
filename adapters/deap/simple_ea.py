import random

from dataclasses import dataclass, field
from typing import Callable, List, Tuple

import numpy as np

from deap import tools
from deap import creator
from deap import base
from deap import algorithms

from applications.discern_frequency.s_t_comb import lexicographic_combinations
from domain.data_sink import DataSink, DataSinkUser
from domain.interfaces import EvoAlgo, InputData, PRNG, Representation, TargetConfiguration, TargetDevice, UniqueID
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
	def wrap_alteration(cls, func, in_count, chromo_gen: GenChromo, data_sink: DataSink) -> Callable[..., Tuple["Individual", ...]]:
		
		def wrapped_func(*args, **kwargs) -> Tuple["Individual", ...]:
			res = func(*[list(args[i].chromo.allele_indices) for i in range(in_count)], *args[in_count:], **kwargs)
			
			chromos = []
			req = RequestObject()
			for allele_indices in res:
				req["allele_indices"] = allele_indices
				chromos.append(chromo_gen(req))
			data_sink.write(f"{cls.__name__}.wrap.{func.__name__}", {
				"in": [a.chromo.identifier for a in args[:in_count]],
				"out": [c.identifier for c in chromos]
			})
			return tuple(Individual(c) for c in chromos)
		
		return wrapped_func

class SimpleEA(EvoAlgo, DataSinkUser):
	def __init__(self, rep: Representation, measure_uc: Measure, uid_gen: UniqueID, prng: PRNG, habitat: TargetConfiguration, target: TargetDevice, data_sink: DataSink) -> None:
		self._rep = rep
		self._measure_uc = measure_uc
		self._init_uc = RandomChromo(prng, rep, uid_gen, data_sink)
		self._chromo_gen = GenChromo(uid_gen, data_sink)
		rep.prepare_config(habitat)
		self._habitat = habitat
		self._target = target
		self._data_sink = data_sink
		
		self._driver_table = lexicographic_combinations(5, 5)
	
	@property
	def data_sink(self) -> DataSink:
		return self._data_sink
	
	def run(self) -> None:
		# create toolbox
		toolbox = self.create_toolbox()
		# create population
		pop = self._init_pop(50)
		# run
		algorithms.eaSimple(pop, toolbox, cxpb=0.7, mutpb=0.001756, ngen=600)
		
	
	def _init_pop(self, count) -> List[Individual]:
		return [Individual(self._init_uc(RequestObject())) for _ in range(count)]
	
	def _evaluate(self, indi: Individual) -> Tuple[int]:
		comb_index = random.choice(range(len(self._driver_table)))
		comb_seq = self._driver_table[comb_index]
		
		eval_req = RequestObject(
			driver_data = InputData([comb_index]),
			#retry = 0,
			measure_timeout = None,
		)
		
		self._rep.decode(self._habitat, indi.chromo)
		carry_enable_state = []
		for bit in self._rep.iter_carry_bits():
			carry_enable_state.append(self._habitat.get_bit(bit))
		self._target.configure(self._habitat)
		data = self._measure_uc(eval_req)
		h_div = (12*0.5) / len(data)
		
		data_parts = [data[i*len(data)//12: (i+1)*len(data)//12] for i in range(12)]
		
		# skip first second
		data_parts = data_parts[2:]
		
		print(f"seq {comb_index} {comb_seq:010b}")
		fast_sum = 0
		slow_sum = 0
		for i, data_part in enumerate(data_parts):
			
			nd = np.array(data_part)
			auc = np.trapz(nd, dx=h_div)
			#print(f"{i}: {auc}")
			if ((comb_seq >> i) & 1):
				fast_sum += auc
			else:
				slow_sum += auc
			#spec = np.fft.rfft(nd)
			
			#m_freq = np.argmax(np.absolute(spec[1:]))+1
			#print(f"{np.fft.rfftfreq(len(nd))[m_freq]}: {spec[m_freq]} [{abs(spec[m_freq])}")
		
		print(f"fast_sum = {fast_sum}, slow_sum = {slow_sum}")
		fit = abs(slow_sum/30730.746 - fast_sum/30527.973)/10
		print(f"fit = {fit}")
		self.write_to_sink("fitness", {
			"fit": fit,
			"fast_sum": fast_sum,
			"slow_sum": slow_sum,
			"chromo_index": indi.chromo.identifier,
			"carry_enable": carry_enable_state,
		})
		return (fit, )
	
	def create_toolbox(self) -> base.Toolbox:
		#creator.create("TestFit", base.Fitness, weights=(1.0,))
		#creator.create("Chromo", list, fitness=creator.TestFit)
		
		toolbox = base.Toolbox()
		
		#toolbox.register("rand_bool", random.randint, 0, 1)
		#toolbox.register("init_individual", tools.initRepeat, creator.Chromo, toolbox.rand_bool, 20)
		#toolbox.register("init_pop", tools.initRepeat, list, toolbox.init_individual)
		
		toolbox.register("mate", Individual.wrap_alteration(tools.cxTwoPoint, 2, self._chromo_gen, self._data_sink))
		toolbox.register(
			"mutate",
			Individual.wrap_alteration(tools.mutUniformInt, 1, self._chromo_gen, self._data_sink),
			low=0, up=[len(g.alleles)-1 for g in self._rep.iter_genes()], indpb=0.05)
		toolbox.register("select", tools.selTournament, tournsize=3)
		toolbox.register("evaluate", self._evaluate)
		
		return toolbox
