import multiprocessing as mp

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Callable, Mapping, Optional, Type

from domain.data_sink import DataSink
from domain.interfaces import DataCollector, Driver, Meter
from domain.request_model import RequestObject
from domain.use_cases import Measure


@dataclass
class InitDetails:
	"""Data necessary to create a new instance"""
	cls: type
	args: tuple = field(default_factory=tuple)
	kwargs: Mapping[str, Any] = field(default_factory=dict)
	
	def create_from(self) -> Any:
		return self.cls(*self.args, **self.kwargs)

@dataclass
class CollectorDetails:
	"""Data necessary to start the collector"""
	# args and kwargs have to be process safe
	driver_det: InitDetails
	# args and kwargs have to be process safe
	meter_det: InitDetails
	# has to be process safe
	data_sink: DataSink
	pause: float = 0
	# prefix for source indication for writes to DataSink
	sink_prefix: Optional[str] = None
	prepare: Optional[Callable[[Driver, Meter, Measure, DataSink], None]] = None
	# parameters passed to request of Measure; have to be process safe
	# if they need to be dynamically create, a callback should be implemented
	req_values: Mapping[str, Any] = field(default_factory=dict)

class ParallelCollector(DataCollector):
	"""Collect data in separate process"""
	def __init__(self, details: CollectorDetails, term_timeout: float=0.1) -> None:
		"""
		details: data for starting data collecting, some data has to be process safe
		term_timeout: seconds before a not yet collecting process is terminated
		"""
		self._details = details
		self._term_timeout = term_timeout
		self._end_event = None
		self._process = None
	
	def __enter__(self) -> "ParallelCollector":
		if self._end_event is not None:
			return self
		
		ctx = mp.get_context("spawn")
		# event from Process that signals the data collection loop started
		self._start_event = ctx.Event()
		# event to Process that signals to end the data collection loop
		self._end_event = ctx.Event()
		self._process = ctx.Process(target=self.collector, args=(self._details, self._start_event, self._end_event))
		
		self._process.start()
		
		return self
	
	def __exit__(self,
		exc_type: Optional[Type[BaseException]],
		exc_value: Optional[BaseException],
		exc_traceback: Optional[TracebackType]
	) -> bool:
		if self._end_event is None:
			return False
		
		self._end_event.set()
		if self._start_event.is_set():
			# collecting started, wait to finish by _end_event
			self._process.join()
		else:
			# collecting didn't even start
			self._process.join(self._term_timeout)
			if self._process.exitcode is None:
				# still not done
				self._process.terminate()
			
		self._end_event = None
		self._start_event = None
		self._process = None
		
		return False
	
	def is_alive(self) -> bool:
		return self._process is not None and self._process.is_alive()
	
	def is_collecting(self) -> bool:
		return self._start_event.is_set()
	
	def wait_collecting(self, timeout=None) -> bool:
		return self._start_event.wait(timeout)
	
	@staticmethod
	def collector(details: CollectorDetails, start_event: mp.Event, end_event: mp.Event) -> None:
		with ExitStack() as ex_stack:
			# setup measurement
			driver = details.driver_det.create_from()
			meter = ex_stack.enter_context(details.meter_det.create_from())
			measure_uc = Measure(driver, meter, details.data_sink, details.sink_prefix)
			if details.prepare:
				details.prepare(driver, meter, measure_uc, details.data_sink)
			
			start_event.set()
			if end_event.is_set():
				# end immediately
				return
			
			# loop until end event
			while True:
				req = RequestObject(details.req_values)
				res = measure_uc(req)
				
				if end_event.wait(details.pause):
					break
		
