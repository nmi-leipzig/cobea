#!/usr/bin/env python3

"""Entities representing enterprise rules

Ideally entities would not depend on anything. Yet as FPGAs are not mere devices, but also essential target of the 
whole enterprise logic, some entities also depend on device specific structures. These structures are called
"base structures" and will be kept to a minimum.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Tuple, TypeVar, Generic, Union, Any, Sequence

from domain.allele_sequence import Allele, AlleleSequence, AlleleList, AlleleAll
from .base_structures import BitPos

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

@dataclass(frozen=True)
class Gene:
	bit_positions: Tuple[BitPos, ...]
	alleles: AlleleSequence
	# human readable description of the gene function
	# should not be relevant for the function itself
	description: str = field(compare=False)

@dataclass(frozen=True)
class Chromosome:
	identifier: int
	allele_indices: Tuple[int, ...]
	
	def __getitem__(self, key):
		return self.allele_indices[key]

class ElementPosition(ABC):
	pass

PosTransImpl = Callable[[Sequence[ElementPosition]], Sequence[ElementPosition]]

@dataclass(frozen=True)
class PosTrans:
	# transformation of element positions
	identifier: str
	description: str
	implementation: PosTransImpl
	
	def __call__(self, in_positions: Sequence[ElementPosition]) -> Sequence[ElementPosition]:
		return self.implementation(in_positions)
