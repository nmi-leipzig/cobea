from abc import ABC, abstractmethod, abstractproperty
from contextlib import AbstractContextManager
from typing import Any, Callable, Union, Mapping, Iterable, Sequence, Tuple

from domain.model import InputData, OutputData, Chromosome, Gene
from domain.request_model import RequestObject, ParameterValues, ParameterUser, Parameter

class ElementPosition(ABC):
	pass

class TargetConfiguration(ABC):
	@abstractmethod
	def to_text(self) -> str:
		raise NotImplementedError()

class TargetDevice(ABC):
	"""Interface for accessing a target device"""
	
	@abstractproperty
	def serial_number(self) -> str:
		raise NotImplementedError()
	
	@abstractproperty
	def hardware_type(self) -> str:
		raise NotImplementedError()
	
	#TODO: change configure to do check of compatability; create other function for configure
	@abstractmethod
	def configure(self, configuration: TargetConfiguration) -> None:
		raise NotImplementedError()
	
	@abstractmethod
	def read_bytes(self, size: int) -> bytes:
		raise NotImplementedError()
	
	@abstractmethod
	def write_bytes(self, data: bytes) -> int:
		raise NotImplementedError()

class Driver(ParameterUser):
	@abstractmethod
	def drive(self, request: RequestObject) -> None:
		raise NotImplementedError()
	
	@abstractmethod
	def clean_up(self, request: RequestObject) -> None:
		raise NotImplementedError()

class Meter(ParameterUser):
	@abstractmethod
	def prepare(self, request: RequestObject) -> None:
		raise NotImplementedError()
	
	@abstractmethod
	def measure(self, request: RequestObject) -> OutputData:
		raise NotImplementedError()

class TargetManager(ABC):
	"""Interface for managing access to target devices"""
	
	@abstractmethod
	def acquire(self, serial_number: Union[str, None]) -> TargetDevice:
		raise NotImplementedError()
	
	@abstractmethod
	def release(self, target: TargetDevice) -> None:
		raise NotImplementedError()

class FitnessFunction(ParameterUser):
	@abstractmethod
	def compute(self, request: RequestObject) -> float:
		raise NotImplementedError()

# interface to compute a fitness function
CorrelationFunction = Callable[[InputData, OutputData], float]

class CorrelationFunctionLibrary(ABC):
	"""Interface for a library of correlation function implementations"""
	
	@abstractmethod
	def get_correlation_function(self, identifier: str) -> CorrelationFunction:
		raise NotImplementedError()

# interface to prepare data for fitness function
Preprocessing = Callable[[InputData, OutputData], Tuple[InputData, OutputData]]

class PreprocessingLibrary(ABC):
	"""Interface for a library of preprocessing implementations"""
	
	@abstractmethod
	def get_preprocessing(self, request: RequestObject) -> Preprocessing:
		raise NotImplementedError()

class Representation(ABC):
	"""Interface for representating the phenotype as a genotype"""
	
	@abstractmethod
	def prepare_config(self, config: TargetConfiguration) -> None:
		"""make modification that are only needed once for a representation"""
		raise NotImplementedError()
	
	@abstractmethod
	def decode(self, config: TargetConfiguration, chromo: Chromosome) -> None:
		"""Decode a chromosome to a Configuration.
		
		The name is not 100 percent correct as decoding maps the chromosome to the phenotype,
		but the real phenotype is the configured FPGA, not the configuration.
		"""
		raise NotImplementedError()
	
	@abstractmethod
	def iter_genes(self) -> Iterable[Gene]:
		raise NotImplementedError()
	

class RepresentationGenerator(ParameterUser):
	"""Interface for generation of a representation """
	
	@abstractmethod
	def __call__(self, request: RequestObject) -> Representation:
		raise NotImplementedError()

# position transformation
PosTrans = Callable[[Sequence[ElementPosition]], Sequence[ElementPosition]]

class PosTransLibrary(ABC):
	"""Interface for a library of position transformations"""
	
	@abstractmethod
	def get_pos_trans(self, request: RequestObject) -> PosTrans:
		raise NotImplementedError()

class EvoAlgo(ABC):
	@abstractmethod
	def run(self) -> None:
		raise NotImplementedError()

class DataSink(AbstractContextManager):
	@abstractmethod
	def write_metadata(self, name: str, data: Any, data_type: type, multiple=False) -> None:
		raise NotImplementedError()

class PRNG(ABC):
	"""Interface for pseudo random number generator"""
	
	@abstractmethod
	def seed(self, int) -> None:
		raise NotImplementedError()
	
	@abstractmethod
	def randint(self, a: int, b: int) -> int:
		raise NotImplementedError()

class UniqueID(ABC):
	"""Interface for generating unique IDs"""
	
	@abstractmethod
	def get_id(self) -> int:
		raise NotImplementedError()
