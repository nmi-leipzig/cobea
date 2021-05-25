from types import TracebackType
from typing import Any, Iterable, Mapping, Optional, Union, Type

from domain.base_structures import BitPos
from domain.data_sink import DataSink, DoneReq
from domain.interfaces import MeasureTimeout, Meter, PRNG, Representation, TargetConfiguration, TargetDevice,\
TargetManager, UniqueID
from domain.model import OutputData, Gene, Chromosome
from domain.request_model import RequestObject, Parameter

class MockBitPos(BitPos, int):
	pass

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
		self.devices = {s: MockTargetDevice(s, hardware_type) for s in range(size)}
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
	
	def prepare(self, request: RequestObject) -> None:
		self.prep_count += 1
	
	def measure(self, request: RequestObject) -> OutputData:
		self.meas_count += 1
		
		if self.meas_count <= self.fail_count:
			raise MeasureTimeout()
		
		return self.output_data
	
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

class MockRandInt(PRNG):
	"""integers are passed to the constructor and returned in the order given
	
	The validity (a<=i<=b) is not checked.
	"""
	
	def __init__(self, int_iter: Iterable[int]) -> None:
		self._int_list = list(int_iter)
		self._int_list.reverse()
	
	def seed(self, int) -> None:
		pass
	
	def randint(self, a: int, b: int) -> int:
		return self._int_list.pop()

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
	
	def write_metadata(self, name: str, data: Any, data_type: type, multiple=False) -> None:
		self.all_list.append(("meta", len(self.all_map["meta"])))
		self.all_map["meta"].append((name, data, data_type, multiple))
	
	def write_request(self, req_data: DoneReq) -> None:
		self.all_list.append(("req", len(self.all_map["req"])))
		self.all_map["req"].append(req_data)
	
	def clear(self):
		self.all_list = []
		self.all_map = {"meta": [], "req": []}
	
	def __enter__(self) -> "MockDataSink":
		self.clear()
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		pass
