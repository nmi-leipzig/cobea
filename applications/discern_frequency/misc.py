from enum import auto, Enum

class DriverType(Enum):
	FPGA = auto()
	DRVMTR = auto()
	DUMMY = auto()
