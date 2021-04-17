from contextlib import contextmanager
from typing import List, NamedTuple
from unittest import TestCase, skipIf
from unittest.mock import MagicMock

import pyvisa

try:
	import usb.core
except ImportError:
	# instert dummy for finding usb devices that never finds anything
	class usb:
		class core:
			@staticmethod
			def find(*args, **kwargs) -> None:
				return None

from adapters.gear.rigol import OsciDS1102E, SetupCmd, FloatCheck, IntCheck, MultiIntCheck, MultiNoSpace

class SetupCmdTest(TestCase):
	def test_creation(self):
		dut = SetupCmd("log")
	
	def test_from_values(self):
		res = SetupCmd.from_values_("log{}", [1, 2], subcmds_=(
			SetupCmd("subcmd", subcmds_=(
				SetupCmd("subsubcmd"), 
			)),
		))
		
		self.assertEqual(2, len(res))
		self.assertEqual("log1", res[0].name_)
		self.assertEqual("log2", res[1].name_)
		# change value to avoid false positive test, caused by value based comparison
		res[0].subcmd.name_="othername"
		subsubcmd_list = [None]*len(res)
		for i, cmd in enumerate(res):
			for subcmd in cmd.subcmds_:
				self.assertEqual(cmd, subcmd.parent_)
				for subsubcmd in subcmd.subcmds_:
					self.assertEqual(subcmd, subsubcmd.parent_)
					subsubcmd_list[i] = subsubcmd
		
		self.assertEqual(subsubcmd_list[0].cmd_(full=False), ":log1:othername:subsubcmd")
		self.assertEqual(subsubcmd_list[1].cmd_(full=False), ":log2:subcmd:subsubcmd")
	
	def test_subcommands(self):
		sub_dut = SetupCmd("subcmd")
		dut = SetupCmd("cmd", subcmds_=(sub_dut, ))
		
		self.assertIn(sub_dut, dut.subcmds_)
		self.assertEqual(dut, sub_dut.parent_)
		self.assertEqual(sub_dut, dut.subcmd)
	
	def test_cmd(self):
		dut = SetupCmd("cmd", [1, 2, 3], 2)
		res = dut.cmd_()
		self.assertEqual(":cmd 2", res)

class FloatCheckTest(TestCase):
	def test_creation(self):
		dut = FloatCheck()
	
	def test_contains(self):
		dut = FloatCheck()
		
		for val in [1, 0, -5.3]:
			with self.subTest(val=val):
				self.assertTrue(val in dut)
		
		for val in ["NAN", "TWO"]:
			with self.subTest(val=val):
				self.assertFalse(val in dut)

class IntCheckTest(TestCase):
	def test_creation(self):
		dut = IntCheck()
	
	def test_contains(self):
		dut = IntCheck()
		
		for val in [1, 0, -5]:
			with self.subTest(val=val):
				self.assertTrue(val in dut)
		
		for val in ["NAN", "TWO", 1.2, -10.3]:
			with self.subTest(val=val):
				self.assertFalse(val in dut)

class MultiNoSpaceTest(TestCase):
	def test_creation(self):
		dut1 = MultiNoSpace()
		dut2 = MultiNoSpace([1])
		dut3 = MultiNoSpace([1, 4, -10])
	
	def test_str(self):
		dut = MultiNoSpace([1, 4, -10])
		self.assertEqual("1,4,-10", str(dut))

class MultiIntCheckTest(TestCase):
	def test_creation(self):
		dut = MultiIntCheck(4)
	
	def test_contains(self):
		dut = MultiIntCheck(2)
		
		for val in [MultiNoSpace([1, -5]), MultiNoSpace([0, 0])]:
			with self.subTest(val=val):
				self.assertTrue(val in dut)
		
		for val in [(1, 2), 2, 1.2, [7, 9]]:
			with self.subTest(val=val):
				self.assertFalse(val in dut)

class OsciDS1102ETest(TestCase):
	def test_creation(self):
		dut = OsciDS1102E()
	
	def check_dev_str(self, dev_str):
		"""check device string and return serial number"""
		
		parts = dev_str.split("::")
		self.assertEqual("6833", parts[1])
		self.assertEqual("1416", parts[2])
		
		return parts[3]
	
	@skipIf(usb.core.find(idVendor=0x1ab1, idProduct=0x0588) is None, "No oscilloscope found")
	def test_find_instrument(self):
		res_man = pyvisa.ResourceManager()
		
		try:
			dev_str = OsciDS1102E.find_instrument(res_man)
		except IOError:
			self.fail("Failed to find oscilloscope")
		
		
		serial_no = self.check_dev_str(dev_str)
		
		try:
			dev_str = OsciDS1102E.find_instrument(res_man, serial_no)
		except IOError:
			self.fail("Failed to find oscilloscope")
		
		res = self.check_dev_str(dev_str)
		self.assertEqual(serial_no, res)
		
		res_man.close()
	
	def test_apply(self):
		class ApplyData(NamedTuple):
			desc: str
			setup: SetupCmd
			writes: List[str]
		
		sub_cases = [
			ApplyData("no value, no subcommand", SetupCmd("NO"), []),
			ApplyData("value, no subcommand", SetupCmd("VAL", ("YES", "NO"), "YES"), [":VAL YES"]),
			ApplyData(
				"no value, subcommand",
				SetupCmd("SUP", subcmds_=(SetupCmd("SUB1", ("YES", "NO"), "YES"), )),
				[":SUP:SUB1 YES"]
			),
			ApplyData(
				"value, subcommand",
				SetupCmd("SUP", ("ON", "OFF"), "OFF", (SetupCmd("SUB1", ("YES", "NO"), "YES"), )),
				[":SUP OFF", ":SUP:SUB1 YES"]
			),
		]
		
		for tc in sub_cases:
			with self.subTest(desc=tc.desc):
				mock_osci = MagicMock()
				
				OsciDS1102E.apply(mock_osci, tc.setup)
				
				call_iter = mock_osci.mock_calls
				self.assertEqual(len(tc.writes), len(call_iter))
				for exp, (name, args, kwargs) in zip(tc.writes, call_iter):
					self.assertEqual("write", name)
					self.assertEqual((exp, ), args)
					self.assertEqual(kwargs, {})
		
	
	@contextmanager
	def get_osci(self):
		res_man = pyvisa.ResourceManager()
		dev_str = OsciDS1102E.find_instrument(res_man)
		osci = res_man.open_resource(dev_str)
		
		try:
			yield osci
		finally:
			osci.close()
			res_man.close()
	
	@skipIf(usb.core.find(idVendor=0x1ab1, idProduct=0x0588) is None, "No oscilloscope found")
	def test_set_up_instrument(self):
		with self.get_osci() as osci:
			OsciDS1102E.set_up_instrument(osci, None)
	
	def test_create_setup(self):
		dut = OsciDS1102E.create_setup()
		
		dut.ACQ.MEMD.value_ = "NORM"
		self.assertEqual(":ACQ:MEMD NORM", dut.ACQ.MEMD.cmd_())
		
		self.assertEqual(":TRIG:EDGE:SWE SING", dut.TRIG.EDGE.SWE.cmd_())
	
	def query_all(self, osci, setup):
		if setup.values_ is not None:
			query = setup.cmd_(write=False)
			with self.subTest(query=query):
				try:
					res = osci.query(query)
				except:
					self.fail()
		
		for subcmd in setup.subcmds_:
			self.query_all(osci, subcmd)
	
	@skipIf(usb.core.find(idVendor=0x1ab1, idProduct=0x0588) is None, "No oscilloscope found")
	def test_create_setup_with_hardware(self):
		dut = OsciDS1102E.create_setup()
		
		with self.get_osci() as osci:
			self.query_all(osci, dut)
