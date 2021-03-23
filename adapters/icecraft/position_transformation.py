from functools import partial
from typing import Sequence, List

from domain.interfaces import PosTransLibrary
from domain.model import PosTransImpl
from domain.request_model import RequestObject, ParameterValues
from adapters.icecraft.misc import IcecraftPosition

class IcecraftPosTransLibrary(PosTransLibrary):
	def __init__(self) -> None:
		self.param_dict = {
			"expand_rectangle": tuple()
		}
	
	def get_implementation(self, request: RequestObject) -> PosTransImpl:
		func = getattr(self, request.identifier)
		params = ParameterValues()
		for name in self.param_dict[request.identifier]:
			params[name] = request[name]
		return partial(func, params=params)
	
	@staticmethod
	def expand_rectangle(corner_points: Sequence[IcecraftPosition], params=None) -> List[IcecraftPosition]:
		x_min = min(t.x for t in corner_points)
		x_max = max(t.x for t in corner_points)
		y_min = min(t.y for t in corner_points)
		y_max = max(t.y for t in corner_points)
		return [IcecraftPosition(x, y) for x in range(x_min, x_max+1) for y in range(y_min, y_max+1)]
