#!/usr/bin/env python3

import unittest

from domain.allele_sequence import Allele, AlleleAll, AlleleList

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
	
