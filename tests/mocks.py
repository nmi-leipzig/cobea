import random
import time

from copy import deepcopy
from types import TracebackType
from typing import Any, Iterable, Mapping, Optional, Union, Sequence, Type, Tuple

from domain.base_structures import BitPos
from domain.data_sink import DataSink
from domain.interfaces import MeasureTimeout, Meter, PRNG, Representation, TargetConfiguration, TargetDevice,\
TargetManager, UniqueID
from domain.model import OutputData, Gene, Chromosome
from domain.request_model import RequestObject, Parameter, ResponseObject


class MockBitPos(BitPos, int):
	def to_ints(self) -> Tuple[int, ...]:
		return (int(self), )


class MockTargetDevice(TargetDevice):
	def __init__(self, serial_number="9555", hardware_type="S6C7", read_data=b""):
		self._serial_number = serial_number
		self._hardware_type = hardware_type
		self._read_data = read_data
		self._configured = []
		self._written = bytes()
	
	@property
	def configured(self):
		return tuple(self._configured)
	
	@property
	def written(self):
		return self._written
	
	@property
	def serial_number(self) -> str:
		return self._serial_number
	
	@property
	def hardware_type(self) -> str:
		return self._hardware_type
	
	def configure(self, configuration: TargetConfiguration) -> None:
		self._configured.append(configuration.to_text())
	
	def read_bytes(self, size: int) -> bytes:
		data = self._read_data[:size]
		self._read_data = self._read_data[size:]
		return data
	
	def write_bytes(self, data: bytes) -> int:
		self._written += data
		return len(data)


class MockTargetManager(TargetManager):
	def __init__(self, size=1):
		hardware_type = "S6C7"
		self.devices = {s: MockTargetDevice(str(s), hardware_type) for s in range(size)}
		self.available = set(self.devices)
	
	def acquire(self, serial_number: Union[str, None]) -> TargetDevice:
		if serial_number is None:
			serial_number = self.available.pop()
		else:
			self.available.remove(serial_number)
		
		return self.devices[serial_number]
	
	def release(self, target: TargetDevice) -> None:
		assert target.serial_number in self.devices
		self.available.add(target.serial_number)


class MockMeter(Meter):
	def __init__(self, output_data: OutputData, fail_count=0):
		self.output_data = output_data
		self.fail_count = fail_count
		self.prep_count = 0
		self.meas_count = 0
	
	def prepare(self, request: RequestObject) -> ResponseObject:
		self.prep_count += 1
		return ResponseObject()
	
	def measure(self, request: RequestObject) -> ResponseObject:
		self.meas_count += 1
		
		if self.meas_count <= self.fail_count:
			raise MeasureTimeout()
		
		return ResponseObject(measurement=self.output_data)
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"measure": [], "prepare": []}
	

class RandomMeter(Meter):
	def __init__(
		self,
		output_len: int,
		measure_delay: float,
		seed: Union[None, int, float, str, bytes, bytearray]=None
	) -> None:
		
		self._output_len = output_len
		self._measure_delay = measure_delay
		self._rng = random.Random(seed)
	
	def prepare(self, request: RequestObject) -> ResponseObject:
		return ResponseObject()
	
	def measure(self, request: RequestObject) -> ResponseObject:
		time.sleep(self._measure_delay)
		data = OutputData([self._rng.random() for _ in range(self._output_len)])
		return ResponseObject(measurement=data)
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"measure": [], "prepare": []}


class MockUniqueID(UniqueID):
	"""IDs are passed to the constructor and returned in the order given"""
	
	def __init__(self, id_iter: Iterable[int]) -> None:
		self._id_list = list(id_iter)
		self._id_list.reverse()
	
	def get_id(self) -> int:
		return self._id_list.pop()
	
	def exclude(self, ids: Iterable[int]) -> None:
		pass



class MockRandInt(PRNG):
	"""integers are passed to the constructor and returned in the order given
	
	The validity (a<=i<=b) is not checked.
	Shuffle does nothing.
	"""
	
	def __init__(self, int_iter: Iterable[int]) -> None:
		self._int_list = list(int_iter)
		self._int_list.reverse()
	
	def get_state(self) -> Any:
		return self._int_list
	
	def randint(self, a: int, b: int) -> int:
		return self._int_list.pop()
	
	def shuffle(self, a: Sequence) -> None:
		pass


class MockRepresentation(Representation):
	"""genes are passed to the constructor"""
	
	def __init__(self, gene_iter: Iterable[Gene]) -> None:
		self._gene_list = list(gene_iter)
	
	def prepare_config(self, config: TargetConfiguration) -> None:
		pass
	
	def decode(self, config: TargetConfiguration, chromo: Chromosome) -> None:
		pass
	
	def iter_genes(self) -> Iterable[Gene]:
		yield from self._gene_list


class MockDataSink(DataSink):
	"""calls to the write functions are recorded
	
	all_list with tuples (write_type, index__func) in order of the call, index_func is the number of the call of the
	specific write function
	all_map from write_type to list of data for each call
	"""
	def __init__(self) -> None:
		self.clear()
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		self.write_list.append((source, deepcopy(data_dict)))
	
	def clear(self):
		self.write_list = []
	
	def __enter__(self) -> "MockDataSink":
		self.clear()
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		return False
