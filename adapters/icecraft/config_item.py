#!/usr/bin/env python3
from abc import ABC, abstractmethod, abstractproperty
from dataclasses import dataclass
from typing import Tuple

from adapters.icecraft.misc import IcecraftBitPosition

@dataclass(frozen=True)
class ConfigItem:
	bits: Tuple[IcecraftBitPosition, ...]
	kind: str
	
	@property
	def identifier(self) -> str:
		return f"{self.bits[0].x:02d}{self.bits[0].y:02d}_{self.kind}"

@dataclass(frozen=True)
class IndexedItem(ConfigItem):
	index: int
	
	@property
	def identifier(self) -> str:
		return f"{self.bits[0].x:02d}{self.bits[0].y:02d}_{self.kind}_{self.index}"

@dataclass(frozen=True)
class ConnectionItem(ConfigItem):
	dst_net: str
	values: Tuple[Tuple[bool, ...], ...]
	src_nets: Tuple[str, ...]
	
	def __post_init__(self):
		assert len(self.values) == len(self.src_nets)
		assert all(len(v)==len(self.bits) for v in self.values)
	
	@property
	def identifier(self) -> str:
		return f"{self.bits[0].x:02d}{self.bits[0].y:02d}_{self.kind}_{self.dst_net}"

@dataclass(frozen=True)
class NamedItem(ConfigItem):
	name: str
	
	@property
	def identifier(self) -> str:
		return f"{self.bits[0].x:02d}{self.bits[0].y:02d}_{self.kind}_{self.name}"
