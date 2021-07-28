import datetime
import re

from dataclasses import dataclass
from functools import partial
from operator import attrgetter, itemgetter, methodcaller
from types import TracebackType
from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple, Type

import h5py
import numpy as np

from domain.allele_sequence import Allele, AlleleAll, AlleleList, AllelePow
from domain.base_structures import BitPos
from domain.data_sink import DataSink
from domain.model import Gene

class IgnoreValue(Exception):
	"""Exception that indicades that a value should not be further processed and be ignored"""
	pass

class InvalidStructure(Exception):
	"""Exception that indicates invalid combination of groups, dataset and attributes
	
	Example: group and dataset with the same name and parent required
	"""
	pass

class InvalidGeneData(Exception):
	"""Exception that indicates invalid data that should describe a gene in an HDF5 file"""
	pass

def noop(x: Any) -> Any:
	return x

def compose(x: Any, funcs: Iterable[Callable]) -> Any:
	"""Apply first function to x, then apply the second function to that result and so on"""
	r = x
	for func in funcs:
		r = func(r)
	return r

@dataclass
class ParamAim:
	# there can be multiple ParamAim instance with the same name
	# to create multiple entries in the HDF5 from the same data 
	names: List[str] # multiple names to allow compound data types and write one value depending on another
	data_type: type
	h5_name: str
	h5_path: str = "/"
	as_attr: bool = True
	# for datasets: shape of a single entry, not the whole dataset
	shape: Tuple[Optional[int], ...] = tuple()
	# by default return first value
	# good for cases where ther is only one name
	alter: Callable[[list], Any] = itemgetter(0)
	compress: str = "gzip"
	comp_opt: int = 7
	shuffle: bool = False

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
			cur_date = datetime.datetime.now(datetime.timezone.utc)
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
		implied_entities = []
		for pa_list in self._write_map.values():
			for pa in pa_list:
				if pa.as_attr:
					# store entities implied by exisitence of attibutes for later
					# as we don't know if this entities are groups or datasets
					implied_entities.append(pa.h5_path)
				else:
					# get or create group
					try:
						grp = self._hdf5_file[pa.h5_path]
					except KeyError:
						grp = self._hdf5_file.create_group(pa.h5_path)
					
					# check or create dataset
					try:
						ds = grp[pa.h5_name]
						if not isinstance(ds, h5py.Dataset):
							raise InvalidStructure(f"group and dataset with same name '{pa.h5_name}' required")
						if ds.dtype != pa.data_type:
							raise InvalidStructure(
								f"different data types required for {pa.h5_name}: {ds.dtype} != {pa.data_type}"
							)
						
						if ds.shape[1:] != pa.shape:
							raise InvalidStructure(
								f"different shape required for {pa.h5_name}: {ds.shape} != {pa.shape}"
							)
						
						if ds.maxshape != (None, *pa.shape):
							raise InvalidStructure(
								f"different maxshape required for {pa.h5_name}: {ds.maxshape} != {(None, *pa.shape)}"
							)
						
					except KeyError:
						ds = grp.create_dataset(
							pa.h5_name,
							shape=(0, *pa.shape),
							dtype=pa.data_type,
							maxshape=(None, *pa.shape),
							compression = pa.compress,
							compression_opts = pa.comp_opt,
							shuffle = pa.shuffle,
						)
		
		for entity_path in implied_entities:
			if entity_path not in self._hdf5_file:
				# every entity that is not yet created has to be a group
				self._hdf5_file.create_group(entity_path)
	
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
		
		return False
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		try:
			aim_list = self._write_map[source]
		except KeyError:
			return
		
		for pa in aim_list:
			try:
				value = pa.alter([data_dict[n] for n in pa.names])
			except IgnoreValue:
				# don't process this value any further
				continue
			
			entity = self._hdf5_file[pa.h5_path]
			
			if pa.as_attr:
				if pa.data_type is None:
					entity.attrs[pa.h5_name] = value
				elif pa.data_type == str:
					entity.attrs[pa.h5_name] = "{}".format(value)
				else:
					entity.attrs.create(pa.h5_name, value, dtype=pa.data_type)
			else:
				dataset = entity[pa.h5_name]
				if len(dataset.shape) == len(np.shape(value)):
					# multiple values
					new_count = len(value)
					new_shape = (dataset.shape[0]+new_count, *dataset.shape[1:])
					dataset.resize(new_shape)
					dataset[-new_count:] = value
				else:
					new_shape = (dataset.shape[0]+1, *dataset.shape[1:])
					dataset.resize(new_shape)
					dataset[-1] = value
				
	
	@staticmethod
	def extract_list(genes: List[Sequence[Gene]], idx: int) -> List[Tuple[bool, ...]]:
		allele_seq = genes[0][idx].alleles
		# only process AlleleList
		if not isinstance(allele_seq, AlleleList):
			raise IgnoreValue()
		
		return [a.values for a in allele_seq]
	
	@staticmethod
	def extract_input_count(genes: List[Sequence[Gene]], idx: int) -> int:
		allele_seq = genes[0][idx].alleles
		# only process AllelePow
		if not isinstance(allele_seq, AllelePow):
			raise IgnoreValue()
		
		return allele_seq.input_count
	
	@staticmethod
	def extract_unused_inputs(genes: List[Sequence[Gene]], idx: int) -> int:
		allele_seq = genes[0][idx].alleles
		# only process AllelePow
		if not isinstance(allele_seq, AllelePow):
			raise IgnoreValue()
		
		return allele_seq.unused_inputs
	
	@classmethod
	def create_gene_aims(cls, name: str, gene_count: int, h5_base_name: str="gene", h5_path: str="/") -> List[ParamAim]:
		"""Create ParamAim instances to store Gene sequences
		
		name: key of the Gene sequence in the data_dict of the write function
		"""
		aims = []
		for index in range(gene_count):
			grp_name = h5_path + "/" + f"gene_{index:05d}"
			aims.append(ParamAim([name], None, "description", grp_name, alter=partial(
				compose,
				funcs = [itemgetter(0), itemgetter(index), attrgetter("description")]
			)))
			aims.append(ParamAim([name], "uint16", "bits", grp_name, alter=partial(compose, funcs = [
				itemgetter(0),
				itemgetter(index),
				attrgetter("bit_positions"),
				partial(map, methodcaller("to_ints")),
				list
			])))
			aims.append(ParamAim([name], None, "allele_type", grp_name, alter=partial(
				compose,
				funcs = [itemgetter(0), itemgetter(index), attrgetter("alleles"), type, attrgetter("__name__")]
			)))
			
			# data specific for type of AlleleSequence
			# AlleleList
			aims.append(ParamAim([name], None, "alleles", grp_name, alter=partial(cls.extract_list, idx=index)))
			
			# AllelePow
			aims.append(
				ParamAim([name], None, "input_count", grp_name, alter=partial(cls.extract_input_count, idx=index))
			)
			aims.append(
				ParamAim([name], None, "unused_inputs", grp_name, alter=partial(cls.extract_unused_inputs, idx=index))
			)
			
			# for AlleleAll only the number of bits is relevant
		
		return aims
	
	@staticmethod
	def extract_genes(grp: h5py.Group, bit_cls: Type[BitPos]) -> List[Gene]:
		"""Create genes based on data in HDF5 group that was stored according to create_gene_aims"""
		gene_list = []
		
		for gene_name in sorted(grp):
			res = re.match(r"gene_(?P<index>\d+)", gene_name)
			index = int(res.group("index"))
			if index != len(gene_list):
				raise InvalidGeneData(f"gene index {index}, should be {len(gene_list)}")
			
			gene_grp = grp[gene_name]
			
			bits = tuple(bit_cls(*b) for b in gene_grp.attrs["bits"])
			
			allele_type = gene_grp.attrs["allele_type"]
			if allele_type == "AlleleList":
				alleles = [Allele(tuple(v), "") for v in gene_grp.attrs["alleles"]]
				allele_seq = AlleleList(alleles)
			elif allele_type == "AllelePow":
				allele_seq = AllelePow(gene_grp.attrs["input_count"], list(gene_grp.attrs["unused_inputs"]))
			elif allele_type == "AlleleAll":
				allele_seq = AlleleAll(len(bits))
			else:
				raise InvalidGeneData(f"unsupport allele type: {allele_type}")
			
			desc = gene_grp.attrs["description"]
			gene_list.append(Gene(bits, allele_seq, desc))
		
		return gene_list
