from dataclasses import dataclass
from typing import List
from unittest import TestCase

import h5py

from adapters.hdf5_sink import HDF5Sink, MetaEntry
from applications.discern_frequency.hdf5_desc import add_meta, HDF5_DICT, pa_gen
from applications.discern_frequency.write_map_util import ExpEntries, FormEntry, FormData, fixed_prefix, missing_hdf5_entries, unknown_hdf5_entries
from domain.model import Chromosome

from .common import del_files


class WriteMapUtilTest(TestCase):
	def test_fixed_prefix(self):
		test_data = [# test input, exp
			("", ""),
			("/", "/"),
			("mapping/carry_data/carry_data_{}", "mapping/carry_data"),
			("/mapping/carry_data/carry_data_{}", "/mapping/carry_data"),
			("/mapping_{}/carry_data/carry_data_{}", ""),
			("mapping_{}/carry_data/carry_data_{}", ""),
		]
		
		for data, exp in test_data:
			with self.subTest(data=data):
				res = fixed_prefix(data)
				self.assertEqual(exp, res)
	
	def create_hdf5(self, hdf5_filename):
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
	
	@dataclass
	class EntryTC:
		desc: str
		entries: ExpEntries
		missing: List[str]
		unknown: List[str]
	
	base_entries = ExpEntries(["fitness.st.desc", "fitness.chromo_id"], [
		FormEntry("rep.carry_data.lut", [FormData(path=[5])]),
		FormEntry("rep.carry_data.values", [FormData(name=[6], path=["abc"])]),
	])
	
	entry_cases = [
		EntryTC("everything unknown", ExpEntries([], []), [], [""]),
		EntryTC("everything known", base_entries, [], []),
		EntryTC("check wildcard", base_entries + ExpEntries([], [FormEntry("rep.carry_data.lut", None),
			FormEntry("rep.carry_data.values", None)]), [], []),
		EntryTC("missing dataset", base_entries + ExpEntries(["habitat"]), ["/habitat"], []),
		EntryTC("missing attr", base_entries + ExpEntries(["chromo.desc"]), ["/individual.description"], []),
		EntryTC("missing attr path data", base_entries + ExpEntries([], [FormEntry("rep.carry_data.lut",
			[FormData(path=[1])])]), ["/mapping/carry_data/carry_data_1.lut_index"], []),
		EntryTC("missing attr name data", base_entries + ExpEntries([], [FormEntry("rep.carry_data.values", 
			[FormData(name=[3], path=["abc"])])]), ["/mapping/carry_data/carry_data_abc.carry_use_3_values"], []),
		EntryTC("missing wildcard", base_entries + ExpEntries([], [FormEntry("rep.carry_data.enable", None)]),
			["/mapping/carry_data/carry_data_{}.carry_enable"], []),
		EntryTC("unknown wildcard", ExpEntries(["fitness.st.desc", "fitness.chromo_id"], [
			FormEntry("rep.carry_data.lut", [FormData(path=[5])])]), [], ["/mapping/carry_data/carry_data_abc"]),
	]
	
	def test_missing_hdf5_entries(self):
		hdf5_filename = "tmp.test_missing_hdf5_entries.h5"
		del_files([hdf5_filename])
		self.create_hdf5(hdf5_filename)
		
		for tc in self.entry_cases:
			with self.subTest(desc=tc.desc), h5py.File(hdf5_filename, "r") as hdf5_file:
				res = missing_hdf5_entries(hdf5_file, tc.entries)
				self.assertEqual(tc.missing, res)
		
		del_files([hdf5_filename])
	
	def test_unknown_hdf5_entries(self):
		hdf5_filename = "tmp.test_missing_hdf5_entries.h5"
		del_files([hdf5_filename])
		self.create_hdf5(hdf5_filename)
		
		for tc in self.entry_cases:
			with self.subTest(desc=tc.desc), h5py.File(hdf5_filename, "r") as hdf5_file:
				res = unknown_hdf5_entries(hdf5_file, tc.entries)
				self.assertEqual(tc.unknown, res)
		
		del_files([hdf5_filename])
	
