"""Intermediate representation of a FPGA structure

The intermediate representation is created from chip database entries.
Afterwards it is modified to fit the specific requirements of  the
current request (e.g. available nets and connections between them).

The final used representation is created from this intermediate
representation. This is necessary as the final usage of the
representation has different requirements (easy storage, simple access)
than the during the creation of the representation (easy modification).

The basic idea is to have a directed graph with potential connections
between nets as edges configurabel elements as vertices (e.g. group of
all bits that define the driver of a net, a LUT). The configurable
elements define how the output id derived from the input (e.g. by
selecting an input).

Multiedges are possible, if a net has two different names that both can
drive the same net.
"""

from dataclasses import dataclass
from functools import total_ordering
from typing import Iterable, Union, Any

from .chip_data_utils import NetData
from .misc import IcecraftNetPosition, IcecraftLUTPosition

@total_ordering
@dataclass(frozen=True, order=False)
class VertexDesig:
	position: Union[IcecraftNetPosition, IcecraftLUTPosition]
	
	def __lt__(self, other: Any) -> bool:
		try:
			return self.position < other.position
		except TypeError:
			# compare IcecraftNetPosition and IcecraftLUTPosition
			if isinstance(self.position, IcecraftLUTPosition):
				# IcecraftLUTPosition is smallest
				return True
			elif isinstance(other.position, IcecraftLUTPosition):
				return False
			else:
				# chould not occur: position is not the same type, both are not IcecraftLUTPosition
				# and there are only 2 possible types
				return NotImplemented
		except AttributeError:
			return NotImplemented
	
	@property
	def tile(self):
		return self.position.tile

@dataclass(frozen=True, order=True)
class EdgeDesig:
	src: VertexDesig
	dst: VertexDesig

@dataclass(frozen=True)
class InterElement:
	rep: "InterRep"

class InterRep:
	def __init__(self, net_data_iter: Iterable[NetData]) -> None:
		pass
