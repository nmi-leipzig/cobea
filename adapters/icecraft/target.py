import os
from typing import List, Union

from .ice_board import FPGABoard, FPGAManager

from domain.interfaces import TargetDevice, TargetManager, TargetConfiguration

HX8K_BOARD = "ICE40HX8K-B-EVN"

class IcecraftDevice(TargetDevice):
	"""ice device"""
	
	def __init__(self, device: FPGABoard) -> None:
		self._device = device
	
	@property
	def serial_number(self) -> str:
		return self._device.serial_number
	
	@property
	def hardware_type(self) -> str:
		return HX8K_BOARD
	
	def close(self) -> None:
		self._device.close()
	
	def flush(self) -> None:
		self._device.flush()
	
	def reset(self) -> None:
		self._device.reset_buffer(True, True)
	
	def configure(self, configuration: TargetConfiguration) -> None:
		# just use the configuration as if it was for the correct device
		
		base_name = "gen_tmp"
		bitstream_name = f"{base_name}.bin"
		# write bin
		configuration.write_bitstream(bitstream_name)
		
		# flash
		self._device.flash_bitstream(bitstream_name)
		
		# remove asc and bin file
		os.remove(bitstream_name)
	
	def read_bytes(self, size: int) -> bytes:
		return self._device.uart.read(size)
	
	def write_bytes(self, data: bytes) -> int:
		return self._device.uart.write(data)

class IcecraftManager(TargetManager):
	"""simple management of icecraft devices without concurrency"""
	
	def __init__(self) -> None:
		self._in_use = set()
	
	def acquire(self, serial_number: Union[str, None] = None) -> TargetDevice:
		if serial_number is None:
			device = FPGABoard.get_suitable_board(black_list=self._in_use)
			serial_number = device.serial_number
		else:
			if serial_number in self._in_use:
				raise ValueError(f"FPGA with serial number {serial_number} already in use")
			device = FPGABoard(serial_number)
		
		self._in_use.add(serial_number)
		icd = IcecraftDevice(device)
		icd.reset()
		
		return icd
	
	def release(self, target: TargetDevice) -> None:
		self._in_use.remove(target.serial_number)
		target.close()
	
	def stuck_workaround(self, serial_number: str) -> None:
		"""Workaround for stuck FPGAs.
		
		The problem seems to occur when not correctly releasing FPGAs in combination with writes. Therefore it is 
		assumed that the cause are messed up transfer buffers.
		"""
		tar = self.acquire(serial_number)
		tar.write_bytes(b"\x00")
		self.release(tar)
	
	@staticmethod
	def get_present_serial_numbers() -> List[str]:
		return FPGABoard.get_suitable_serial_numbers()
	
	@classmethod
	def device_present(cls) -> bool:
		return len(cls.get_present_serial_numbers()) < 1

class MultiIcecraftManager(TargetManager):
	"""management of ice devices in multiprocessing environments"""
	
	def __init__(self) -> None:
		self._fpga_manager = FPGAManager.create_manager()
	
	def acquire(self, serial_number: Union[str, None]) -> TargetDevice:
		raise NotImplementedError()
	
	def release(self, target: TargetDevice) -> None:
		raise NotImplementedError()

