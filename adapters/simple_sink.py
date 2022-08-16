from types import TracebackType
from typing import Any, Mapping, Optional, Type

from domain.data_sink import DataSink

class StdSink(DataSink):
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		print(f"{source}: {[n + '=' + str(v)[:50] + ', ' for n, v in data_dict.items()]}")
	
	def __enter__(self) -> "StdSink":
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		return False

class TextfileSink(DataSink):
	def __init__(self, filename: str) -> None:
		self._file = None
		self._filename = filename
	
	def open(self) -> None:
		if self._file is not None:
			return
		
		self._file = open(self._filename, "w", encoding="utf-8")
	
	def close(self) -> None:
		if self._file is None:
			return
		
		self._file.close()
		self._file = None
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		self._file.write(f"{source}: {[n+'='+str(v)[:50]+', ' for n, v in data_dict.items()]}\n")
	
	def __enter__(self) -> "StdSink":
		self.open()
		
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		self.close()
		return False
	
