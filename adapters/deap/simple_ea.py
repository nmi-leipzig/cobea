import datetime
import random
import time

from dataclasses import dataclass, field
from enum import auto, Enum
from typing import Callable, Iterable, List, Optional, Tuple

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

class EvalMode(Enum):
	NEW = auto()
	ELITE = auto()
	ALL = auto()

creator.create("SimpleFit", base.Fitness, weights=(1.0, ))

@dataclass
class Individual:
	chromo: Chromosome
	fitness: creator.SimpleFit=field(default_factory=creator.SimpleFit, init=False)
	rank_prob: creator.SimpleFit=field(default_factory=creator.SimpleFit, init=False)
	
	def __len__(self) -> int:
		return len(self.chromo.allele_indices)
	
	def __getitem__(self, index: int) -> int:
		return self.chromo.allele_indices[index]
	
	@classmethod
	def wrap_alteration(cls, func, in_count, chromo_gen: GenChromo, data_sink: DataSink) -> Callable[..., Tuple["Individual", ...]]:
		
		def wrapped_func(*args, **kwargs) -> Tuple["Individual", ...]:
			in_indis = args[:in_count]
			
			res = func(*[list(i.chromo.allele_indices) for i in in_indis], *args[in_count:], **kwargs)
			
			out_indis = []
			req = RequestObject()
			for allele_indices in res:
				allele_indices_tup = tuple(allele_indices)
				new_indi = None
				# found in input?
				for old in in_indis:
					if old.chromo.allele_indices == allele_indices_tup:
						new_indi = old
						break
				if new_indi is None:
					# create new chromosome
					req["allele_indices"] = allele_indices_tup
					chromo = chromo_gen(req)
					new_indi = Individual(chromo)
				out_indis.append(new_indi)
			
			if data_sink is not None:
				data_sink.write(f"{cls.__name__}.wrap.{func.__name__}", {
					"in": [i.chromo.identifier for i in in_indis],
					"out": [i.chromo.identifier for i in out_indis]
				})
			
			return tuple(out_indis)
		
		return wrapped_func

class SimpleEA(EvoAlgo, DataSinkUser):
	def __init__(self, rep: Representation, measure_uc: Measure, uid_gen: UniqueID, prng: PRNG, habitat: TargetConfiguration, target: TargetDevice, trig_len: int, data_sink: DataSink) -> None:
		self._rep = rep
		self._measure_uc = measure_uc
		self._init_uc = RandomChromo(prng, rep, uid_gen, data_sink)
		self._chromo_gen = GenChromo(uid_gen, data_sink)
		rep.prepare_config(habitat)
		self._habitat = habitat
		self._target = target
		self._trig_len = trig_len
		self._data_sink = data_sink
		
		self._driver_table = lexicographic_combinations(5, 5)
	
	@property
	def data_sink(self) -> DataSink:
		return self._data_sink
	
	def run(self, pop_size: int, gen_count: int, crossover_prob: float, mutation_prob: float, eval_mode: EvalMode) -> None:
		self.write_to_sink("ea_params", {
			"pop_size": pop_size,
			"gen_count": gen_count,
			"crossover_prob": crossover_prob,
			"mutation_prob": mutation_prob,
			"eval_mode": eval_mode.name,
		})
		# DEAP uses random directly, so store it's inital state
		self.write_to_sink("random_initial", {"state": random.getstate()})
		
		# create toolbox
		toolbox = self.create_toolbox(mutation_prob)
		
		# create population
		pop = self._init_pop(pop_size)
		
		# run
		#algorithms.eaSimple(pop, toolbox, cxpb=crossover_prob, mutpb=mutation_prob, ngen=gen_count)
		self.org_ea(pop, toolbox, crossover_prob, mutation_prob, gen_count, eval_mode)
		
		# DEAP uses random directly, so store it's inital state
		self.write_to_sink("random_final", {"state": random.getstate()})
		
	
	@staticmethod
	def evaluate_invalid(pop: List[Individual], toolbox: base.Toolbox) -> None:
		"""Evaluate fitness for all indiviuals with invalid fitness"""
		# the same individual may be multiple times in the population
		# -> avoid doing multiple evaluations for one individual by making the list entries unique
		seen = set()
		invalid_list = [
			i for i in pop if not i.fitness.valid and not (i.chromo.identifier in seen or seen.add(i.chromo.identifier))
		]
		fitness_list = toolbox.map(toolbox.evaluate, invalid_list)
		for indi, fit in zip(invalid_list, fitness_list):
			indi.fitness.values = fit
	
	def org_ea(self, pop: List[Individual], toolbox: base.Toolbox, cxpb: float, mutpb: float, ngen: int,
		eval_mode: EvalMode) -> None:
		
		pop_size = len(pop)
		# prepare rank probabilities
		s = 2.0
		prob_list = [(2-s)/pop_size+2*i*(s-1)/(pop_size*(pop_size-1)) for i in range(pop_size)]
		
		# initial evaluation
		prev_time = time.perf_counter()
		self.evaluate_invalid(pop, toolbox)
		best = max([p.fitness.values for p in pop])
		
		start_time = time.perf_counter()
		for gen_nr in range(ngen):
			cur_time = time.perf_counter()
			try:
				eta = (cur_time - start_time) * (ngen/gen_nr - 1)
			except ZeroDivisionError:
				# can't estimate for 0 generation
				eta = -1.0
			print(f"Generation {gen_nr} took {cur_time-prev_time:.1f} s, eta : {eta:.1f} s; highest fitness: {best}")
			prev_time = cur_time
			
			
			self.write_to_sink("gen", {"pop": [p.chromo.identifier for p in pop]})
			# find probability based on rank
			ranked = sorted(pop, key=lambda x:x.fitness)
			for indi, rp in zip(ranked, prob_list):
				indi.rank_prob.values = (rp, )
			
			elite = ranked[-1:]
			best = elite[0].fitness.values
			progeny = toolbox.select(pop, pop_size-1, fit_attr="rank_prob")
			# no need to invalidate fitness explicitly as the Individual.wrap_alteration already creates new 
			# Individual instances for altered chromosomes
			
			# algorithms.varAnd mutates the population in place and invalidates the fitness values accordingly
			# but that is not necessary as Individual.wrap_alteration already creates new individuals (and chromosomes)
			# without fitness if the allele_indices were altered
			# -> implement own version here to avoid superfluous evaluations
			
			# crossover
			for i in range(1, len(progeny), 2):
				# use random to be consistent with DEAP
				if random.random() < cxpb:
					progeny[i-1], progeny[i] = toolbox.mate(progeny[i-1], progeny[i])
			# mutation
			#print(f"before_mut: {[p.chromo.identifier for p in progeny]}")
			progeny = [r[0] for r in map(toolbox.mutate, progeny)]
			#print(f"after_mut: {[p.chromo.identifier for p in progeny]}")
			
			pop = elite + progeny
			if eval_mode == EvalMode.ELITE:
				self.invalidate(elite)
			elif eval_mode == EvalMode.ALL:
				self.invalidate(pop)
			# nothing to do for EvalMode.NEW as the new individuals have no valid fitness value
			
			
			self.evaluate_invalid(pop, toolbox)
			
		
		self.write_to_sink("gen", {"pop": [p.chromo.identifier for p in pop]})
		
		cur_time = time.perf_counter()
		print(f"{ngen} generations took {cur_time-start_time:.2f} s")
		
	
	def _init_pop(self, count) -> List[Individual]:
		return [Individual(self._init_uc(RequestObject())) for _ in range(count)]
	
	def _evaluate(self, indi: Individual, comb_index: Optional[int]=None) -> Tuple[int]:
		if comb_index is None:
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
		cur_time = datetime.datetime.now(datetime.timezone.utc)
		data = self._measure_uc(eval_req)
		
		h_div = (12*0.5) / len(data)
		
		# skip before trigger
		data = data[-self._trig_len:]
		
		data_parts = [data[i*len(data)//10: (i+1)*len(data)//10] for i in range(10)]
		
		fast_sum = 0
		slow_sum = 0
		for i, data_part in enumerate(data_parts):
			nd = np.array(data_part)
			auc = np.trapz(nd, dx=h_div)
			
			if ((comb_seq >> i) & 1):
				fast_sum += auc
			else:
				slow_sum += auc
		
		fit = abs(slow_sum/30730.746 - fast_sum/30527.973)/10
		self.write_to_sink("fitness", {
			"fit": fit,
			"fast_sum": fast_sum,
			"slow_sum": slow_sum,
			"chromo_index": indi.chromo.identifier,
			"carry_enable": carry_enable_state,
			"time": cur_time,
		})
		return (fit, )
	
	def create_toolbox(self, mutation_prob: float) -> base.Toolbox:
		#creator.create("TestFit", base.Fitness, weights=(1.0,))
		#creator.create("Chromo", list, fitness=creator.TestFit)
		
		toolbox = base.Toolbox()
		
		#toolbox.register("rand_bool", random.randint, 0, 1)
		#toolbox.register("init_individual", tools.initRepeat, creator.Chromo, toolbox.rand_bool, 20)
		#toolbox.register("init_pop", tools.initRepeat, list, toolbox.init_individual)
		
		toolbox.register("mate", Individual.wrap_alteration(tools.cxOnePoint, 2, self._chromo_gen, self._data_sink))
		toolbox.register(
			"mutate",
			Individual.wrap_alteration(tools.mutUniformInt, 1, self._chromo_gen, self._data_sink),
			low=0, up=[len(g.alleles)-1 for g in self._rep.iter_genes()], indpb=mutation_prob)
		toolbox.register("select", tools.selRoulette)
		toolbox.register("evaluate", self._evaluate)
		
		return toolbox
	
	@staticmethod
	def invalidate(indis: Iterable[Individual]):
		for i in indis:
			try:
				del i.fitness.values
			except AttributeError:
				pass
