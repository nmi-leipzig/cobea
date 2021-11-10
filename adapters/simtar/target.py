from domain.interfaces import TargetConfiguration, TargetDevice

from .pos import SimtarBitPos


class SimtarDev(TargetDevice):
	"""Device for simple target"""
	count = 0
	
	def __init__(self) -> None:
		self._sn = str(self.count)
		self.count += 1
		self._lut = [False]*16
		self._active = False
		self._input = 0
	
	def serial_number(self) -> str:
		self._sn
	
	def hardware_type(self) -> str:
		return "SIMPLETARGET"
	
	def configure(self, configuration: TargetConfiguration) -> None:
		# first 16 bits are LUT entries
		self._lut = [b for b in configuration.get_multi_bits([SimtarBitPos(i) for i in range(16)])]
		# 17th bit is activation flag
		self._active = configuration.get_bit(SimtarBitPos(16))
	
	def read_bytes(self, size: int) -> bytes:
		if self._active:
			return b"\x01" if self._lut[self._input] else b"\x00"
		else:
			return b"\xff"
	
	def write_bytes(self, data: bytes) -> int:
		if len(data) == 0:
			return 0
		
		self._input = data[0] & 0x0f
		
		return 1

