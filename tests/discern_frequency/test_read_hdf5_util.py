import os

from functools import partial
from operator import attrgetter, itemgetter
from unittest import TestCase

import h5py

from adapters.hdf5_sink import compose, HDF5Sink, ParamAim
from adapters.icecraft import IcecraftRawConfig
from applications.discern_frequency.hdf5_desc import HDF5_DICT, pa_gen
from applications.discern_frequency.read_hdf5_util import read_chromosome, read_habitat, read_s_t_index,\
	read_carry_enable_values
from domain.model import Chromosome

from .common import del_files, TEST_DATA_DIR


class WriteReadHDF5Test(TestCase):
	"""test cycle of writing to and reading from HDF5"""
	
	def setUp(self):
		self.asc_dir = os.path.dirname(os.path.abspath(__file__))
	
	def test_write_read_habitat(self):
		asc_filename = os.path.join(self.asc_dir, "freq_hab.asc")
		exp = IcecraftRawConfig.create_from_filename(asc_filename)
		
		hdf5_filename = "tmp.test_read_write_habitat.h5"
		del_files([hdf5_filename])
		
		write_map = {"th": [pa_gen("habitat", ["text"])]}
		
		with HDF5Sink(write_map, filename=hdf5_filename) as sink:
			sink.write("th", {"text": bytearray(exp.to_text(), encoding="utf-8")})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_habitat(hdf5_file)
		
		self.assertEqual(exp.to_text(), res.to_text())
		
		del_files([hdf5_filename])
	
	def test_write_read_chromosome(self):
		chromo_id = 7
		exp = Chromosome(chromo_id, (2, 5, 1, 9))
		
		for width in [8, 16, 32]:
			with self.subTest(width=width):
				hdf5_filename = "tmp.test_read_write_chromosome.h5"
				del_files([hdf5_filename])
				
				chromo_desc = HDF5_DICT["chromo.indices"]
				write_map = {"th": [
					ParamAim(["chromo"], f"uint{width}", chromo_desc.h5_name, chromo_desc.h5_path, chromo_desc.as_attr,
						shape=(4, ), alter=partial(compose, funcs=[itemgetter(0), attrgetter("allele_indices")])
					),
					pa_gen(
						"chromo.id", ["chromo"],  alter=partial(compose, funcs=[itemgetter(0), attrgetter("identifier")])
					),
				]}
				
				with HDF5Sink(write_map, filename=hdf5_filename) as sink:
					sink.write("th", {"chromo": exp})
				
				with h5py.File(hdf5_filename, "r") as hdf5_file:
					res = read_chromosome(hdf5_file, chromo_id)
				
				self.assertEqual(exp, res)
				
				del_files([hdf5_filename])
	
	def test_write_read_s_t_index(self):
		exp = 173
		
		hdf5_filename = "tmp.test_read_write_s_t_index.h5"
		del_files([hdf5_filename])
		
		write_map = {"th": [pa_gen("fitness.st", ["st"])]}
		
		with HDF5Sink(write_map, filename=hdf5_filename) as sink:
			sink.write("th", {"st": exp})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_s_t_index(hdf5_file, 0)
		
		self.assertEqual(exp, res)
		
		del_files([hdf5_filename])
	
	def test_write_read_carry_enable_values(self):
		carry_values = [
			[True, False, False],
			[False, False, False],
			[True, False, True],
			[False, True, False],
		]
		idx = 2
		
		hdf5_filename = "tmp.test_read_write_carry_enable_values.h5"
		del_files([hdf5_filename])
		
		write_map = {"th": [pa_gen("carry_enable.values", ["cev"], shape=(len(carry_values[0]), ))]}
		
		with HDF5Sink(write_map, filename=hdf5_filename) as sink:
			for cev in carry_values:
				sink.write("th", {"cev": cev})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_carry_enable_values(hdf5_file, idx)
		
		
		self.assertEqual(carry_values[idx], res)
		
		del_files([hdf5_filename])
