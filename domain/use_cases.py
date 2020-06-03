from abc import ABC, abstractmethod
from typing import Any, Dict

from domain.model import FitnessFunction, Preprocessing
from domain.interfaces import FitnessFunctionLibrary, PreprocessingLibrary, ParameterRepository

class RequestObject(Dict[str, Any]):
	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError as ke:
			raise AttributeError from ke

class UseCase(ABC):
	def __call__(self, request: RequestObject) -> Any:
		result = self.perform(request)
		return result
	
	@abstractmethod
	def perform(self, request: RequestObject) -> Any:
		raise NotImplementedError()

class CreateFitnessFunction(UseCase):
	def __init__(self, library: FitnessFunctionLibrary) -> None:
		self._library = library
	
	def perform(self, request: RequestObject) -> FitnessFunction:
		implementation = self._library.get_implementation(request["identifier"])
		return FitnessFunction(request["identifier"], request["description"], implementation)

class CreatePreprocessing(UseCase):
	def __init__(self, library: PreprocessingLibrary) -> None:
		self._library = library
	
	def perform(self, request: RequestObject) -> Preprocessing:
		implementation = self._library.get_implementation(request["identifier"])
		return Preprocessing(request["identifier"], request["description"], implementation)

class ReadParameter(UseCase):
	def __init__(self, repository: ParameterRepository) -> None:
		self._repository = repository
	
	def __call__(self, request: RequestObject) -> Any:
		return self._repository.read_value(request["param"])
