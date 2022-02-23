import os

from argparse import Namespace
from contextlib import ExitStack
from unittest import skip, TestCase
from unittest.mock import MagicMock

import h5py

from adapters.dummies import DummyDriver
from adapters.icecraft import IcecraftPosition, IcecraftRawConfig, IcecraftRepGen
from adapters.minvia import MinviaDriver
from applications.discern_frequency.action import extract_carry_enable, FreqSumFF, remeasure, run, setup_from_args_hdf5
from applications.discern_frequency.hdf5_content import ENTRIES_REMEASURE, ENTRIES_RUN, missing_hdf5_entries,\
	unknown_hdf5_entries
from domain.model import Chromosome, InputData, OutputData
from domain.request_model import ResponseObject, RequestObject

from .common import TEST_DATA_DIR
from ..mocks import RandomMeter


class FreqSumFFTest(TestCase):
	def test_create(self):
		dut = FreqSumFF(5, 5)
	
	def test_compute(self):
		test_cases = [# combination index, measurement, expected result
			(0, [255*256]*5+[0]*5, 1.0691833355591607), # 0b0000011111
			(251, [61461.492]*5+[0]*5, 1), # 0b1111100000
			(65, [10000]*10, 0.0010807097233555662), # 0b100110011
			(65, [3, 4, 3, 0, 5, 2, 1, 0, 2, 1], 3.6140597599635693e-05), # 0b100110011
		]
		
		dut = FreqSumFF(5, 5)
		for comb_idx, data, exp in test_cases:
			with self.subTest(comb_idx=comb_idx, exp=exp):
				req = RequestObject(driver_data = InputData([comb_idx]), measurement=OutputData(data))
				res = dut.compute(req)
				self.assertAlmostEqual(exp, res.fitness, 15)
	
	def test_compute_error(self):
		test_cases = [# combination index, measurement, expected error
			(0, [], ValueError),
			(251, [61461.492]*6+[0]*5, ValueError),
			(65, [1]*9, ValueError),
		]
		
		dut = FreqSumFF(5, 5)
		for comb_idx, data, exp in test_cases:
			with self.subTest(comb_idx=comb_idx, exp=exp):
				req = RequestObject(driver_data = InputData([comb_idx]), measurement=OutputData(data))
				with self.assertRaises(exp):
					res = dut.compute(req)
				


class ActionTest(TestCase):
	def setUp(self):
		import applications.discern_frequency
		self.app_path = os.path.dirname(os.path.abspath(applications.discern_frequency.__file__))
	
	def test_extract_carry_enable(self):
		rep_gen = IcecraftRepGen()
		req = RequestObject(tiles=[IcecraftPosition(5, 17)], output_lutffs=[])
		rep = rep_gen(req).representation
		
		carry_bits = list(rep.iter_carry_bits())
		self.assertEqual(8, len(carry_bits))
		
		habitat = IcecraftRawConfig.create_empty()
		genes = list(rep.iter_genes())
		chromo = Chromosome(7, (0,)*len(genes))
		
		res = extract_carry_enable(rep, habitat, chromo)
		self.assertEqual(len(carry_bits), len(res.carry_enable))
		for bit, val in zip(carry_bits, res.carry_enable):
			exp = habitat.get_bit(bit)
			self.assertEqual(exp, val)
	
	def test_run_dummy(self):
		out_filename = "tmp.test_run_dummy.h5"
		self.run_dummy(out_filename)
		
		self.check_hdf5(out_filename)
		
		self.delete([out_filename])
	
	def run_dummy(self, out_filename):
		# delete previous results
		self.delete([out_filename])
		
		args = Namespace(
			output = out_filename,
			dummy = True,
			temperature = None,
			habitat = os.path.join(self.app_path, "nhabitat.asc"),
			area = [10, 29, 10, 29],
			in_port = ["10", "29", "lft"],
			out_port = ["10", "29", "top"],
			habitat_con = None,
			freq_gen_con = None,
			pop_size = 5,
			generations = 3,
			crossover_prob = 0.7,
			mutation_prob = 0.001756,
			eval_mode = "ALL",
		)
		run(args)
		
		return args
	
	def delete(self, filename_list):
		for filename in filename_list:
			try:
				os.remove(filename)
			except FileNotFoundError:
				pass
	
	def check_hdf5(self, hdf5_filename, entries = ENTRIES_RUN):
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			missing = missing_hdf5_entries(hdf5_file, entries)
			self.assertEqual(0, len(missing), f"Missing entries: {missing}")
			unknown = unknown_hdf5_entries(hdf5_file, entries)
			if len(unknown):
				print(f"Warning: unknonw entries {unknown}")
	
	def test_setup_from_args_hdf5_dummy(self):
		# create HDF5 input file
		hdf5_filename = "tmp.test_setup_from_args_hdf5_dummy.hdf5"
		org_args = self.run_dummy(hdf5_filename)
		
		# call
		args = Namespace(dummy=True)
		write_map = {}
		metadata = {}
		with h5py.File(hdf5_filename, "r") as hdf5_file, ExitStack() as stack:
			res = setup_from_args_hdf5(args, hdf5_file, stack, write_map, metadata)
		
		# check
		self.assertIsInstance(res.driver, MinviaDriver)
		self.assertIsInstance(res.target, MagicMock)
		self.assertIsInstance(res.meter, RandomMeter)
		for name, exp in [("data", None), ("rising_edge", 0), ("falling_edge", 0), ("trig_len", 0), ("offset", 0)]:
			val = getattr(res.cal_data, name)
			self.assertEqual(exp, val)
		self.assertEqual(res.sink_writes, [])
		
		self.assertIn("Measure.perform", write_map)
		self.assertGreaterEqual(len(write_map["Measure.perform"]), 1)
		self.assertIn("fitness/measurement", metadata)
		self.assertGreaterEqual(len(metadata["fitness/measurement"]), 1)
		
		# clean up
		self.delete([hdf5_filename])
	
	def test_run_remeasure_dummy(self):
		run_filename = "tmp.test_run_remeasure_dummy.run.h5"
		out1_filename = "tmp.test_run_remeasure_dummy.re1.h5"
		out2_filename = "tmp.test_run_remeasure_dummy.re2.h5"
		fn_list = [run_filename, out1_filename, out2_filename]
		self.delete(fn_list)
		
		self.run_dummy(run_filename)
		
		# check
		self.check_hdf5(run_filename)
		
		args = Namespace(
			output = out1_filename,
			dummy = True,
			temperature = None,
			freq_gen_type = None,
			data_file = run_filename,
			index = 3,
			rounds = 4,
			comb_index = None,
		)
		remeasure(args)
		
		# check
		self.check_hdf5(out1_filename, ENTRIES_REMEASURE)
		
		# remeasure the result of remeasure
		args.output = out2_filename
		args.data_file = out1_filename
		remeasure(args)
		
		# check
		self.check_hdf5(out2_filename, ENTRIES_REMEASURE)
		
		self.delete(fn_list)
