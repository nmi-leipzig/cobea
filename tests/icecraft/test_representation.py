import unittest

import adapters.icecraft as icecraft
from domain.request_model import RequestObject

from ..test_request_model import check_parameter_user

class IcecraftRepGenTest(unittest.TestCase):
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
