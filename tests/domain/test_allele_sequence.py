#!/usr/bin/env python3

import unittest
import math
from typing import NamedTuple, Tuple, List

from domain.allele_sequence import Allele, AlleleAll, AlleleList, AllelePow

class AlleleTest(unittest.TestCase):
	def test_eq(self):
		a = Allele((True, True, False), "original")
		with self.subTest():
			self.assertTrue(a==a)
		
		for vals, desc, exp in (
			(a.values, a.description, True),
			(a.values, "other", True),
			((False, )*3, "other", False),
			((False, )*3, a.description, False),
			((True, )*4, a.description, False),
			((True, )*2, a.description, False),
		):
			b = Allele(vals, desc)
			with self.subTest():
				self.assertEqual(a==b, exp)

class AlleleListTest(unittest.TestCase):
	def setUp(self):
		self.exp_alleles = [
			Allele((False, False, False), "first"),
			Allele((False, True, False), "second"),
			Allele((False, False, True), "third"),
			Allele((True, False, True), "fourth"),
		]
	
	def test_creation(self):
		alleles = AlleleList(self.exp_alleles)
	
	def test_len(self):
		alleles = AlleleList(self.exp_alleles)
		
		exp_len = len(self.exp_alleles)
		self.assertEqual(exp_len, len(alleles), f"Length should be {exp_len}")
	
	def test_getitem(self):
		alleles = AlleleList(self.exp_alleles)
		
		exp_len = len(self.exp_alleles)
		self.assertEqual(self.exp_alleles, [alleles[i] for i in range(exp_len)], "Wrong allele for index")
	
	def test_values_index(self):
		alleles = AlleleList(self.exp_alleles)
		
		for index, allele in enumerate(self.exp_alleles):
			with self.subTest(allele=allele):
				self.assertEqual(index, alleles.values_index(allele.values), "Wrong index for allele")
	
	def test_values_index_error(self):
		alleles = AlleleList(self.exp_alleles)
		
		with self.assertRaises(ValueError):
			alleles.values_index((True, )*3)

class AlleleAllTest(unittest.TestCase):
	def setUp(self):
		self.exp_alleles_dict = {
			1:[
				Allele((False, ), "0"),
				Allele((True, ), "1"),
			],
			2: [
				Allele((False, False), "0"),
				Allele((False, True), "1"),
				Allele((True, False), "2"),
				Allele((True, True), "3"),
			],
			3: [
				Allele((False, False, False), "0"),
				Allele((False, False, True), "1"),
				Allele((False, True, False), "2"),
				Allele((False, True, True), "3"),
				Allele((True, False, False), "4"),
				Allele((True, False, True), "5"),
				Allele((True, True, False), "6"),
				Allele((True, True, True), "7"),
			]
		}
	
	def create(self, bit_count):
		return AlleleAll(bit_count), self.exp_alleles_dict[bit_count]
	
	def test_creation(self):
		for bit_count in self.exp_alleles_dict:
			with self.subTest(bit_count=bit_count):
				alleles, exp_alleles = self.create(bit_count)
	
	def test_len(self):
		for bit_count in self.exp_alleles_dict:
			with self.subTest(bit_count=bit_count):
				alleles, exp_alleles = self.create(bit_count)
				
				exp_len = len(exp_alleles)
				self.assertEqual(exp_len, len(alleles), f"Length should be {exp_len}")
	
	def test_getitem(self):
		for bit_count in self.exp_alleles_dict:
			with self.subTest(bit_count=bit_count):
				alleles, exp_alleles = self.create(bit_count)
				
				for index, allele in enumerate(exp_alleles):
					with self.subTest(index=index):
						self.assertEqual(allele, alleles[index], "Wrong allele for index")
	
	def test_values_index(self):
		for bit_count in self.exp_alleles_dict:
			with self.subTest(bit_count=bit_count):
				alleles, exp_alleles = self.create(bit_count)
				
				for index, allele in enumerate(exp_alleles):
					with self.subTest(allele=allele):
						self.assertEqual(index, alleles.values_index(allele.values), "Wrong index for allele")
	
	def test_values_index_error(self):
		for bit_count in self.exp_alleles_dict:
			with self.subTest(bit_count=bit_count):
				alleles, exp_alleles = self.create(bit_count)
				with self.assertRaises(ValueError):
					alleles.values_index((True, )*(bit_count-1))
	

class AllelePowTest(unittest.TestCase):
	class AllelePowTestData(NamedTuple):
		desc: str
		input_count: int
		unused_inputs: Tuple[int, ...]
		alleles: Tuple[Allele, ...]
		output_map: List[Tuple[int, ...]]
		
	
	test_cases = (
		AllelePowTestData(
			"no unused inputs, 1 input", 1, tuple(),
			(
				Allele((False, False), "0"),
				Allele((False, True), "1"),
				Allele((True, False), "2"),
				Allele((True, True), "3"),
			),
			[(1, ), (0, )]
		),
		AllelePowTestData(
			"all inputs unused, 1 input", 1, (0, ),
			(
				Allele((False, False), "const 0"),
				Allele((True, True), "const 1"),
			),
			[(0, 1)]
		),
		AllelePowTestData(
			"all inputs unused, 3 inputs", 3, (0, 1, 2),
			(
				Allele((False, )*8, "const 0"),
				Allele((True, )*8, "const 1"),
			),
			[(0, 1, 2, 3, 4, 5, 6, 7)]
		),
		AllelePowTestData(
			"two inputs, first unused", 2, (0, ),
			(
				Allele((False, False, False, False), "0"),
				Allele((False, False, True, True), "1"),
				Allele((True, True, False, False), "2"),
				Allele((True, True, True, True), "3"),
			),
			[(2, 3), (0, 1)]
		),
		AllelePowTestData(
			"two inputs, second unused", 2, (1, ),
			(
				Allele((False, False, False, False), "0"),
				Allele((False, True, False, True), "1"),
				Allele((True, False, True, False), "2"),
				Allele((True, True, True, True), "3"),
			),
			[(1, 3), (0, 2)]
		),
	)
	
	def create_instance(self, test_case):
		return AllelePow(test_case.input_count, test_case.unused_inputs)
	
	def test_creation(self):
		for test_case in self.test_cases:
			with self.subTest(desc=test_case.desc):
				self.create_instance(test_case)
	
	def test_output_map(self):
		for test_case in self.test_cases:
			with self.subTest(desc=test_case.desc):
				dut = self.create_instance(test_case)
				
				# plausibility check
				len_sum = 0
				full_set = set()
				for s in dut._output_map:
					len_sum += len(s)
					full_set.update(s)
				
				self.assertEqual(len_sum, len(full_set), "Inconsistent length; Doublicated values?")
				self.assertEqual(set(range(pow(2, test_case.input_count))), full_set)
				
				self.assertEqual(test_case.output_map, dut._output_map)
	
	def test_len(self):
		for test_case in self.test_cases:
			with self.subTest(desc=test_case.desc):
				dut = self.create_instance(test_case)
				exp_len = len(test_case.alleles)
				
				self.assertEqual(exp_len, len(dut))
	
	def test_getitem(self):
		for test_case in self.test_cases:
			with self.subTest(desc=test_case.desc):
				dut = self.create_instance(test_case)
				
				for index, exp_allele in enumerate(test_case.alleles):
					self.assertEqual(exp_allele, dut[index])
	
	def test_values_index(self):
		for test_case in self.test_cases:
			with self.subTest(desc=test_case.desc):
				dut = self.create_instance(test_case)
				
				for exp_index, allele in enumerate(test_case.alleles):
					self.assertEqual(exp_index, dut.values_index(allele.values))
	
	def check_eq(self, a, b, exp):
		res = (a == b)
		self.assertEqual(exp, res)
		res = (b == a)
		self.assertEqual(exp, res)
	
	def test_eq(self):
		for tc_a in self.test_cases:
			for tc_b in self.test_cases:
				with self.subTest(desc=f"'{tc_a.desc}' == '{tc_b.desc}'"):
					a = self.create_instance(tc_a)
					b = self.create_instance(tc_b)
					exp = (tc_a == tc_b)
					
					self.check_eq(a, b, exp)
		
		for i in range(1, 5):
			with self.subTest(desc=f"AlleleAll == AllelePow for {i}"):
				dut_1 = AlleleAll(i)
				dut_2 = AllelePow(i, [])
				
				self.check_eq(dut_1, dut_2, False)
	
	def test_size_in_bits(self):
		for test_case in self.test_cases:
			with self.subTest(desc=test_case.desc):
				dut = self.create_instance(test_case)
				exp_len = math.log2(len(test_case.alleles))
				
				self.assertEqual(exp_len, dut.size_in_bits())
		
	
	def generic_delete_bit_test(self, delete_func):
		test_cases = (
			(0b00000000, 3, 0b00000000),
			(0b11111111, 4, 0b01111111),
			(0b11001100, 0, 0b01100110),
			(0b11001100, 3, 0b01100100),
			(0b11001100, 10, 0b11001100),
			(0b1101101001011000, 10, 0b0110111001011000),
		)
		
		for value, bit_index, exp in test_cases:
			with self.subTest(desc=f"delete bit {bit_index:2d} of {value:08b}"):
				res = delete_func(value, bit_index)
				self.assertEqual(exp, res, f"{exp:08b} != {res:08b}")
	
	def test_delete_bit(self):
		self.generic_delete_bit_test(AllelePow.delete_bit)
	
	def generic_delete_bits(self, delete_func):
		test_cases = (
			(0b00000000, (0, 3), 0b00000000),
			(0b01001110, (4, ), 0b00101110),
			(0b01001110, (1, 3), 0b00010010),
			(0b11110101, (2, 4, 6), 0b00011001),
		)
		
		for value, bit_indices, exp in test_cases:
			with self.subTest(desc=f"delete bits {bit_indices} of {value:08b}"):
				res = delete_func(value, bit_indices)
				self.assertEqual(exp, res, f"{exp:08b} != {res:08b}")
	
	def test_delete_bits(self):
		self.generic_delete_bits(AllelePow.delete_bits)
	
	def generic_insert_bit_test(self, insert_func):
		test_cases = (
			(0b00000000, 3, 0b00000000),
			(0b01111111, 4, 0b11101111),
			(0b01100110, 0, 0b11001100),
			(0b01100100, 3, 0b11000100),
			(0b11001100, 10, 0b11001100),
			(0b0110111001011000, 10, 0b1101101001011000),
		)
		
		for value, bit_index, exp in test_cases:
			with self.subTest(value=value, bit_index=bit_index):
				res = insert_func(value, bit_index)
				self.assertEqual(exp, res, f"{exp:08b} != {res:08b}")
	
	def test_insert_bit(self):
		self.generic_insert_bit_test(AllelePow.insert_bit)
	
	def generic_insert_bits_test(self, insert_func):
		test_cases = (
			(0b00000000, (0, 3), 0b00000000),
			(0b00101110, (4, ), 0b01001110),
			(0b00010010, (1, 3), 0b01000100),
			(0b00011001, (2, 4, 6), 0b10100001),
		)
		
		for value, bit_indices, exp in test_cases:
			with self.subTest(value=value, bit_indices=bit_indices):
				res = insert_func(value, bit_indices)
				self.assertEqual(exp, res, f"{exp:08b} != {res:08b}")
		
	
	def test_insert_bits(self):
		self.generic_insert_bits_test(AllelePow.insert_bits)
	
