import h5py

from adapters.icecraft import IcecraftRawConfig
from applications.discern_frequency.hdf5_desc import HDF5_DICT
from domain.model import Chromosome


def read_habitat(hdf5_file: h5py.File) -> IcecraftRawConfig:
	desc = HDF5_DICT["habitat"]
	hab_data = hdf5_file[desc.h5_path][desc.h5_name]
	hab_text = hab_data[:].tobytes().decode(encoding="utf-8")
	return IcecraftRawConfig.from_text(hab_text)

