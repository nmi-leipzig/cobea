from typing import Iterable, List, Mapping

from domain.allele_sequence  import Allele, AlleleAll, AlleleList, AllelePow
from domain.interfaces import Representation, RepresentationGenerator, TargetConfiguration
from domain.model import Chromosome, Gene
from domain.request_model import Parameter, ResponseObject, RequestObject

from adapters.simtar.pos import SimtarBitPos


class SimtarRep(Representation):
	"""Representation of simple target"""
	
	def __init__(self, genes: List[Gene], constant: List[Gene]) -> None:
		self._genes = genes
		self._constant = constant
	
	def prepare_config(self, config: TargetConfiguration) -> None:
		for const in self._constant:
			config.set_multi_bits(const.bit_positions, const.alleles[0].values)
	
	def decode(self, config: TargetConfiguration, chromo: Chromosome) -> None:
		"""Decode a chromosome to a Configuration.
		
		The name is not 100 percent correct as decoding maps the chromosome to the phenotype,
		but the real phenotype is the configured FPGA, not the configuration.
		"""
		if len(self._genes) != len(chromo.allele_indices):
			raise ValueError(f"Length mismatch: {len(self._genes)} genes, but {len(chromo.allele_indices)} alleles")
		
		for gene, allele_index in zip(self._genes, chromo.allele_indices):
			config.set_multi_bits(gene.bit_positions, gene.alleles[allele_index].values)
	
	def iter_genes(self) -> Iterable[Gene]:
		yield from self._genes


class SimtarRepGen(RepresentationGenerator):
	"""Generator of representations for simple target"""
	
	@property
	def parameters(self) -> Mapping[str, Iterable[Parameter]]:
		return {"__call__": [Parameter("always_active", bool, default=True)]}
	
	def __call__(self, request: RequestObject) -> ResponseObject:
		genes = [
			Gene(
				tuple(SimtarBitPos(i) for i in range(16)),
				AllelePow(4, []),
				"LUT"
			)
		]
		constant = []
		
		if request.always_active:
			constant.append(
				Gene(
					(SimtarBitPos(16), ),
					AlleleList([Allele((True, ), "active")]),
					"active flag"
				)
			)
		else:
			genes.append(
				Gene(
					(SimtarBitPos(16), ),
					AlleleAll(1),
					"active flag"
				)
			)
		
		return ResponseObject(representation=SimtarRep(genes, constant))
	
