import datetime
import h5py

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple, Type

from domain.allele_sequence import AlleleList, AllelePow
from domain.data_sink import DataSink
from domain.model import Gene

class IgnoreValue(Exception):
	"""Exception that indicades that a value should not be further processed and be ignored"""
	pass

@dataclass
class ParamAim:
	# there can be multiple ParamAim instance with the same name
	# to create multiple entries in the HDF5 from the same data 
	name: str
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	shape: Tuple[Optional[int], ...] = tuple()
	alter: Callable[[Any], Any] = lambda x: x

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
			try:
				value = pa.alter(data_dict[pa.name])
			except IgnoreValue:
				# don't process this value any further
				continue
			
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
				
	
	@staticmethod
	def create_gene_aims(name: str, gene_count: int, h5_base_name: str="gene", h5_path: str="/") -> List[ParamAim]:
		"""Create ParamAim instances to store Gene sequences
		
		name: key of the Gene sequence in the data_dict of the write function
		"""
		aims = []
		for index in range(gene_count):
			grp_name = h5_path + "/" + f"gene_{index:05d}"
			#aims.append(ParamAim())
			aims.append(ParamAim(name, None, "description", grp_name, alter=lambda g, i=index: g[i].description))
			aims.append(ParamAim(name, "uint16", "bits", grp_name,
				alter=lambda g, i=index: [b.to_ints() for b in g[i].bit_positions]))
			aims.append(ParamAim(name, None, "allele_type", grp_name,
				alter=lambda g, i=index: type(g[i].alleles).__name__))
			
			# data specific for type of AlleleSequence
			def extract_list(genes: Sequence[Gene], idx: int=index) -> List[Tuple[bool, ...]]:
				allele_seq = genes[idx].alleles
				# only process AlleleList
				if not isinstance(allele_seq, AlleleList):
					raise IgnoreValue()
				
				return [a.values for a in allele_seq]
			
			aims.append(ParamAim(name, None, "alleles", grp_name, alter=extract_list))
			
			def extract_input_count(genes: Sequence[Gene], idx: int=index) -> int:
				allele_seq = genes[idx].alleles
				# only process AllelePow
				if not isinstance(allele_seq, AllelePow):
					raise IgnoreValue()
				
				return allele_seq.input_count
			
			aims.append(ParamAim(name, None, "input_count", grp_name, alter=extract_input_count))
			
			def extract_unused_inputs(genes: Sequence[Gene], idx: int=index) -> int:
				allele_seq = genes[idx].alleles
				# only process AllelePow
				if not isinstance(allele_seq, AllelePow):
					raise IgnoreValue()
				
				return allele_seq.unused_inputs
			
			aims.append(ParamAim(name, None, "unused_inputs", grp_name, alter=extract_unused_inputs))
			
			# for AlleleAll only the number of bits is relevant
		
		return aims
