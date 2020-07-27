import os
import sys
from enum import Enum, auto
from dataclasses import dataclass

sys.path.append(
	os.path.join(
		os.path.dirname(
			os.path.dirname(
				os.path.dirname(
					os.path.dirname(os.path.abspath(__file__))
				)
			)
		),
		"components",
		"board"
	)
	
)
from device_data import BRAMMode, TilePosition

from domain.model import BitPosition

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
	def from_coords(cls, x, y, *args, **kwargs):
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
	net: str


