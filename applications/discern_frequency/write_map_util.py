"""Functions for handling the write map for HDF5 sinks"""

import re

from dataclasses import astuple, dataclass, field
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from typing import Any, Dict, Iterable, List, Optional, Tuple

import h5py

from adapters.gear.rigol import FloatCheck, IntCheck, SetupCmd
from adapters.hdf5_sink import compose, IgnoreValue, MetaEntry, MetaEntryMap, ParamAim, ParamAimMap
from adapters.icecraft import IcecraftRep
from applications.discern_frequency.hdf5_desc import add_rep, add_meta, HDF5_DICT, pa_gen


@dataclass
class FormData:
	"""Data for inserting HDF5 groups and names"""
	name: Iterable = field(default_factory=tuple)
	path: Iterable = field(default_factory=tuple)


@dataclass
class FormEntry:
	key: str
	data: Optional[List[FormData]]


@dataclass
class ExpEntries:
	simple: List[str]
	form: List[FormEntry] = field(default_factory=list)
	
	def __add__(self, other: "ExpEntries") -> "ExpEntries":
		return ExpEntries(self.simple+other.simple, self.form+other.form)


ENTRIES_MEASURE = ExpEntries([])

ENTRIES_REP = ExpEntries([])

ENTRIES_RUN = ENTRIES_REP + ENTRIES_MEASURE


def create_rng_aim(name: str, prefix: str) -> List[ParamAim]:
	return [
		ParamAim([name], "int64", f"{prefix}version", alter=partial(compose, funcs=[itemgetter(0), itemgetter(0)])),
		ParamAim([name], "int64", f"{prefix}mt_state", alter=partial(compose, funcs=[itemgetter(0), itemgetter(1)])),
		ParamAim([name], "float64",f"{prefix}next_gauss",alter=partial(compose, funcs=[itemgetter(0), itemgetter(2)])),
	]

def ignore_same(x: list) -> Any:
	"""raise IgnoreValue of first two elements are equal, else return the last
	
	That way a third value can be rejected when two other values are identical
	"""
	if x[0] == x[1]:
		raise IgnoreValue()
	return x[-1]

def is_rep_fitting(rep: IcecraftRep, chromo_bits: int) -> bool:
	"""check if representation fits in a certain number of bits"""
	for gene in rep.iter_genes():
		if len(gene.alleles) > 1<<chromo_bits:
			return False
	
	return True

def create_base(rep: IcecraftRep, chromo_bits: 16) -> Tuple[ParamAimMap, MetaEntryMap]:
	"""Create HDF5Sink write map with entries that are always required"""
	if not is_rep_fitting(rep, chromo_bits):
		raise ValueError(f"representation needs more than {chromo_bits} bits")
	
	# use attrgetter and so on to allow pickling for multiprocessing
	
	chromo_aim = [
		pa_gen(
			"chromo.indices", ["return"], data_type=f"uint{chromo_bits}", shape=(len(rep.genes), ),
			comp_opt=9, shuffle=True
		),
		pa_gen("chromo.id", ["return"], comp_opt=9, shuffle=True),
	]
	
	write_map = {
		"Measure.perform": [
			pa_gen("fitness.st", ["driver_data"], comp_opt=9, shuffle=True),
			ParamAim(["return"], "float64", "time", "fitness", as_attr=False,
				 alter=partial(compose, funcs=[itemgetter(0), attrgetter("time"), methodcaller("timestamp")]), comp_opt=9,
				 shuffle=True),
		],
		"RandomChromo.perform": chromo_aim,
		"GenChromo.perform": chromo_aim,
		"habitat": [pa_gen("habitat", ["text"], alter=partial(compose, funcs=[itemgetter(0), partial(bytearray,
			encoding="utf-8")]), comp_opt=9),],
	}
	
	metadata = {
		"fitness": [MetaEntry("description", "data regarding the fitness values")],
		"fitness/time": [
			MetaEntry("description", "time the measurement started; timezone UTC"),
			MetaEntry("unit", "seconds since 01.01.1970 00:00:00")
		],
		"mapping": [MetaEntry("description", "mapping of the genotype (allele indices) to configuration bits")],
		"mapping/genes": [MetaEntry("description", "part of the configuration bits that is configurable")],
		"mapping/constant": [MetaEntry("description", "part of the configuration bits that is fixed")],
	}
	add_meta(metadata, "habitat.desc", "basic configuration of the target FPGA that defines the periphery of the "
		"evolved part; the values are bytes of the asc format")
	add_meta(metadata, "chromo.desc", "data for the genotype")
	add_meta(metadata, "chromo.id.desc", "unique ID of every chromosome")
	add_meta(metadata, "chromo.indices.desc", "allele choices for every chromosome")
	add_meta(metadata, "fitness.st.desc", "index of the s-t-combination used for determining the order of 5 1 kHz and "
		"5 10 kHz bursts")
	add_meta(metadata, "carry_enable.desc", "values of carry enable bits; derived from the configuration bits defined "
		"by the genotype")
	add_meta(metadata, "rep.carry_data.desc", "data describing how to derive the carry bits from the configuration bits "
		"defined by the genotype")
	
	add_rep(metadata, rep)
	
	return write_map, metadata

def add_fpga_osci(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	"""Add the entries for a FPGA driver and oscilloscope meter to an existing HDF5Sink write map and metadata"""
	
	write_map.setdefault("Measure.perform", []).append(ParamAim(["return"], "uint8", "measurement", "fitness",
		alter=partial(compose, funcs=[itemgetter(0), attrgetter("measurement")]), as_attr=False, shape=(2**19, ), shuffle=False))
	
	write_map.setdefault("calibration", []).extend([
		ParamAim(["data"], "float64", "calibration", as_attr=False, shuffle=False),
		ParamAim(["rising_edge"], "uint64", "rising_edge", "calibration"),
		ParamAim(["falling_edge"], "uint64", "falling_edge", "calibration"),
		ParamAim(["trig_len"], "uint64", "trig_len", "calibration"),
		ParamAim(["offset"], "float64", "offset", "calibration"),
	])
	
	write_map.setdefault("freq_gen", []).extend([ParamAim(["text"], "uint8", "freq_gen", as_attr=False,
		alter=partial(compose, funcs=[itemgetter(0), partial(bytearray, encoding="utf-8")]), comp_opt=9),])
	
	metadata.setdefault("fitness/measurement", []).append(
		MetaEntry("description", "raw output of the phenotype measured by an oscilloscope; each " 
			"measurement took 6 s; in the last 5 s 10 bursts of either 1 kHz or 10 kHz were presented at the input;"
			" only this last 5 s are relevant for the fitness value; the volt value can be computed by v = (125 - "
			"r)*:CHAN1:SCAL/25 - :CHAN1:OFFS")
	)
	
	metadata.setdefault("calibration", []).extend([
		MetaEntry("description", "calibrate the measurement time to the exact duration of the 10 bursts; the "
			"trigger signaling the bursts should start at 0.5 s"),
		MetaEntry("unit", "Volt"),
	])
	metadata.setdefault("freq_gen", []).append(
		MetaEntry("description", "configuration of the driver FPGA that creates the frequency bursts; the values "
			"are bytes of the asc format")
	)

def add_drvmtr(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	"""Add the entries for a MCU based combined driver and meter to an existing HDF5Sink write map and metadata"""
	
	write_map.setdefault("Measure.perform", []).append(ParamAim(["return"], "uint16", "measurement", "fitness",
		alter=partial(compose, funcs=[itemgetter(0), attrgetter("measurement")]), as_attr=False, shape=(10*256, ), shuffle=False))
	
	metadata.setdefault("fitness/measurement", []).append(
		MetaEntry("description", "output of the phenotype processed by an analog integrator measured by a MCU based ADC" 
			"; 10 0.5 s bursts of either 1 kHz or 10 kHz were presented at the input; per burst 256 measurements were"
			" performed")
	)

def add_dummy(write_map: ParamAimMap, metadata: MetaEntryMap, sub_count: int) -> None:
	"""Add the entries for a dummy driver and random meter to an existing HDF5Sink write map and metadata"""
	
	write_map.setdefault("Measure.perform", []).append(ParamAim(["return"], "float64", "measurement", "fitness",
		alter=partial(compose, funcs=[itemgetter(0), attrgetter("measurement")]), as_attr=False, shape=(10*sub_count, ), shuffle=False))
	
	metadata.setdefault("fitness/measurement", []).append(
		MetaEntry("description", f"random output for simulating a measurement; 10 bursts each {sub_count} measurements")
	)
	

def add_temp(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	temp_map = {
		"temperature.perform": [
			ParamAim(["return"], "float16", "celsius", "temperature", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), attrgetter("measurement"), itemgetter(0)]), comp_opt=9, shuffle=True),
		],
		"temperature.additional": [
			ParamAim(["time"], "float64", "time", "temperature", as_attr=False,
				alter=partial(compose, funcs=[itemgetter(0), methodcaller("timestamp")]), comp_opt=9, shuffle=True),
		],
		# use ParamAim for temp serial as it is collected in a separate process
		"meta.temp": [
			ParamAim(["sn"], str, "temp_reader_serial_number", "temperature"),
			ParamAim(["hw"], str, "temp_reader_hardware", "temperature"),
			ParamAim(["sensor_sn"], str, "temp_sensor_serial_number", "temperature"),
			ParamAim(["sensor_hw"], str, "temp_sensor_hardware", "temperature"),
		],
	}
	
	temp_meta = {
		"temperature": [MetaEntry("description", "temperature recorded at the surface of the FPGA")],
		"temperature/celsius": [MetaEntry("description", "measured temperature"), MetaEntry("unit", "degree celsius")],
		"temperature/time": [
			MetaEntry("description", "time the temperature measurement started; timezone UTC"),
			MetaEntry("unit", "seconds since 01.01.1970 00:00:00")
		],
	}
	
	write_map.update(temp_map)
	metadata.update(temp_meta)


def add_measure(write_map: ParamAimMap, metadata: MetaEntryMap, rep: IcecraftRep) -> None:
	"""Add the entries for MeasureFitness use case"""
	ea_map = {
		"MeasureFitness.perform": [
			ParamAim(["return"], "float64", "value", "fitness", as_attr=False, alter=partial(compose, funcs=[
				itemgetter(0), attrgetter("fitness")]), comp_opt=9, shuffle=True),
			ParamAim(["return"], "float64", "fast_sum", "fitness", as_attr=False, alter=partial(compose, funcs=[
				itemgetter(0), attrgetter("fast_sum")]), comp_opt=9, shuffle=True),
			ParamAim(["return"], "float64", "slow_sum", "fitness", as_attr=False, alter=partial(compose, funcs=[
				itemgetter(0), attrgetter("slow_sum")]), comp_opt=9, shuffle=True),
			pa_gen("fitness.chromo_id", ["chromosome"], comp_opt=9, shuffle=True),
			pa_gen("carry_enable.values", ["return"], alter=partial(compose, funcs=[itemgetter(0),
				attrgetter("carry_enable")]), shape=(len(list(rep.iter_carry_bits())), ), comp_opt=4),
			ParamAim(["generation"], "uint64", "generation", "fitness", as_attr=False, comp_opt=9, shuffle=True),
		],
	}
	
	ea_meta = {
		"fitness/value": [MetaEntry("description", "actual fitness value")],
		"fitness/fast_sum": [MetaEntry("description", "aggregated area under the curve for all 10 kHz bursts")],
		"fitness/slow_sum": [MetaEntry("description", "aggregated area under the curve for all 1 kHz bursts")],
		"fitness/chromo_id": [MetaEntry("description", "ID of the corresponding chromosome")],
		"fitness/generation": [MetaEntry("description", "generation in which the fitness was evaluated")],
	}
	
	write_map.update(ea_map)
	metadata.update(ea_meta)


def add_ea(write_map: ParamAimMap, metadata: MetaEntryMap, pop_size: int) -> None:
	"""Add the entries for an evolutionary algorithm to an existing HDF5Sink write map"""
	
	ea_map = {
		"SimpleEA.ea_params": [
			ParamAim(["pop_size"], "uint64", "pop_size"),
			ParamAim(["gen_count"], "uint64", "gen_count"),
			ParamAim(["crossover_prob"], "float64", "crossover_prob"),
			ParamAim(["mutation_prob"], "float64", "mutation_prob"),
			ParamAim(["eval_mode"], str, "eval_mode"),
		],
		"SimpleEA.random_initial": create_rng_aim("state", "random_initial_"),
		"SimpleEA.random_final": create_rng_aim("state", "random_final_"),
		"SimpleEA.gen":[
			ParamAim(["pop"], "uint64", "population", as_attr=False, shape=(pop_size, ), shuffle=True),
		],
		"Individual.wrap.cxOnePoint": [
			ParamAim(["in"], "uint64", "parents", "crossover", as_attr=False, shape=(2, ), comp_opt=9, shuffle=True),
			ParamAim(["out"], "uint64", "children", "crossover", as_attr=False, shape=(2, ), comp_opt=9, shuffle=True),
			ParamAim(["generation"], "uint64", "generation", "crossover", as_attr=False, comp_opt=9, shuffle=True),
		],
		"Individual.wrap.mutUniformInt": [
			ParamAim(
				["out", "in"], "uint64", "parent", "mutation", as_attr=False,
				alter=partial(compose, funcs=[ignore_same, itemgetter(0)]), comp_opt=9, shuffle=True
			),
			ParamAim(
				["in", "out"], "uint64", "child", "mutation", as_attr=False,
				alter=partial(compose, funcs=[ignore_same, itemgetter(0)]), comp_opt=9, shuffle=True
			),
			ParamAim(
				["in", "out", "generation"], "uint64", "generation", "mutation", as_attr=False,
				alter=ignore_same, comp_opt=9, shuffle=True
			),
		],
		"prng": [ParamAim(["seed"], "int64", "prng_seed")] + create_rng_aim("final_state", "prng_final_"),
	}
	
	ea_meta = {
		"population": [MetaEntry("description", "IDs of the chromosomes included in each generation")],
		"crossover": [MetaEntry("description", "IDs of the chromosomes participating in and resulting from crossover")],
		"crossover/generation": [MetaEntry("description", "value i means crossover occured while generating generation "
			"i from generation i-1")],
		"mutation": [MetaEntry("description", "IDs of chromosomes resulting from mutation; as all chromosomes of a "
			"generation participate in mutation, only alterations are recorded")],
		"mutation/generation": [MetaEntry("description", "value i means mutation occured while generating generation "
			"i from generation i-1")],
	}
	
	write_map.update(ea_map)
	metadata.update(ea_meta)

def create_for_run(rep: IcecraftRep, pop_size: int, chromo_bits: 16, temp: bool=True)-> Tuple[ParamAimMap,
	MetaEntryMap]:
	"""Create HDF5Sink write map for running a full evolutionary algorithm"""
	write_map, metadata = create_base(rep, chromo_bits)
	if temp:
		add_temp(write_map, metadata)
	add_ea(write_map, metadata, pop_size)
	add_measure(write_map, metadata, rep)
	
	return write_map, metadata

def meter_setup_to_meta(setup: SetupCmd) -> List[MetaEntry]:
	if not setup.condition_(setup):
		return []
	
	res = []
	if setup.values_ is not None:
		if setup.value_ not in setup.values_:
			raise ValueError(f"'{setup.value_}' invalid for {setup.name_}")
		
		if isinstance(setup.values_, FloatCheck):
			data_type = float
		elif isinstance(setup.values_, IntCheck):
			data_type = int
		else:
			data_type = type(setup.values_[0])
		res.append(MetaEntry(setup.cmd_(full=False), setup.value_, data_type))
	
	for subcmd in setup.subcmds_:
		res.extend(meter_setup_to_meta(subcmd))
	
	return res

def fixed_prefix(path: str) -> str:
	"""Find longest prefix without palceholder"""
	parts = path.split("/")
	i = 0
	for p in parts:
		if re.search("{}", p):
			break
		i += 1
	
	return "/".join(parts[:i])

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
	
	def visit_pat(grp, path_parts, attr):
		if len(path_parts) == 0:
			grp.visited = True
			if attr is None:
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
			visit_pat(grp, path_parts[1:], attr)
			return
		
		grp.visited = True
		
		if "{}" in path_parts[0]:
			pat = path_parts[0].replace("{}", ".*")
			for name in grp.sub:
				if re.match(pat, name):
					visit_pat(grp.sub[name], path_parts[1:], attr)
		else:
			try:
				sub = grp.sub[path_parts[0]]
			except KeyError:
				return
			
			visit_pat(sub, path_parts[1:], attr)
	
	def start_visit(path, name, as_attr):
		if as_attr:
			visit_pat(hdf5_root, path.split("/"), name)
		else:
			visit_pat(hdf5_root, path.split("/")+[name], None)
	
	for desc_key in exp_entries.simple:
		desc = HDF5_DICT[desc_key]
		start_visit(desc.h5_path, desc.h5_name, desc.as_attr)
	
	for entry in exp_entries.form:
		desc = HDF5_DICT[entry.key]
		if entry.data is None:
			start_visit(desc.h5_path, desc.h5_name, desc.as_attr)
			continue
		
		for dat in entry.data:
			full_name = desc.h5_name.format(*dat.name)
			full_path = desc.h5_path.format(*dat.path)
			
			start_visit(full_path, full_name, desc.as_attr)
	
	def collect_unvisited(node, path, unvisited):
		if not node.visited:
			unvisited.append(path)
			# don't go deeper, as it is obvious that all attributes and subgroups were not visited
			return
		
		# attriutes
		for name, visited in node.attrs.items():
			if visited:
				continue
			
			unvisited.append(path+"."+name)
		
		if node.sub is None:
			# Dataset
			return
		
		# sub
		for name, sub in node.sub.items():
			collect_unvisited(sub, path+"/"+name, unvisited)
	
	res = []
	collect_unvisited(hdf5_root, "", res)
	
	return res
 
