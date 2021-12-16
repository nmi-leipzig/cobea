from typing import Any, List

import h5py
import numpy as np

from adapters.icecraft import IcecraftBitPosition, IcecraftRawConfig
from applications.discern_frequency.hdf5_desc import HDF5Desc, HDF5_DICT
from domain.model import Chromosome


def data_from_desc(hdf5_file: h5py.File, desc: HDF5Desc) -> Any:
	grp = hdf5_file[desc.h5_path]
	if desc.as_attr:
		return grp.attrs[desc.h5_name]
	else:
		return grp[desc.h5_name]

def read_habitat(hdf5_file: h5py.File) -> IcecraftRawConfig:
	desc = HDF5_DICT["habitat"]
	hab_data = data_from_desc(hdf5_file, desc)
	hab_text = hab_data[:].tobytes().decode(encoding="utf-8")
	return IcecraftRawConfig.from_text(hab_text)

def read_chromosome(hdf5_file: h5py.File, identifier: int) -> Chromosome:
	id_desc = HDF5_DICT["chromo.id"]
	idx_desc = HDF5_DICT["chromo.indices"]
	try:
		chromo_index = np.where(data_from_desc(hdf5_file, id_desc)[:] == identifier)[0][0]
	except IndexError:
		raise ValueError(f"Chromosome {identifier} not found.")
	
	allele_indices = tuple(data_from_desc(hdf5_file, idx_desc)[chromo_index])
	return Chromosome(identifier, allele_indices)

def read_s_t_index(hdf5_file: h5py.File, fit_index: int) -> int:
	desc = HDF5_DICT["fitness.st"]
	return data_from_desc(hdf5_file, desc)[fit_index]

def read_carry_enable_values(hdf5_file: h5py.File, fit_index: int) -> List[bool]:
	desc = HDF5_DICT["carry_enable.values"]
	data = data_from_desc(hdf5_file, desc)[fit_index]
	return data.tolist()

def read_carry_enable_bits(hdf5_file: h5py.File) -> List[IcecraftBitPosition]:
	desc = HDF5_DICT["carry_enable.bits"]
	raw = data_from_desc(hdf5_file, desc)
	return [IcecraftBitPosition(*c) for c in raw]