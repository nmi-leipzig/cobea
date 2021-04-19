import random

from typing import Tuple

from deap import tools
from deap import creator
from deap import base
from deap import algorithms

from domain.interfaces import EvoAlgo, InputData
from domain.request_model import RequestObject
from domain.use_cases import Measure

class SimpleEA(EvoAlgo):
	
	def __init__(self, measure_uc: Measure) -> None:
		self._measure_uc = measure_uc
	
	def run(self) -> None:
		# create toolbox
		toolbox = self.create_toolbox()
		# create population
		pop = toolbox.init_pop(n=10)
		# run
		algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.1, ngen=5)
		
	
	def _evaluate(self, i) -> Tuple[int]:
		driver_req = RequestObject(
			driver_data = InputData([0]),
		)
		data = self._measure_uc(driver_req)
		return (sum(i)+sum(data), )
	
	def create_toolbox(self) -> base.Toolbox:
		creator.create("TestFit", base.Fitness, weights=(1.0,))
		creator.create("Chromo", list, fitness=creator.TestFit)
		
		toolbox = base.Toolbox()
		
		toolbox.register("rand_bool", random.randint, 0, 1)
		toolbox.register("init_individual", tools.initRepeat, creator.Chromo, toolbox.rand_bool, 20)
		toolbox.register("init_pop", tools.initRepeat, list, toolbox.init_individual)
		
		toolbox.register("mate", tools.cxTwoPoint)
		toolbox.register("mutate", tools.mutFlipBit, indpb=0.05)
		toolbox.register("select", tools.selTournament, tournsize=3)
		toolbox.register("evaluate", self._evaluate)
		
		return toolbox
