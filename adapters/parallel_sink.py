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

class ParallelSink(DataSink):
	"""Wraps around another DataSink and executes it in a separate process.
	"""
	
	def __init__(self, sink_type: Type[DataSink], sink_args: tuple=tuple(), sink_kwargs: dict={}) -> None:
		self._sink_details = SinkDetails(sink_type, sink_args, sink_kwargs)
		self._ctx = mp.get_context("spawn")
		self._write_queue = None
		self._process = None
	
	def __enter__(self) -> "ParallelSink":
		self._write_queue = self._ctx.JoinableQueue()
		self._process = self._ctx.Process(target=self.writer, args=(self._sink_details, self._write_queue))
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
	
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		self._write_queue.put((source, data_dict))
	
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
