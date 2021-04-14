from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Tuple

import pyvisa

from domain.interfaces import Meter
from domain.model import OutputData
from domain.request_model import RequestObject

@dataclass
class SetupCmd:
	"""
	
	The names of all methods and variables end with an '_' to avoid interference with exposed subcommands.
	"""
	name_: str
	values_: Any = None # has to support a in b syntax, e.g. __contains__ or iter
	value_: Any = None
	subcmds_: Tuple["SetupCmd"] = field(default_factory=tuple)
	parent_: Optional["SetupCmd"] = field(default=None, init=False)
	prefix_: str = ":"
	write_: str = " "
	read_: str = "?"
	
	def __post_init__(self):
		for subcmd in self.subcmds_:
			setattr(self, subcmd.name_, subcmd)
			subcmd.parent_ = self
	
	def cmd(self, write=True, full=True) -> str:
		parts = []
		if self.parent_ is not None:
			parts.append(self.parent_.cmd(full=False))
		parts.append(self.prefix_)
		parts.append(self.name_)
		if full:
			if self.values_ is None:
				raise ValueError("Can't create full command without values")
			if write:
				parts.append(self.write_)
				parts.append(str(self.value_))
			else:
				parts.append(self.read_)
		
		return "".join(parts)
	
	@classmethod
	def from_values_(cls, name: str, values: Iterable[Any], *args, **kwargs):
		return [cls(name.format(v), *deepcopy(args), **deepcopy(kwargs)) for v in values]

class OsciDS1102E(Meter):
	def prepare(self, request: RequestObject) -> None:
		raise NotImplementedError()
	
	def measure(self, request: RequestObject) -> OutputData:
		raise NotImplementedError()
	
	#open
	#is_open
	#close
	#__enter__
	#__exit__
	
	@staticmethod
	def find_instrument(res_man: pyvisa.ResourceManager, serial_number: Optional[str]=None) -> str:
		if serial_number is None:
			query = "USB[0-9]*::6833::1416::?*::INSTR"
		else:
			query = f"USB[0-9]*::6833::1416::{serial_number}?*::INSTR"
		
		res_list = res_man.list_resources(query)
		try:
			dev_str = res_list[0]
		except IndexError as ie:
			raise IOError("No matching Rigol found") from ie
		
		return dev_str
	
	@staticmethod
	def create_setup() -> SetupCmd:
		# commands
		# ACQ:SAMP
		return SetupCmd("", prefix_="", subcmds_=(
			SetupCmd("ACQ", subcmds_=(
				SetupCmd("TYPE", ("NORM", "AVER", "PEAK"), "NORM"),
				SetupCmd("MODE", ("RTIM", "ETIM"), "RTIM"),
				SetupCmd("AVER", (2, 4, 8, 16, 32, 64, 128, 256), 16),
				SetupCmd("MEMD", ("LONG", "NORMAL"), "LONG"),
			)),
		))
	
	@staticmethod
	def set_up_instrument(osci: pyvisa.Resource, setup: "SetupDS1102E") -> None:
		osci.write(":CHAN1:DISP ON")
		osci.write(":CHAN2:DISP OFF")
		
		# set trigger
		# trigger mode: edge
		osci.write(":TRIG:MODE EDGE")
		# CHAN2 can still be trigger source even if it's off
		osci.write(":TRIG:EDGE:SOUR CHAN2")
		# slope raising
		osci.write(":TRIG:EDGE:SLOP POS")
		# sweep single
		osci.write(":TRIG:EDGE:SWE SINGLE")
		# coupling dc
		osci.write(":TRIG:EDGE:COUP DC")
		# trigger level 1 V
		osci.write(":TRIG:EDGE:LEV 1")
		
		# probe 1 or 10
		# koax -> 1; x10 probe -> 10 (higher bandwith)
		osci.write(":CHAN1:PROB 10")
		
		# set timebase
		osci.write(":TIM:SCAL 0.5")
		# trigger offset
		osci.write(":TIM:OFFS 2.5")
		
		# get scales
		offset = osci.query(":CHAN1:OFFS?")
		scale = osci.query(":CHAN1:SCAL?")
		osci.write(":ACQ:MEMD LONG")
		osci.write(":ACQ:TYPE NORM")
		osci.write(":ACQ:MODE REAL_TIME")
