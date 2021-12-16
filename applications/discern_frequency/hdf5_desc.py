"""Description how data is stored in HDF5 files

Especially data that is required for both reading and writing.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


from adapters.hdf5_sink import MetaEntry, MetaEntryMap, ParamAim


class HDF5Desc(NamedTuple):
	"""Data required for both reading from and writing to a HDF5 file"""
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	shape: Tuple[Optional[int], ...] = tuple()


HDF5_DICT= {
	"habitat": HDF5Desc("uint8", "habitat", "/", False, tuple()),
	"habitat.desc": HDF5Desc(str, "description", "habitat"),
	"chromo.desc": HDF5Desc(str, "description", "individual"), 
	"chromo.id": HDF5Desc("uint64", "chromo_id", "individual", False),
	"chromo.id.desc": HDF5Desc(str, "description", "individual/chromo_id"), 
	# type and shape have to be derived from representation
	"chromo.indices": HDF5Desc("dyn", "chromosome", "individual", False),
	"chromo.indices.desc": HDF5Desc(str, "description", "individual/chromosome"),
	"fitness.st": HDF5Desc("uint8", "s_t_index", "fitness", False),
	"fitness.st.desc": HDF5Desc(str, "description", "fitness/s_t_index"),
	"carry_enable.values": HDF5Desc(bool, "carry_enable", "fitness", False, None),
	"carry_enable.bits": HDF5Desc("uint16", "bits", "fitness/carry_enable"),
	"carry_enable.desc": HDF5Desc(str, "description", "fitness/carry_enable"),
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
	
	return ParamAim(req_names, typ, desc.h5_name, desc.h5_path, desc.as_attr, shape, **kwargs)

def add_meta(metadata: MetaEntryMap, meta_name: str, value: Any) -> None:
	"""Add MetaEntry to metadata
	
	The MetaEntry is created from data retrieved by meta_name
	"""
	desc = HDF5_DICT[meta_name]
	if not desc.as_attr:
		raise ValueError(f"{meta_name} can't be stored as metadata: as_attr is False")
	entry = MetaEntry(desc.h5_name, value, desc.data_type)
	metadata.setdefault(desc.h5_path, []).append(entry)