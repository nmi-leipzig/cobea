import itertools
import multiprocessing
import os
import platform
import random
import re
import subprocess
import time

from collections import defaultdict
from contextlib import ExitStack
from dataclasses import asdict
from unittest import skipIf, TestCase
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt
import numpy as np

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
from adapters.parallel_sink import ParallelSink
from adapters.simple_sink import TextfileSink
from adapters.temp_meter import TempMeter
from applications.discern_frequency.action import calibrate, DataCollectionError, start_temp
from applications.discern_frequency.s_t_comb import lexicographic_combinations
from domain.interfaces import InputData
from domain.request_model import RequestObject
from domain.use_cases import Measure

class DetectSetupError(Exception):
	pass

class HWSetupTest(TestCase):
	def setUp(self):
		self.app_path = os.path.dirname(os.path.abspath(applications.discern_frequency.__file__))
		self.local_path = os.path.dirname(os.path.abspath(__file__))
	
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
		setup.TIM.OFFS.value_ = 2.5
		
		setup.TRIG.MODE.value_ = "EDGE"
		setup.TRIG.EDGE.SOUR.value_ = "CHAN2"
		setup.TRIG.EDGE.SLOP.value_ = "POS"#"NEG"#
		setup.TRIG.EDGE.SWE.value_ = "SING"
		setup.TRIG.EDGE.COUP.value_ = "DC"
		setup.TRIG.EDGE.LEV.value_ = 1.5
		
		#setup.WAV.POIN.MODE.value_ = "NOR"
		
		return setup
	
	def detect_fpgas(self):
		# return driver_sn, target_sn
		
		# two FPGAs available
		sn_list = IcecraftManager.get_present_serial_numbers()
		if len(sn_list) != 2:
			raise DetectSetupError()
		
		# check which FPGA is the drive and which is the target
		# for the moment just assume the one with the lower last 3 three digits is the target
		if sn_list[0][-3:] < sn_list[1][-3:]:
			return sn_list[1], sn_list[0]
		else:
			return sn_list[0], sn_list[1]
	
	def detect_setup(self):
		# osci available
		osci_list = list(usb.core.find(find_all=True, idVendor=0x1ab1, idProduct=0x0588))
		if len(osci_list) != 1:
			raise DetectSetupError()
		
		meter_sn = osci_list[0].serial_number
		
		driver_sn, target_sn = self.detect_fpgas()
		
		return (driver_sn, target_sn, meter_sn)
	
	def flash_device(self, dev, asc_filename, app_path=True):
		if app_path:
			asc_path = os.path.join(self.app_path, asc_filename)
		else:
			asc_path = os.path.join(self.local_path, asc_filename)
		
		config = IcecraftRawConfig.create_from_filename(asc_path)
		dev.configure(config)
	
	def show_data(self, data, fft=False, trig_len=None):
		fig, ax = plt.subplots(6, 2, sharex=True, sharey=True)
		ax = ax.flatten()
		if trig_len is None:
			data_parts = [data[len(data)*i//len(ax):len(data)*(i+1)//len(ax)] for i in range(len(ax))]
		else:
			trig = len(data)//12
			after_trig = data[trig:trig+trig_len]
			after = len(ax) - 2
			data_parts = [data[:trig]] + [
				after_trig[trig_len*i//after:trig_len*(i+1)//after] for i in range(after)
			] + [data[trig+trig_len:]]
		for i, (sub, sub_data) in enumerate(zip(ax, data_parts)):
			
			if fft:
				spec = np.fft.rfft(sub_data)
				sub.plot(np.fft.rfftfreq(len(sub_data)), np.absolute(spec))
				
				m_freq = np.argmax(np.absolute(spec[1:]))+1
				#print(f"{np.fft.rfftfreq(len(sub_data))[m_freq]}: {spec[m_freq]} [{abs(spec[m_freq])}")
			else:
				sub.plot(sub_data)
		
		plt.show()
	
	def print_stats(self, sub_data):
		for sd in sub_data:
			print(f"mean: {np.mean(sd)}")
			print(f"var: {np.var(sd)}")
			print(f"std: {np.std(sd)}")
			print(f"max dev: {max(abs(np.array(sd)-np.mean(sd)))}")
			print()
		
	
	def test_measurement(self):
		try:
			driver_sn, target_sn, meter_sn = self.detect_setup()
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware setup.")
		
		man = IcecraftManager()
		
		idx_to_comb = lexicographic_combinations(5, 5)
		
		too_short = 0
		gen = man.acquire(driver_sn)
		target = man.acquire(target_sn)
		
		meter_setup = self.create_meter_setup()
		meter = OsciDS1102E(meter_setup)
		try:
			self.flash_device(gen, "freq_gen.asc")
			#self.flash_device(gen, "ctr_drv_2_5.asc")
			self.flash_device(target, "dummy_hab.asc")
			#self.flash_device(target, "const_target.asc")
			
			driver = FixedEmbedDriver(gen, "B")
			
			#meter.close()
			#cal_data = calibrate(driver)
			#meter = OsciDS1102E(meter_setup)
		
			measure_uc = Measure(driver, meter)
			
			req = RequestObject(
				driver_data = InputData([0]),
				measure_timeout = 3,
				retry = 1,
			)
			
			for comb_index in [0, 14]:
				comb = idx_to_comb[comb_index]
				#print(f"{comb_index} {comb:010b}")
				req["driver_data"] = InputData([comb_index])
				
				bef = time.perf_counter()
				data = measure_uc(req)
				aft = time.perf_counter()
				print(f"whole measurement took {aft-bef} s")
				if len(data) != 524288:
					print(f"only got {len(data)} bytes")
					too_short += 1
				
				#trig_lev = 1.5
				#nd = np.array(data)
				#rising_at = np.flatnonzero(
				#	((nd[:-1] <= trig_lev) & (nd[1:] > trig_lev)) |
				#	((nd[:-1] >= trig_lev) & (nd[1:] < trig_lev))
				#)+1
				#print(rising_at[1:]-rising_at[:-1])
				#self.show_data(data)
				#self.show_data(data, trig_len=cal_data.trig_len)
				#self.show_data(data, True)
				#self.show_data(data, True, cal_data.trig_len)
				
				
				# split
				sub_data = [data[len(data)*i//12:len(data)*(i+1)//12] for i in range(12)]
				# remove first and last
				sub_data = sub_data[1:11]
				#self.print_stats(sub_data)
				# check fft
				tmp_comb = comb
				for sd in sub_data:
					#nd = np.array(sd)
					fast = tmp_comb & 1
					tmp_comb >>= 1
					
					spec = np.fft.rfft(sd)
					m_index = np.argmax(np.absolute(spec[1:]))+1
					m_freq = np.fft.rfftfreq(len(sd))[m_index]
					
					if fast:
						low = 0.09
						high = 0.12
					else:
						low = 0.009
						high = 0.012
					
					self.assertGreaterEqual(high, m_freq)
					self.assertLessEqual(low, m_freq)
		finally:
			man.release(target)
			man.release(gen)
			meter.close()
		
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
		
		meter = OsciDS1102E(meter_setup, meter_sn)
		
		with meter:
			mp = multiprocessing.get_context("spawn")
			for i in range(3):
				p = mp.Process(target=self.create_and_write, args=(driver_sn, ))
				p.start()
				time.sleep(3)
				p.terminate()
				
				man = IcecraftManager()
				
				man.stuck_workaround(driver_sn)
				
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
	
	def check_fpga(self, fpga):
		# flash echo
		self.flash_device(fpga, "echo.asc", app_path=False)
		
		# write and read data
		for part_size, part_count in (list(itertools.product([1, 2, 3, 4, 15, 16], range(1, 3)))
		+ list(itertools.product([32, 1024], (1, 2)))):
			#print(f"{part_count} x {part_size} bytes")
			part_list = [bytes(random.getrandbits(8) for _ in range(part_size)) for _ in range(part_count)]
			# write parts
			with self.subTest(fpga=fpga.serial_number, part_size=part_size, part_count=part_count, mode="write chunks"):
				fpga.reset()
				for part in part_list:
					write_count = fpga.write_bytes(part)
					self.assertEqual(part_size, write_count)
					
					res = fpga.read_bytes(part_size)
					self.assertEqual(part, res)
			
			# write once
			with self.subTest(part_size=part_size, part_count=part_count, mode="write once"):
				fpga.reset()
				write_count = fpga.write_bytes(b"".join(part_list))
				self.assertEqual(part_size*part_count, write_count)
				for part in part_list:
					res = fpga.read_bytes(part_size)
					self.assertEqual(part, res)
				
	
	def test_fpgas(self):
		try:
			driver_sn, target_sn = self.detect_fpgas()
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware FPGAs.")
		
		man = IcecraftManager()
		man.stuck_workaround(driver_sn)
		man.stuck_workaround(target_sn)
		
		fpgas = []
		fpgas.append(man.acquire(driver_sn))
		fpgas.append(man.acquire(target_sn))
		try:
			for dev in fpgas:
				self.check_fpga(dev)
		finally:
			for dev in fpgas:
				man.release(dev)
	
	def test_calibrate(self):
		try:
			driver_sn, target_sn, meter_sn = self.detect_setup()
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware FPGAs.")
		
		man = IcecraftManager()
		man.stuck_workaround(driver_sn)
		
		gen = man.acquire(driver_sn)
		
		#target = man.acquire(args.target)
		
		self.flash_device(gen, "freq_gen.asc")
		driver = FixedEmbedDriver(gen, "B")
		
		res = calibrate(driver)
		#print(asdict(res))
		
		man.release(gen)
	
	def test_target_out(self):
		# target creates values independant from driver to see quality of output
		try:
			driver_sn, target_sn, meter_sn = self.detect_setup()
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware setup.")
		
		man = IcecraftManager()
		
		idx_to_comb = lexicographic_combinations(5, 5)
		
		target = man.acquire(target_sn)
		
		meter_setup = self.create_meter_setup()
		meter_setup.TRIG.EDGE.SOUR.value_ = "CHAN1"
		meter = OsciDS1102E(meter_setup)
		
		with ExitStack() as stack:
			stack.callback(man.release, target)
			stack.enter_context(meter)
			
			self.flash_device(target, "freq_gen.asc")
			
			
			driver = FixedEmbedDriver(target, "B")
			
			measure_uc = Measure(driver, meter)
			
			req = RequestObject(
				driver_data = InputData([0]),
				measure_timeout = 3,
				retry = 1,
			)
			
			for comb_index in [0]:
				comb = idx_to_comb[comb_index]
				req["driver_data"] = InputData([comb_index])
				
				data = measure_uc(req)
				
				sub_data = [data[len(data)*i//12:len(data)*(i+1)//12] for i in range(12)]
				# remove unused
				sub_data = sub_data[2:]
				#self.print_stats(sub_data)
	
	@skipIf(platform.system()!="Linux", "Linux only")
	def test_temp_lock(self):
		# test if a lock occurs when the temperature sensor doesn't start the measurement
		self.assert_timeout(self.temp_lock_target, 2)
	
	@staticmethod
	def temp_lock_target():
		# mock TempMeter to just block
		with patch("applications.discern_frequency.action.TempMeter", new=BlockMeter):
			with ExitStack() as stack:
				out_filename = "tmp.test_temp_lock.txt"
				sink = ParallelSink(TextfileSink, (out_filename, ))
				
				stack.enter_context(sink)
				
				try:
					start_temp("", stack, sink, 0.1)
				except DataCollectionError:
					pass
	
	def assert_timeout(self, func, timeout, func_args=tuple(), func_kwargs={}):
		ctx = multiprocessing.get_context("spawn")
		pro = ctx.Process(target=func, args=func_args, kwargs=func_kwargs)
		
		pro.start()
		pro.join(timeout)
		
		if pro.is_alive():
			# children seem to be cleaned up, but there are three process left with parent 1, not the current process
			pro.terminate()
			raise AssertionError(f"{func} didn't finish in {timeout} s")
	
	@classmethod
	def get_offspring(cls, pid):
		ppid_pid_map = cls.get_ppid_pid_map()
		res = []
		stack = [pid]
		while stack:
			cur = stack.pop()
			if cur in res:
				continue
			
			stack.extend(ppid_pid_map[cur])
			res.extend(ppid_pid_map[cur])
		
		return res
	
	@staticmethod
	def get_ppid_pid_map():
		ps_out = subprocess.run(["ps", "-o", "pid,ppid"], check=True, stdout=subprocess.PIPE, text=True).stdout
		lines = ps_out.split("\n")[1:]
		ppid_pid_map = defaultdict(list)
		for line in lines:
			res = re.match(r"\s*(?P<pid>\d+)\s+(?P<ppid>\d+)", line)
			if res is None:
				continue
			ppid_pid_map[int(res.group("ppid"))].append(int(res.group("pid")))
		
		return ppid_pid_map

class BlockMeter(TempMeter):
	def __enter__(self) -> "TempMeter":
		# just block
		while True:
			time.sleep(0.5)
		
		# minimum effort to avoid Exceptions
		self._arduino = MagicMock()
		self._arduino.read.return_value = b"\x00\xff"
		self._aruidno_sn = "X"*10
		self._ds18b20_sn = "X"*20
		
		return self

