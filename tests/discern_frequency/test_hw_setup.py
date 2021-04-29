import multiprocessing
import os
import time

from unittest import TestCase

try:
	import usb.core
except ImportError:
	# instert dummy for finding usb devices that never finds anything
	class usb:
		class core:
			@staticmethod
			def find(*args, **kwargs) -> None:
				try:
					if kwargs["find_all"]:
						return []
				except KeyError:
					pass
				return None

import applications.discern_frequency

from adapters.icecraft import IcecraftManager
from adapters.embed_driver import FixedEmbedDriver
from adapters.gear.rigol import OsciDS1102E
from adapters.icecraft import IcecraftManager, IcecraftRawConfig
from domain.interfaces import InputData
from domain.request_model import RequestObject
from domain.use_cases import Measure

class DetectSetupError(Exception):
	pass

class HWSetupTest(TestCase):
	def setUp(self):
		self.asc_path = os.path.dirname(os.path.abspath(applications.discern_frequency.__file__))
	
	def create_meter_setup(self):
		setup = OsciDS1102E.create_setup()
		setup.CHAN1.DISP.value_ = "ON"
		setup.CHAN1.PROB.value_ = 10
		setup.CHAN1.SCAL.value_ = 1
		setup.CHAN1.OFFS.value_ = 0
		
		setup.CHAN2.DISP.value_ = "ON"#"OFF"#
		setup.CHAN2.PROB.value_ = 1
		setup.CHAN2.SCAL.value_ = 1
		
		setup.ACQ.MEMD.value_ = "LONG"
		setup.ACQ.TYPE.value_ = "NORM"
		setup.ACQ.MODE.value_ = "RTIM"
		
		setup.TIM.SCAL.value_ = 0.5
		setup.TIM.OFFS.value_ = 2
		
		setup.TRIG.MODE.value_ = "EDGE"
		setup.TRIG.EDGE.SOUR.value_ = "CHAN2"
		setup.TRIG.EDGE.SLOP.value_ = "POS"#"NEG"#
		setup.TRIG.EDGE.SWE.value_ = "SING"
		setup.TRIG.EDGE.COUP.value_ = "DC"
		setup.TRIG.EDGE.LEV.value_ = 1.5
		
		#setup.WAV.POIN.MODE.value_ = "NOR"
		
		return setup
	
	def detect_setup(self):
		# osci available
		osci_list = list(usb.core.find(find_all=True, idVendor=0x1ab1, idProduct=0x0588))
		if len(osci_list) != 1:
			raise DetectSetupError()
		
		meter_sn = osci_list[0].serial_number
		
		# two FPGAs available
		sn_list = IcecraftManager.get_present_serial_numbers()
		if len(sn_list) != 2:
			raise DetectSetupError()
		
		# check which FPGA is the drive and which is the target
		# for the moment just assume the one with the lower last 3 three digits is the target
		if sn_list[0][-3:] < sn_list[1][-3:]:
			target_sn = sn_list[0]
			driver_sn = sn_list[1]
		else:
			target_sn = sn_list[1]
			driver_sn = sn_list[0]
		
		return (driver_sn, target_sn, meter_sn)
	
	def flash_device(self, dev, asc_filename):
		config = IcecraftRawConfig.create_from_file(os.path.join(self.asc_path, asc_filename))
		dev.configure(config)
	
	def test_measurement(self):
		try:
			driver_sn, target_sn, meter_sn = self.detect_setup()
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware setup.")
		
		man = IcecraftManager()
		
		too_short = 0
		gen = man.acquire(driver_sn)
		target = man.acquire(target_sn)
		try:
			self.flash_device(gen, "freq_gen.asc")
			self.flash_device(target, "dummy_hab.asc")
			
			meter_setup = self.create_meter_setup()
			meter = OsciDS1102E(meter_setup)
			
			driver = FixedEmbedDriver(gen, "B")
		
			measure_uc = Measure(driver, meter)
			
			req = RequestObject(
				driver_data = InputData([0]),
				measure_timeout = None,
				retry = 0,
			)
			
			for _ in range(10):
				data = measure_uc(req)
				if len(data) != 524288:
					print(f"only got {len(data)} bytes")
					too_short += 1
		finally:
			man.release(target)
			man.release(gen)
		
		self.assertEqual(0, too_short)
	
	@staticmethod
	def create_and_write(driver_sn):
		#print("start")
		man = IcecraftManager()
		gen = man.acquire(driver_sn)
		try:
			# send command that should be invalid
			#print("start write")
			gen.write_bytes(b"\xff\xff"*1000000)
			#print("end write")
		finally:
			man.release(gen)
		#print("end")
	
	def test_blocked_buffer(self):
		try:
			driver_sn, target_sn, meter_sn = self.detect_setup()
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware setup.")
		
		meter_setup = self.create_meter_setup()
		meter_setup.TIM.SCAL.value_ = 0.05
		meter_setup.TIM.OFFS.value_ = 3*meter_setup.TIM.SCAL.value_
		
		meter = OsciDS1102E(meter_setup)
		
		mp = multiprocessing.get_context("spawn")
		for i in range(3):
			p = mp.Process(target=self.create_and_write, args=(driver_sn, ))
			p.start()
			time.sleep(3)
			p.terminate()
			
			man = IcecraftManager()
			
			gen = man.acquire(driver_sn)
			try:
				# flash trigger
				self.flash_device(gen, "freq_gen.asc")
				#time.sleep(7)
				
				driver = FixedEmbedDriver(gen, "B")
				print("start measure")
				measure_uc = Measure(driver, meter)
				
				req = RequestObject(
					driver_data = InputData([0]),
					retry = 3,
					measure_timeout = 3,
				)
				data = measure_uc(req)
			finally:
				man.release(gen)
