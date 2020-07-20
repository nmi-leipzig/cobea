#!/usr/bin/env python3

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Tuple, TypeVar, Generic, Union, Any, List, Sequence

class TargetConfiguration(ABC):
	@abstractmethod
	def to_text(self) -> str:
		raise NotImplementedError()

class InputData(tuple):
	pass

class OutputData(tuple):
	pass

FitnessFunctionImpl = Callable[[InputData, OutputData], float]

@dataclass(frozen=True)
class FitnessFunction:
	identifier: str
	description: str
	implementation: FitnessFunctionImpl
	
	def __call__(self, input_data: InputData, output_data: OutputData) -> float:
		return self.implementation(input_data, output_data)

PreprocessingImpl = Callable[[InputData, OutputData], Tuple[InputData, OutputData]]

@dataclass(frozen=True)
class Preprocessing:
	identifier: str
	description: str
	implementation: PreprocessingImpl
	
	def __call__(self, input_data: InputData, output_data: OutputData) -> Tuple[InputData, OutputData]:
		return self.implementation(input_data, output_data)

class BitPosition(ABC):
	pass

@dataclass(frozen=True)
class Allele:
	values: Sequence[bool]
	description: str

@dataclass(frozen=True)
class Gene:
	bit_positions: Sequence[BitPosition]
	alleles: Sequence[Allele]
	description: str

@dataclass(frozen=True)
class Chromosome:
	identifier: int
	allele_indices: Tuple[int]
	
	def __getitem__(self, key):
		return self.allele_indices[key]

