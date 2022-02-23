"""Data and Functions regarding HDF5 contents with respect to action functions (run, remeasure, ...)"""

import re

from dataclasses import dataclass, field
from enum import auto, Enum
from typing import Dict, Iterable, List, Optional

import h5py

from applications.discern_frequency.hdf5_desc import HDF5_DICT
from applications.discern_frequency.read_hdf5_util import data_from_key


class ContentType(Enum):
	"""Type of contents of HDF5 files"""
	RUN = auto()
	RESTART = auto()
	REMEASURE = auto()
	CLAMP = auto()
	SPECTRUM = auto()


@dataclass
class FormData:
	"""Data for inserting in f-strings of HDF5 groups and names"""
	name: Iterable = field(default_factory=tuple)
	path: Iterable = field(default_factory=tuple)


@dataclass
class FormEntry:
	key: str
	data: Optional[List[FormData]]
	sub_known: bool = False # assume all attributes and sub groups are known


@dataclass
class ExpEntries:
	simple: List[str]
	form: List[FormEntry] = field(default_factory=list)
	
	def __add__(self, other: "ExpEntries") -> "ExpEntries":
		return ExpEntries(self.simple+other.simple, self.form+other.form)

ENTRIES_BASE = ExpEntries(["git_commit", "python"])

ENTRIES_RE = ExpEntries(["re.org"])

ENTRIES_DESC = ExpEntries(["habitat.out_port.pos", "habitat.out_port.dir"])

ENTRIES_REP = ExpEntries(["rep.carry_data.desc", "rep.output", "rep.colbufctrl.bits",
	"rep.colbufctrl.indices", "rep.desc", "rep.genes.desc", "rep.const.desc"], [FormEntry("rep.carry_data.lut", None),
	FormEntry("rep.carry_data.enable", None), FormEntry("rep.carry_data.bits", None),
	FormEntry("rep.carry_data.values", None), FormEntry("rep.genes", None, True), FormEntry("rep.const", None, True)])

ENTRIES_MEASURE = ExpEntries(["habitat", "habitat.desc", "habitat.in_port.pos", "habitat.in_port.dir",
	"habitat.area.min", "habitat.area.max", "chromo.desc", "chromo.id", "chromo.id.desc",
	"chromo.indices", "chromo.indices.desc", "fitness.chromo_id", "fitness.chromo_id.desc", "fitness.st",
	"fitness.st.desc", "carry_enable.values", "carry_enable.bits", "carry_enable.desc", "fitness.desc", "fitness.time",
	"fitness.time.desc", "fitness.time.unit", "fitness.value", "fitness.fast_sum", "fitness.slow_sum",
	"fitness.value.desc", "fitness.fast_sum.desc", "fitness.slow_sum.desc", "fitness.measurement",
	"fitness.measurement.desc", "fitness.driver_type"])

ENTRIES_HW = ExpEntries(["fitness.driver.sn", "fitness.driver.hw", "fitness.target.sn", "fitness.target.hw",
	"fitness.meter.sn", "fitness.meter.hw", "habitat.con", "freq_gen.con"])

ENTRIES_TEMP = ExpEntries(["temp.desc", "temp.value", "temp.value.desc", "temp.value.unit", "temp.time",
	"temp.time.desc", "temp.time.unit", "temp.reader.sn", "temp.reader.hw", "temp.sensor.sn", "temp.sensor.hw"])

ENTRIES_OSCI = ExpEntries(["osci.calibration", "osci.calibration.desc", "osci.calibration.unit",
	"osci.calibration.rising", "osci.calibration.falling", "osci.calibration.trig_len", "osci.calibration.offset",
	"freq_gen", "freq_gen.desc", "fitness.meter.fw"])

ENTRIES_EA = ExpEntries(["fitness.generation", "fitness.generation.desc", "ea.pop", "ea.pop.desc", "ea.crossover.desc",
	"ea.crossover.in", "ea.crossover.out", "ea.crossover.generation", "ea.crossover.generation.desc",
	"ea.mutation.desc", "ea.mutation.parent", "ea.mutation.child", "ea.mutation.generation",
	"ea.mutation.generation.desc", "ea.pop_size", "ea.gen_count", "ea.crossover_prob", "ea.mutation_prob",
	"ea.eval_mode", ], [
	FormEntry("rand.version", [FormData(["random_initial_"]), FormData(["random_final_"]), FormData(["prng_final_"])]),
	FormEntry("rand.state", [FormData(["random_initial_"]), FormData(["random_final_"]), FormData(["prng_final_"])]),
	FormEntry("rand.gauss", [FormData(["random_initial_"]), FormData(["random_final_"]), FormData(["prng_final_"])]),
	FormEntry("rand.seed", [FormData(["prng_"])])])

ENTRIES_RUN = ENTRIES_BASE + ENTRIES_REP + ENTRIES_MEASURE + ENTRIES_EA + ENTRIES_DESC

ENTRIES_REMEASURE = ENTRIES_BASE + ENTRIES_REP + ENTRIES_MEASURE + ENTRIES_DESC + ENTRIES_RE


def missing_hdf5_entries(hdf5_file:h5py.File, exp_entries: ExpEntries) -> List[str]:
	missing = []
	
	def count_matches(grp, path_parts, attr):
		"""count how many times a path or path.attr occures; supports placeholders"""
		if len(path_parts) == 0:
			if attr is None:
				return 1
			if "{}" not in attr:
				return int(attr in grp.attrs)
			pat = attr.replace("{}", ".*")
			return len([a for a in grp.attrs if re.match(pat, a)])
		
		part = path_parts[0]
		if not part:
			return count_matches(grp, path_parts[1:], attr)
		if not isinstance(grp, h5py.Group):
			return 0
		if "{}" not in part:
			try:
				return count_matches(grp[part], path_parts[1:], attr)
			except KeyError:
				return 0
		
		pat = part.replace("{}", ".*")
		return sum([count_matches(grp[s], path_parts[1:], attr) for s in grp if re.match(pat, s)])
	
	def check_missing(path, name, as_attr):
		if as_attr:
			if count_matches(hdf5_file, path.split("/"), name) == 0:
				missing.append(f"{'' if path.startswith('/') else '/'}{path}.{name}")
		else:
			if count_matches(hdf5_file, path.split("/")+[name], None) == 0:
				missing.append(f"{'' if path.startswith('/') else '/'}{path}{'' if path.endswith('/') else '/'}{name}")
	
	for desc_key in exp_entries.simple:
		desc = HDF5_DICT[desc_key]
		check_missing(desc.h5_path, desc.h5_name, desc.as_attr)
	
	for entry in exp_entries.form:
		desc = HDF5_DICT[entry.key]
		if entry.data is None:
			check_missing(desc.h5_path, desc.h5_name, desc.as_attr)
			continue
		
		for dat in entry.data:
			full_name = desc.h5_name.format(*dat.name)
			full_path = desc.h5_path.format(*dat.path)
			
			check_missing(full_path, full_name, desc.as_attr)
	
	return missing

def unknown_hdf5_entries(hdf5_file: h5py.File, exp_entries: ExpEntries) -> List[str]:
	@dataclass
	class Node:
		attrs: Dict[str, bool] = field(default_factory=dict)
		sub: Optional[Dict[str, "Node"]] = None # None for data sets
		visited: bool = False
		
		def add_attr(self, name):
			self.attrs[name] = False
	
	def collect_sub(grp, nd):
		for name in grp.attrs:
			nd.add_attr(name)
		
		if isinstance(grp, h5py.Dataset):
			nd.sub = None
			return
		
		nd.sub = {}
		for name, sub_grp in grp.items():
			nd.sub[name] = Node()
			collect_sub(sub_grp, nd.sub[name])
	
	hdf5_root = Node()
	collect_sub(hdf5_file, hdf5_root)
	
	def visit_all_sub(grp):
		"""Set visited True for all attributes and subgroups, recusively"""
		for cur in grp.attrs:
			grp.attrs[cur] = True
		
		if grp.sub is None:
			# dataset
			return
		
		for sub in grp.sub.values():
			sub.visited = True
			visit_all_sub(sub)
	
	def visit_pat(grp, path_parts, attr, sub_known):
		if len(path_parts) == 0:
			grp.visited = True
			if attr is None:
				if sub_known:
					visit_all_sub(grp)
				return
			
			if "{}" in attr:
				pat = attr.replace("{}", ".*")
				for name in grp.attrs:
					if re.match(pat, name):
						grp.attrs[name] = True
			else:
				try:
					grp.attrs[attr] = True
				except KeyError:
					pass
			return
		
		if grp.sub is None:
			# dataset
			# don't set visited as the path continues, but the HDF5 hierarchy ends
			return
		
		if not path_parts[0]:
			visit_pat(grp, path_parts[1:], attr, sub_known)
			return
		
		grp.visited = True
		
		if "{}" in path_parts[0]:
			pat = path_parts[0].replace("{}", ".*")
			for name in grp.sub:
				if re.match(pat, name):
					visit_pat(grp.sub[name], path_parts[1:], attr, sub_known)
		else:
			try:
				sub = grp.sub[path_parts[0]]
			except KeyError:
				return
			
			visit_pat(sub, path_parts[1:], attr, sub_known)
	
	def start_visit(path, name, as_attr, sub_known):
		if as_attr:
			visit_pat(hdf5_root, path.split("/"), name, sub_known)
		else:
			visit_pat(hdf5_root, path.split("/")+[name], None, sub_known)
	
	for desc_key in exp_entries.simple:
		desc = HDF5_DICT[desc_key]
		start_visit(desc.h5_path, desc.h5_name, desc.as_attr, False)
	
	for entry in exp_entries.form:
		desc = HDF5_DICT[entry.key]
		if entry.data is None:
			start_visit(desc.h5_path, desc.h5_name, desc.as_attr, entry.sub_known)
			continue
		
		for dat in entry.data:
			full_name = desc.h5_name.format(*dat.name)
			full_path = desc.h5_path.format(*dat.path)
			
			start_visit(full_path, full_name, desc.as_attr, entry.sub_known)
	
	def collect_unvisited(node, path, unvisited):
		if not node.visited:
			unvisited.append(f"{'' if path.startswith('/') else '/'}{path}")
			# don't go deeper, as it is obvious that all attributes and subgroups were not visited
			return
		
		# attriutes
		for name, visited in node.attrs.items():
			if visited:
				continue
			
			unvisited.append(f"{'' if path.startswith('/') else '/'}{path}.{name}")
		
		if node.sub is None:
			# Dataset
			return
		
		# sub
		for name, sub in node.sub.items():
			collect_unvisited(sub, f"{path}/{name}", unvisited)
	
	res = []
	collect_unvisited(hdf5_root, "", res)
	
	return res


def get_content_type(hdf5_file: h5py.File) -> ContentType:
	def key_available(key):
		try:
			val = data_from_key(hdf5_file, key)
		except KeyError:
			return False
		return True
	
	if key_available("ea.pop"):
		# run & restart
		# run vs restart: re.org
		return ContentType.RESTART if key_available("re.org") else ContentType.RUN
	
	if key_available("clamp.value"):
		# clamp: clamped
		return ContentType.CLAMP
	
	if key_available("spectrum.volt"):
		# spectrum: volt
		return ContentType.SPECTRUM
	
	return ContentType.REMEASURE
