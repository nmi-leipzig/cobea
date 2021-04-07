from enum import Enum, auto
from dataclasses import dataclass
from typing import Tuple, Iterable

from .ice_board.device_data import BRAMMode

from domain.base_structures import BitPos
from domain.model import Gene
from domain.interfaces import ElementPosition

TILE_EXTERNAL_BITS = -1
TILE_ALL = -2
TILE_ALL_LOGIC = -3

class LUTFunction(Enum):
	CONST_0 = auto()
	CONST_1 = auto()
	AND = auto()
	OR = auto()
	NAND = auto()
	NOR = auto()
	PARITY = auto()

@dataclass(frozen=True, order=True)
class IcecraftPosition(ElementPosition):
	x: int
	y: int
	
	@property
	def tile(self) -> "IcecraftPosition":
		return IcecraftPosition(self.x, self.y)
	
	@classmethod
	def from_tile(cls, tile: "IcecraftPosition", *args, **kwargs):
		return cls(tile.x, tile.y, *args, **kwargs)

@dataclass(frozen=True, order=True)
class IcecraftBitPosition(BitPos, IcecraftPosition):
	group: int
	index: int

@dataclass(frozen=True, order=True)
class IcecraftLUTPosition(IcecraftPosition):
	z: int

class IcecraftColBufCtrl(IcecraftLUTPosition):
	"""Describes a column buffer control"""
	pass

@dataclass(frozen=True, order=True)
class IcecraftNetPosition(IcecraftPosition):
	name: str

class IcecraftResource(IcecraftNetPosition):
	"""Resource in a tile
	
	Resource can be a net or a LUT
	"""
	pass

@dataclass(frozen=True, order=True)
class IcecraftConnection(IcecraftPosition):
	src_name: str
	dst_name: str
	
	@property
	def src(self):
		return IcecraftNetPosition(self.x, self.y, self.src_name)
	
	@property
	def dst(self):
		return IcecraftNetPosition(self.x, self.y, self.dst_name)

class IcecraftResCon(IcecraftConnection):
	"""Connection between ressources"""
	pass

@dataclass(frozen=True, order=True)
class IcecraftGeneConstraint:
	"""Constraint for genes
	
	Allows for restricting allele values, reordering of bits and
	grouping of genes to 'super gene".
	"""
	bits: Tuple[IcecraftBitPosition, ...]
	values: Iterable[Tuple[bool, ...]]

class IcecraftError(Exception):
	"""Base class for exceptions in icecraft"""
	pass

class IcecraftInputError(IcecraftError):
	"""Error in input"""
	pass

class IcecraftSatisfiabilityError(IcecraftError):
	"""Condition for representation or unsatisfiable"""
	pass
