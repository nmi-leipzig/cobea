from enum import Enum, auto
from dataclasses import dataclass
from typing import Tuple, Iterable

from .ice_board.device_data import BRAMMode, TilePosition

from domain.model import BitPosition, Gene

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

@dataclass(frozen=True)
class IcecraftPosition:
	tile: TilePosition
	
	@property
	def x(self):
		return self.tile.x
	
	@property
	def y(self):
		return self.tile.y
	
	@classmethod
	def from_coords(cls, x: int, y: int, *args, **kwargs):
		return cls(TilePosition(x, y), *args, **kwargs)
	

@dataclass(frozen=True, order=True)
class IcecraftBitPosition(BitPosition, IcecraftPosition):
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
		return IcecraftNetPosition(self.tile, self.src_name)
	
	@property
	def dst(self):
		return IcecraftNetPosition(self.tile, self.dst_name)

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
