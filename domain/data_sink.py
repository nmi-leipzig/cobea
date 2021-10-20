import functools

from abc import ABC, abstractmethod, abstractproperty
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Tuple

from domain.request_model import create_get_req

class DataSink(AbstractContextManager):
	@abstractmethod
	def write(self, source: str, data_dict: Mapping[str, Any]) -> None:
		raise NotImplementedError()

class DataSinkUser(ABC):
	@abstractproperty
	def data_sink(self) -> DataSink:
		raise NotImplementedError()
	
	@property
	def prefix(self) -> str:
		return type(self).__name__
	
	def write_to_sink(self, sub_name: str, data_dict: Mapping[str, Any]) -> None:
		if self.data_sink is None:
			return
		self.data_sink.write(f"{self.prefix}.{sub_name}", data_dict)

def sink_request(func: Callable) -> Callable:
	"""Decorator for functions with request parameter to send request to a DataSink
	
	The function has to be a method of an object that implements ParameterUser and DataSinkUser
	
	Should be used after wrappers manipulating the input (e.g. setting default values)
	"""
	
	get_req = create_get_req(func)
	
	@functools.wraps(func)
	def wrap(*args, **kwargs):
		# first arg should be self, i.e. the object that the function belongs to
		obj = args[0]
		func_name = func.__name__
		params = obj.parameters[func_name]
		
		req = get_req(*args, **kwargs)
		
		# copy data from request
		values = {p.name: req[p.name] for p in params}
		
		# execute decorated function
		res = func(*args, **kwargs)
		
		# copy result
		# use 'return' so it is easy to avoid conflicts with other parameter names by prohibting Python keywords
		# which are already banned for RequestObject
		values["return"] = res
		
		# write request to data sink
		sink = obj.write_to_sink(func_name, values)
		
		return res
	
	return wrap

