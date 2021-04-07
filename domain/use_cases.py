from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Iterable

from domain.model import FitnessFunction, Preprocessing, OutputData, Chromosome
from domain.interfaces import FitnessFunctionLibrary, PreprocessingLibrary, ParameterRepository,\
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
		output_data = self._meter(target, request)
		self._target_manager.release(target)
		
		return output_data

class CreateFitnessFunction(UseCase):
	def __init__(self, library: FitnessFunctionLibrary) -> None:
		self._library = library
		self._parameters = {"perform": [
			Parameter("identifier", str),
			Parameter("description", str),
		]}
	
	def perform(self, request: RequestObject) -> FitnessFunction:
		implementation = self._library.get_implementation(request["identifier"])
		return FitnessFunction(request["identifier"], request["description"], implementation)

class CreatePreprocessing(UseCase):
	def __init__(self, library: PreprocessingLibrary) -> None:
		self._library = library
		self._parameters = {"perform": [
			Parameter("identifier", str),
			Parameter("description", str),
		]}
	
	def perform(self, request: RequestObject) -> Preprocessing:
		implementation = self._library.get_implementation(request)
		return Preprocessing(request["identifier"], request["description"], implementation)

class ReadParameter(UseCase):
	def __init__(self, repository: ParameterRepository) -> None:
		self._repository = repository
		self._parameters = {"perform": [
			Parameter("param", str),
		]}
	
	def perform(self, request: RequestObject) -> Any:
		return self._repository.read_value(request["param"])

class DecodeChromosome(UseCase):
	"""Decode a chromosome to a Configuration.
	
	The name is not 100 percent correct as decoding maps the chromosome to the phenotype,
	but the real phenotype is the configured FPGA, not the configuration.
	"""
	def __init__(self, rep: Representation) -> None:
		self._rep = rep
		self._parameters = {"perform": [
			Parameter("configuration", TargetConfiguration),
			Parameter("chromosome", Chromosome),
		]}
	
	def perform(self, request: RequestObject) -> Any:
		self._rep.decode(request.configuration, request.chromosome)

class CreateRepresentation(UseCase):
	def __init__(self, rep_gen: RepresentationGenerator) -> None:
		self._rep_gen = rep_gen
		self._parameters = {"perform": []}
		call_params = rep_gen.parameters["__call__"]
		self._parameters["perform"].extend(call_params)
	
	def perform(self, request: RequestObject) -> Representation:
		return self._rep_gen(request)
