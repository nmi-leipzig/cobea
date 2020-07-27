#!/usr/bin/env python3

import collections
import math
from dataclasses import dataclass, field
from typing import Iterable, Tuple, Any

@dataclass(frozen=True)
class Allele:
	values: Tuple[bool]
	description: str = field(compare=False)
	
	def __post_init__(self):
		super().__setattr__("values", tuple(self.values))

class AlleleSequence(collections.Sequence):
	"""base class for collections of alleles"""
	
	def size_in_bits(self) -> float:
		"""Return amount of bits required to represent this AlleleSequence
		
		Fractions of bits are possible.
		"""
		return math.log2(len(self))
	
	def values_index(self, values: Iterable[bool]) -> int:
		"""return index of passed bit values"""
		raise NotImplementedError()

class AlleleList(AlleleSequence):
	"""simple list of alleles"""
	
	def __init__(self, alleles: Iterable[Allele]) -> None:
		#self._allele_list = sorted(alleles, key=lambda a:a.values)
		self._alleles = tuple(alleles)
	
	def __len__(self) -> int:
		return len(self._alleles)
	
	def __getitem__(self, key: int) -> Allele:
		return self._alleles[key]
	
	def __eq__(self, other: Any) -> bool:
		if isinstance(other, self.__class__):
			return self._alleles == other._alleles
		else:
			return NotImplemented
	
	def __hash__(self):
		return hash(self._alleles)
	
	def values_index(self, values: Iterable[bool]) -> int:
		values_tup = tuple(values)
		for i, allele in enumerate(self._alleles):
			if allele.values == values_tup:
				return i
		raise ValueError("No allele with bit values {}".format(values))
	
	def is_complete(self) -> bool:
		"""are all possible combinations in the list"""
		if len(self) == 0 or len(self) < 2**len(self[0]):
			return False
		
		# check uniqueness of elements
		assert len(self) == len(set(self))
		
		return True

class AlleleAll(AlleleSequence):
	"""all possible combinations of the list"""
	
	def __init__(self, bit_count: int) -> None:
		self._bit_count = bit_count
	
	def __len__(self) -> int:
		return pow(2, self._bit_count)
	
	def __getitem__(self, key: int) -> Allele:
		if key >= len(self) or key < 0:
			raise IndexError()
		
		tmp = []
		index = key
		for i in range(self._bit_count):
			tmp.append(key%2==1)
			key //= 2
		
		tmp.reverse()
		
		return Allele(tuple(tmp), "{}".format(index))
	
	def __eq__(self, other: Any) -> bool:
		if isinstance(other, self.__class__):
			return self._bit_count == other._bit_count
		else:
			return NotImplemented
	
	def __hash__(self):
		return hash(self._bit_count)
	
	@property
	def bit_count(self) -> int:
		return self._bit_count
	
	def size_in_bits(self) -> float:
		return float(self.bit_count)
	
	def values_index(self, values: Iterable[bool]) -> int:
		if len(values) != self.bit_count:
			raise ValueError("No allele with bit values {}".format(values))
		
		index = 0
		for value in values:
			index <<= 1
			if value:
				index |= 1
		
		return index
