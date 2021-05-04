
from adapters.icecraft.chip_data_utils import UNCONNECTED_NAME
from adapters.icecraft.config_item import IndexedItem
from adapters.icecraft.representation import IcecraftRep
from adapters.icecraft.misc import IcecraftBitPosition, IcecraftGeneConstraint, IcecraftLUTPosition, IcecraftPosition, IcecraftResCon, IcecraftResource, LUTFunction, TILE_ALL, TILE_ALL_LOGIC
from domain.allele_sequence import Allele, AlleleAll, AlleleList
from domain.model import Gene
from domain.request_model import RequestObject

from ..common import create_bits

GEN_REQUEST = RequestObject(
	tiles = [IcecraftPosition(15, 17), IcecraftPosition(16, 17)],
	output_lutffs = [IcecraftLUTPosition(16, 18, 5)],
	lut_functions = [LUTFunction.CONST_0, LUTFunction.CONST_1, LUTFunction.NAND],
	gene_constraints = [
		# constraint truth table
		IcecraftGeneConstraint(create_bits(15, 17, (
				(10, 40), (11, 40), (11, 41), (10, 41), (10, 42), (11, 42), (11, 43), (10, 43),
				(10, 39), (11, 39), (11, 38), (10, 38), (10, 37), (11, 37), (11, 36), (10, 36)
			)),
			((False, )*16, (True, )*16)
		),
		# restrict  connections
		IcecraftGeneConstraint(create_bits(16, 17, ((4, 14), (5, 14), (5, 15), (5, 16), (5, 17))), (
			(False, False, False, False, False),
			(True, False, True, False, True),
		)),
		# connect connections in different tiles
		IcecraftGeneConstraint(
			create_bits(15, 17, ((1, 44), (11, 44))) + create_bits(16, 17, ((1, 44), (11, 44))),
			((False, )*4, (True, )*4)
		),
	],
	prune_no_viable_src = False,
	exclude_resources = [IcecraftResource(TILE_ALL, TILE_ALL, "")],
	include_resources = [
		IcecraftResource(TILE_ALL_LOGIC, TILE_ALL_LOGIC, "LUT#0"),
		IcecraftResource(TILE_ALL_LOGIC, TILE_ALL_LOGIC, "LUT#5"),
		# neigh_op_lft_0 is valid for both tiles as it is the external input
		IcecraftResource(16, 17, "NET#neigh_op_lft_5"),
		IcecraftResource(15, 17, "NET#neigh_op_rgt_0"), IcecraftResource(15, 17, "NET#neigh_op_rgt_5"),
	] + [
		IcecraftResource(TILE_ALL_LOGIC, TILE_ALL_LOGIC, f"NET#{n}") for n in [
			UNCONNECTED_NAME, "glb_netwk_0", "lutff_0/out", "lutff_5/out", "neigh_op_lft_0",
			"lutff_0/in_", "lutff_5/in_", "local_g\d_0", "local_g\d_5", "lutff_global/", "glb2local_1",
			"local_g2_1", # create const that is not unconnected
		]
	],
	exclude_connections = [IcecraftResCon(TILE_ALL_LOGIC, TILE_ALL_LOGIC, f"NET#{UNCONNECTED_NAME}", "NET#local_g1_5")],
	include_connections = [IcecraftResCon(16, 17, f"NET#{UNCONNECTED_NAME}", "NET#local_g1_5")],
)

EXP_REP = IcecraftRep(
	[
		Gene(
			create_bits(15, 17, ((1, 44), (11, 44))) + create_bits(16, 17, ((1, 44), (11, 44))), 
			AlleleList(
				(Allele((False, False, False, False), '0; 0; 0; 0'), Allele((True, True, True, True), '1; 1; 1; 1'))
			), 
			'(15, 17) LUT#0 Set_NoReset; (15, 17) LUT#5 Set_NoReset; (16, 17) LUT#0 Set_NoReset; '\
			'(16, 17) LUT#5 Set_NoReset; constraint'),
		Gene((IcecraftBitPosition(15, 17, 0, 0), ), AlleleAll(1), 'tile (15, 17) NegClk'),
		Gene(
			create_bits(15, 17, ((8, 0), (8, 1), (9, 0), (9, 1))),
			AlleleList((
				Allele((False, False, False, False), 'unconnected'),
				Allele((False, True, False, False),'NET#glb_netwk_0')
			)),
			'(15, 17) NET#glb2local_1'
		),
		Gene(
			create_bits(15, 17, ((0, 14), (1, 14), (1, 15), (1, 16), (1, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out'),
				Allele((True, False, True, False, True), 'NET#neigh_op_lft_0')
			)),
			'(15, 17) NET#local_g0_0'
		),
		Gene(
			create_bits(15, 17, ((2, 15), (2, 16), (2, 17), (2, 18), (3, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, False, False), 'NET#glb2local_1'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out')
			)),
			'(15, 17) NET#local_g0_5'
		),
		Gene(
			create_bits(15, 17, ((4, 14), (5, 14), (5, 15), (5, 16), (5, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out'),
				Allele((True, False, True, False, True), 'NET#neigh_op_lft_0')
			)),
			'(15, 17) NET#local_g1_0'
		),
		Gene(
			create_bits(15, 17, ((8, 14), (9, 14), (9, 15), (9, 16), (9, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out'),
				Allele((True, False, True, False, True), 'NET#neigh_op_rgt_0')
			)),
			'(15, 17) NET#local_g2_0'
		),
		Gene(
			create_bits(15, 17, ((10, 15), (10, 16), (10, 17), (10, 18), (11, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out'),
				Allele((True, False, True, True, False), 'NET#neigh_op_rgt_5')
			)),
			'(15, 17) NET#local_g2_5'
		),
		Gene(
			create_bits(15, 17, ((12, 14), (13, 14), (13, 15), (13, 16), (13, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out'),
				Allele((True, False, True, False, True), 'NET#neigh_op_rgt_0')
			)),
			'(15, 17) NET#local_g3_0'
		),
		Gene(
			create_bits(15, 17, ((14, 15), (14, 16), (14, 17), (14, 18), (15, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out'),
				Allele((True, False, True, True, False), 'NET#neigh_op_rgt_5')
			)),
			'(15, 17) NET#local_g3_5'
		),
		Gene(
			create_bits(15, 17, ((0, 26), (1, 26), (1, 27), (1, 28), (1, 29))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, False, False, True), 'NET#local_g0_0'),
				Allele((False, False, False, True, True), 'NET#local_g2_0'),
				Allele((True, False, True, False, True), 'NET#local_g1_5'),
				Allele((True, False, True, True, True), 'NET#local_g3_5')
			)),
			'(15, 17) NET#lutff_0/in_0'
		),
		Gene(
			create_bits(15, 17, ((0, 27), (0, 28), (0, 29), (0, 30), (1, 30))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#local_g0_5'),
				Allele((False, True, True, False, False), 'NET#local_g2_1'),
				Allele((False, True, True, True, False), 'NET#local_g2_5'),
				Allele((True, False, True, False, False), 'NET#local_g1_0'),
				Allele((True, True, True, False, False), 'NET#local_g3_0')
			)),
			'(15, 17) NET#lutff_0/in_1'
		),
		Gene(
			create_bits(15, 17, ((0, 35), (1, 32), (1, 33), (1, 34), (1, 35))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, True, False, False, False), 'NET#local_g0_0'),
				Allele((False, True, True, False, False), 'NET#local_g2_0'),
				Allele((True, True, False, True, False), 'NET#local_g1_5'),
				Allele((True, True, True, True, False), 'NET#local_g3_5')
			)),
			'(15, 17) NET#lutff_0/in_2'
		),
		Gene(
			create_bits(15, 17, ((0, 31), (0, 32), (0, 33), (0, 34), (1, 31))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, True, False, True, False), 'NET#local_g1_0'),
				Allele((False, True, True, False, False), 'NET#local_g2_1'),
				Allele((False, True, True, True, False), 'NET#local_g3_0'),
				Allele((True, True, False, False, False), 'NET#local_g0_5'),
				Allele((True, True, True, False, False), 'NET#local_g2_5')
			)),
			'(15, 17) NET#lutff_0/in_3'
		),
		Gene(
			create_bits(15, 17, ((10, 26), (11, 26), (11, 27), (11, 28), (11, 29))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, False, True, True), 'NET#local_g2_1'),
				Allele((False, False, True, False, True), 'NET#local_g1_0'),
				Allele((False, False, True, True, True), 'NET#local_g3_0'),
				Allele((True, False, False, False, True), 'NET#local_g0_5'),
				Allele((True, False, False, True, True), 'NET#local_g2_5')
			)),
			'(15, 17) NET#lutff_5/in_0'
		),
		Gene(
			create_bits(15, 17, ((10, 27), (10, 28), (10, 29), (10, 30), (11, 30))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, False, False), 'NET#local_g0_0'),
				Allele((False, True, True, False, False), 'NET#local_g2_0'),
				Allele((True, False, True, True, False), 'NET#local_g1_5'),
				Allele((True, True, True, True, False), 'NET#local_g3_5')
			)),
			'(15, 17) NET#lutff_5/in_1'
		),
		Gene(
			create_bits(15, 17, ((10, 35), (11, 32), (11, 33), (11, 34), (11, 35), (10, 50))),
			AlleleList((
				Allele((False, False, False, False, False, False), 'unconnected'),
				Allele((False, True, False, True, False, False), 'NET#local_g1_0'),
				Allele((False, True, True, False, False, False), 'NET#local_g2_1'),
				Allele((False, True, True, True, False, False), 'NET#local_g3_0'),
				Allele((True, True, False, False, False, False), 'NET#local_g0_5'),
				Allele((True, True, True, False, False, False), 'NET#local_g2_5')
			)),
			'(15, 17) NET#lutff_5/in_2'
		),
		Gene(
			create_bits(15, 17, ((10, 31), (10, 32), (10, 33), (10, 34), (11, 31))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, True, True, False, False), 'NET#local_g2_0'),
				Allele((True, True, False, True, False), 'NET#local_g1_5'),
				Allele((True, True, True, True, False), 'NET#local_g3_5')
			)),
			'(15, 17) NET#lutff_5/in_3'
		),
		Gene(
			create_bits(15, 17, ((2, 0), (2, 1), (2, 2), (3, 0), (3, 2))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, False, False), 'NET#glb_netwk_0'),
				Allele((False, False, True, False, True), 'NET#local_g0_0'),
				Allele((True, False, True, False, True), 'NET#local_g2_0')
			)),
			'(15, 17) NET#lutff_global/clk'
		),
		Gene(
			create_bits(15, 17, ((14, 0), (14, 1), (15, 0), (15, 1))),
			AlleleList((
				Allele((False, False, False, False), 'unconnected'),
				Allele((False, True, False, False), 'NET#glb_netwk_0'),
				Allele((False, True, True, True), 'NET#local_g1_5'),
				Allele((True, True, True, True), 'NET#local_g3_5')
			)),
			'(15, 17) NET#lutff_global/s_r'
		),
		Gene((IcecraftBitPosition(15, 17, 0, 45), ), AlleleAll(1), '(15, 17) LUT#0 DffEnable'),
		Gene((IcecraftBitPosition(15, 17, 1, 45), ), AlleleAll(1), '(15, 17) LUT#0 AsyncSetReset'),
		Gene(
			create_bits(15, 17, (
				(0, 40), (1, 40), (1, 41), (0, 41), (0, 42), (1, 42), (1, 43), (0, 43),
				(0, 39), (1, 39), (1, 38), (0, 38), (0, 37), (1, 37), (1, 36), (0, 36)
			)),
			AlleleList((
				Allele((
					False, False, False, False, False, False, False, False,
					False, False, False, False, False, False, False, False
				), 'CONST_0'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, False
				), 'NAND'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, True
				), 'CONST_1')
			)),
			'(15, 17) LUT#0 TruthTable'
		),
		Gene((IcecraftBitPosition(15, 17, 10, 45), ), AlleleAll(1), '(15, 17) LUT#5 DffEnable'),
		Gene((IcecraftBitPosition(15, 17, 11, 45), ), AlleleAll(1), '(15, 17) LUT#5 AsyncSetReset'),
		Gene(
			create_bits(15, 17, (
				(10, 40), (11, 40), (11, 41), (10, 41), (10, 42), (11, 42), (11, 43), (10, 43),
				(10, 39), (11, 39), (11, 38), (10, 38), (10, 37), (11, 37), (11, 36), (10, 36)
			)),
			AlleleList((
				Allele((
					False, False, False, False, False, False, False, False,
					False, False, False, False, False, False, False, False
				), 'CONST_0'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, True
				), 'CONST_1')
			)),
			'(15, 17) LUT#5 TruthTable; constraint'
		),
		Gene((IcecraftBitPosition(16, 17, 0, 0), ), AlleleAll(1), 'tile (16, 17) NegClk'),
		Gene(
			create_bits(16, 17, ((8, 0), (8, 1), (9, 0), (9, 1))),
			AlleleList((
				Allele((False, False, False, False), 'unconnected'),
				Allele((False, True, False, False), 'NET#glb_netwk_0')
			)),
			'(16, 17) NET#glb2local_1'
		),
		Gene(
			create_bits(16, 17, ((0, 14), (1, 14), (1, 15), (1, 16), (1, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out'),
				Allele((True, False, True, False, True), 'NET#neigh_op_lft_0')
			)),
			'(16, 17) NET#local_g0_0'
		),
		Gene(
			create_bits(16, 17, ((2, 15), (2, 16), (2, 17), (2, 18), (3, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, False, False), 'NET#glb2local_1'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out'),
				Allele((True, False, True, True, False), 'NET#neigh_op_lft_5')
			)),
			'(16, 17) NET#local_g0_5'
		),
		Gene(
			create_bits(16, 17, ((4, 14), (5, 14), (5, 15), (5, 16), (5, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, True, False, True), 'NET#neigh_op_lft_0')
			)),
			'(16, 17) NET#local_g1_0; constraint'
		),
		Gene(
			create_bits(16, 17, ((6, 15), (6, 16), (6, 17), (6, 18), (7, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out'),
				Allele((True, False, True, True, False), 'NET#neigh_op_lft_5')
			)),
			'(16, 17) NET#local_g1_5'
		),
		Gene(
			create_bits(16, 17, ((8, 14), (9, 14), (9, 15), (9, 16), (9, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out')
			)),
			'(16, 17) NET#local_g2_0'
		),
		Gene(
			create_bits(16, 17, ((10, 15), (10, 16), (10, 17), (10, 18), (11, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out')
			)),
			'(16, 17) NET#local_g2_5'
		),
		Gene(
			create_bits(16, 17, ((12, 14), (13, 14), (13, 15), (13, 16), (13, 17))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((True, False, False, False, True), 'NET#lutff_0/out')
			)),
			'(16, 17) NET#local_g3_0'
		),
		Gene(
			create_bits(16, 17, ((14, 15), (14, 16), (14, 17), (14, 18), (15, 18))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#lutff_5/out')
			)),
			'(16, 17) NET#local_g3_5'
		),
		Gene(
			create_bits(16, 17, ((0, 26), (1, 26), (1, 27), (1, 28), (1, 29))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, False, False, True), 'NET#local_g0_0'),
				Allele((False, False, False, True, True), 'NET#local_g2_0'),
				Allele((True, False, True, False, True), 'NET#local_g1_5'),
				Allele((True, False, True, True, True), 'NET#local_g3_5')
			)),
			'(16, 17) NET#lutff_0/in_0'
		),
		Gene(
			create_bits(16, 17, ((0, 27), (0, 28), (0, 29), (0, 30), (1, 30))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, True, False), 'NET#local_g0_5'),
				Allele((False, True, True, False, False), 'NET#local_g2_1'),
				Allele((False, True, True, True, False), 'NET#local_g2_5'),
				Allele((True, False, True, False, False), 'NET#local_g1_0'),
				Allele((True, True, True, False, False), 'NET#local_g3_0')
			)),
			'(16, 17) NET#lutff_0/in_1'
		),
		Gene(
			create_bits(16, 17, ((0, 35), (1, 32), (1, 33), (1, 34), (1, 35))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, True, False, False, False), 'NET#local_g0_0'),
				Allele((False, True, True, False, False), 'NET#local_g2_0'),
				Allele((True, True, False, True, False), 'NET#local_g1_5'),
				Allele((True, True, True, True, False), 'NET#local_g3_5')
			)),
			'(16, 17) NET#lutff_0/in_2'
		),
		Gene(
			create_bits(16, 17, ((0, 31), (0, 32), (0, 33), (0, 34), (1, 31))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, True, False, True, False), 'NET#local_g1_0'),
				Allele((False, True, True, False, False), 'NET#local_g2_1'),
				Allele((False, True, True, True, False), 'NET#local_g3_0'),
				Allele((True, True, False, False, False), 'NET#local_g0_5'),
				Allele((True, True, True, False, False), 'NET#local_g2_5')
			)),
			'(16, 17) NET#lutff_0/in_3'
		),
		Gene(
			create_bits(16, 17, ((10, 26), (11, 26), (11, 27), (11, 28), (11, 29))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, False, True, True), 'NET#local_g2_1'),
				Allele((False, False, True, False, True), 'NET#local_g1_0'),
				Allele((False, False, True, True, True), 'NET#local_g3_0'),
				Allele((True, False, False, False, True), 'NET#local_g0_5'),
				Allele((True, False, False, True, True), 'NET#local_g2_5')
			)),
			'(16, 17) NET#lutff_5/in_0'
		),
		Gene(
			create_bits(16, 17, ((10, 27), (10, 28), (10, 29), (10, 30), (11, 30))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, False, False), 'NET#local_g0_0'),
				Allele((False, True, True, False, False), 'NET#local_g2_0'),
				Allele((True, False, True, True, False), 'NET#local_g1_5'),
				Allele((True, True, True, True, False), 'NET#local_g3_5')
			)),
			'(16, 17) NET#lutff_5/in_1'
		),
		Gene(
			create_bits(16, 17, ((10, 35), (11, 32), (11, 33), (11, 34), (11, 35), (10, 50))),
			AlleleList((
				Allele((False, False, False, False, False, False), 'unconnected'),
				Allele((False, True, False, True, False, False), 'NET#local_g1_0'),
				Allele((False, True, True, False, False, False), 'NET#local_g2_1'),
				Allele((False, True, True, True, False, False), 'NET#local_g3_0'),
				Allele((True, True, False, False, False, False), 'NET#local_g0_5'),
				Allele((True, True, True, False, False, False), 'NET#local_g2_5')
			)),
			'(16, 17) NET#lutff_5/in_2'
		),
		Gene(
			create_bits(16, 17, ((10, 31), (10, 32), (10, 33), (10, 34), (11, 31))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, True, True, False, False), 'NET#local_g2_0'),
				Allele((True, True, False, True, False), 'NET#local_g1_5'),
				Allele((True, True, True, True, False), 'NET#local_g3_5')
			)),
			'(16, 17) NET#lutff_5/in_3'
		),
		Gene(
			create_bits(16, 17, ((2, 0), (2, 1), (2, 2), (3, 0), (3, 2))),
			AlleleList((
				Allele((False, False, False, False, False), 'unconnected'),
				Allele((False, False, True, False, False), 'NET#glb_netwk_0'),
				Allele((False, False, True, False, True), 'NET#local_g0_0'),
				Allele((True, False, True, False, True), 'NET#local_g2_0')
			)),
			'(16, 17) NET#lutff_global/clk'
		),
		Gene(
			create_bits(16, 17, ((14, 0), (14, 1), (15, 0), (15, 1))),
			AlleleList((
				Allele((False, False, False, False), 'unconnected'),
				Allele((False, True, False, False), 'NET#glb_netwk_0'),
				Allele((False, True, True, True), 'NET#local_g1_5'),
				Allele((True, True, True, True), 'NET#local_g3_5')
			)),
			'(16, 17) NET#lutff_global/s_r'
		),
		Gene((IcecraftBitPosition(16, 17, 0, 45), ), AlleleAll(1), '(16, 17) LUT#0 DffEnable'),
		Gene((IcecraftBitPosition(16, 17, 1, 45), ), AlleleAll(1), '(16, 17) LUT#0 AsyncSetReset'),
		Gene(
			create_bits(16, 17, (
				(0, 40), (1, 40), (1, 41), (0, 41), (0, 42), (1, 42), (1, 43), (0, 43),
				(0, 39), (1, 39), (1, 38), (0, 38), (0, 37), (1, 37), (1, 36), (0, 36)
			)),
			AlleleList((
				Allele((
					False, False, False, False, False, False, False, False,
					False, False, False, False, False, False, False, False
				), 'CONST_0'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, False
				), 'NAND'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, True
				), 'CONST_1')
			)),
			'(16, 17) LUT#0 TruthTable'
		),
		Gene((IcecraftBitPosition(16, 17, 10, 45), ), AlleleAll(1), '(16, 17) LUT#5 DffEnable'),
		Gene((IcecraftBitPosition(16, 17, 11, 45), ), AlleleAll(1), '(16, 17) LUT#5 AsyncSetReset'),
		Gene(
			create_bits(16, 17, (
				(10, 40), (11, 40), (11, 41), (10, 41), (10, 42), (11, 42), (11, 43), (10, 43),
				(10, 39), (11, 39), (11, 38), (10, 38), (10, 37), (11, 37), (11, 36), (10, 36)
			)),
			AlleleList((
				Allele((
					False, False, False, False, False, False, False, False,
					False, False, False, False, False, False, False, False
				), 'CONST_0'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, False
				), 'NAND'),
				Allele((
					True, True, True, True, True, True, True, True,
					True, True, True, True, True, True, True, True
				), 'CONST_1')
			)),
			'(16, 17) LUT#5 TruthTable'
		),
	], # genes
	[
		Gene(
			create_bits(15, 17, ((6, 15), (6, 16), (6, 17), (6, 18), (7, 18))),
			AlleleList((Allele((False, False, True, True, False), 'NET#lutff_5/out'), )),
			'(15, 17) NET#local_g1_5'
		),
		Gene(
			create_bits(15, 17, ((8, 15), (8, 16), (8, 17), (8, 18), (9, 18))),
			AlleleList((Allele((False, False, False, False, False), 'unconnected'),)),
			'(15, 17) NET#local_g2_1'
		),
		Gene(
			create_bits(15, 17, ((4, 0), (4, 1), (5, 0), (5, 1))),
			AlleleList((Allele((False, False, False, False), 'unconnected'),)),
			'(15, 17) NET#lutff_global/cen'
		),
		Gene(
			create_bits(16, 17, ((8, 15), (8, 16), (8, 17), (8, 18), (9, 18))),
			AlleleList((Allele((False, False, False, False, False), 'unconnected'),)),
			'(16, 17) NET#local_g2_1'
		),
		Gene(
			create_bits(16, 17, ((4, 0), (4, 1), (5, 0), (5, 1))),
			AlleleList((Allele((False, False, False, False), 'unconnected'), )),
			'(16, 17) NET#lutff_global/cen'
		)
	], # constant
	[
		IndexedItem((IcecraftBitPosition(15, 24, 9, 7), ), 'ColBufCtrl', 0),
		IndexedItem((IcecraftBitPosition(16, 24, 9, 7), ), 'ColBufCtrl', 0)
	], # colbufctrl
	(IcecraftLUTPosition(16, 18, 5), ) # output
) # end of EXP_REP
