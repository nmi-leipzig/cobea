from typing import Any

from domain.model import FitnessFunction, Preprocessing, Parameter
from domain.interfaces import FitnessFunctionLibrary, PreprocessingLibrary, ParameterRepository

class CreateFitnessFunction:
	def __init__(self, library: FitnessFunctionLibrary) -> None:
		self._library = library
	
	def __call__(self, identifier: str, description: str) -> FitnessFunction:
		implementation = self._library.get_implementation(identifier)
		return FitnessFunction(identifier, description, implementation)

class CreatePreprocessing:
	def __init__(self, library: PreprocessingLibrary) -> None:
		self._library = library
	
	def __call__(self, identifier: str, description: str) -> Preprocessing:
		implementation = self._library.get_implementation(identifier)
		return Preprocessing(identifier, description, implementation)

class ReadParameter:
	def __init__(self, repository: ParameterRepository) -> None:
		self._repository = repository
	
	def __call__(self, param: Parameter) -> Any:
		return self._repository.read_value(param)
