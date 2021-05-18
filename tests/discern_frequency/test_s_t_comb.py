from unittest import TestCase

from applications.discern_frequency.s_t_comb import lexicographic_combinations, position_to_binary, combinations_count

def is_s_t_combination(s: int, t: int, comb: int) -> bool:
	""" return True iff comb represents a (s, t)-combination"""
	b = bin(comb)[2:]
	ones = b.count("1")
	zeros = b.count("0")
	# leading zeros are left out -> there can be less
	return t == ones and s >= zeros

class STCombTest(TestCase):
	def test_meta_is_s_t_combination(self):
		test_cases = (
			(1, 1, 0b00, False),
			(1, 1, 0b01, True),
			(1, 1, 0b10, True),
			(1, 1, 0b11, False),
			(1, 1, 0b100, False),
			(2, 1, 0b100, True),
			(2, 1, 0b101, False),
			(3, 3, 0b000111, True),
			(3, 3, 0b111000, True),
			(3, 3, 0b1110000, False),
		)
		
		for s, t, comb, exp in test_cases:
			with self.subTest(s=s, t=t, comb=bin(comb)):
				res = is_s_t_combination(s, t, comb)
				self.assertEqual(exp, res)
	
	def test_position_to_binary(self):
		test_cases = (
			([0], 0b1),
			([1], 0b10),
			([0, 1], 0b11),
			([2], 0b100),
			([0, 2], 0b101),
			([0, 1, 2], 0b111),
			([3, 4, 5], 0b111000),
		)
		
		for pos_comb, bin_comb in test_cases:
			with self.subTest(pos_comb=pos_comb, bin_comb=bin(bin_comb)):
				res = position_to_binary(pos_comb)
				self.assertEqual(bin_comb, res)
	
	def test_lexicographic_combinations_precomputed(self):
		"""compare combinations to precomputed correct results"""
		test_cases = (
			(1, 1, [0b01, 0b10]),
			(2, 1, [0b001, 0b010, 0b100]),
			(2, 2, [0b0011, 0b0101, 0b0110, 0b1001, 0b1010, 0b1100]),
			(2, 3, [0b00111, 0b01011, 0b01101, 0b01110, 0b10011, 0b10101, 0b10110, 0b11001, 0b11010, 0b11100]),
			(3, 2, [0b00011, 0b00101, 0b00110, 0b01001, 0b01010, 0b01100, 0b10001, 0b10010, 0b10100, 0b11000]),
		)
		
		for s, t, exp in test_cases:
			with self.subTest(s=s, t=t):
				res = lexicographic_combinations(s, t)
				self.assertEqual(exp, res)
	
	def test_lexicographic_combinations_plausible(self):
		"""check combinations for plausibility"""
		test_cases = ((5, 5), (3, 4), (4, 3))
		
		for s, t in test_cases:
			with self.subTest(s=s, t=t):
				res = lexicographic_combinations(s, t)
				# check correctness
				for c in res:
					self.assertTrue(is_s_t_combination(s, t, c))
				# check uniqueness
				comb_set = set(res)
				self.assertEqual(len(res), len(comb_set))
				# check completeness
				exp_count = combinations_count(s, t)
				self.assertEqual(exp_count, len(res))
				# check order
				for i in range(len(res)-1):
					self.assertTrue(res[i] < res[i+1], f"Wrong order {bin(res[i])} before {bin(res[i+1])}")
	
	def test_combinations_count(self):
		test_cases = (
			(0, 0, 1),
			(0, 1, 1),
			(1, 0, 1),
			(1, 1, 2),
			(2, 2, 6),
			(5, 5, 252),
		)
		
		for s, t, exp in test_cases:
			with self.subTest(s=s, t=t):
				res = combinations_count(s, t)
				self.assertEqual(exp, res)
