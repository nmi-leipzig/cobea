import numpy as np
from scipy.stats import stats

from domain.interfaces import FitnessFunction, FitnessFunctionLibrary
from domain.model import InputData, OutputData

class SciPyFunctions(FitnessFunctionLibrary):
	
	def __init__(self):
		pass
	
	def get_fitness_function(self, identifier: str) -> FitnessFunction:
		return getattr(self, identifier)
	
	@staticmethod
	def pearsons_correlation(input_data: InputData, output_data: OutputData) -> float:
		corr = abs(stats.pearsonr(input_data, output_data)[0])
		if np.isnan(corr):
			corr = 0
		
		return corr
