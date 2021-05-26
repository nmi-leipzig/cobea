import functools

from abc import ABC, abstractmethod, abstractproperty
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable, Tuple

from domain.request_model import create_get_req

@dataclass(frozen=True)
class ReqVal:
	"""Represent a value of a parameter in a request"""
	name: str
	value: Any
	data_type: type
	multiple: bool

@dataclass(frozen=True)
class DoneReq:
	"""Represent finished request"""
	values: Tuple[ReqVal]
	result: Any
	creator: str

class DataSink(AbstractContextManager):
	@abstractmethod
	def write_metadata(self, name: str, data: Any, data_type: type, multiple=False) -> None:
		raise NotImplementedError()
	
	@abstractmethod
	def write_request(self, req_data: DoneReq) -> None:
		raise NotImplementedError()

class DataSinkUser(ABC):
	@abstractproperty
	def data_sink(self) -> DataSink:
		raise NotImplementedError()

def sink_request(func: Callable) -> Callable:
	"""Decorator for functions with request parameter to send request to a DataSink
	
	The function has to be a method of an object that implements ParameterUser and DataSinkUser
	
	Should be used after wrappers manipulating the input (e.g. setting default values)
	"""
	
	get_req = create_get_req(func)
	
	@functools.wraps(func)
	def wrap(*args, **kwargs):
		# first arg should be self, i.e. the object that the functon belongs to
		obj = args[0]
		func_name = func.__name__
		params = obj.parameters[func_name]
		class_name = type(obj).__name__
		
		req = get_req(*args, **kwargs)
		
		# copy data from request
		values = tuple(ReqVal(p.name, req[p.name], p.data_type, p.multiple) for p in params)
		
		# execute decorated function
		res = func(*args, **kwargs)
		
		# copy result
		done = DoneReq(
			values,
			res,
			f"{class_name}.{func_name}"
		)
		
		# write request to data sink
		sink = obj.data_sink
		if sink is not None:
			sink.write_request(done)
		
		return res
	
	return wrap

