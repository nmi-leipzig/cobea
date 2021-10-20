from typing import Tuple
from functools import partial

import numpy as np
from scipy.stats import stats

from domain.interfaces import Preprocessing, PreprocessingLibrary
from domain.model import InputData, OutputData
from domain.request_model import ParameterValues


class SciPyPreprocessing(PreprocessingLibrary):
	# preprocessing identifier -> parameters required
	param_dict = {
		"select": ("start", "end"),
	}
	
	def __init__(self):
		pass
	
	def get_item(self, identifier: str, params: ParameterValues) -> Preprocessing:
		func = getattr(self, identifier)
		return partial(func, params=params)
	
	@staticmethod
	def select(input_data: InputData, output_data: OutputData, params: ParameterValues) -> Tuple[InputData, OutputData]:
		new_in = InputData(input_data[params.start:params.end])
		new_out = OutputData(output_data[params.start:params.end])
		
		return new_in, new_out
