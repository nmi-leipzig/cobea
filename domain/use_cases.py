from abc import ABC, abstractmethod
from functools import reduce
from typing import Any, Dict, Mapping, Iterable

from domain.data_sink import DataSink, DataSinkUser, sink_request
from domain.model import OutputData, Chromosome
from domain.interfaces import DataSink, Driver, EvoAlgo, FitnessFunction, MeasureTimeout, Meter, Preprocessing,\
PreprocessingLibrary, PosTrans, PosTransLibrary, PRNG, RepresentationGenerator, Representation, TargetConfiguration,\
TargetManager, UniqueID
from domain.request_model import RequestObject, ParameterUser, Parameter, set_req_defaults

class UseCase(ParameterUser, DataSinkUser):
	@set_req_defaults
	def __call__(self, request: RequestObject) -> Any:
		result = self.perform(request)
		return result
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		res = dict(self._parameters)
		res["__call__"] = res["perform"]
		return res
	
	@property
	def data_sink(self) -> DataSink:
		return self._data_sink
	
	@abstractmethod
	def perform(self, request: RequestObject) -> Any:
		raise NotImplementedError()

class Measure(UseCase):
	def __init__(self, driver: Driver, meter: Meter, data_sink: DataSink=None) -> None:
		self._driver = driver
		self._meter = meter
		sub_params = [
			[Parameter("retry", int, default=0)],
			driver.parameters["drive"], driver.parameters["clean_up"],
			meter.parameters["prepare"], meter.parameters["measure"]
		]
		self._parameters = {"perform": reduce(self.meld_parameters, sub_params)}
		
		self._data_sink = data_sink
	
	@sink_request
	def perform(self, request: RequestObject) -> OutputData:
		attempt = 0
		while True:
			attempt += 1
			self._meter.prepare(request)
			self._driver.drive(request)
			
			try:
				output_data = self._meter.measure(request)
			except MeasureTimeout:
				print(f"Got timeout on attempt {attempt}")
				if attempt <= request.retry:
					continue
				else:
					raise
			
			self._driver.clean_up(request)
			break
		
		return output_data

class MeasureFitness(UseCase):
	def __init__(self,
		rep: Representation,
		measure_uc: Measure,
		fit_func: FitnessFunction,
		data_sink: DataSink=None
	) -> None:
		self._rep = rep
		self._measure_uc = measure_uc
		self._fit_func = fit_func
		
		sub_params = [
			[
				Parameter("configuration", TargetConfiguration),
				Parameter("chromosome", Chromosome),
			],
			measure_uc.parameters["__call__"], fit_func.parameters["compute"],
		]
		perf_params = reduce(self.meld_parameters, sub_params)
		for provided in ["output_data"]:
			try:
				del perf_params[provided]
			except KeyError:
				# not needed
				pass
		self._parameters = {"perform": perf_params}
		
		self._data_sink = data_sink
	
	@sink_request
	def perform(self, request: RequestObject) -> float:
		request["configuration"] = self._rep.decode(request.configuration, request.chromosome)
		request["output_data"] = self._measure_uc(request)
		return self._fit_func.compute(request)

class RunEvoAlgo(UseCase):
	def __init__(self, evo_algo: EvoAlgo, data_sink: DataSink=None) -> None:
		self._evo_algo = evo_algo
		self._target_manager = target_manager
		self._meter = meter
		self._data_sink = data_sink
		self._parameters = {"perform": []}
	
	@sink_request
	def perform(self, request: RequestObject) -> None:
		with self._data_sink:
			self._evo_algo.run()

class GenChromo(UseCase):
	"""Generate Chromosome"""
	
	def __init__(self, uid_gen: UniqueID, data_sink: DataSink=None) -> None:
		self._uid_gen = uid_gen
		self._parameters = {
			"perform": [Parameter("allele_indices", int, multiple=True)]
		}
		
		self._data_sink = data_sink
	
	@sink_request
	def perform(self, request: RequestObject) -> Chromosome:
		new_id = self._uid_gen.get_id()
		indices = tuple(request.allele_indices)
		chromo = Chromosome(new_id, indices)
		return chromo

class RandomChromo(UseCase):
	"""Generate a random chromosome"""
	
	def __init__(self, prng: PRNG, rep: Representation, uid_gen: UniqueID, data_sink: DataSink=None) -> None:
		self._prng = prng
		self._rep = rep
		self._chromo_gen = GenChromo(uid_gen)
		
		self._parameters = {"perform": []}
		
		self._data_sink = data_sink
	
	@sink_request
	def perform(self, request: RequestObject) -> Chromosome:
		indices = [self._prng.randint(0, len(g.alleles)-1) for g in self._rep.iter_genes()]
		return self._chromo_gen(RequestObject(allele_indices=indices))
