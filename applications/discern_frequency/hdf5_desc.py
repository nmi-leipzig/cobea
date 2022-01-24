"""Description how data is stored in HDF5 files

Especially data that is required for both reading and writing.
"""

from dataclasses import astuple, dataclass
from functools import partial
from operator import attrgetter, itemgetter
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Tuple


from adapters.hdf5_sink import chain_funcs, HDF5Sink, MetaEntry, MetaEntryMap, ParamAim
from adapters.icecraft import CarryData, IcecraftRep


class HDF5Desc(NamedTuple):
	"""Data required for both reading from and writing to a HDF5 file"""
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	shape: Tuple[Optional[int], ...] = tuple()
	alter: Callable = None

HDF5_DICT= {
	"habitat": HDF5Desc("uint8", "habitat", "/", False, tuple()),
	"habitat.desc": HDF5Desc(str, "description", "habitat"),
	"chromo.desc": HDF5Desc(str, "description", "individual"), 
	"chromo.id": HDF5Desc("uint64", "chromo_id", "individual", False,
		alter=chain_funcs([itemgetter(0), attrgetter("chromosome"), attrgetter("identifier")])),
	"chromo.id.desc": HDF5Desc(str, "description", "individual/chromo_id"), 
	# type and shape have to be derived from representation
	"chromo.indices": HDF5Desc("dyn", "chromosome", "individual", False,
		alter=chain_funcs([itemgetter(0), attrgetter("chromosome"), attrgetter("allele_indices")])),
	"chromo.indices.desc": HDF5Desc(str, "description", "individual/chromosome"),
	"fitness.chromo_id": HDF5Desc("uint64", "chromo_id", "fitness", False,
		alter=chain_funcs([itemgetter(0), attrgetter("identifier")])),
	"fitness.st": HDF5Desc("uint8", "s_t_index", "fitness", False),
	"fitness.st.desc": HDF5Desc(str, "description", "fitness/s_t_index"),
	"carry_enable.values": HDF5Desc(bool, "carry_enable", "fitness", False, None),
	"carry_enable.bits": HDF5Desc("uint16", "bits", "fitness/carry_enable"),
	"carry_enable.desc": HDF5Desc(str, "description", "fitness/carry_enable"),
	"rep.carry_data.lut": HDF5Desc("uint8", "lut_index", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.enable": HDF5Desc("uint16", "carry_enable", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.bits": HDF5Desc("uint16", r"carry_use_{}_bits", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.values": HDF5Desc(bool, r"carry_use_{}_values", r"mapping/carry_data/carry_data_{}"),
	"rep.carry_data.desc": HDF5Desc(str, "description", "mapping/carry_data"),
	# just store path, HDF5Sink takes care of the rest
	"rep.genes": HDF5Desc(None, "gene", "mapping/genes"),
	"rep.const": HDF5Desc(None, "gene", "mapping/constant"),
	"rep.output":  HDF5Desc("uint16", "output_lutff", "mapping", alter=chain_funcs([partial(map, astuple), list])),
	"rep.colbufctrl.bits": HDF5Desc("uint16", "colbufctrl_bits", "mapping",
		alter=chain_funcs([partial(map, chain_funcs([attrgetter("bits"), partial(map, astuple), list])), list])),
	"rep.colbufctrl.indices": HDF5Desc("uint16", "colbufctrl_index", "mapping",
		alter=chain_funcs([partial(map, attrgetter("index")), list])),
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
	
	if "alter" not in kwargs and desc.alter:
		kwargs["alter"] = desc.alter
	
	return ParamAim(req_names, typ, desc.h5_name, desc.h5_path, desc.as_attr, shape, **kwargs)

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
	append_dict_list(metadata, HDF5Sink.create_gene_meta(rep.genes, desc.h5_name, desc.h5_path))
	desc = HDF5_DICT["rep.const"]
	append_dict_list(metadata, HDF5Sink.create_gene_meta(rep.constant, desc.h5_name, desc.h5_path))
	
	add_meta(metadata, "rep.colbufctrl.bits", rep.colbufctrl)
	add_meta(metadata, "rep.colbufctrl.indices", rep.colbufctrl)
	
	add_meta(metadata, "rep.output", rep.output)
	
	add_carry_data(metadata, rep.iter_carry_data())
