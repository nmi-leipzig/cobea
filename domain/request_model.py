from typing import Any, Dict, Mapping, Iterable
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
