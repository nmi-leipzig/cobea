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
}

def pa_gen(gen_name: str, req_names: List[str], **kwargs: Dict[str, Any]) -> ParamAim:
	"""Generate ParamAim by gen_name
	
	(req_)names are passed as parameter
	data_type, h5_name, h5_path, as_attr and shape are retrieved by gen_name
	other entries of ParamAim can be passed as kwargs
	"""
	desc = HDF5_DICT[gen_name]
	return ParamAim(req_names, *desc, **kwargs)

def add_meta(metadata: MetaEntryMap, meta_name: str, value: Any) -> None:
	"""Add MetaEntry to metadata
	
	The MetaEntry is created from data retrieved by meta_name
	"""
	desc = HDF5_DICT[meta_name]
	if not desc.as_attr:
		raise ValueError(f"{meta_name} can't be stored as metadata: as_attr is False")
	entry = MetaEntry(desc.h5_name, value, desc.data_type)
	metadata.setdefault(desc.h5_path, []).append(entry)
