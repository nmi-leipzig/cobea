from typing import Any, List, Tuple, Union

import h5py
import numpy as np

from adapters.icecraft import CarryData, CarryDataMap, IcecraftBitPosition, IcecraftLUTPosition, IcecraftRawConfig,\
	IndexedItem, PartConf
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

def get_with_index(hdf5_file: h5py.File, desc: HDF5Desc, index: int) -> Union[h5py.Group, h5py.AttributeManager]:
	"""Returns group or attributes when formating path with an index"""
	
	grp = hdf5_file[desc.h5_path.format(index)]
	if desc.as_attr:
		return grp.attrs
	return grp

def read_carry_use(hdf5_file: h5py.File, cd_index) -> List[PartConf]:
	res = []
	bit_desc = HDF5_DICT["rep.carry_data.bits"]
	val_desc = HDF5_DICT["rep.carry_data.values"]
	
	bit_grp = get_with_index(hdf5_file, bit_desc, cd_index)
	val_grp = get_with_index(hdf5_file, val_desc, cd_index)
	pc_index = 0
	while True:
		try:
			bit_raw = bit_grp[bit_desc.h5_name.format(pc_index)].tolist()
		except KeyError:
			break
		
		val_raw = val_grp[val_desc.h5_name.format(pc_index)].tolist()
		
		res.append(PartConf(tuple(IcecraftBitPosition(*c) for c in bit_raw), tuple(val_raw)))
		
		pc_index += 1
	
	return res

def read_rep_carry_data(hdf5_file: h5py.File) -> CarryDataMap:
	cd_map = {}
	lut_desc = HDF5_DICT["rep.carry_data.lut"]
	ena_desc = HDF5_DICT["rep.carry_data.enable"]
	
	cd_index = 0
	while True:
		try:
			ena_grp = get_with_index(hdf5_file, ena_desc, cd_index)
		except KeyError:
			break
		
		enable_raw = ena_grp[ena_desc.h5_name].tolist()
		enable = tuple(IcecraftBitPosition(*c) for c in enable_raw)
		lut_index = get_with_index(hdf5_file, lut_desc, cd_index)[lut_desc.h5_name].item()
		
		carry_data = CarryData(lut_index, enable, read_carry_use(hdf5_file, cd_index))
		cd_map.setdefault(enable[0].tile, {})[lut_index] = carry_data
		
		
		cd_index += 1
	
	return cd_map

def read_rep_output(hdf5_file: h5py.File) -> Tuple[IcecraftLUTPosition, ]:
	desc = HDF5_DICT["rep.output"]
	raw = data_from_desc(hdf5_file, desc)
	return tuple(IcecraftLUTPosition(*c) for c in raw)

def read_rep_colbufctrl(hdf5_file: h5py.File) -> Tuple[IndexedItem, ]:
	bit_desc = HDF5_DICT["rep.colbufctrl.bits"]
	idx_desc = HDF5_DICT["rep.colbufctrl.indices"]
	
	bit_raw = data_from_desc(hdf5_file, bit_desc)
	idx_raw = data_from_desc(hdf5_file, idx_desc)
	if len(bit_raw) != len(idx_raw):
		raise ValueError(f"number of bits and indices don't match: {len(bit_raw)} != {len(idx_raw)}")
	
	return tuple(IndexedItem(tuple(IcecraftBitPosition(*p) for p in b), "ColBufCtrl", i)
		for b, i in zip(bit_raw.tolist(), idx_raw.tolist()))
