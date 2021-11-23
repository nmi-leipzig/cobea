import datetime

from abc import ABC, abstractmethod
from copy import deepcopy
from functools import reduce
from typing import Any, Dict, Iterable, Mapping, NewType, Optional, Callable

from domain.data_sink import DataSink, DataSinkUser, sink_request
from domain.model import OutputData, Chromosome
from domain.interfaces import DataSink, Driver, EvoAlgo, FitnessFunction, MeasureTimeout, Meter, Preprocessing, \
	PreprocessingLibrary, PosTrans, PosTransLibrary, PRNG, RepresentationGenerator, Representation, TargetConfiguration, \
	TargetManager, UniqueID, TargetDevice, InputGen
from domain.request_model import RequestObject, ParameterUser, Parameter, set_req_defaults, ResponseObject


class UseCase(ParameterUser, DataSinkUser):
	@set_req_defaults
	def __call__(self, request: RequestObject) -> ResponseObject:
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
	def perform(self, request: RequestObject) -> ResponseObject:
		raise NotImplementedError()


class Measure(UseCase):
	def __init__(self, driver: Driver, meter: Meter, data_sink: DataSink=None, prefix: Optional[str]=None) -> None:
		self._driver = driver
		self._meter = meter
		sub_params = [
			[Parameter("retry", int, default=0)],
			driver.parameters["drive"], driver.parameters["clean_up"],
			meter.parameters["prepare"], meter.parameters["measure"]
		]
		self._parameters = {"perform": reduce(self.meld_parameters, sub_params)}
		
		self._prefix = prefix
		if self._prefix is None:
			self._prefix = type(self).__name__
		
		self._data_sink = data_sink
	
	@property
	def prefix(self) -> str:
		return self._prefix
	
	@sink_request
	def perform(self, request: RequestObject) -> ResponseObject:
		attempt = 0
		while True:
			attempt += 1
			res = self._meter.prepare(request)
			res.update(self._driver.drive(request))
			
			# create aware datetime object; utcnow would create naive datetime object
			cur_time = datetime.datetime.now(datetime.timezone.utc)
			try:
				res.update(self._meter.measure(request))
			except MeasureTimeout:
				print(f"Got timeout on attempt {attempt}")
				if attempt <= request.retry:
					continue
				else:
					raise
			
			res.update(self._driver.clean_up(request))
			break

		res["time"] = cur_time

		return res


ExInfoCallable = NewType("ExInfoCallable", Callable[[Representation, TargetConfiguration, Chromosome], ResponseObject])


class DecTarget(UseCase):
	"""Decodes the genotype (chromosome) to the actual phenotype (configured target)."""
	
	def __init__(self, rep: Representation, habitat: TargetConfiguration, target: TargetDevice, extract_info:
	Optional[ExInfoCallable]=None, data_sink: DataSink=None) -> None:
		self._rep = rep
		self._habitat = habitat
		self._target = target
		self._extract_info = extract_info
		self._data_sink = data_sink
		self._parameters = {"perform": [Parameter("chromosome", Chromosome)]}
	
	@sink_request
	def perform(self, request: RequestObject) -> ResponseObject:
		self._rep.decode(self._habitat, request.chromosome)
		self._target.configure(self._habitat)
		res = ResponseObject(configuration=deepcopy(self._habitat))
		if self._extract_info:
			res.update(self._extract_info(self._rep, self._habitat, request.chromosome))
		
		return res


class MeasureFitness(UseCase):
	def __init__(self,
		decode_uc: DecTarget,
		measure_uc: Measure,
		fit_func: FitnessFunction,
		input_gen: Optional[InputGen],
		prep: Callable[[OutputData], OutputData] = lambda x: x,
		data_sink: DataSink=None
	) -> None:
		self._decode_uc = decode_uc
		self._measure_uc = measure_uc
		self._fit_func = fit_func
		self._input_gen = input_gen
		self._prep = prep
		self._data_sink = data_sink
		
		sub_params = [
			[
				Parameter("chromosome", Chromosome),
			],
			decode_uc.parameters["__call__"], measure_uc.parameters["__call__"], fit_func.parameters["compute"],
		]
		provided_list = ["measurement", "raw_measurement"]
		
		if input_gen:
			sub_params.append(input_gen.parameters["generate"])
			provided_list.append("driver_data")
		
		perf_params = reduce(self.meld_parameters, sub_params)
		perf_params = self.filter_parameters(perf_params, provided_list)
		self._parameters = {"perform": perf_params}
	
	@sink_request
	def perform(self, request: RequestObject) -> ResponseObject:
		req = RequestObject(request)
		res = self._decode_uc(request)
		
		if self._input_gen:
			gen_res = self._input_gen.generate(req)
			res.update(gen_res)
			# result is needed for measure
			req.update(gen_res)
		
		mea_res = self._measure_uc(req)
		res.update(mea_res)
		res["raw_measurement"] = req["raw_measurement"] = res.measurement
		res["measurement"] = req["measurement"] = self._prep(res.measurement)
		
		res.update(self._fit_func.compute(req))
		
		return res

class RunEvoAlgo(UseCase):
	def __init__(self, evo_algo: EvoAlgo, data_sink: DataSink=None) -> None:
		self._evo_algo = evo_algo
		self._target_manager = target_manager
		self._meter = meter
		self._data_sink = data_sink
		self._parameters = {"perform": []}
	
	@sink_request
	def perform(self, request: RequestObject) -> ResponseObject:
		with self._data_sink:
			self._evo_algo.run()

		return ResponseObject()

class GenChromo(UseCase):
	"""Generate Chromosome"""
	
	def __init__(self, uid_gen: UniqueID, data_sink: DataSink=None) -> None:
		self._uid_gen = uid_gen
		self._parameters = {
			"perform": [Parameter("allele_indices", int, multiple=True)]
		}
		
		self._data_sink = data_sink
	
	@sink_request
	def perform(self, request: RequestObject) -> ResponseObject:
		new_id = self._uid_gen.get_id()
		indices = tuple(request.allele_indices)
		chromo = Chromosome(new_id, indices)
		return ResponseObject(chromosome=chromo)

class RandomChromo(UseCase):
	"""Generate a random chromosome"""
	
	def __init__(self, prng: PRNG, rep: Representation, uid_gen: UniqueID, data_sink: DataSink=None) -> None:
		self._prng = prng
		self._rep = rep
		self._chromo_gen = GenChromo(uid_gen)
		
		self._parameters = {"perform": []}
		
		self._data_sink = data_sink
	
	@sink_request
	def perform(self, request: RequestObject) -> ResponseObject:
		indices = [self._prng.randint(0, len(g.alleles)-1) for g in self._rep.iter_genes()]
		return self._chromo_gen(RequestObject(allele_indices=indices))
