from typing import Any, Union, Mapping, Iterable

from domain.base_structures import BitPos
from domain.interfaces import TargetDevice, TargetConfiguration, TargetManager, Meter, UniqueID, PRNG, Representation
from domain.model import OutputData, Gene, Chromosome
from domain.request_model import RequestObject, Parameter

class MockBitPos(BitPos, int):
	pass

class MockTargetDevice(TargetDevice):
	def __init__(self, serial_number="9555", hardware_type="S6C7"):
		self._serial_number = serial_number
		self._hardware_type = hardware_type
	
	@property
	def serial_number(self) -> str:
		return self._serial_number
	
	@property
	def hardware_type(self) -> str:
		return self._hardware_type
	
	def configure(self, configuration: TargetConfiguration) -> None:
		pass
	
	def read_bytes(self, size: int) -> bytes:
		return bytes((7,))*size
	
	def write_bytes(self, data: bytes) -> int:
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
	def __init__(self, output_data: OutputData):
		self.output_data = output_data
	
	def measure(self, target: TargetDevice, request: RequestObject) -> OutputData:
		return self.output_data
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"__call__": []}
	

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
