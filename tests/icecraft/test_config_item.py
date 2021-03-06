#!/usr/bin/env python3

import unittest

import adapters.icecraft.config_item as config_item
from adapters.icecraft import IcecraftBitPosition

class ConfigItemTest(unittest.TestCase):
	dut_class = config_item.ConfigItem
	test_data = (
		((IcecraftBitPosition(3, 4, 6, 7), ), "config_kind"),
		((IcecraftBitPosition(3, 4, 6, 8), ), "other_kind"),
	)
	
	def create(self, data):
		return self.dut_class(*data)
	
	def test_creation(self):
		dut = self.create(self.test_data[0])
	
	def test_values(self):
		bits, kind = self.test_data[0]
		
		dut = config_item.ConfigItem(bits, kind)
		
		self.assertEqual(bits, dut.bits)
		self.assertEqual(kind, dut.kind)
	
	def test_identifier(self):
		duts = [self.create(d) for d in self.test_data]
		duts.append(self.create(self.test_data[0]))
		
		with self.subTest(desc="is str"):
			for dut in duts:
				self.assertTrue(isinstance(dut.identifier, str))
		
		with self.subTest(desc="same for same values"):
			self.assertEqual(duts[0].identifier, duts[-1].identifier)
		
		with self.subTest(desc="different for different values"):
			self.assertNotEqual(duts[0].identifier, duts[1].identifier)

class IndexedItemTest(ConfigItemTest):
	dut_class = config_item.IndexedItem
	test_data = (
		((IcecraftBitPosition(3, 4, 6, 7), ), "indexed_kind", 6),
		((IcecraftBitPosition(3, 4, 6, 8), ), "other_kind", 1),
	)
	
	def test_values(self):
		bits, kind, index = self.test_data[0]
		
		dut = config_item.IndexedItem(bits, kind, index)
		
		self.assertEqual(bits, dut.bits)
		self.assertEqual(kind, dut.kind)
		self.assertEqual(index, dut.index)

class ConnectionItemTest(ConfigItemTest):
	dut_class = config_item.ConnectionItem
	test_data = (
		(
			(IcecraftBitPosition(3, 4, 6, 7), IcecraftBitPosition(3, 4, 6, 8)),
			"connection",
			"one_net",
			((True, False), (True, True)),
			("src_net_one", "src_net_two")
		),
		(
			(IcecraftBitPosition(3, 4, 7, 7), IcecraftBitPosition(3, 4, 7, 8)),
			"connection",
			"two_net",
			((True, False), (True, True)),
			("src_net_one", "src_net_two")
		),
	)
	
	def test_post_init_checks(self):
		with self.subTest(desc="less values than sources"):
			data = list(self.test_data[0])
			data[3] = data[3][:1]
			with self.assertRaises(AssertionError):
				self.dut_class(*data)
		
		with self.subTest(desc="wrong values length"):
			data = list(self.test_data[0])
			data[3] = (data[3][0], data[3][1][:1])
			with self.assertRaises(AssertionError):
				self.dut_class(*data)
	
	def test_values(self):
		bits, kind, dst_net, values, src_nets = self.test_data[0]
		
		dut = config_item.ConnectionItem(bits, kind, dst_net, values, src_nets)
		
		self.assertEqual(bits, dut.bits)
		self.assertEqual(kind, dut.kind)
		self.assertEqual(dst_net, dut.dst_net)
		self.assertEqual(values, dut.values)
		self.assertEqual(src_nets, dut.src_nets)

class NamedItemTest(ConfigItemTest):
	dut_class = config_item.NamedItem
	test_data = (
		(
			(IcecraftBitPosition(3, 4, 6, 7), ),
			"NamedKind",
			"KIND_NAME"
		),
		(
			(IcecraftBitPosition(3, 4, 6, 8), ),
			"NamedKind",
			"OTHER_NAME"
		),
	)
	
	def test_values(self):
		bits, kind, name = self.test_data[0]
		
		dut = self.create(self.test_data[0])
		
		self.assertEqual(bits, dut.bits)
		self.assertEqual(kind, dut.kind)
		self.assertEqual(name, dut.name)
