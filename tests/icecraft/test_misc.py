import unittest

from adapters.icecraft import IcecraftPosition, IcecraftBitPosition, IcecraftLUTPosition,\
IcecraftColBufCtrl, IcecraftNetPosition, IcecraftConnection

class IcecraftPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = IcecraftPosition(12, 4)
	
	def test_tile(self):
		dut = IcecraftPosition(12, 4)
		self.assertEqual(dut, dut.tile)
	
	def test_from_tile(self):
		x = 3
		y = 4
		
		dut = IcecraftPosition.from_tile(IcecraftPosition(x, y))
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)

class IcecraftBitPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = IcecraftBitPosition(1, 2, 3, 4)
	
	def check_values(self, dut, x, y, group, index):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(group, dut.group)
		self.assertEqual(index, dut.index)
		self.assertEqual((x, y, group, index), dut.to_ints())
	
	def test_values(self):
		x = 3
		y = 4
		group = 5
		index = 6
		
		dut = IcecraftBitPosition(x, y, group, index)
		self.check_values(dut, x, y, group, index)
	
	def test_from_tile(self):
		x = 3
		y = 4
		group = 5
		index = 6
		
		dut = IcecraftBitPosition.from_tile(IcecraftPosition(x, y), group, index)
		self.check_values(dut, x, y, group, index)

class IcecraftLUTPositionTest(unittest.TestCase):
	dut_cls = IcecraftLUTPosition
	
	def test_creation(self):
		dut = self.dut_cls(1, 2, 3)
	
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
		
		dut = self.dut_cls(x, y, z)
		self.check_values(dut, x, y, z)
	
	def test_from_tile(self):
		x = 3
		y = 4
		z = 5
		
		dut = self.dut_cls.from_tile(IcecraftPosition(x, y), z)
		self.check_values(dut, x, y, z)

class IcecraftColBufCtrlTest(IcecraftLUTPositionTest):
	dut_cls = IcecraftColBufCtrl

class IcecraftNetPositionTest(unittest.TestCase):
	def test_creation(self):
		dut = IcecraftNetPosition(1, 2, "test_net")
	
	def check_values(self, dut, x, y, name):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(name, dut.name)
	
	def test_values(self):
		x = 3
		y = 4
		name = "test_net"
		
		dut = IcecraftNetPosition(x, y, name)
		self.check_values(dut, x, y, name)
	
	def test_from_tile(self):
		x = 3
		y = 4
		name = "test_net"
		
		dut = IcecraftNetPosition.from_tile(IcecraftPosition(x, y), name)
		self.check_values(dut, x, y, name)

class IcecraftConnectionTest(unittest.TestCase):
	def test_creation(self):
		dut = IcecraftConnection(5, 1, "net_a", "net_b")
	
	def check_values(self, dut, x, y, src_name, dst_name):
		self.assertEqual(x, dut.tile.x)
		self.assertEqual(y, dut.tile.y)
		self.assertEqual(x, dut.x)
		self.assertEqual(y, dut.y)
		self.assertEqual(src_name, dut.src_name)
		self.assertEqual(dst_name, dut.dst_name)
		self.assertEqual(IcecraftNetPosition(dut.x, dut.y, src_name), dut.src)
		self.assertEqual(IcecraftNetPosition(dut.x, dut.y, dst_name), dut.dst)
	
	def test_values(self):
		x = 9
		y = 2
		src_name = "source_name"
		dst_name = "destination_name"
		
		dut = IcecraftConnection(x, y, src_name, dst_name)
		self.check_values(dut, x, y, src_name, dst_name)
	
	def test_from_tile(self):
		x = 9
		y = 2
		src_name = "source_name"
		dst_name = "destination_name"
		
		dut = IcecraftConnection.from_tile(IcecraftPosition(x, y), src_name, dst_name)
		self.check_values(dut, x, y, src_name, dst_name)
