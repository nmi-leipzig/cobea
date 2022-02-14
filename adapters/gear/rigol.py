import re
import time

from copy import deepcopy
from dataclasses import dataclass, field
from math import isfinite
from types import TracebackType
from typing import Any, Callable, Iterable, List, Mapping, Optional, Tuple, Type

import pyvisa

from domain.interfaces import IdentifiableHW, MeasureTimeout, Meter
from domain.model import OutputData
from domain.request_model import Parameter, ResponseObject, RequestObject

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

class InvalidMsgError(Exception):
	pass

class OsciDS1102E(Meter, IdentifiableHW):
	def __init__(self, setup: SetupCmd, serial_number: Optional[str]=None, data_chan: int=1, raw: bool=False) -> None:
		"""
		
		raw: flag for returning raw bytes instead of volt floats
		"""
		self._setup = setup
		self._serial_number = serial_number
		self._hw_type = None
		self._firmware_version = None
		self._data_chan = data_chan
		self._raw = raw
		self._is_open = False
		self._res_man = None
		self._dev_str = None
		self._osci = None
		self._prep = None
		self._delay = 0.1
		
		self.open()
		self._read_idn()
		self.apply(self._osci, self._setup, self._delay)
		
	
	def _read_idn(self) -> None:
		idn = self._osci.query("*IDN?")
		parts = idn.split(",")
		
		self._serial_number = parts[2]
		self._hw_type = f"{parts[0]} {parts[1]}"
		self._firmware_version = parts[3]
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"prepare": [], "measure": [Parameter("measure_timeout", float, default=None)]}
	
	@property
	def serial_number(self) -> str:
		return self._serial_number
	
	@property
	def hardware_type(self) -> str:
		return self._hw_type
	
	@property
	def firmware_version(self) -> str:
		return self._firmware_version
	
	def reset(self) -> None:
		self._osci.write("*RST")
		time.sleep(self._delay)
	
	@staticmethod
	def raw_to_volt_from_setup(setup: SetupCmd, data_chan: int) -> Callable[[Iterable[int]], Iterable[float]]:
		"""Creates a function that converts raw integer values to float Volt values."""
		
		if data_chan == 1:
			scale = setup.CHAN1.SCAL.value_
			offset = setup.CHAN1.OFFS.value_
		else:
			scale = setup.CHAN2.SCAL.value_
			offset = setup.CHAN2.OFFS.value_
		
		def func(raw_data: Iterable[int]) -> List[float]:
			return OutputData([(125-r)*scale/25-offset for r in raw_data])
		
		return func
	
	def raw_to_volt_func(self) -> Callable[[Iterable[int]], Iterable[float]]:
		"""Creates a function that converts raw integer values to float Volt values.
		
		The oscilloscope setup at the time of creation of the convertion function are respected
		for the conversion.
		"""
		return self.raw_to_volt_from_setup(self._setup, self._data_chan)
	
	def open(self):
		if self._is_open:
			return
		
		self._res_man = pyvisa.ResourceManager()
		self._dev_str = self.find_instrument(self._res_man, self._serial_number)
		self._osci = self._res_man.open_resource(self._dev_str)
		
		# if a raw data block is transfered in multiple chunks, the last 10 bytes of the first chunk are missing
		# -> use chunk size that fits largest block 1024*1024+10
		self._osci.chunk_size = 2*1024*1024
		# large chunks can take a long time -> increase timeout
		self._osci.timeout = 60000
		
		if self._raw:
			self._prep = lambda x: OutputData(x)
		else:
			self._prep = self.raw_to_volt_func()
		
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
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		self.close()
		
		return False
	
	def prepare(self, request: RequestObject) -> ResponseObject:
		#self.open()
		
		#self.read_and_print(self._osci, self._setup)
		self._osci.write(":RUN")
		while self._osci.query(":TRIG:STAT?") != "WAIT":
			time.sleep(self._delay)
		
		# for small time scales (20 ms or less) the trigger might come too fast -> wait a bit (0.03 s seem to work)
		if self._setup.TIM.SCAL.value_ <= 0.02:
			time.sleep(0.03)

		return ResponseObject()
	
	def measure(self, request: RequestObject) -> ResponseObject:
		start_time = time.perf_counter()
		while self._osci.query(":TRIG:STAT?") not in ("T'D", "STOP"):
			if request.measure_timeout is not None and time.perf_counter() - start_time > request.measure_timeout:
				raise MeasureTimeout()
			time.sleep(self._delay)
		
		while self._osci.query(":TRIG:STAT?") != "STOP":
			time.sleep(self._delay)
		
		raw_data = self._read_data(self._data_chan)

		return ResponseObject(measurement=self._prep(raw_data))

	def _read_data(self, chan: int) -> bytes:
		self._osci.write(f":WAV:DATA? CHAN{chan}")
		
		bef = time.perf_counter()
		block = self._osci.read_raw()
		aft = time.perf_counter()
		
		# decode header
		if block[0:1] != b"#":
			print(len(block), block[:40])
			raise InvalidMsgError(f"starts not with #, but {data[:1]}")
		len_len = int(block[1:2])
		length = int(block[2:2+len_len])
		
		raw_data = block[2+len_len:]
		
		#print(f"{len(raw_data)+10} bytes in {aft-bef} s, {(len(raw_data)+10)/(aft-bef)} b/s")
		#assert raw_data[:2] == bytes("#8", "utf8"), f"not #8, but {data[:2]}"
		#length = int(raw_data[2:10])
		#print(f"expected {length} bytes of data and 10 header bytes")
		if len(raw_data) != length:
			raise InvalidMsgError(f"Expected {length} bytes, but got {len(raw_data)}")
		
		return raw_data
	
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
	def apply(cls, osci: pyvisa.Resource, setup: SetupCmd, delay: float=0.01) -> None:
		"""Apply values of the setup while respecting the connection between different values.
		
		One example for a connection between different values: if TRIG:MODE is EDGE, then only subcommands of TRIG:EDGE
		will be written, as e.g. subcommands of TRIG:PULS are not relevant.
		"""
		if not setup.condition_(setup):
			return
		
		if setup.values_ is not None:
			if setup.value_ not in setup.values_:
				raise ValueError(f"'{setup.value_}' invalid for {setup.name_}")
			#print(setup.cmd_(write=True))
			osci.write(setup.cmd_(write=True))
			time.sleep(delay)
		
		for subcmd in setup.subcmds_:
			cls.apply(osci, subcmd, delay)
	
	@classmethod
	def read_and_print(cls, osci: pyvisa.Resource, setup: SetupCmd, relevant: bool=True) -> None:
		if relevant and not setup.condition_(setup):
			return
		
		if setup.values_ is not None:
			query = setup.cmd_(write=False)
			res = osci.query(query)
			print(f"{query} -> {res}")
		
		for subcmd in setup.subcmds_:
			cls.read_and_print(osci, subcmd)
	
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
	
