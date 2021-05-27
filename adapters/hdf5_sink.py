import datetime
import h5py

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Callable, List, Mapping, Optional, Tuple, Type

from domain.data_sink import DataSink

@dataclass
class ParamAim:
	name: str
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	shape: Tuple[Optional[int], ...] = tuple()
	transform: Callable[[Any], Any] = lambda x: x

class HDF5Sink(DataSink):
	def __init__(self,
		write_map: Mapping[str, List[ParamAim]],
		hdf5_filename: Optional[str]=None,
		mode: str="w"
	) -> None:
		"""
		mode: mode for opening the file (r, r+, w, x, a)
		"""
		if hdf5_filename is None:
			cur_date = datetime.datetime.today()
			hdf5_filename = f"evo-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"
		self._hdf5_filename = hdf5_filename
		assert mode in ("r", "r+", "w", "x", "a")
		self._mode = mode
		self._hdf5_file = None
		# define mapping to process write
		# (source, data_dict) -> (group, data_type, multiple, dataset_or_attrs)
		self._write_map = write_map
	
	def prepare_structure(self) -> None:
		"""Prepare groups and datasets"""
		for pa_list in self._write_map.values():
			for pa in pa_list:
				try:
					grp = self._hdf5_file[pa.h5_path]
				except KeyError:
					grp = self._hdf5_file.create_group(pa.h5_path)
				
				if not pa.as_attr:
					try:
						ds = grp[pa.h5_name]
						assert ds.dtype == pa.data_type
						assert ds.shape[1:] == pa.shape
						assert ds.maxshape == (None, *pa.shape)
					except KeyError:
						ds = grp.create_dataset(
							pa.h5_name,
							shape=(0, *pa.shape),
							dtype=pa.data_type,
							maxshape=(None, *pa.shape),
							compression = "gzip",
						)
	
	def open(self) -> None:
		if self._hdf5_file is not None:
			return
		
		self._hdf5_file = h5py.File(self._hdf5_filename, self._mode)
	
	def close(self) -> None:
		if self._hdf5_file is None:
			return
		self._hdf5_file.close()
		self._hdf5_file = None
	
	def __enter__(self) -> "HDF5Sink":
		self.open()
		self.prepare_structure()
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		self.close()
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		try:
			aim_list = self._write_map[source]
		except KeyError:
			return
		
		for pa in aim_list:
			value = data_dict[pa.name]
			entity = self._hdf5_file[pa.h5_path]
			
			if pa.as_attr:
				if pa.data_type is None:
					entity.attrs[pa.h5_name] = value
				elif pa.data_type == str:
					entity.attrs[pa.h5_name] = "{}".format(meta.data)
				else:
					entity.attrs.create(pa.h5_name, value, dtype=pa.data_type)
			else:
				dataset = entity[pa.h5_name]
				new_shape = (dataset.shape[0]+1, *dataset.shape[1:])
				dataset.resize(new_shape)
				dataset[-1] = value
				
