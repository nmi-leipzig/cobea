from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional, Tuple
from unittest import TestCase

from adapters.deap.simple_ea import EvalMode, Individual, InfoSource, SimpleEA
from adapters.embed_driver import FixedEmbedDriver
from adapters.embed_meter import FixedEmbedMeter
from adapters.simtar import SimtarConfig, SimtarDev, SimtarRepGen
from adapters.prng import BuiltInPRNG
from adapters.unique_id import SimpleUID
from domain.interfaces import Driver, Meter, OutputData, PRNG, Representation, TargetConfiguration, TargetDevice, UniqueID
from domain.data_sink import DataSink
from domain.model import Chromosome
from domain.request_model import RequestObject
from domain.use_cases import GenChromo, Measure

from .mocks import MockDataSink


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
			indi = Individual(chromo_gen(req).chromosome)
			
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
				indis = [Individual(chromo_gen(RequestObject(allele_indices=r)).chromosome) for r in td.raw]
				
				res = dut(*indis)
				
				self.assertEqual(2, len(res))
				
				for index, (eq, exp) in enumerate(zip(td.equal, td.exp_alleles)):
					if eq is None:
						self.check_individual_different(indis[0], res[index])
						self.check_individual_different(indis[1], res[index])
					else:
						self.assertEqual(indis[eq], res[index])
					
					self.assertEqual(exp, res[index].chromo.allele_indices)

class SimpleEATest(TestCase):
	@dataclass
	class SEAData:
		dut: SimpleEA = None
		#mf_uc: MeasureFitness = None
		rep: Representation = None
		habitat: TargetConfiguration = None
		target: TargetDevice = None
		#dec_uc: DecTarget = None
		drv: Driver = None
		mtr: Meter = None
		mea_uc: Measure = None
		#ff: FitnessFunction = None
		#uc_req: RequestObject = None # prepared request for call to MeasureFitness
		prep: Callable[[OutputData], OutputData] = None
		#drv_list: List[InputData] = None
		#gen: Optional[InputGen] = None
		uid_gen: UniqueID = None
		prng: PRNG = None
		sink: DataSink = None
	
	def create_dut_data(self):
		res = self.SEAData()
		res.sink = MockDataSink()
		# dec
		gen = SimtarRepGen()
		req = RequestObject(always_active=False)
		res.rep = gen(req).representation
		rep = res.rep
		def icb():
			for gene in rep.iter_genes():
				yield from gene.bit_positions
		res.rep.iter_carry_bits = icb
		
		res.habitat = SimtarConfig()
		res.rep.prepare_config(res.habitat)
		
		res.target = SimtarDev()
		#res.dec_uc = DecTarget(res.rep, res.habitat, res.target)
		
		# Measure
		res.drv = FixedEmbedDriver(res.target, "B")
		res.mtr = FixedEmbedMeter(res.target, 1, "B")
		res.mea_uc = Measure(res.drv, res.mtr, data_sink=res.sink)
		
		#FitnessFunction
		#res.ff = ReduceFF(lambda a, b: a+b)
		
		# prepare request
		#res.uc_req = RequestObject(
		#	prefix = bytes(),
		#	output_count = 1,
		#	output_format = "B",
		#	meter_dev = res.target,
		#)
		
		#InputGen
		#res.drv_list = [InputData([i]) for i in range(16)]
		#res.gen = SeqGen(res.drv_list)
		
		res.prep = lambda a: OutputData(([float(v) for v in a]*10)[:10])
		#res.mf_uc = MeasureFitness(res.dec_uc, res.mea_uc, res.ff, res.gen, prep=res.prep)
		
		res.uid_gen = SimpleUID()
		res.prng = BuiltInPRNG()
		
		res.dut = SimpleEA(res.rep, res.mea_uc, res.uid_gen, res.prng, res.habitat, res.target, res.sink, res.prep)
		
		return res
	
	def test_create(self):
		dut_data = self.create_dut_data()
	
	def test_run(self):
		dut_data = self.create_dut_data()
		dut = dut_data.dut
		dut.run(5, 3, 0.7, 0.5, EvalMode.ALL)
		#print(dut_data.sink.write_list)
