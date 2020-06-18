from typing import Any, Dict

class ParameterValues(Dict[str, Any]):
	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError as ke:
			raise AttributeError from ke

class RequestObject(ParameterValues):
	pass
