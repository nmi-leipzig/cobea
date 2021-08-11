import multiprocessing as mp

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Mapping, Optional, Type

from domain.data_sink import DataSink

@dataclass(frozen=True)
class SinkDetails:
	cls: Type[DataSink]
	args: tuple
	kwargs: dict

class ParSubSink(DataSink):
	"""DataSink with access to a ParallelSink, that can be passed to new Processes"""
	def __init__(self, write_queue: mp.JoinableQueue) -> None:
		self._write_queue = write_queue
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		self._write_queue.put((source, data_dict))
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		return False

class ParallelSink(DataSink):
	"""Wraps around another DataSink and executes it in a separate process.
	"""
	
	def __init__(self, sink_type: Type[DataSink], sink_args: tuple=tuple(), sink_kwargs: dict={}) -> None:
		self._sink_details = SinkDetails(sink_type, sink_args, sink_kwargs)
		self._write_queue = None
		self._process = None
	
	def __enter__(self) -> "ParallelSink":
		ctx = mp.get_context("spawn")
		self._write_queue = ctx.JoinableQueue()
		self._process = ctx.Process(target=self.writer, args=(self._sink_details, self._write_queue))
		self._process.start()
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		self._write_queue.put(None)
		self._write_queue.join()
		self._process.join()
		
		self._write_queue = None
		self._process = None
		
		return False
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		self._write_queue.put((source, data_dict))
	
	def get_sub(self) -> ParSubSink:
		"""Return a DataSink that writes to the wrapped sink can be passed to other processes
		
		As the ParallelSink sink holds a reference to the started Process it can't be passed directly to other Process
		instances. To still use the wrapped DataSink from multiple Process instances, a process safe ParSubSink can
		be created with this function.
		"""
		return ParSubSink(self._write_queue)
	
	@staticmethod
	def writer(sink_details: SinkDetails, write_queue: mp.JoinableQueue) -> None:
		core_sink = sink_details.cls(*sink_details.args, **sink_details.kwargs)
		
		with core_sink:
			while True:
				item = write_queue.get()
				if item is None:
					break
				
				core_sink.write(*item)
				write_queue.task_done()
			
		write_queue.task_done()
