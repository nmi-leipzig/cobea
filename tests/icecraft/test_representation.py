import unittest

import adapters.icecraft as icecraft
from adapters.icecraft.representation import NetRelation
from domain.request_model import RequestObject
from adapters.icecraft.chip_data_utils import NetData

from ..test_request_model import check_parameter_user

class IcecraftRepGenTest(unittest.TestCase):
	raw_nets = [
		NetData(((2, 3, "internal"), ), False, (0,)),
		NetData(((0, 3, "right"), (1, 3, "out"), (2, 3, "left")), True, (1, )),
		NetData(((1, 3, "wire_in"), (2, 3, "wire_out")), False, (0, )),
	]
	
	def create_net_relations(self):
		return [icecraft.representation.NetRelation(n) for n in self.raw_nets]
	
	def test_creation(self):
		dut = icecraft.IcecraftRepGen()
	
	def test_call(self):
		dut = icecraft.IcecraftRepGen()
		req = RequestObject()
		req["x_min"] = 2
		req["y_min"] = 2
		req["x_max"] = 2
		req["y_max"] = 2
		req["exclude_nets"] = ["sp4", "sp12", "glb_netwk"]
		req["include_nets"] = []
		req["output_lutffs"] = [icecraft.IcecraftLUTPosition.from_coords(2, 2, 2)]
		req["joint_input_nets"] = []
		req["lone_input_nets"] = []
		req["lut_functions"] = [icecraft.LUTFunction.NAND, icecraft.LUTFunction.AND]
		
		dut(req)
	
	def parse_gene(self, raw_gene, desc=""):
		tile = icecraft.TilePosition(*raw_gene[0])
		
		bit_pos = []
		for raw_bit in raw_gene[1]:
			bit_pos.append(icecraft.IcecraftBitPosition(tile, *raw_bit))
		
		raw_alleles = raw_gene[2]
		if raw_alleles == []:
			alleles = model.AlleleAll(len(bit_pos))
		else:
			tmp_alleles = []
			for j, raw_allele in enumerate(raw_alleles):
				tmp_alleles.append(model.Allele(raw_allele, f"allele {j}"))
			
			alleles = model.AlleleList(tmp_alleles)
		
		return model.Gene(tuple(bit_pos), alleles, desc)
	
	@unittest.skip
	def test_correct_rep(self):
		with open(os.path.join(TEST_DATA_DIR, "rep_creation.json"), "r") as json_file:
			raw_test_data = json.load(json_file)
		dut = icecraft.IcecraftRepGen()
		
		for raw_test in raw_test_data:
			with self.subTest():
				# read test data and create request
				req = RequestObject()
				req["x_min"] = raw_test[0]
				req["y_min"] = raw_test[1]
				req["x_max"] = raw_test[2]
				req["y_max"] = raw_test[3]
				req["exclude_nets"] = [v for v, d in raw_test[4]]
				req["include_nets"] = [v for v, d in raw_test[5]]
				output = [icecraft.IcecraftLUTPosition.from_coords(*c) for c in raw_test[6]]
				req["output_lutffs"] = list(output)
				req["joint_input_nets"] = raw_test[7]
				req["lone_input_nets"] = raw_test[8]
				req["lut_functions"] = [icecraft.LUTFunction[s] for s in raw_test[9]]
				
				genes = []
				
				for i, raw_gene in enumerate(raw_test[10]):
					genes.append(self.parse_gene(raw_gene, f"gene {i}"))
				
				const_bits = []
				for i, raw_const in enumerate(raw_test[11]):
					const_bits.append(self.parse_gene(raw_const, f"const {i}"))
				
				used_colbufctrl = []
				for raw_ctrl in raw_test[12]:
					used_colbufctrl.append(icecraft.IcecraftColBufCtrl.from_coords(*raw_ctrl))
				
				# call DUT
				rep = dut(req)
				
				# check representation
				self.assertEqual(set(genes), set(rep.genes))
				self.assertEqual(set(const_bits), set(constant))
				self.assertEqual(set(used_colbufctrl), set(rep.colbufctrl))
				self.assertEqual(set(output), set(rep.output))
				
		
	
	def test_parameter_user(self):
		rep_gen = icecraft.IcecraftRepGen()
		check_parameter_user(self, rep_gen)
	
	def test_tiles_from_rectangle(self):
		test_data = (
			((2, 2, 2, 2), [(2, 2)]), # single tile
			((3, 5, 7, 5), [(3, 5), (4, 5), (5, 5), (6, 5), (7, 5)]), # row
			((7, 9, 7, 13), [(7, 9), (7, 10), (7, 11), (7, 12), (7, 13)]), # colum
			((4, 6, 5, 7), [(4, 6), (4, 7), (5, 6), (5, 7)]), # no inner tile
			((5, 8, 7, 10), [(5, 8), (5, 9), (5, 10), (6, 8), (6, 9), (6, 10), (7, 8), (7, 9), (7, 10)]), # inner tile
		)
		
		for rect, exp in test_data:
			res = icecraft.IcecraftRepGen.tiles_from_rectangle(*rect)
			res_set = set(res)
			
			# no duplicates
			self.assertEqual(len(res), len(res_set))
			
			# correct tiles
			self.assertEqual(set(exp), res_set)
	
	def test_net_map_from_net_relations(self):
		test_input = self.create_net_relations()
		
		res = icecraft.IcecraftRepGen.net_map_from_net_relations(test_input)
		
		# check all net_data in map
		for net_rel in test_input:
			for net_id in net_rel.segment:
				net_res = res[net_id]
				self.assertEqual(net_rel, net_res)
		
		# check consistency
		for net_id, net_res in res.items():
			self.assertIn(net_id, net_res.segment)
			self.assertIn(net_res, test_input)
	
	def check_uniqueness(self, iterable):
		self.assertEqual(len(iterable), len(set(iterable)))
	
	def test_populate_source_groups(self):
		net_relations = self.create_net_relations()
		net_map = icecraft.IcecraftRepGen.net_map_from_net_relations(net_relations)
		
		# left -> internal
		# wire_out -> internal
		# out -> wire_in
		BitPos = icecraft.IcecraftBitPosition
		ConnectionItem = icecraft.config_item.ConnectionItem
		con_configs = [
			ConnectionItem(
				(BitPos.from_coords(2, 3, 7, 0), BitPos.from_coords(2, 3, 7, 1)),
				"connection",
				"internal",
				((True, False), (True, True)),
				("left", "wire_out")
			),
			ConnectionItem(
				(BitPos.from_coords(1, 3, 6, 10), BitPos.from_coords(1, 3, 6, 11)),
				"connection",
				"out",
				((True, False), ),
				("wire_in", )
			),
			
		]
		
		res = icecraft.IcecraftRepGen.populate_source_groups(net_map, con_configs)
		
		res_configs = [s.config_item for s in res]
		self.check_uniqueness(res_configs)
		
		self.assertEqual(set(con_configs), set(res_configs))
		
		with self.subTest(desc="source group to destination"):
			for src_grp in res:
				self.assertIn(src_grp, src_grp.dst.src_grp_list)
		
		with self.subTest(desc="destination to source group"):
			for net_rel in net_relations:
				for src_grp in net_rel.src_grp_list:
					self.assertEqual(net_rel, src_grp.dst)
		
		with self.subTest(desc="source group to source"):
			for src_grp in res:
				for i, src in enumerate(src_grp.src_list):
					self.assertIn((*src_grp.tile, src_grp.config_item.src_nets[i]), src.segment)
					self.assertIn(src_grp, src.dst_grp_list)
		
		with self.subTest(desc="source to source group"):
			for net_rel in net_relations:
				for index, dst_grp in zip(net_rel.dst_indices, net_rel.dst_grp_list):
					self.assertEqual(net_rel, dst_grp.src_list[index])
