from enum import auto, Enum
from typing import Any

from adapters.hdf5_sink import IgnoreValue


class DriverType(Enum):
	FPGA = auto()
	DRVMTR = auto()
	DUMMY = auto()


def ignore_same(x: list) -> Any:
	"""raise IgnoreValue of first two elements are equal, else return the last
	
	That way a third value can be rejected when two other values are identical
	"""
	if x[0] == x[1]:
		raise IgnoreValue()
	return x[-1]
