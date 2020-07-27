import unittest

import adapters.icecraft as icecraft


class IcecraftBitPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = icecraft.IcecraftBitPosition(icecraft.TilePosition(1, 2), 3, 4)
	
	def check_values(self, dut, x, y, group, index):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(group, dut.group)
		self.assertEqual(index, dut.index)
	
	def test_values(self):
		x = 3
		y = 4
		group = 5
		index = 6
		
		dut = icecraft.IcecraftBitPosition(icecraft.TilePosition(x, y), group, index)
		self.check_values(dut, x, y, group, index)
	
	def test_from_coords(self):
		x = 3
		y = 4
		group = 5
		index = 6
		
		dut = icecraft.IcecraftBitPosition.from_coords(x, y, group, index)
		self.check_values(dut, x, y, group, index)
		

class IcecraftLUTPositionTest(unittest.TestCase):
	dut_cls = icecraft.IcecraftLUTPosition
	
	def test_creation(self):
		dut = self.dut_cls(icecraft.TilePosition(1, 2), 3)
	
	def check_values(self, dut, x, y, z):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(z, dut.z)
	
	def test_values(self):
		x = 3
		y = 4
		z = 5
		
		dut = self.dut_cls(icecraft.TilePosition(x, y), z)
		self.check_values(dut, x, y, z)
	
	def test_from_coords(self):
		x = 3
		y = 4
		z = 5
		
		dut = self.dut_cls.from_coords(x, y, z)
		self.check_values(dut, x, y, z)
	


class IcecraftColBufCtrlTest(IcecraftLUTPositionTest):
	dut_cls = icecraft.IcecraftColBufCtrl

class IcecraftNetPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = icecraft.IcecraftNetPosition(icecraft.TilePosition(1, 2), "test_net")
	
	def check_values(self, dut, x, y, net):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(net, dut.net)
	
	def test_values(self):
		x = 3
		y = 4
		net = "test_net"
		
		dut = icecraft.IcecraftNetPosition(icecraft.TilePosition(x, y), net)
		self.check_values(dut, x, y, net)
	
	def test_from_coords(self):
		x = 3
		y = 4
		net = "test_net"
		
		dut = icecraft.IcecraftNetPosition.from_coords(x, y, net)
		self.check_values(dut, x, y, net)
		

