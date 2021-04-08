from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Iterable

from domain.model import OutputData, Chromosome
from domain.interfaces import FitnessFunctionLibrary, Preprocessing, PreprocessingLibrary, EvoAlgo, DataSink, PRNG,\
TargetManager, Meter, RepresentationGenerator, Representation, PosTrans, PosTransLibrary, TargetConfiguration,\
UniqueID
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

class RunEvoAlgo(UseCase):
	def __init__(self, evo_algo: EvoAlgo, data_sink: DataSink) -> None:
		self._evo_algo = evo_algo
		self._target_manager = target_manager
		self._meter = meter
		self._data_sink = data_sink
		self._parameters = {"perform": []}
	
	def perform(self, request: RequestObject) -> None:
		with self._data_sink:
			self._evo_algo.run()

class GenChromo(UseCase):
	"""Generate Chromosome"""
	
	def __init__(self, uid_gen: UniqueID) -> None:
		self._uid_gen = uid_gen
		self._parameters = {
			"perform": [Parameter("allele_indices", int, multiple=True)]
		}
	
	def perform(self, request: RequestObject) -> Chromosome:
		new_id = self._uid_gen.get_id()
		indices = tuple(request.allele_indices)
		chromo = Chromosome(new_id, indices)
		return chromo

class RandomChromo(UseCase):
	"""Generate a random chromosome"""
	
	def __init__(self, prng: PRNG, rep: Representation, uid_gen: UniqueID) -> None:
		self._prng = prng
		self._rep = rep
		self._chromo_gen = GenChromo(uid_gen)
		
		self._parameters = {"perform": []}
	
	def perform(self, request: RequestObject) -> None:
		indices = [self._prng.randint(0, len(g.alleles)-1) for g in self._rep.iter_genes()]
		return self._chromo_gen(RequestObject(allele_indices=indices))
