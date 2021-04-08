import unittest

from domain.model import Chromosome

class ChromosomeTest(unittest.TestCase):
	def test_creation(self):
		chromo = Chromosome(2, (1, 2, 3))
	
	def test_getitem(self):
		allele_indices = (1, 2, 3)
		chromo = Chromosome(2, allele_indices)
		for i, a in enumerate(allele_indices):
			self.assertEqual(a, chromo[i])
