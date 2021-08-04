from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple
from unittest import TestCase

from adapters.deap.simple_ea import Individual, InfoSource
from adapters.unique_id import SimpleUID
from domain.model import Chromosome
from domain.request_model import RequestObject
from domain.use_cases import GenChromo

class MockIS(InfoSource):
	def __init__(self, info: Mapping[str, Any]) -> None:
		self._info = info
	
	def get_info(self) -> Mapping[str, Any]:
		return self._info

class IndividualTest(TestCase):
	def test_wrapping(self):
		def alter_1(raw: List[int], param1: float) -> Tuple[List[int]]:
			return (raw, )
		
		res = Individual.wrap_alteration(alter_1, 1, None, None, {})
	
	def check_individual_different(self, indi1, indi2):
		self.assertNotEqual(indi1.chromo.identifier, indi2.chromo.identifier)
		
		self.assertIsInstance(indi1.chromo.allele_indices, tuple)
		self.assertIsInstance(indi2.chromo.allele_indices, tuple)
		
		self.assertNotEqual(indi1.chromo.allele_indices, indi2.chromo.allele_indices)
	
	def test_wrapped_call(self):
		data_sink = None
		chromo_gen = GenChromo(SimpleUID(), data_sink)
		info_src = MockIS({"info": 7})
		
		with self.subTest(desc="single input"):
			def alter_1(raw: List[int], param1: float) -> Tuple[List[int]]:
				if param1 < 1:
					return (raw, )
				else:
					return([raw[0]+1]+raw[1:], )
			
			dut = Individual.wrap_alteration(alter_1, 1, chromo_gen, data_sink, info_src)
			# change
			req = RequestObject(allele_indices=(1, 2, 3))
			indi = Individual(chromo_gen(req))
			
			res = dut(indi, 3.7)
			
			self.assertEqual(1, len(res))
			res_indi = res[0]
			self.check_individual_different(indi, res_indi)
			self.assertEqual(res_indi.chromo.allele_indices, (2, 2, 3))
			
			# no change
			res = dut(indi, 0.5)
			self.assertEqual(1, len(res))
			res_indi = res[0]
			self.assertEqual(indi, res_indi)
			self.assertEqual(res_indi.chromo.allele_indices, (1, 2, 3))
		
		with self.subTest(desc="double input"):
			@dataclass
			class DoubleTD:
				desc: str
				raw: Tuple[List[int], List[int]]
				equal: Tuple[Optional[int], Optional[int]]
				exp_alleles: Tuple[Tuple[int, ...], Tuple[int, ...]]
			
			def alter_2(raw0: List[int], raw1: List[int]) -> Tuple[List[int], List[int]]:
				if raw0[0] == 1:
					res0 = [raw0[0]+1]+raw0[1:]
				else:
					res0 = raw0
				
				if raw1[0] == 1:
					res1 = [raw1[0]+1]+raw1[1:]
				else:
					res1 = raw1
				
				if raw0[1] == 1:
					return (res1, res0)
				else:
					return (res0, res1)
			
			dut = Individual.wrap_alteration(alter_2, 2, chromo_gen, data_sink, info_src)
			
			test_data = [
				DoubleTD("no change", ([4, 5], [6, 7]), (0, 1), ((4, 5), (6, 7))),
				DoubleTD("switch", ([4, 1], [6, 7]), (1, 0), ((6, 7), (4, 1))),
				DoubleTD("alter first", ([1, 5], [2, 7]), (None, 1), ((2, 5), (2, 7))),
				DoubleTD("alter second", ([3, 5], [1, 7]), (0, None), ((3, 5), (2, 7))),
				DoubleTD("alter both", ([1, 5], [1, 7]), (None, None), ((2, 5), (2, 7))),
				DoubleTD("alter first and switch", ([1, 1], [2, 7]), (1, None), ((2, 7), (2, 1))),
				DoubleTD("alter second and switch", ([3, 1], [1, 7]), (None, 0), ((2, 7), (3, 1))),
				DoubleTD("alter both and switch", ([1, 1], [1, 7]), (None, None), ((2, 7), (2, 1))),
				DoubleTD("coincidentally the same", ([1, 5], [2, 5]), (1, 1), ((2, 5), (2, 5))),
			]
			
			for td in test_data:
				indis = [Individual(chromo_gen(RequestObject(allele_indices=r))) for r in td.raw]
				
				res = dut(*indis)
				
				self.assertEqual(2, len(res))
				
				for index, (eq, exp) in enumerate(zip(td.equal, td.exp_alleles)):
					if eq is None:
						self.check_individual_different(indis[0], res[index])
						self.check_individual_different(indis[1], res[index])
					else:
						self.assertEqual(indis[eq], res[index])
					
					self.assertEqual(exp, res[index].chromo.allele_indices)
