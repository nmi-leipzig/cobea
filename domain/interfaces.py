from abc import ABC, abstractmethod, abstractproperty
from typing import Any, Callable, Union, Mapping, Iterable, Sequence, Tuple

from domain.model import FitnessFunctionImpl, InputData, OutputData, Chromosome
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


class Meter(ParameterUser):
	@abstractmethod
	def __call__(self, target: TargetDevice, request: RequestObject) -> OutputData:
		raise NotImplementedError()

class TargetManager(ABC):
	"""Interface for managing access to target devices"""
	
	@abstractmethod
	def acquire(self, serial_number: Union[str, None]) -> TargetDevice:
		raise NotImplementedError()
	
	@abstractmethod
	def release(self, target: TargetDevice) -> None:
		raise NotImplementedError()

class FitnessFunctionLibrary(ABC):
	"""Interface for a library of fitness function implementations"""
	
	@abstractmethod
	def get_implementation(self, identifier: str) -> FitnessFunctionImpl:
		raise NotImplementedError()

# interface to prepare data for fitness function
Preprocessing = Callable[[InputData, OutputData], Tuple[InputData, OutputData]]

class PreprocessingLibrary(ABC):
	"""Interface for a library of preprocessing implementations"""
	
	@abstractmethod
	def get_preprocessing(self, request: RequestObject) -> Preprocessing:
		raise NotImplementedError()

class ParameterRepository(ABC):
	"""Interface for getting values for parameters"""
	
	@abstractmethod
	def read_value(self, identifier: str) -> Any:
		raise NotImplementedError()

class Representation(ABC):
	"""Interface for representating the phenotype as a genotype"""
	
	@abstractmethod
	def prepare_config(self, config: TargetConfiguration) -> None:
		"""make modification that are only needed once for a representation"""
		raise NotImplementedError()
	
	@abstractmethod
	def decode(self, config: TargetConfiguration, chromo: Chromosome) -> None:
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
