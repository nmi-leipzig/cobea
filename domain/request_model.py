from typing import Any, Dict, Mapping, Iterable, List
from abc import ABC, abstractproperty
from dataclasses import dataclass

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

class ParameterUser(ABC):
	"""Classes that use parameters"""
	
	@abstractproperty
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		raise NotImplementedError()
	
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
