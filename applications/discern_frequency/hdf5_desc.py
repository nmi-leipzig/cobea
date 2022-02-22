"""Description how data is stored in HDF5 files

Especially data that is required for both reading and writing.
"""

from dataclasses import astuple, dataclass
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Tuple


from adapters.hdf5_sink import chain_funcs, HDF5Sink, MetaEntry, MetaEntryMap, ParamAim
from adapters.icecraft import CarryData, IcecraftRep
from applications.discern_frequency.misc import ignore_same


class HDF5Desc(NamedTuple):
	"""Data required for both reading from and writing to a HDF5 file"""
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	shape: Tuple[Optional[int], ...] = tuple()
	alter: Callable = None

HDF5_DICT= {# simple placeholders like {} are allowed, formatting instructions like {:05d} not
	"habitat": HDF5Desc("uint8", "habitat", "/", False, tuple()),
	"habitat.desc": HDF5Desc(str, "description", "habitat"),
	"habitat.con": HDF5Desc(str, "connection", "habitat"),
	"habitat.area.min": HDF5Desc("uint16", "area_min_pos", "habitat"),
	"habitat.area.max": HDF5Desc("uint16", "area_max_pos", "habitat"),
	"habitat.in_port.pos": HDF5Desc("uint16", "in_port_pos", "habitat"),
	"habitat.in_port.dir": HDF5Desc(str, "in_port_dir", "habitat"),
	"habitat.out_port.pos": HDF5Desc("uint16", "out_port_pos", "habitat"),
	"habitat.out_port.dir": HDF5Desc(str, "out_port_dir", "habitat"),
	"chromo.desc": HDF5Desc(str, "description", "individual"), 
	"chromo.id": HDF5Desc("uint64", "chromo_id", "individual", False,
		alter=chain_funcs([itemgetter(0), attrgetter("chromosome"), attrgetter("identifier")])),
	"chromo.id.desc": HDF5Desc(str, "description", "individual/chromo_id"), 
	# type and shape have to be derived from representation
	"chromo.indices": HDF5Desc("dyn", "chromosome", "individual", False,
		alter=chain_funcs([itemgetter(0), attrgetter("chromosome"), attrgetter("allele_indices")])),
	"chromo.indices.desc": HDF5Desc(str, "description", "individual/chromosome"),
	"git_commit": HDF5Desc(str, "git_commit", "/"),
	"python": HDF5Desc(str, "python_version", "/"),
	"rand.seed": HDF5Desc("int64", r"{}seed", "/"),
	"rand.version": HDF5Desc("int64", r"{}version", "/", alter=chain_funcs([itemgetter(0), itemgetter(0)])),
	"rand.state": HDF5Desc("int64", r"{}mt_state", "/", alter=chain_funcs([itemgetter(0), itemgetter(1)])),
	"rand.gauss": HDF5Desc("float64", r"{}next_gauss", "/", alter=chain_funcs([itemgetter(0), itemgetter(2)])),
	"ea.pop_size": HDF5Desc("uint64", "pop_size"),
	"ea.gen_count": HDF5Desc("uint64", "gen_count"),
	"ea.crossover_prob": HDF5Desc("float64", "crossover_prob"),
	"ea.mutation_prob": HDF5Desc("float64", "mutation_prob"),
	"ea.eval_mode": HDF5Desc(str, "eval_mode", alter=chain_funcs([itemgetter(0), attrgetter("name")])),
	"ea.pop": HDF5Desc("uint64", "population", "/", False, None),
	"ea.pop.desc": HDF5Desc(str, "description", "population"),
	"ea.crossover.desc": HDF5Desc(str, "description", "crossover"),
	"ea.crossover.in": HDF5Desc("uint64", "parents", "crossover", False, (2, )),
	"ea.crossover.out": HDF5Desc("uint64", "children", "crossover", False, (2, )),
	"ea.crossover.generation": HDF5Desc("uint64", "generation", "crossover", False),
	"ea.crossover.generation.desc": HDF5Desc(str, "description", "crossover/generation"),
	"ea.mutation.desc": HDF5Desc(str, "description", "mutation"),
	"ea.mutation.parent": HDF5Desc("uint64", "parent", "mutation", False, alter=chain_funcs([ignore_same,
		itemgetter(0)])),
	"ea.mutation.child": HDF5Desc("uint64", "child", "mutation", False, alter=chain_funcs([ignore_same,
		itemgetter(0)])),
	"ea.mutation.generation": HDF5Desc("uint64", "generation", "mutation", False, alter=ignore_same),
	"ea.mutation.generation.desc": HDF5Desc(str, "description", "mutation/generation"),
	"fitness.chromo_id": HDF5Desc("uint64", "chromo_id", "fitness", False,
		alter=chain_funcs([itemgetter(0), attrgetter("identifier")])),
	"fitness.chromo_id.desc": HDF5Desc(str, "description", "fitness/chromo_id"),
	"fitness.desc": HDF5Desc(str, "description", "fitness"),
	"fitness.st": HDF5Desc("uint8", "s_t_index", "fitness", False),
	"fitness.st.desc": HDF5Desc(str, "description", "fitness/s_t_index"),
	"fitness.time": HDF5Desc("float64", "time", "fitness", False, alter=chain_funcs([itemgetter(0), attrgetter("time"),
		methodcaller("timestamp")])),
	"fitness.time.desc": HDF5Desc(str, "description", "fitness/time"),
	"fitness.time.unit": HDF5Desc(str, "unit", "fitness/time"),
	"fitness.value": HDF5Desc("float64", "value", "fitness", False, alter=chain_funcs([itemgetter(0),
		attrgetter("fitness")])),
	"fitness.value.desc": HDF5Desc(str, "description", "fitness/value"),
	"fitness.fast_sum": HDF5Desc("float64", "fast_sum", "fitness", False, alter=chain_funcs([itemgetter(0),
		attrgetter("fast_sum")])),
	"fitness.fast_sum.desc": HDF5Desc(str, "description", "fitness/fast_sum"),
	"fitness.slow_sum": HDF5Desc("float64", "slow_sum", "fitness", False, alter=chain_funcs([itemgetter(0),
		attrgetter("slow_sum")])),
	"fitness.slow_sum.desc": HDF5Desc(str, "description", "fitness/slow_sum"),
	"fitness.generation": HDF5Desc("uint64", "generation", "fitness", False),
	"fitness.generation.desc": HDF5Desc(str, "description", "fitness/generation"),
	"fitness.measurement": HDF5Desc(None, "measurement", "fitness", False),
	"fitness.measurement.desc": HDF5Desc(str, "description", "fitness/measurement"),
	"fitness.driver_type": HDF5Desc(str, "driver_type", "fitness/measurement", alter=attrgetter("name")),
	"fitness.driver.sn": HDF5Desc(str, "driver_serial_number", "fitness/measurement"),
	"fitness.driver.hw": HDF5Desc(str, "driver_hardware", "fitness/measurement"),
	"fitness.meter.sn": HDF5Desc(str, "meter_serial_number", "fitness/measurement"),
	"fitness.meter.hw": HDF5Desc(str, "meter_hardware", "fitness/measurement"),
	"fitness.meter.fw": HDF5Desc(str, "meter_firmware", "fitness/measurement"),
	"fitness.target.sn": HDF5Desc(str, "target_serial_number", "fitness/measurement"),
	"fitness.target.hw": HDF5Desc(str, "target_hardware", "fitness/measurement"),
	"osci.calibration": HDF5Desc("float64", "calibration", as_attr=False),
	"osci.calibration.desc": HDF5Desc(str, "description", "calibration"),
	"osci.calibration.unit": HDF5Desc(str, "unit", "calibration"),
	"osci.calibration.rising": HDF5Desc("uint64", "rising_edge", "calibration"),
	"osci.calibration.falling": HDF5Desc("uint64", "falling_edge", "calibration"),
	"osci.calibration.trig_len": HDF5Desc("uint64", "trig_len", "calibration"),
	"osci.calibration.offset": HDF5Desc("float64", "offset", "calibration"),
	"osci.channel": HDF5Desc("uint8", "data_channel", "fitness/measurement"),
	"freq_gen": HDF5Desc("uint8", "freq_gen", as_attr=False, alter=chain_funcs([itemgetter(0),
		partial(bytearray, encoding="utf-8")])),
	"freq_gen.desc": HDF5Desc(str, "description", "freq_gen"),
	"freq_gen.con": HDF5Desc(str, "connection", "freq_gen"),
	"carry_enable.values": HDF5Desc(bool, "carry_enable", "fitness", False, None),
	"carry_enable.bits": HDF5Desc("uint16", "bits", "fitness/carry_enable",
		alter=chain_funcs([partial(map, methodcaller("to_ints")), list])),
	"carry_enable.desc": HDF5Desc(str, "description", "fitness/carry_enable"),
	"re.org": HDF5Desc(str, "original_filename" "/"),
	"rep.carry_data.lut": HDF5Desc("uint8", "lut_index", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.enable": HDF5Desc("uint16", "carry_enable", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.bits": HDF5Desc("uint16", r"carry_use_{}_bits", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.values": HDF5Desc(bool, r"carry_use_{}_values", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.desc": HDF5Desc(str, "description", "mapping/carry_data"),
	# just store path, HDF5Sink takes care of the rest
	"rep.desc": HDF5Desc(str, "description", "mapping"),
	"rep.genes": HDF5Desc(None, "gene{}", "mapping/genes", False),
	"rep.genes.desc": HDF5Desc(str, "description", "mapping/genes"),
	"rep.const": HDF5Desc(None, "gene{}", "mapping/constant", False),
	"rep.const.desc": HDF5Desc(str, "description", "mapping/constant"),
	"rep.output":  HDF5Desc("uint16", "output_lutff", "mapping", alter=chain_funcs([partial(map, astuple), list])),
	"rep.colbufctrl.bits": HDF5Desc("uint16", "colbufctrl_bits", "mapping",
		alter=chain_funcs([partial(map, chain_funcs([attrgetter("bits"), partial(map, astuple), list])), list])),
	"rep.colbufctrl.indices": HDF5Desc("uint16", "colbufctrl_index", "mapping",
		alter=chain_funcs([partial(map, attrgetter("index")), list])),
	"temp.desc": HDF5Desc(str, "description", "temperature"),
	"temp.value": HDF5Desc("float16", "celsius", "temperature", False, alter=chain_funcs([itemgetter(0),
		attrgetter("measurement"), itemgetter(0)])),
	"temp.value.desc": HDF5Desc(str, "description", "temperature/celsius"),
	"temp.value.unit": HDF5Desc(str, "unit", "temperature/celsius"),
	"temp.time": HDF5Desc("float64", "time", "temperature", False, alter=chain_funcs([itemgetter(0),
		methodcaller("timestamp")])),
	"temp.time.desc": HDF5Desc(str, "description", "temperature/time"),
	"temp.time.unit": HDF5Desc(str, "unit", "temperature/time"),
	"temp.reader.sn": HDF5Desc(str, "temp_reader_serial_number", "temperature"),
	"temp.reader.hw": HDF5Desc(str, "temp_reader_hardware", "temperature"),
	"temp.sensor.sn": HDF5Desc(str, "temp_sensor_serial_number", "temperature"),
	"temp.sensor.hw": HDF5Desc(str, "temp_sensor_hardware", "temperature"),
	"clamp.desc": HDF5Desc(str, "description", "clamp"),
	"clamp.parent": HDF5Desc("uint64", "parent", "clamp", False),
	"clamp.parent.desc": HDF5Desc(str, "description", "clamp/parent"),
	"clamp.child": HDF5Desc("uint64", "child", "clamp", False),
	"clamp.child.desc": HDF5Desc(str, "description", "clamp/child"),
	"clamp.cell": HDF5Desc("uint16", "cell", "clamp", False, (2, ), alter=chain_funcs([itemgetter(0), astuple])),
	"clamp.cell.desc": HDF5Desc(str, "description", "clamp/cell"),
	"clamp.value": HDF5Desc(bool, "value", "clamp", False),
	"clamp.value.desc": HDF5Desc(str, "description", "clamp/value"),
	"clamp.clamped": HDF5Desc(bool, "clamped", "clamp", False),
	"clamp.clamped.desc": HDF5Desc(str, "description", "clamp/clamped"),
	"spectrum.volt": HDF5Desc("float64", "voltage", "fitness", False, shape=None),
	"spectrum.volt.desc": HDF5Desc(str, "description", "fitness/voltage"),
	"spectrum.volt.unit": HDF5Desc(str, "unit", "fitness/voltage"),
	"spectrum.cycles": HDF5Desc("uint16", "cycles", "fitness", False),
	"spectrum.cycles.desc": HDF5Desc(str, "description", "fitness/cycles"),
	"spectrum.cycles.unit": HDF5Desc(str, "unit", "fitness/cycles"),
	"spectrum.freq": HDF5Desc("float64", "frequency", "fitness", False),
	"spectrum.freq.desc": HDF5Desc(str, "description", "fitness/frequency"),
	"spectrum.freq.unit": HDF5Desc(str, "unit", "fitness/frequency"),
	"spectrum.period": HDF5Desc("float64", "period", "fitness", False),
	"spectrum.period.desc": HDF5Desc(str, "description", "fitness/period"),
	"spectrum.period.unit": HDF5Desc(str, "unit", "fitness/period"),
	"spectrum.mean": HDF5Desc("float64", "mean", "fitness", False),
	"spectrum.mean.desc": HDF5Desc(str, "description", "fitness/mean"),
	"spectrum.mean.unit": HDF5Desc(str, "unit", "fitness/mean"),
}

def pa_gen(gen_name: str, req_names: List[str], **kwargs: Dict[str, Any]) -> ParamAim:
	"""Generate ParamAim by gen_name
	
	(req_)names are passed as parameter
	data_type, h5_name, h5_path, as_attr and shape are retrieved by gen_name
	other entries of ParamAim can be passed as kwargs
	data_type and shape can also be overritten by kwargs
	"""
	desc = HDF5_DICT[gen_name]
	
	try:
		typ = kwargs["data_type"]
		del kwargs["data_type"]
	except KeyError:
		typ = desc.data_type
	
	try:
		shape = kwargs["shape"]
		del kwargs["shape"]
	except KeyError:
		shape = desc.shape
	
	try:
		name = desc.h5_name.format(*kwargs["name_args"])
		del kwargs["name_args"]
	except KeyError:
		name = desc.h5_name
	
	try:
		path = desc.h5_path.format(*kwargs["path_args"])
		del kwargs["path_args"]
	except KeyError:
		path = desc.h5_path
	
	if "alter" not in kwargs and desc.alter:
		kwargs["alter"] = desc.alter
	
	return ParamAim(req_names, typ, name, path, desc.as_attr, shape, **kwargs)

def add_meta(metadata: MetaEntryMap, meta_name: str, value: Any) -> None:
	"""Add MetaEntry to metadata
	
	The MetaEntry is created from data retrieved by meta_name
	"""
	desc = HDF5_DICT[meta_name]
	if not desc.as_attr:
		raise ValueError(f"{meta_name} can't be stored as metadata: as_attr is False")
	if desc.alter:
		value = desc.alter(value)
	entry = MetaEntry(desc.h5_name, value, desc.data_type)
	metadata.setdefault(desc.h5_path, []).append(entry)

def add_carry_data(metadata: MetaEntryMap, cd_iter: Iterable[CarryData]) -> None:
	lut_desc = HDF5_DICT["rep.carry_data.lut"]
	ena_desc = HDF5_DICT["rep.carry_data.enable"]
	bit_desc = HDF5_DICT["rep.carry_data.bits"]
	val_desc = HDF5_DICT["rep.carry_data.values"]
	for i, cd in enumerate(cd_iter):
		metadata.setdefault(lut_desc.h5_path.format(i), []).append(
			MetaEntry(lut_desc.h5_name, cd.lut_index, lut_desc.data_type)
		)
		metadata.setdefault(ena_desc.h5_path.format(i), []).append(
			MetaEntry(ena_desc.h5_name, [astuple(b) for b in cd.carry_enable], ena_desc.data_type)
		)
		metadata.setdefault(bit_desc.h5_path.format(i), []).extend([
			MetaEntry(bit_desc.h5_name.format(k), [astuple(b) for b in p.bits], bit_desc.data_type) 
			for k, p in enumerate(cd.carry_use)
		])
		metadata.setdefault(val_desc.h5_path.format(i), []).extend([
			MetaEntry(val_desc.h5_name.format(k), p.values, val_desc.data_type) for k, p in enumerate(cd.carry_use)
		])

def add_rep(metadata: MetaEntryMap, rep: IcecraftRep) -> None:
	def append_dict_list(org, new):
		for key, lst in new.items():
			org.setdefault(key, []).extend(lst)
	
	desc = HDF5_DICT["rep.genes"]
	append_dict_list(metadata, HDF5Sink.create_gene_meta(rep.genes, desc.h5_name.format(""), desc.h5_path))
	desc = HDF5_DICT["rep.const"]
	append_dict_list(metadata, HDF5Sink.create_gene_meta(rep.constant, desc.h5_name.format(""), desc.h5_path))
	
	add_meta(metadata, "rep.colbufctrl.bits", rep.colbufctrl)
	add_meta(metadata, "rep.colbufctrl.indices", rep.colbufctrl)
	
	add_meta(metadata, "rep.output", rep.output)
	
	add_carry_data(metadata, rep.iter_carry_data())
	
	add_meta(metadata, "carry_enable.bits", list(rep.iter_carry_bits()))
