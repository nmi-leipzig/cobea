from abc import ABC, abstractmethod
from typing import Any

from domain.model import FitnessFunctionImpl, PreprocessingImpl, Parameter

class FitnessFunctionLibrary(ABC):
	"""Interface for a library of fitness function implementations"""
	
	@abstractmethod
	def get_implementation(self, identifier: str) -> FitnessFunctionImpl:
		raise NotImplementedError()

class PreprocessingLibrary(ABC):
	"""Interface for a library of preprocessing implementations"""
	
	@abstractmethod
	def get_implementation(self, identifier: str) -> PreprocessingImpl:
		raise NotImplementedError()

class ParameterRepository(ABC):
	"""Interface for getting values for parameters"""
	
	@abstractmethod
	def read_value(self, param: Parameter) -> Any:
		raise NotImplementedError()
