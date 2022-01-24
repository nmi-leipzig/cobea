import os

from dataclasses import astuple, dataclass, field
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from typing import Iterable, List
from unittest import TestCase

import h5py

from adapters.hdf5_sink import chain_funcs, compose, HDF5Sink, MetaEntry, ParamAim
from adapters.icecraft import CarryData, CarryDataMap, IcecraftBitPosition, IcecraftLUTPosition, IcecraftPosition,\
	IcecraftRawConfig, IndexedItem, PartConf
from applications.discern_frequency.hdf5_desc import add_carry_data, add_meta, add_rep, HDF5_DICT, pa_gen
from applications.discern_frequency.read_hdf5_util import read_chromosome, read_habitat, read_s_t_index,\
	read_rep_carry_data, read_carry_enable_bits, read_carry_enable_values, read_rep_colbufctrl, read_rep_output,\
	read_rep, read_fitness_chromo_id, get_chromo_bits
from domain.model import Chromosome

from tests.icecraft.data.rep_data import EXP_REP

from .common import del_files, TEST_DATA_DIR

@dataclass
class FormData:
	"""Data for inserting HDF5 groups and names"""
	name: Iterable = field(default_factory=tuple)
	path: Iterable = field(default_factory=tuple)

@dataclass
class FormEntry:
	key: str
	data: List[FormData]

@dataclass
class ExpEntries:
	simple: List[str]
	form: List[FormEntry] = field(default_factory=list)
	
	def __add__(self, other: "ExpEntries") -> "ExpEntries":
		return ExpEntries(self.simple+other.simple, self.form+other.form)

ENTRIES_MEASURE = ExpEntries([])

ENTRIES_REP = ExpEntries([])

ENTRIES_RUN = ENTRIES_REP + ENTRIES_MEASURE

def missing_hdf5_entries(hdf5_file, exp_entries):
	missing = []
	
	def check_pna(path, name, as_attr):
		grp = hdf5_file[path]
		if as_attr:
			return grp.attrs[name]
		else:
			return grp[name]
	
	for desc_key in exp_entries.simple:
		desc = HDF5_DICT[desc_key]
		try:
			check_pna(desc.h5_path, desc.h5_name, desc.as_attr)
		except KeyError:
			missing.append(f"{desc.h5_path}/{desc.h5_name}")
	
	for entry in exp_entries.form:
		desc = HDF5_DICT[entry.key]
		for dat in entry.data:
			full_name = desc.h5_name.format(*dat.name)
			full_path = desc.h5_path.format(*dat.path)
			
			try:
				check_pna(full_path, full_name, desc.as_attr)
			except KeyError:
				missing.append(f"{full_path}/{full_name}")
				break
	
	return missing


class WriteReadHDF5Test(TestCase):
	"""test cycle of writing to and reading from HDF5"""
	
	def setUp(self):
		self.asc_dir = os.path.dirname(os.path.abspath(__file__))
	
	def check_hdf5_entires(self, hdf5_file, exp_entries):
		missing = missing_hdf5_entries(hdf5_file, exp_entries)
		self.assertEqual(0, len(missing), f"{missing}")
	
	def test_meta_check_hdf5_entries(self):
		entries = ExpEntries(["fitness.st.desc"], [
			FormEntry("rep.carry_data.lut", [FormData(path=[5])]),
			FormEntry("rep.carry_data.values", [FormData(name=[6], path=["abc"])]),
		])
		
		hdf5_filename = "tmp.test_meta_check_hdf5_entries.h5"
		del_files([hdf5_filename])
		
		metadata = {}
		add_meta(metadata, "fitness.st.desc", "simple attr entry")
		
		lut_desc = HDF5_DICT["rep.carry_data.lut"]
		metadata[lut_desc.h5_path.format(5)] = [MetaEntry(lut_desc.h5_name, 3, lut_desc.data_type)]
		
		val_desc = HDF5_DICT["rep.carry_data.values"]
		metadata[val_desc.h5_path.format("abc")] = [MetaEntry(val_desc.h5_name.format(6), [True], val_desc.data_type)]
		
		write_map = {"th": [pa_gen("fitness.chromo_id", ["fc"])]}
		
		with HDF5Sink(write_map, metadata, filename=hdf5_filename) as sink:
			chromo = Chromosome(23, (2, 5, 1, 9))
			sink.write("th", {"fc": chromo})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			with self.subTest(desc="all available"):
				self.check_hdf5_entires(hdf5_file, entries)
			
			with self.subTest(desc="missing dataset"):
				exp_entries = entries + ExpEntries(["habitat"])
				with self.assertRaises(AssertionError):
					self.check_hdf5_entires(hdf5_file, exp_entries)
			
			with self.subTest(desc="missing attr"):
				exp_entries = entries + ExpEntries(["chromo.desc"])
				with self.assertRaises(AssertionError):
					self.check_hdf5_entires(hdf5_file, exp_entries)
			
			with self.subTest(desc="missing attr path data"):
				exp_entries = entries + ExpEntries([], [FormEntry("rep.carry_data.lut", [FormData(path=[1])])])
				with self.assertRaises(AssertionError):
					self.check_hdf5_entires(hdf5_file, exp_entries)
			
			with self.subTest(desc="missing attr name data"):
				exp_entries = entries + ExpEntries([], [FormEntry("rep.carry_data.values", [
					FormData(name=[3], path=["abc"])])])
				with self.assertRaises(AssertionError):
					self.check_hdf5_entires(hdf5_file, exp_entries)
		
		del_files([hdf5_filename])
	
	def test_write_read_habitat(self):
		asc_filename = os.path.join(self.asc_dir, "freq_hab.asc")
		exp = IcecraftRawConfig.create_from_filename(asc_filename)
		
		hdf5_filename = "tmp.test_write_read_habitat.h5"
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
				hdf5_filename = "tmp.test_write_read_chromosome.h5"
				del_files([hdf5_filename])
				
				chromo_desc = HDF5_DICT["chromo.indices"]
				write_map = {"th": [
					pa_gen("chromo.indices", ["chromo"], data_type=f"uint{width}", shape=(4, ),
						alter=chain_funcs([itemgetter(0), attrgetter("allele_indices")])),
					pa_gen("chromo.id", ["chromo"],  alter=chain_funcs([itemgetter(0), attrgetter("identifier")])),
				]}
				
				with HDF5Sink(write_map, filename=hdf5_filename) as sink:
					sink.write("th", {"chromo": exp})
				
				with h5py.File(hdf5_filename, "r") as hdf5_file:
					res = read_chromosome(hdf5_file, chromo_id)
					res_width = get_chromo_bits(hdf5_file)
				
				self.assertEqual(exp, res)
				self.assertEqual(width, res_width)
				
				del_files([hdf5_filename])
	
	def test_write_read_s_t_index(self):
		exp = 173
		
		hdf5_filename = "tmp.test_write_read_s_t_index.h5"
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
		
		hdf5_filename = "tmp.test_write_read_carry_enable_values.h5"
		del_files([hdf5_filename])
		
		write_map = {"th": [pa_gen("carry_enable.values", ["cev"], shape=(len(carry_values[0]), ))]}
		
		with HDF5Sink(write_map, filename=hdf5_filename) as sink:
			for cev in carry_values:
				sink.write("th", {"cev": cev})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_carry_enable_values(hdf5_file, idx)
		
		self.assertEqual(carry_values[idx], res)
		
		del_files([hdf5_filename])
	
	def test_write_read_carry_enable_bits(self):
		bits = [IcecraftBitPosition(4, 3, 0, 51), IcecraftBitPosition(4, 3, 0, 50), IcecraftBitPosition(12, 3, 4, 13)]
		
		hdf5_filename = "tmp.test_write_read_carry_enable_bits.h5"
		del_files([hdf5_filename])
		
		write_map = {"th": [pa_gen("carry_enable.bits", ["ceb"], alter=partial(compose, funcs=[
			itemgetter(0), partial(map, methodcaller("to_ints")), list]))]}
		
		with HDF5Sink(write_map, filename=hdf5_filename) as sink:
			sink.write("th", {"ceb": bits})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_carry_enable_bits(hdf5_file)
		
		self.assertEqual(bits, res)
		
		del_files([hdf5_filename])
	
	def test_write_read_rep_carry_data(self):
		exp = {
			IcecraftPosition(3, 4): {
				0: CarryData(0, (IcecraftBitPosition(3, 4, 13, 4), ), [
					PartConf((IcecraftBitPosition(3, 4, 3, 3), ), (True, ))
				]),
				1: CarryData(1, (IcecraftBitPosition(3, 4, 13, 5), IcecraftBitPosition(3, 4, 13, 6)), [
					PartConf((IcecraftBitPosition(3, 5, 3, 3), IcecraftBitPosition(3, 5, 3, 7), ), (True, False))
				]),
			},
			IcecraftPosition(7, 9): {
				2: CarryData(2, (IcecraftBitPosition(7, 9, 13, 4), ), [
					PartConf((IcecraftBitPosition(7, 9, 3, 3), ), (True, ))
				]),
				5: CarryData(5, (IcecraftBitPosition(7, 9, 13, 5), ), [
					PartConf((IcecraftBitPosition(8, 9, 3, 3), IcecraftBitPosition(8, 10, 3, 7), ), (True, False))
				]),
			},
		}
		
		hdf5_filename = "tmp.test_write_read_rep_carry_data.h5"
		del_files([hdf5_filename])
		
		metadata = {}
		def iter_carry_data(cdm):
			for lut_map in exp.values():
				yield from lut_map.values()
		add_carry_data(metadata, iter_carry_data(exp))
		
		with HDF5Sink({}, metadata=metadata, filename=hdf5_filename) as sink:
			pass
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_rep_carry_data(hdf5_file)
		
		self.assertEqual(exp, res)
		
		del_files([hdf5_filename])
	
	def test_write_read_rep_output(self):
		exp = (IcecraftLUTPosition(1, 2, 3), IcecraftLUTPosition(13, 28, 7))
		
		hdf5_filename = "tmp.test_write_read_rep_output.h5"
		del_files([hdf5_filename])
		
		metadata = {}
		add_meta(metadata, "rep.output", exp)
		
		with HDF5Sink({}, metadata=metadata, filename=hdf5_filename) as sink:
			pass
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_rep_output(hdf5_file)
		
		self.assertEqual(exp, res)
		
		del_files([hdf5_filename])
	
	def test_write_read_rep_colbufctrl(self):
		exp = [
			IndexedItem((IcecraftBitPosition(3, 4, 13, 4), ), "ColBufCtrl", 5),
			IndexedItem((IcecraftBitPosition(7, 9, 13, 5), ), "ColBufCtrl", 3),
			IndexedItem((IcecraftBitPosition(3, 25, 13, 5), ), "ColBufCtrl", 4),
		]
		hdf5_filename = "tmp.test_write_read_rep_colbufctrl.h5"
		del_files([hdf5_filename])
		
		metadata = {}
		add_meta(metadata, "rep.colbufctrl.bits", exp)
		add_meta(metadata, "rep.colbufctrl.indices", exp)
		
		with HDF5Sink({}, metadata=metadata, filename=hdf5_filename) as sink:
			pass
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_rep_colbufctrl(hdf5_file)
		
		self.assertEqual(exp, res)
		
		del_files([hdf5_filename])
	
	def test_write_read_rep(self):
		exp = EXP_REP
		
		hdf5_filename = "tmp.test_write_read_rep.h5"
		del_files([hdf5_filename])
		
		metadata = {}
		add_rep(metadata, exp)
		
		with HDF5Sink({}, metadata=metadata, filename=hdf5_filename) as sink:
			pass
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_rep(hdf5_file)
		
		self.assertEqual(exp, res)
		
		del_files([hdf5_filename])
	
	def test_write_read_fitness_chromo_id(self):
		exp = 25
		
		hdf5_filename = "tmp.test_write_read_fitness_chromo_id.h5"
		del_files([hdf5_filename])
		
		write_map = {"th": [pa_gen("fitness.chromo_id", ["fc"])]}
		
		with HDF5Sink(write_map, filename=hdf5_filename) as sink:
			chromo = Chromosome(exp, (2, 5, 1, 9))
			sink.write("th", {"fc": chromo})
		
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			res = read_fitness_chromo_id(hdf5_file, 0)
		
		self.assertEqual(exp, res)
		
		del_files([hdf5_filename])
	
