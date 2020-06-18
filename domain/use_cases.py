from abc import ABC, abstractmethod
from typing import Any, Dict

from domain.model import FitnessFunction, Preprocessing, OutputData
from domain.interfaces import FitnessFunctionLibrary, PreprocessingLibrary, ParameterRepository, TargetManager, Meter
from domain.request_model import RequestObject

class UseCase(ABC):
	def __call__(self, request: RequestObject) -> Any:
		result = self.perform(request)
		return result
	
	@abstractmethod
	def perform(self, request: RequestObject) -> Any:
		raise NotImplementedError()

class Measure(UseCase):
	def __init__(self, target_manager: TargetManager, meter: Meter) -> None:
		self._target_manager = target_manager
		self._meter = meter
	
	def perform(self, request: RequestObject) -> OutputData:
		target = self._target_manager.acquire(request.serial_number)
		output_data = self._meter(target, request)
		self._target_manager.release(target)
		
		return output_data

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
	
	def perform(self, request: RequestObject) -> Any:
		return self._repository.read_value(request["param"])
