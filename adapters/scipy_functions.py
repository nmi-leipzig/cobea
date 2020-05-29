import numpy as np
from scipy.stats import stats

from domain.interfaces import FitnessFunctionLibrary
from domain.model import FitnessFunctionImpl, TestInput, TestOutput

class SciPyFunctions(FitnessFunctionLibrary):
	
	def __init__(self):
		pass
	
	def get_implementation(self, identifier: str) -> FitnessFunctionImpl:
		return getattr(self, identifier)
	
	@staticmethod
	def pearsons_correlation(test_input: TestInput, test_output: TestOutput) -> float:
		corr = abs(stats.pearsonr(test_input, test_output)[0])
		if np.isnan(corr):
			corr = 0
		
		return corr
