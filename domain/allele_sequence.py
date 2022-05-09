#!/usr/bin/env python3

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence, Tuple, Any, List

@dataclass(frozen=True)
class Allele:
	values: Tuple[bool]
	description: str = field(compare=False)
	
	def __post_init__(self):
		super().__setattr__("values", tuple(self.values))

class AlleleSequence(Sequence):
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
	
	def __repr__(self):
		return f"AlleleList(alleles={self._alleles})"
		

class AlleleAll(AlleleSequence):
	"""all possible combinations of bit values"""
	
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
	
	def __repr__(self):
		return f"AlleleAll(bit_count={self.bit_count})"

class AllelePow(AlleleSequence):
	"""all possible output combinations of a LUT with used and unused inputs
	
	A LUT with i inputs has 2^i possible outputs (input combinations), which corresponds to
	the number of bits. Therefore there are 2^2^i possible combinations of
	outputs (i.e. sequence items).
	
	The output is independent from unused inputs. Hence if u inputs are unused,
	the number of bits remains 2^i, but the number of possible outputs
	reduces to 2^(i-u) and the number of possible combinations of outputs to 2^2^(i-u).
	"""
	
	def __init__(self, input_count: int, unused_inputs: Iterable[int]) -> None:
		if len(set(unused_inputs)) != len(unused_inputs):
			raise ValueError(f"unused input entered multiple times: {unused_inputs}")
		for u in unused_inputs:
			if u >= input_count:
				raise ValueError(f"input {u} not in inputs [0..{input_count-1}]")
		
		self._input_count = input_count
		self._unused = tuple(sorted(unused_inputs))
		self._used = tuple(i for i in range(input_count) if i not in self._unused)
		self._pos_outputs = pow(2, self._input_count-len(self._unused))
		self._output_map = self._create_output_map()
	
	def _create_output_map(self) -> List[Tuple[int, ...]]:
		"""create map from the bit of an AlleleSequence index (aka key)
		to the bits in an allele that have the same value
		"""
		output_map = []
		
		# create all combinations of unused inputs
		unused_combs = [self.insert_bits(i, self._used) for i in range(pow(2, len(self._unused)))]
		
		# iterate over possible outputs
		for in_comb in range(self._pos_outputs):
			# insert bits from unused outputs
			used_base = self.insert_bits(in_comb, self._unused)
			same_out = tuple(used_base|u for u in unused_combs)
			output_map.append(same_out)
		
		# as the index is sorted by lowest index last, while tuples of
		# bool are ordered by lowest index first, the index has to be reversed
		output_map.reverse()
		return output_map
	
	@property
	def input_count(self) -> int:
		return self._input_count
	
	@property
	def unused_inputs(self) -> Tuple[int, ...]:
		return self._unused
	
	def __len__(self) -> int:
		return pow(2, self._pos_outputs)
	
	def __getitem__(self, key: int) -> Allele:
		if key >= len(self) or key < 0:
			raise IndexError()
		
		tmp = [None] * (1 << self._input_count)
		index = key
		for i, out_bits in enumerate(self._output_map):
			bit_val = key%2==1
			key //= 2
			
			for bit_index in out_bits:
				tmp[bit_index] = bit_val
		
		return Allele(tuple(tmp), "{}".format(index))
	
	def __eq__(self, other: Any) -> bool:
		if isinstance(other, self.__class__):
			return self._input_count == other._input_count and self._unused == other._unused
		else:
			return NotImplemented
	
	def __hash__(self):
		return hash((self._input_count, self._unused))
	
	def __repr__(self):
		return f"AllelePow(input_count={self._input_count}, unused_inputs={self._unused})"
		
	def size_in_bits(self) -> float:
		return float(self._pos_outputs)
	
	def values_index(self, values: Iterable[bool]) -> int:
		index = 0
		for out_bits in reversed(self._output_map):
			index <<= 1
			value = values[out_bits[0]]
			
			for bit_index in out_bits:
				if values[bit_index] != value:
					raise ValueError(f"No allele with bit values {values}: is {value} at {out_bits[0]}, but {values[bit_index]} at {bit_index}")
			
			if value:
				index |= 1
		
		return index
	
	@staticmethod
	def delete_bit(value, bit_index):
		"""delete a single bit from an integer"""
		prefix = value & ((1 << bit_index) - 1)
		suffix = value ^ (value & ((1 << bit_index + 1) - 1))
		
		return (suffix >> 1) | prefix
	
	@classmethod
	def delete_bits(cls, value, bit_indices):
		"""delete multiple bits from an integer
		
		the bit indices are noted with respect to the original value
		e.g.: value = 0b01101010, bit_indices=(0, 2, 4) -> 0b00001111
		"""
		for offset, bit_index in enumerate(sorted(bit_indices)):
			value = cls.delete_bit(value, bit_index - offset)
		return value
	
	@staticmethod
	def insert_bit(value, bit_index):
		"""insert single bit in integer value
		
		the new bit is reset (i.e. 0)
		"""
		prefix = value & ((1 << bit_index) - 1)
		suffix = value ^ prefix
		
		return (suffix << 1) | prefix
	
	@classmethod
	def insert_bits(cls, value, bit_indices):
		"""insert multiple bits in integer value
		
		the bit indices are the inidices of the new bits after every bit was inserted
		e.g.: value=0b00001111, bit_indices=(0, 2, 4) -> 0b01101010
		"""
		for bit_index in bit_indices:
			value = cls.insert_bit(value, bit_index)
		
		return value
	
