from deap import tools
from deap import creator
from deap import base
from deap import algorithms

from domain.interfaces import EvoAlgo

class SimpleEA(EvoAlgo):
	
	def __init__(self) -> None:
		pass
	
	def run(self) -> None:
		
	
	@staticmethod
	def create_toolbox():
		
		toolbox = base.Toolbox()
		
		toolbox.register("rand_bool", random.randint, 0, 1)
		toolbox.register("init_individual", tools.initRepeat, creator.Chromo, toolbox.rand_bool, 20)
		toolbox.register("init_pop", tools.initRepeat, list, toolbox.init_individual)
		
		toolbox.register("mate", tools.cxTwoPoint)
		toolbox.register("mutate", tools.mutFlipBit, indpb=0.05)
		toolbox.register("select", tools.selTournament, tournsize=3)
		
		return toolbox
