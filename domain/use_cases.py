from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Iterable

from domain.model import OutputData, Chromosome
from domain.interfaces import FitnessFunctionLibrary, Preprocessing, PreprocessingLibrary,\
TargetManager, Meter, RepresentationGenerator, Representation, PosTrans, PosTransLibrary, TargetConfiguration
from domain.request_model import RequestObject, ParameterUser, Parameter

class UseCase(ParameterUser):
	def __call__(self, request: RequestObject) -> Any:
		result = self.perform(request)
		return result
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return self._parameters
	
	@abstractmethod
	def perform(self, request: RequestObject) -> Any:
		raise NotImplementedError()

class Measure(UseCase):
	def __init__(self, target_manager: TargetManager, meter: Meter) -> None:
		self._target_manager = target_manager
		self._meter = meter
		self._parameters = {"perform": [Parameter("serial_number", str)]}
		call_params = meter.parameters["__call__"]
		self._parameters["perform"].extend(call_params)
	
	def perform(self, request: RequestObject) -> OutputData:
		target = self._target_manager.acquire(request.serial_number)
		try:
			output_data = self._meter(target, request)
		finally:
			self._target_manager.release(target)
		
		return output_data
