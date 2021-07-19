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
	cls: Type[DataSink]
	args: tuple = field(default_factory=tuple)
	kwargs: Mapping[str, Any] = field(default_factory=dict)
	
	def create_from(self) -> Any:
		return self.cls(*self.args, **self.kwargs)

@dataclass
class CollectorDetails:
	"""Data necessary to start the collector"""
	driver_det: InitDetails
	meter_det: InitDetails
	data_sink: DataSink
	pause: float = 0
	# prefix for source indication for writes to DataSink
	sink_prefix: Optional[str] = None
	prepare: Callable[[Driver, Meter, Measure, DataSink], None] = lambda a, b, c, d: None
	# parameters passed to request of Measure; have to be process safe
	# if they need to be dynamically create, a callback should be implemented
	req_values: Mapping[str, Any] = field(default_factory=dict)

class ParallelCollector(DataCollector):
	"""Collect data in separate process"""
	def __init__(self, details: CollectorDetails) -> None:
		"""data_sink, args, kwargs, and request values have to be process safe"""
		self._details = details
		self._end_event = None
		self._process = None
	
	def __enter__(self) -> "ParallelCollector":
		if self._end_event is not None:
			return self
		
		ctx = mp.get_context("spawn")
		self._end_event = ctx.Event()
		self._process = ctx.Process(target=self.collector, args=(self._details, self._end_event))
		
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
		self._process.join()
		
		self._end_event = None
		self._process = None
		
		return False
	
	@staticmethod
	def collector(details: CollectorDetails, end_event: mp.Event) -> None:
		with ExitStack() as ex_stack:
			# setup measurement
			driver = details.driver_det.create_from()
			meter = ex_stack.enter_context(details.meter_det.create_from())
			# don't pass data_sink as we would have no method to distinguish between Different Measure use cases
			measure_uc = Measure(driver, meter, details.data_sink, details.sink_prefix)
			details.prepare(driver, meter, measure_uc, details.data_sink)
			
			# loop until end event
			while True:
				req = RequestObject(details.req_values)
				res = measure_uc(req)
				
				if end_event.wait(details.pause):
					break
		
