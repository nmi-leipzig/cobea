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
