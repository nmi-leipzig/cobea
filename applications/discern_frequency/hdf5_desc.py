"""Description how data is stored in HDF5 files

Especially data that is required for both reading and writing.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


from adapters.hdf5_sink import ParamAim


class HDF5Desc(NamedTuple):
	"""Data required for both reading from and writing to a HDF5 file"""
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	shape: Tuple[Optional[int], ...] = tuple()


HDF5_DICT= {
	"habitat": HDF5Desc("uint8", "habitat", "/", False, tuple()),
}

def pa_gen(gen_name: str, req_names: List[str], **kwargs: Dict[str, Any]) -> ParamAim:
	"""Generate ParamAim by gen_name
	
	(req_)names are passed as parameter
	data_type, h5_name, h5_path, as_attr and shape are retrieved by gen_name
	other entries of ParamAim can be passed as kwargs
	"""
	desc = HDF5_DICT[gen_name]
	return ParamAim(req_names, *desc, **kwargs)
