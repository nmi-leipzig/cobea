from unittest import TestCase, skipIf

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

from adapters.gear.rigol import OsciDS1102E, SetupCmd

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

class OsciDS1102ETest(TestCase):
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
	
	@skipIf(usb.core.find(idVendor=0x1ab1, idProduct=0x0588) is None, "No oscilloscope found")
	def test_set_up_instrument(self):
		res_man = pyvisa.ResourceManager()
		dev_str = OsciDS1102E.find_instrument(res_man)
		osci = res_man.open_resource(dev_str)
		
		OsciDS1102E.set_up_instrument(osci, None)
		
		osci.close()
	
	def test_create_setup(self):
		dut = OsciDS1102E.create_setup()
		
		dut.ACQ.MEMD.value_ = "NORM"
		self.assertEqual(":ACQ:MEMD NORM", dut.ACQ.MEMD.cmd_())
		
		self.assertEqual(":TRIG:EDGE:SWE SING", dut.TRIG.EDGE.SWE.cmd_())
