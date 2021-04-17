import re

from copy import deepcopy
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Callable, Iterable, Mapping, Optional, Tuple, List

import pyvisa

from domain.interfaces import Meter
from domain.model import OutputData
from domain.request_model import Parameter, RequestObject

@dataclass
class SetupCmd:
	"""
	
	The names of all methods and variables end with an '_' to avoid interference with exposed subcommands.
	"""
	name_: str
	values_: Any = None # has to support a in b syntax, e.g. __contains__ or iter; in general only coarse check
	value_: Any = None
	subcmds_: Tuple["SetupCmd"] = field(default_factory=tuple)
	condition_: Callable[["SetupCmd"], bool] = lambda _: True
	parent_: Optional["SetupCmd"] = field(default=None, init=False)
	prefix_: str = ":"
	write_: str = " "
	read_: str = "?"
	
	def __post_init__(self):
		for subcmd in self.subcmds_:
			setattr(self, subcmd.name_, subcmd)
			subcmd.parent_ = self
	
	def cmd_(self, write=True, full=True) -> str:
		parts = []
		if self.parent_ is not None:
			parts.append(self.parent_.cmd_(full=False))
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

class FloatCheck:
	def __contains__(self, item: Any) -> bool:
		try:
			v = float(item)
			return isfinite(v)
		except:
			return False

class IntCheck:
	def __contains__(self, item: Any) -> bool:
		try:
			# convert to str first to avoid false positive for floats
			v = int(str(item))
			return True
		except:
			return False

class MultiNoSpace(List[int]):
	def __str__(self) -> str:
		return ",".join([str(i) for i in self])

class MultiIntCheck:
	def __init__(self, count: int) -> None:
		self._count = count
	
	def __contains__(self, item: Any) -> bool:
		res = re.match("".join([r"-?\d,"]*(self._count-1)+[r"-?\d$"]), str(item))
		return res is not None

class OsciDS1102E(Meter):
	def __init__(self, serial_number: Optional[str]=None):
		self._serial_number = serial_number
		self._is_open = False
		self._res_man = None
		self._dev_str = None
		self._osci = None
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"prepare": [], "measure": []}
	
	def open(self):
		if self._is_open:
			return
		
		self._res_man = pyvisa.ResourceManager()
		self._dev_str = self.find_instrument(self._res_man, self._serial_number)
		self._osci = self._res_man.open_resource(self._dev_str)
		
		self._is_open = True
	
	def close(self):
		if not self._is_open:
			return
		
		self._is_open = False
		
		self._osci.close()
		self._res_man.close()
		
		self._res_man = None
		self._osci = None
	
	def __enter__(self) -> "OsciDS1102E":
		self.open()
		return self
	
	def __exit__(self,exc_type, exc_value, traceback):
		self.close()
	
	def prepare(self, request: RequestObject) -> None:
		raise NotImplementedError()
	
	def measure(self, request: RequestObject) -> OutputData:
		raise NotImplementedError()
	
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
	
	@classmethod
	def apply(cls, osci: pyvisa.Resource, setup: SetupCmd) -> None:
		"""Apply values of the setup while respecting the connection between different values.
		
		One example for a connection between different values: if TRIG:MODE is EDGE, then only subcommands of TRIG:EDGE
		will be written, as e.g. subcommands of TRIG:PULS are not relevant.
		"""
		if not setup.condition_(setup):
			return
		
		if setup.values_ is not None:
			if setup.value_ not in setup.values_:
				raise ValueError(f"'{setup.value_}' invalid for {setup.name_}")
			
			osci.write(setup.cmd_(write=True))
		
		for subcmd in setup.subcmds_:
			cls.apply(osci, subcmd)
	
	@staticmethod
	def create_setup() -> SetupCmd:
		# very simple representation of the setup, especially following points have to be regarded:
		# - validity of values may depend on vales of other parameters; this is not checked
		# - return values are always str, even if they are e.g. float values
		# - there are multiple ways to express the same value, e.g. for :TIM:FORM: XY and X-Y mean the same
		#   -> the returned value may not be exactly the same as the value written, despite a successful write
		# - sometimes the returned value itself is an invalid write value
		# - there are multiple ways to express a command, e.g. TIM and TIMebase are the same command
		
		# commands
		# ACQ:SAMP
		# TRIG:STAT
		# Trig%50
		# FORC
		# STOR:FACT:LOAD
		# CHAN1:MEMD
		# CHAN2:MEMD
		# WAV:DATA
		# MEAS: all basic measurements
		# KEY: controll keys directly
		# INFO:LANG
		# BEEP:ACT
		#
		# other options
		# DISP (not relevant for measurement)
		# TRIG:PATT:PATT (no digital channels in DS1102E + complicated value system)
		# LA (not available in DS1102E)
		return SetupCmd("", prefix_="", subcmds_=(
			SetupCmd("ACQ", subcmds_=(
				SetupCmd("TYPE", ("NORM", "AVER", "PEAK"), "NORM"),
				SetupCmd("MODE", ("RTIM", "ETIM"), "RTIM"),
				SetupCmd(
					"AVER",
					(2, 4, 8, 16, 32, 64, 128, 256),
					16,
					condition_=lambda s: s.parent_.TYPE.value_=="AVER"
				),
				SetupCmd("MEMD", ("LONG", "NORMAL"), "LONG"),
			)),
			SetupCmd("TIM", subcmds_=(
				SetupCmd("MODE", ("MAIN", "DEL"), "MAIN"),
				SetupCmd("OFFS", FloatCheck(), 0),
				SetupCmd("SCAL", FloatCheck(), 0.5),
				SetupCmd("FORM", ("XY", "YT", "SCAN"), "YT"),
				SetupCmd("DEL", subcmds_=(
					SetupCmd("OFFS", FloatCheck(), 0),
					SetupCmd("SCAL", FloatCheck(), 0.5),
				), condition_=lambda s: s.parent_.MODE.value_=="DEL"),
			)),
			SetupCmd("TRIG", subcmds_=(
				SetupCmd("MODE", ("EDGE", "PULS", "VIDEO", "SLOP", "ALT"), "EDGE"),
				SetupCmd("HOLD", FloatCheck(), 0.0005),
				SetupCmd("EDGE", subcmds_=(
					SetupCmd("SOUR", ("CHAN1", "CHAN2", "EXT", "ACL"), "CHAN1"),
					SetupCmd("LEV", FloatCheck(), 1),
					SetupCmd("SWE", ("AUTO", "NORM", "SING"), "SING"),
					SetupCmd("COUP", ("DC", "AC", "HF", "LF"), "DC"),
					SetupCmd("SLOP", ("POS", "NEG"), "POS"),
					SetupCmd("SENS", FloatCheck(), 0.5),
				), condition_=lambda s: s.parent_.MODE.value_=="EDGE"),
				SetupCmd("PULS", subcmds_=(
					SetupCmd("SOUR", ("CHAN1", "CHAN2", "EXT"), "CHAN1"),
					SetupCmd("LEV", FloatCheck(), 1),
					SetupCmd("SWE", ("AUTO", "NORM", "SING"), "SING"),
					SetupCmd("COUP", ("DC", "AC", "HF", "LF"), "DC"),
					SetupCmd("MODE", ("+GRE", "+LESS", "+EQU", "-GRE", "-LESS", "-EQU"), "+GRE"),
					SetupCmd("SENS", FloatCheck(), 0.5),
					SetupCmd("WIDT", FloatCheck(), 0.001),
				), condition_=lambda s: s.parent_.MODE.value_=="PULS"),
				SetupCmd("VIDEO", subcmds_=(
					SetupCmd("SOUR", ("CHAN1", "CHAN2", "EXT"), "CHAN1"),
					SetupCmd("LEV", FloatCheck(), 1),
					SetupCmd("MODE", ("ODD", "EVEN", "LINE", "ALL"), "ALL"),
					SetupCmd("POL", ("POS", "NEG"), "POS"),
					SetupCmd("STAN", ("NTSC", "PALS"), "PALS"),
					SetupCmd("LINE", IntCheck(), 1),
					SetupCmd("SENS", FloatCheck(), 0.5),
				), condition_=lambda s: s.parent_.MODE.value_=="VIDEO"),
				SetupCmd("SLOP", subcmds_=(
					SetupCmd("SOUR", ("CHAN1", "CHAN2", "EXT"), "CHAN1"),
					SetupCmd("SWE", ("AUTO", "NORM", "SING"), "SING"),
					SetupCmd("COUP", ("DC", "AC", "HF", "LF"), "DC"),
					SetupCmd("TIME", FloatCheck(), 0.000001),
					SetupCmd("SENS", FloatCheck(), 0.5),
					SetupCmd("MODE", ("+GRE", "+LESS", "+EQU", "-GRE", "-LESS", "-EQU"), "+GRE"),
					SetupCmd("WIND", ("PA", "PB", "PAB", "NA", "NB", "NAB"), "PAB"),
					SetupCmd("LEVA", FloatCheck(), 0.1),
					SetupCmd("LEVB", FloatCheck(), -0.1),
				), condition_=lambda s: s.parent_.MODE.value_=="SLOP"),
				SetupCmd("ALT", subcmds_=(
					#TODO: problem: SOUR switches to completely new set of variables, but atm only one is stored
					SetupCmd("SOUR", ("CHAN1", "CHAN2"), "CHAN1"),
					SetupCmd("TYPE", ("EDGE", "PULS", "SLOP", "VIDEO"), "EDGE"),
					SetupCmd("TSCAL", FloatCheck(), 0.000001),
					SetupCmd("TOFFS", FloatCheck(), 0),
					SetupCmd("EDGE", subcmds_=(
						SetupCmd("LEV", FloatCheck(), 1),
						SetupCmd("SLOP", ("POS", "NEG"), "POS"),
						SetupCmd("COUP", ("DC", "AC", "HF", "LF"), "AC"),
						SetupCmd("HOLD", FloatCheck(), 0.0005),
						SetupCmd("SENS", FloatCheck(), 0.5),
					)),
					SetupCmd("PULS", subcmds_=(
						SetupCmd("LEV", FloatCheck(), 1),
						SetupCmd("MODE", ("+GRE", "+LESS", "+EQU", "-GRE", "-LESS", "-EQU"), "+GRE"),
						SetupCmd("TIME", FloatCheck(), 0.000001),
						SetupCmd("COUP", ("DC", "AC", "HF", "LF"), "DC"),
						SetupCmd("HOLD", FloatCheck(), 0.0005),
						SetupCmd("SENS", FloatCheck(), 0.5),
					)),
					SetupCmd("VIDEO", subcmds_=(
						SetupCmd("LEV", FloatCheck(), 1),
						SetupCmd("MODE", ("ODD", "EVEN", "LINE", "ALL"), "ALL"),
						SetupCmd("POL", ("POS", "NEG"), "POS"),
						SetupCmd("STAN", ("NTSC", "PALS"), "PALS"),
						SetupCmd("LINE", IntCheck(), 1),
						SetupCmd("HOLD", FloatCheck(), 0.0005),
						SetupCmd("SENS", FloatCheck(), 0.5),
					)),
					SetupCmd("SLOP", subcmds_=(
						SetupCmd("MODE", ("+GRE", "+LESS", "+EQU", "-GRE", "-LESS", "-EQU"), "+GRE"),
						SetupCmd("TIME", FloatCheck(), 0.000001),
						SetupCmd("WIND", ("PA", "PB", "PAB", "NA", "NB", "NAB"), "PAB"),
						SetupCmd("LEVA", FloatCheck(), 0.1),
						SetupCmd("LEVB", FloatCheck(), -0.1),
						SetupCmd("COUP", ("DC", "AC", "HF", "LF"), "DC"),
						SetupCmd("HOLD", FloatCheck(), 0.0005),
						SetupCmd("SENS", FloatCheck(), 0.5),
					)),
					
				), condition_=lambda s: s.parent_.MODE.value_=="ALT"),
			)),
			SetupCmd("MATH", subcmds_=(
				SetupCmd("DISP", ("ON", "OFF"), "OFF"),
				SetupCmd("OPER", ("A+B", "A-B", "AB", "FFT"), "A_B", condition_=lambda s: s.parent_.DISP.value_=="ON"),
			)),
			SetupCmd("FFT", subcmds_=(
				SetupCmd("DISP", ("ON", "OFF"), "OFF"),
			)),
			*SetupCmd.from_values_("CHAN{}", [1, 2], subcmds_=(
				SetupCmd("BWL", ("ON", "OFF"), "OFF"),
				SetupCmd("COUP", ("DC", "AC", "GND"), "DC"),
				SetupCmd("DISP", ("ON", "OFF"), "ON"),
				SetupCmd("INV", ("ON", "OFF"), "OFF"),
				# set probe before offset and scale as change of the former influences the values of the later
				SetupCmd("PROB", [1, 5, 10, 50, 100, 500, 1000], 1),
				SetupCmd("OFFS", FloatCheck(), 0),
				SetupCmd("SCAL", FloatCheck(), 1),
				SetupCmd("FILT", ("ON", "OFF"), "OFF", subcmds_=( # subcmds available in menu, but not documented
					SetupCmd(
						"TYPE",
						("LPAS", "HPAS", "BPAS", "BTR"),
						"LPAS",
						condition_=lambda s: s.parent_.value_=="ON"
					),
					SetupCmd(
						"LLIM",
						FloatCheck(),
						49.5,
						condition_=lambda s: s.parent_.value_=="ON" and s.parent_.TYPE.value_ in ("HPAS", "BPAS", "BTR")
					),
					SetupCmd(
						"ULIM",
						FloatCheck(),
						50.5,
						condition_=lambda s: s.parent_.value_=="ON" and s.parent_.TYPE.value_ in ("LPAS", "BPAS", "BTR")
					),
				)),
				SetupCmd("VERN", ("ON", "OFF"), "OFF"),
			)),
			SetupCmd("MEAS", subcmds_=(
				SetupCmd("TOT", ("ON", "OFF"), "OFF"),
				SetupCmd("SOUR", ("CH1", "CH2"), "CH1"),
			)),
			SetupCmd("WAV", subcmds_=(
				SetupCmd("POIN", subcmds_=(
					SetupCmd("MODE", ("NOR", "RAW", "MAX"), "RAW"),
				)),
			)),
			SetupCmd("COUN", subcmds_=(
				SetupCmd("ENAB", ("ON", "OFF"), "OFF"),
			)),
			SetupCmd("BEEP", subcmds_=(
				SetupCmd("ENAB", ("ON", "OFF"), "OFF"),
			)),
		))
	
