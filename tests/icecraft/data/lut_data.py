from dataclasses import dataclass
from typing import List

from adapters.icecraft.misc import LUTFunction
from domain.allele_sequence import AlleleSequence, AlleleList, AlleleAll, AllelePow, Allele


@dataclass
class TruthTableData:
	input_count: int
	unused_inputs: List[int]
	lut_functions: List[LUTFunction]
	allele_seq: AlleleSequence

TRUTH_TABLE = (
	TruthTableData(4, [], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True),
		(False, True, True, False, True, False, False, True, True, False, False, True, False, True, True, False),
		(False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
		(True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
	)])),
	TruthTableData(4, [1], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, True),
		(False, True, False, True, True, False, True, False, True, False, True, False, False, True, False, True),
		(False, True, False, True, True, True, True, True, True, True, True, True, True, True, True, True),
		(True, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, False, True, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
	)])),
	TruthTableData(4, [3], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, True),
		(False, True, True, False, True, False, False, True, False, True, True, False, True, False, False, True),
		(False, True, True, True, True, True, True, True, False, True, True, True, True, True, True, True),
		(True, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False),
		(True, True, True, True, True, True, True, False, True, True, True, True, True, True, True, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
	)])),
	TruthTableData(4, [1, 2], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(False, False, False, False, False, False, False, False, False, True, False, True, False, True, False, True),
		(False, True, False, True, False, True, False, True, True, False, True, False, True, False, True, False),
		(False, True, False, True, False, True, False, True, True, True, True, True, True, True, True, True),
		(True, False, True, False, True, False, True, False, False, False, False, False, False, False, False, False),
		(True, True, True, True, True, True, True, True, True, False, True, False, True, False, True, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
	)])),
	TruthTableData(4, [0, 3], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False),
		(False, False, False, False, False, False, True, True, False, False, False, False, False, False, True, True),
		(False, False, True, True, True, True, False, False, False, False, True, True, True, True, False, False),
		(False, False, True, True, True, True, True, True, False, False, True, True, True, True, True, True),
		(True, True, False, False, False, False, False, False, True, True, False, False, False, False, False, False),
		(True, True, True, True, True, True, False, False, True, True, True, True, True, True, False, False),
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True),
	)])),
	TruthTableData(4, [0, 1, 2], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0
		(False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True), # AND, OR, PARITY
		(True, True, True, True, True, True, True, True, False, False, False, False, False, False, False, False), # NAND, NOR
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1
	)])),
	TruthTableData(4, [0, 1, 3], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0
		(False, False, False, False, True, True, True, True, False, False, False, False, True, True, True, True), # AND, OR, PARITY
		(True, True, True, True, False, False, False, False, True, True, True, True, False, False, False, False), # NAND, NOR
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1
	)])),
	TruthTableData(4, [0, 1, 2, 3], list(LUTFunction), AlleleList([Allele(v, "") for v in (
		(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False), # CONST_0, OR, NAND, PARITY
		(True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True), # CONST_1, AND, NOR
	)])),
)
