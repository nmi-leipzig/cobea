"""Functions for handling the write map for HDF5 sinks"""

import re

from dataclasses import astuple, dataclass, field
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from typing import Any, Dict, Iterable, List, Optional, Tuple

import h5py

from adapters.gear.rigol import FloatCheck, IntCheck, SetupCmd
from adapters.hdf5_sink import chain_funcs, compose, MetaEntry, MetaEntryMap, ParamAim, ParamAimMap
from adapters.icecraft import IcecraftRep
from applications.discern_frequency.hdf5_desc import add_rep, add_meta, HDF5_DICT, pa_gen


def extend_dict_list(org: Dict[Any, list], new: Dict[Any, list]) -> None:
	for key, new_list in new.items():
		org.setdefault(key, []).extend(new_list)


def create_rng_aim(name: str, prefix: str) -> List[ParamAim]:
	return [
		pa_gen("rand.version", [name], name_args=[prefix]),
		pa_gen("rand.state", [name], name_args=[prefix]),
		pa_gen("rand.gauss", [name], name_args=[prefix]),
	]

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
		"RandomChromo.perform": chromo_aim,
		"GenChromo.perform": chromo_aim,
		"habitat": [pa_gen("habitat", ["text"], alter=partial(compose, funcs=[itemgetter(0), partial(bytearray,
			encoding="utf-8")]), comp_opt=9),],
	}
	
	metadata = {}
	add_meta(metadata, "rep.desc", "mapping of the genotype (allele indices) to configuration bits")
	add_meta(metadata, "rep.genes.desc", "part of the configuration bits that is configurable")
	add_meta(metadata, "rep.const.desc", "part of the configuration bits that is fixed")
	add_meta(metadata, "habitat.desc", "basic configuration of the target FPGA that defines the periphery of the "
		"evolved part; the values are bytes of the asc format")
	add_meta(metadata, "chromo.desc", "data for the genotype")
	add_meta(metadata, "chromo.id.desc", "unique ID of every chromosome")
	add_meta(metadata, "chromo.indices.desc", "allele choices for every chromosome")
	add_meta(metadata, "rep.carry_data.desc", "data describing how to derive the carry bits from the configuration bits "
		"defined by the genotype")
	
	add_rep(metadata, rep)
	
	return write_map, metadata


def add_calibration(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	write_map.setdefault("calibration", []).extend([
		pa_gen("osci.calibration", ["data"], shuffle=False),
		pa_gen("osci.calibration.rising", ["rising_edge"]),
		pa_gen("osci.calibration.falling", ["falling_edge"]),
		pa_gen("osci.calibration.trig_len", ["trig_len"]),
		pa_gen("osci.calibration.offset", ["offset"]),
	])
	
	add_meta(metadata, "osci.calibration.desc", "calibrate the measurement time to the exact duration of the 10 bursts;"
			" the trigger signaling the bursts should start at 0.5 s")
	add_meta(metadata, "osci.calibration.unit", "Volt")


def add_freq_gen(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	write_map.setdefault("freq_gen", []).append(pa_gen("freq_gen", ["text"], comp_opt=9))
	
	add_meta(metadata, "freq_gen.desc", "configuration of the driver FPGA that creates the frequency bursts; the values "
			"are bytes of the asc format")


def add_fpga_osci(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	"""Add the entries for a FPGA driver and oscilloscope meter to an existing HDF5Sink write map and metadata"""
	
	add_calibration(write_map, metadata)
	add_freq_gen(write_map, metadata)
	
	write_map.setdefault("Measure.perform", []).append(pa_gen("fitness.measurement", ["return"], data_type="uint8",
		alter=chain_funcs([itemgetter(0), attrgetter("measurement")]), shape=(2**19, ), shuffle=False))
	
	add_meta(metadata, "fitness.measurement.desc", "raw output of the phenotype measured by an oscilloscope; each " 
			"measurement took 6 s; in the last 5 s 10 bursts of either 1 kHz or 10 kHz were presented at the input;"
			" only this last 5 s are relevant for the fitness value; the volt value can be computed by v = (125 - "
			"r)*:CHAN1:SCAL/25 - :CHAN1:OFFS")

def add_drvmtr(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	"""Add the entries for a MCU based combined driver and meter to an existing HDF5Sink write map and metadata"""
	
	write_map.setdefault("Measure.perform", []).append(pa_gen("fitness.measurement", ["return"], data_type="uint16",
		alter=chain_funcs([itemgetter(0), attrgetter("measurement")]), shape=(10*256, ), shuffle=False))
	
	add_meta(metadata, "fitness.measurement.desc", "output of the phenotype processed by an analog integrator measured " 
			"by a MCU based ADC; 10 0.5 s bursts of either 1 kHz or 10 kHz were presented at the input; per burst 256 "
			"measurements were performed")

def add_dummy(write_map: ParamAimMap, metadata: MetaEntryMap, sub_count: int) -> None:
	"""Add the entries for a dummy driver and random meter to an existing HDF5Sink write map and metadata"""
	
	write_map.setdefault("Measure.perform", []).append(pa_gen("fitness.measurement", ["return"], data_type="float64", 
		alter=chain_funcs([itemgetter(0), attrgetter("measurement")]), shape=(10*sub_count, ), shuffle=False))
	
	add_meta(metadata, "fitness.measurement.desc", f"random output for simulating a measurement; 10 bursts each "
		f"{sub_count} measurements")
	

def add_temp(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	temp_map = {
		"temperature.perform": [pa_gen("temp.value", ["return"], comp_opt=9, shuffle=True)],
		"temperature.additional": [pa_gen("temp.time", ["time"], comp_opt=9, shuffle=True)],
		# use ParamAim for temp serial as it is collected in a separate process
		"meta.temp": [
			pa_gen("temp.reader.sn", ["sn"]),
			pa_gen("temp.reader.hw", ["hw"]),
			pa_gen("temp.sensor.sn", ["sensor_sn"]),
			pa_gen("temp.sensor.hw", ["sensor_hw"]),
		],
	}
	
	add_meta(metadata, "temp.desc", "temperature recorded at the surface of the FPGA")
	add_meta(metadata, "temp.value.desc", "measured temperature")
	add_meta(metadata, "temp.value.unit", "degree celsius")
	add_meta(metadata, "temp.time.desc", "time the temperature measurement started; timezone UTC")
	add_meta(metadata, "temp.time.unit", "seconds since 01.01.1970 00:00:00")
	
	extend_dict_list(write_map, temp_map)


def add_measure(write_map: ParamAimMap, metadata: MetaEntryMap, rep: IcecraftRep) -> None:
	"""Add the entries for MeasureFitness use case"""
	write_map.setdefault("Measure.perform", []).extend([
		pa_gen("fitness.st", ["driver_data"], comp_opt=9, shuffle=True),
		pa_gen("fitness.time", ["return"], comp_opt=9, shuffle=True),
	])
	ea_map = {
		"MeasureFitness.perform": [
			pa_gen("fitness.value", ["return"], comp_opt=9, shuffle=True),
			pa_gen("fitness.fast_sum", ["return"], comp_opt=9, shuffle=True),
			pa_gen("fitness.slow_sum", ["return"], comp_opt=9, shuffle=True),
			pa_gen("fitness.chromo_id", ["chromosome"], comp_opt=9, shuffle=True),
			pa_gen("carry_enable.values", ["return"], alter=partial(compose, funcs=[itemgetter(0),
				attrgetter("carry_enable")]), shape=(len(list(rep.iter_carry_bits())), ), comp_opt=4),
		],
	}
	
	add_meta(metadata, "fitness.value.desc", "actual fitness value")
	add_meta(metadata, "fitness.fast_sum.desc", "aggregated area under the curve for all 10 kHz bursts")
	add_meta(metadata, "fitness.slow_sum.desc", "aggregated area under the curve for all 1 kHz bursts")
	add_meta(metadata, "fitness.chromo_id.desc", "ID of the corresponding chromosome")
	add_meta(metadata, "fitness.st.desc", "index of the s-t-combination used for determining the order of 5 1 kHz and "
		"5 10 kHz bursts")
	add_meta(metadata, "fitness.desc", "data regarding the fitness values")
	add_meta(metadata, "fitness.time.desc", "time the measurement started; timezone UTC")
	add_meta(metadata, "fitness.time.unit", "seconds since 01.01.1970 00:00:00")
	add_meta(metadata, "carry_enable.desc", "values of carry enable bits; derived from the configuration bits defined "
		"by the genotype")
	
	extend_dict_list(write_map, ea_map)


def add_ea(write_map: ParamAimMap, metadata: MetaEntryMap, pop_size: int) -> None:
	"""Add the entries for an evolutionary algorithm to an existing HDF5Sink write map"""
	
	write_map.setdefault("MeasureFitness.perform", []).append(pa_gen("fitness.generation", ["generation"], comp_opt=9, shuffle=True))
	
	ea_map = {
		"SimpleEA.ea_params": [
			pa_gen("ea.pop_size", ["pop_size"]),
			pa_gen("ea.gen_count", ["gen_count"]),
			pa_gen("ea.crossover_prob", ["crossover_prob"]),
			pa_gen("ea.mutation_prob", ["mutation_prob"]),
			pa_gen("ea.eval_mode", ["eval_mode"]),
		],
		"SimpleEA.random_initial": create_rng_aim("state", "random_initial_"),
		"SimpleEA.random_final": create_rng_aim("state", "random_final_"),
		"SimpleEA.gen":[
			pa_gen("ea.pop", ["pop"], shape=(pop_size, ), shuffle=True),
		],
		"Individual.wrap.cxOnePoint": [
			pa_gen("ea.crossover.in", ["in"], comp_opt=9, shuffle=True),
			pa_gen("ea.crossover.out", ["out"], comp_opt=9, shuffle=True),
			pa_gen("ea.crossover.generation", ["generation"], comp_opt=9, shuffle=True),
		],
		"Individual.wrap.mutUniformInt": [
			pa_gen("ea.mutation.parent", ["out", "in"], comp_opt=9, shuffle=True),
			pa_gen("ea.mutation.child", ["in", "out"], comp_opt=9, shuffle=True),
			pa_gen("ea.mutation.generation", ["in", "out", "generation"], comp_opt=9, shuffle=True),
		],
		"prng": [pa_gen("rand.seed", ["seed"], name_args=["prng_"])] + create_rng_aim("final_state", "prng_final_"),
	}
	
	add_meta(metadata, "ea.mutation.desc", "IDs of chromosomes resulting from mutation; as all chromosomes of a "
		"generation participate in mutation, only alterations are recorded")
	add_meta(metadata, "ea.mutation.generation.desc", "value i means mutation occured while generating generation "
		"i from generation i-1")
	add_meta(metadata, "ea.crossover.desc", "IDs of the chromosomes participating in and resulting from crossover")
	add_meta(metadata, "ea.crossover.generation.desc", "value i means crossover occured while generating generation "
		"i from generation i-1")
	add_meta(metadata, "ea.pop.desc", "IDs of the chromosomes included in each generation")
	add_meta(metadata, "fitness.generation.desc", "generation in which the fitness was evaluated")
	
	extend_dict_list(write_map, ea_map)


def add_clamp(write_map: ParamAimMap, metadata: MetaEntryMap) -> None:
	add_meta(metadata, "clamp.desc", "Iteratively set function units to fixed value if this does not impair the "
		"fitness")
	add_meta(metadata, "clamp.parent.desc", "ID of the previous chromosome")
	add_meta(metadata, "clamp.child.desc", "ID of the clamped chromosome")
	add_meta(metadata, "clamp.cell.desc", "Cell whos function unit was clamped")
	add_meta(metadata, "clamp.value.desc", "Value the cell was clamped to")
	add_meta(metadata, "clamp.clamped.desc", "True iff cell was kept clamped")
	
	write_map["clamp"] = [
		pa_gen("clamp.parent", ["parent"], comp_opt=9, shuffle=True),
		pa_gen("clamp.child", ["child"], comp_opt=9, shuffle=True),
		pa_gen("clamp.cell", ["cell"], comp_opt=9, shuffle=True),
		pa_gen("clamp.value", ["value"], comp_opt=4),
		pa_gen("clamp.clamped", ["clamped"], comp_opt=4),
	]


def create_for_run(rep: IcecraftRep, pop_size: int, chromo_bits: 16, temp: bool=True) -> Tuple[ParamAimMap,
	MetaEntryMap]:
	"""Create HDF5Sink write map for running a full evolutionary algorithm"""
	write_map, metadata = create_base(rep, chromo_bits)
	if temp:
		add_temp(write_map, metadata)
	add_ea(write_map, metadata, pop_size)
	add_measure(write_map, metadata, rep)
	
	return write_map, metadata

def create_for_remeasure(rep: IcecraftRep, chromo_bits: 16, temp: bool=True) -> Tuple[ParamAimMap, MetaEntryMap]:
	"""Create HDF5Sink write map for running a full evolutionary algorithm"""
	write_map, metadata = create_base(rep, chromo_bits)
	if temp:
		add_temp(write_map, metadata)
	add_measure(write_map, metadata, rep)
	
	return write_map, metadata


def create_for_spectrum(rep: IcecraftRep, chromo_bits: 16, volt_len: int, temp: bool=True) -> Tuple[ParamAimMap, MetaEntryMap]:
	"""Create HDF5Sink write map for measuring response to a series of frequencies"""
	write_map, metadata = create_base(rep, chromo_bits)
	if temp:
		add_temp(write_map, metadata)
	
	add_calibration(write_map, metadata)
	add_freq_gen(write_map, metadata)
	
	write_map.setdefault("Measure.perform", []).extend([
		pa_gen("fitness.measurement", ["return"], data_type="uint8", alter=chain_funcs([itemgetter(0),
			attrgetter("measurement")]), shape=(2**19, ), shuffle=False),
		pa_gen("spectrum.cycles", ["driver_data"], alter=chain_funcs([itemgetter(0), itemgetter(0)]), comp_opt=9,
			shuffle=True),
		pa_gen("fitness.time", ["return"], comp_opt=9, shuffle=True),
	])
	
	write_map.setdefault("spectrum.carry", []).extend([
		pa_gen("carry_enable.values", ["carry_enable"], shape=(len(list(rep.iter_carry_bits())), ), comp_opt=4),
	])
	
	add_meta(metadata, "fitness.measurement.desc", "raw output of the phenotype measured by an oscilloscope; each " 
			"measurement took 6 s; in the last 5 s a specific frequency was constantly presented to the input; "
			"the volt value can be computed by v = (125 - r)*:CHAN1:SCAL/25 - :CHAN1:OFFS")
	add_meta(metadata, "spectrum.cycles.desc", "number of clock cycles per period; clock of frequency generator si 12 MHz")
	add_meta(metadata, "spectrum.cycles.unit", "clock cycles of the frequency generator")
	add_meta(metadata, "fitness.time.desc", "time the measurement started; timezone UTC")
	add_meta(metadata, "fitness.time.unit", "seconds since 01.01.1970 00:00:00")
	add_meta(metadata, "carry_enable.desc", "values of carry enable bits; derived from the configuration bits defined "
		"by the genotype")
	
	write_map.setdefault("spectrum.measure", []).extend([
		pa_gen("spectrum.volt", ["volt"], shape=(volt_len, )),
		pa_gen("spectrum.freq", ["freq"], comp_opt=9, shuffle=True),
		pa_gen("spectrum.period", ["period"], comp_opt=9, shuffle=True),
		pa_gen("spectrum.mean", ["mean_volt"], comp_opt=9, shuffle=True),
	])
	
	add_meta(metadata, "spectrum.volt.desc", "voltage values computed from the measurement")
	add_meta(metadata, "spectrum.volt.unit", "Volt")
	add_meta(metadata, "spectrum.freq.desc", "generated frequency")
	add_meta(metadata, "spectrum.freq.unit", "Hertz")
	add_meta(metadata, "spectrum.period.desc", "period of the generated frequency")
	add_meta(metadata, "spectrum.period.unit", "Seconds")
	add_meta(metadata, "spectrum.mean.desc", "mean voltage")
	add_meta(metadata, "spectrum.mean.unit", "Volt")
	
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


def write_setup(metadata: MetaEntryMap, setup: SetupCmd) -> None:
	desc = HDF5_DICT["osci.setup"]
	entries = meter_setup_to_meta(setup)
	metadata.setdefault(desc.h5_path, []).extend(entries)

