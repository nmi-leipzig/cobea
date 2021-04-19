import random

from deap import tools
from deap import creator
from deap import base
from deap import algorithms

from domain.interfaces import EvoAlgo

class SimpleEA(EvoAlgo):
	
	def __init__(self) -> None:
		pass
	
	def run(self) -> None:
		# create toolbox
		toolbox = self.create_toolbox()
		# create population
		pop = toolbox.init_pop(n=10)
		# run
		algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.1, ngen=5)
		
	
	@staticmethod
	def create_toolbox() -> base.Toolbox:
		creator.create("TestFit", base.Fitness, weights=(1.0,))
		creator.create("Chromo", list, fitness=creator.TestFit)
		
		toolbox = base.Toolbox()
		
		toolbox.register("rand_bool", random.randint, 0, 1)
		toolbox.register("init_individual", tools.initRepeat, creator.Chromo, toolbox.rand_bool, 20)
		toolbox.register("init_pop", tools.initRepeat, list, toolbox.init_individual)
		
		toolbox.register("mate", tools.cxTwoPoint)
		toolbox.register("mutate", tools.mutFlipBit, indpb=0.05)
		toolbox.register("select", tools.selTournament, tournsize=3)
		toolbox.register("evaluate", lambda i: (sum(i), ))
		
		return toolbox
