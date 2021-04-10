from abc import ABC, abstractmethod
from functools import reduce
from typing import Any, Dict, Mapping, Iterable

from domain.model import OutputData, Chromosome
from domain.interfaces import FitnessFunctionLibrary, Preprocessing, PreprocessingLibrary, EvoAlgo, DataSink, PRNG,\
TargetManager, Meter, RepresentationGenerator, Representation, PosTrans, PosTransLibrary, TargetConfiguration,\
UniqueID, Driver
from domain.request_model import RequestObject, ParameterUser, Parameter

class UseCase(ParameterUser):
	def __call__(self, request: RequestObject) -> Any:
		result = self.perform(request)
		return result
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		res = dict(self._parameters)
		res["__call__"] = res["perform"]
		return res
	
	@abstractmethod
	def perform(self, request: RequestObject) -> Any:
		raise NotImplementedError()

class Measure(UseCase):
	def __init__(self, driver: Driver, meter: Meter) -> None:
		self._driver = driver
		self._meter = meter
		sub_params = [
			driver.parameters["drive"], driver.parameters["clean_up"],
			meter.parameters["prepare"], meter.parameters["measure"]
		]
		self._parameters = {"perform": reduce(self.meld_parameters, sub_params)}
	
	def perform(self, request: RequestObject) -> OutputData:
		self._meter.prepare(request)
		self._driver.drive(request)
		output_data = self._meter.measure(request)
		self._driver.clean_up(request)
		
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
