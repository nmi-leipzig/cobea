import numpy as np
from scipy.stats import pearsonr

from domain.interfaces import CorrelationFunction, CorrelationFunctionLibrary
from domain.model import InputData, OutputData
from domain.request_model import ParameterValues


class SciPyFunctions(CorrelationFunctionLibrary):
	
	def __init__(self):
		pass
	
	def get_item(self, identifier: str, params: ParameterValues) -> CorrelationFunction:
		return getattr(self, identifier)
	
	@staticmethod
	def pearsons_correlation(input_data: InputData, output_data: OutputData) -> float:
		corr = abs(pearsonr(input_data, output_data)[0])
		if np.isnan(corr):
			corr = 0
		
		return corr
