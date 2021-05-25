import functools
import inspect

from abc import ABC, abstractproperty
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping

class _NO_DEFAULT:
	pass
NO_DEFAULT = _NO_DEFAULT()

@dataclass(frozen=True)
class Parameter:
	name: str
	data_type: type
	default: Any = NO_DEFAULT
	multiple: bool = False

class ParameterValues(Dict[str, Any]):
	def __getattr__(self, name: str):
		try:
			return self[name]
		except KeyError as ke:
			raise AttributeError from ke

class RequestObject(ParameterValues):
	pass

def create_get_req(func: Callable) -> Callable[..., RequestObject]:
	"""create a function that extracts the Request from call parameters for a function"""
	
	req_index = None
	req_par = None
	for i, par in enumerate(inspect.signature(func).parameters.values()):
		if par.annotation == RequestObject:
			if req_index is not None:
				raise ValueError("callable has multiple parameters annotated as RequestObject")
			
			req_index = i
			req_par = par
	
	if req_par is None:
		raise ValueError("callable has no parameters annotated as RequestObject")
	
	def pos(*a, **kw) -> RequestObject:
		return a[req_index]
	
	def keyword(*a, **kw) -> RequestObject:
		return kw[req_par.name]
	
	def pos_or_keyword(*a, **kw) -> RequestObject:
		try:
			return pos(*a, **kw)
		except IndexError:
			return keyword(*a, **kw)
	
	if req_par.kind == inspect.Parameter.POSITIONAL_ONLY:
		get_req = pos
	elif req_par.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
		get_req = pos_or_keyword
	elif req_par.kind == inspect.Parameter.KEYWORD_ONLY:
		get_req = keyword
	else:
		raise ValueError(f"callable has RequestObject annotated on wrong kind of parameter: {req_par.kind}")
	
	return get_req

def set_req_defaults(func: Callable) -> Callable:
	"""set defaults in request"""
	
	get_req = create_get_req(func)
	
	@functools.wraps(func)
	def wrap(*args, **kwargs):
		req = get_req(*args, **kwargs)
		def_parms = args[0].default_parameters[func.__name__]
		for name, default in def_parms.items():
			if name in req:
				continue
			req[name] = default
		
		return func(*args, **kwargs)
	
	return wrap

class ParameterUser(ABC):
	"""Classes that use parameters"""
	
	@abstractproperty
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		raise NotImplementedError()
	
	@property
	def default_parameters(self) -> Mapping[str, Mapping[str, Any]]:
		return self.extract_defaults(self.parameters)
	
	@staticmethod
	def extract_defaults(parameters: Mapping[str, Iterable[Parameter]]) -> Mapping[str, Mapping[str, Any]]:
		defaults = {k: {p.name: p.default for p in l if p.default!=NO_DEFAULT} for k, l in parameters.items()}
		
		return defaults
	
	@staticmethod
	def meld_parameters(a: Iterable[Parameter], b: Iterable[Parameter]) -> List[Parameter]:
		"""Meld two iterables of Parameters into a single list.
		
		Assumptions: 
			a is valid, i.e. no two parameters of a have the same name. 
			b is valid, i.e. no two parameters of b have the same name.
		
		If any parameters in b have the same name as a parameter in a, they have to have the same data_type and
		multiple value. The default value n such cases is taken from a.
		"""
		a_map = {p.name: p for p in a}
		p_list = list(a)
		
		for param in b:
			try:
				a_param = a_map[param.name]
			except KeyError:
				p_list.append(param)
				continue
			
			if a_param.data_type != param.data_type:
				raise ValueError(f"data type different for {param.name}")
			if a_param.multiple != param.multiple:
				raise ValueError(f"multiple different for {param.name}")
		
		return p_list
