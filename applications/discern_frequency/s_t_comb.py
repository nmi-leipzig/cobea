"""Module for (s, t)-combinations

An (s, t)-combination is used as defined by Donald Knuth in "The Art of Computer Programming"
Volume 4 Fascicle 3A 7.2.1.3. I.e. a selection of t out of n objects (n = s + t).

The most interessting representation is  a_n-1...a_1 a_0 with a_i in {0, 1}, 0 for a unselected
element and 1 for a selected element. E.g. 01110 and 10101 are (2, 3)-combinations.
"""

from typing import List, Iterable
import itertools
import math

def position_to_binary(position_list: List[int]) -> int:
	"""Convert the representation of a combination by list of position to binary.
	
	E.g. [0, 2, 4] -> 10101
	"""
	res = 0
	for i in position_list:
		res |= 1 << i
	return res

def lexicographic_combinations(s: int, t: int) -> List[int]:
	"""Generate all valid (s, t)-combination in lexicographic order.
	
	Each combination is represented as integer a_n-1 ... a_1 a_0.
	"""
	pos_lists = itertools.combinations(range(s+t), t)
	bin_list = [position_to_binary(p) for p in pos_lists]
	
	return list(bin_list)
