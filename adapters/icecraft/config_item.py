#!/usr/bin/env python3
from abc import ABC, abstractmethod, abstractproperty
from dataclasses import dataclass
from typing import Tuple

from .misc import IcecraftBitPosition

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
	
	@property
	def identifier(self) -> str:
		return f"{self.bits[0].x:02d}{self.bits[0].y:02d}_{self.kind}_{self.dst_net}"
