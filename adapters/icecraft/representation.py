from typing import Sequence, Mapping
from dataclasses import dataclass

from domain.interfaces import Representation, RepresentationGenerator
from domain.model import TargetConfiguration, Gene, Chromosome
from domain.request_model import RequestObject, Parameter

from .misc import IcecraftLUTPosition, IcecraftColBufCtrl, IcecraftNetPosition, LUTFunction

@dataclass
class IcecraftRep(Representation):
	genes: Sequence[Gene]
	# constant genes, i.e. with exactly one allele
	constant: Sequence[Gene]
	#colbufctrl
	colbufctrl: Sequence[IcecraftColBufCtrl]
	# output_lutffs
	output: Sequence[IcecraftLUTPosition]
	
	def prepare_config(self, config: TargetConfiguration) -> None:
		# set constant bits
		# set ColBufCtrl for global network input
		pass
	
	def decode(self, config: TargetConfiguration, chromo: Chromosome) -> None:
		pass
	

class IcecraftRepGen(RepresentationGenerator):
	def __init__(self) -> None:
		self._parameters = {"__call__": [
			Parameter("x_min", int),
			Parameter("y_min", int),
			Parameter("x_max", int),
			Parameter("y_max", int),
			Parameter("exclude_nets", str, multiple=True),
			Parameter("include_nets", str, multiple=True),
			Parameter("output_lutffs", IcecraftLUTPosition, multiple=True),
			Parameter("joint_input_nets", str, default=[], multiple=True),
			Parameter("lone_input_nets", IcecraftNetPosition, default=[], multiple=True),
			Parameter("lut_functions", LUTFunction, default=[], multiple=True),
		]}
	
	@property
	def parameters(self) -> Mapping[str, Parameter]:
		return self._parameters
	
	def __call__(self, request: RequestObject) -> IcecraftRep:
		return IcecraftRep([], [], [], tuple(sorted(request.output_lutffs)))

