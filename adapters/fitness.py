from functools import reduce
from typing import Any, Callable

from domain.interfaces import FitnessFunction
from domain.request_model import ResponseObject, RequestObject

class ReduceFF(FitnessFunction):
	"""Computes fitness function by applying reduce to measurements"""
	def __init__(self, red_func: Callable[[Any, Any], Any], initializer: Any=0) -> None:
		self._red_func = red_func
		self._initializer = initializer
	
	def compute(self, request: RequestObject) -> ResponseObject:
		fit = reduce(self._red_func, request.measurement, self._initializer)
		return ResponseObject(fitness=fit)
