"""Minimum viable implementations

Primarily for tests and runs without hardware. More flexible than dummy implementations.
"""

from typing import Callable, Iterable, Mapping, NewType, Optional

from domain.data_sink import DataSink
from domain.interfaces import Driver, Meter
from domain.model import OutputData
from domain.request_model import ResponseObject, RequestObject, Parameter

ReqCall = NewType("ReqCall", Callable[[RequestObject], ResponseObject])


def empty_res(req: RequestObject) -> ResponseObject:
	return ResponseObject()


class MinviaDriver(Driver):
	def __init__(self, drive_params: Iterable[Parameter]=[], drive_func: Optional[ReqCall]=None, clean_up_params:
	Iterable[Parameter]=[], clean_up_func: Optional[ReqCall]=None):
		self._drive_params = list(drive_params)
		self._clean_up_params = list(clean_up_params)
		
		self._drive_func = drive_func or empty_res
		self._clean_up_func = clean_up_func or empty_res
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"drive": self._drive_params, "clean_up": self._clean_up_params}
	
	def drive(self, request: RequestObject) -> ResponseObject:
		return self._drive_func(request)
	
	def clean_up(self, request: RequestObject) -> ResponseObject:
		return self._clean_up_func(request)
