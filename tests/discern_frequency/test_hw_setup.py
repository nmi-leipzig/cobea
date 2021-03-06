import itertools
import multiprocessing
import os
import platform
import random
import re
import struct
import subprocess
import time

from argparse import Namespace
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import asdict
from serial import Serial, SerialTimeoutException
from serial.tools.list_ports import comports
from unittest import skipIf, TestCase
from unittest.mock import MagicMock, patch

import h5py
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
from adapters.mcu_drv_mtr import MCUDrvMtr
from adapters.parallel_sink import ParallelSink
from adapters.simple_sink import TextfileSink
from adapters.temp_meter import TempMeter
from applications.discern_frequency.action import calibrate, create_preprocessing_mcu, DataCollectionError, remeasure, run, start_temp
from applications.discern_frequency.s_t_comb import lexicographic_combinations
from applications.discern_frequency.hdf5_content import ENTRIES_REMEASURE, ENTRIES_RUN, missing_hdf5_entries,\
	unknown_hdf5_entries
from domain.interfaces import InputData
from domain.request_model import RequestObject
from domain.use_cases import Measure

from .common import del_files

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
	
	def detect_osci_setup(self):
		# osci available
		osci_list = list(usb.core.find(find_all=True, idVendor=0x1ab1, idProduct=0x0588))
		if len(osci_list) != 1:
			raise DetectSetupError()
		
		meter_sn = osci_list[0].serial_number
		
		driver_sn, target_sn = self.detect_fpgas()
		
		return (driver_sn, target_sn, meter_sn)
	
	def detect_mcu_setup(self, baudrate=500000):
		# FPGA target
		sn_list = IcecraftManager.get_present_serial_numbers()
		if len(sn_list) < 1:
			raise DetectSetupError()
		
		sn_list.sort(key=lambda x: x[-3:])
		target_sn = sn_list[0]
		
		drv_mtr_sn = self.detect_drv_mtr(baudrate)
		
		return (drv_mtr_sn, target_sn)
	
	def detect_drv_mtr(self, baudrate=500000):
		# MCU driver and meter
		ports = comports()
		arduino_ports = [p for p in ports if p.manufacturer and p.manufacturer.startswith("Arduino")]
		for port in arduino_ports:
			try:
				with Serial(port=port.device, baudrate=baudrate, timeout=2, write_timeout=2) as arduino:
					arduino.reset_input_buffer()
					arduino.reset_output_buffer()
					
					# Arduino reboots on connecting serial -> wait till reboot is done
					time.sleep(2)
					
					# check if initial data is send
					time.sleep(1)
					init_data = arduino.read(2)
					if len(init_data) != 2:
						continue
					
					init_val = struct.unpack("<h", init_data)[0]
					if init_val >= 1024:
						# initial data should be ADC result so the maximum value is 1023
						continue
					
					return port.serial_number
			except SerialTimeoutException:
				continue
		raise DetectSetupError()
	
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
			driver_sn, target_sn, meter_sn = self.detect_osci_setup()
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
			#self.flash_device(target, "freq_hab.asc", app_path=False)
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
				data = measure_uc(req).measurement
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
	
	def test_drv_mtr_measurement(self):
		baudrate = 500000
		try:
			drv_mtr_sn, target_sn = self.detect_mcu_setup(baudrate)
		except DetectSetupError:
			self.skipTest("Couldn't detect hardware setup.")
		
		idx_to_comb = lexicographic_combinations(5, 5)
		def check_val(comb_index, data):
			self.assertEqual(10, len(data))
			comb = idx_to_comb[comb_index]
			for i in range(10):
				if (comb >> i) & 1:
					self.assertGreater(data[i], 170*256)
				else:
					self.assertLess(data[i], 10*256)
		
		with ExitStack() as stack:
			man = IcecraftManager()
			
			target = man.acquire(target_sn)
			stack.callback(man.release, target)
			
			drv_mtr = MCUDrvMtr(drv_mtr_sn, 10*256, return_format="<h", init_size=2, baudrate=baudrate)
			stack.enter_context(drv_mtr)
			
			measure_uc = Measure(drv_mtr, drv_mtr)
			prep = create_preprocessing_mcu(256)
			
			for hab_asc, check in [
				("freq_hab.asc", check_val),
				("high_hab.asc", lambda i, d: self.assertTrue(all(v>170*256 for v in d))),
				("low_hab.asc", lambda i, d: self.assertTrue(all(v<10*256 for v in d)))
			]:#]:#
				#comb = idx_to_comb[comb_index]
				self.generic_drv_mtr(measure_uc, target, hab_asc, [120], prep, check)
	
	def generic_drv_mtr(self, measure_uc, target, hab_asc, comb_index_list, preprocessing, check):
		req = RequestObject(
			driver_data = InputData([0]),
			measure_timeout = 3,
			retry = 1,
		)
		
		self.flash_device(target, hab_asc, app_path=False)
		
		for comb_index in comb_index_list:
			with self.subTest(hab_asc=hab_asc, comb_index=comb_index):
				req["driver_data"] = InputData([comb_index])
				
				bef = time.perf_counter()
				data = measure_uc(req).measurement
				aft = time.perf_counter()
				#print(f"whole measurement took {aft-bef} s")
				data = preprocessing(data)
				
				print(data)
				if check:
					check(comb_index, data)
		
	
	def run_run(self, hdf5_filename, use_mcu):
		del_files([hdf5_filename])
		
		if use_mcu:
			baudrate = 500000
			try:
				drv_mtr_sn, target_sn = self.detect_mcu_setup(baudrate)
			except DetectSetupError:
				self.skipTest("Couldn't detect hardware setup.")
			
			args = Namespace(
				output = hdf5_filename,
				dummy = False,
				generator = None,
				target = target_sn,
				meter = drv_mtr_sn,
				temperature = None,
				freq_gen_type = "DRVMTR",
				freq_gen = None,
				habitat = os.path.join(self.app_path, "nhabitat.asc"),
				area = [13, 32, 13, 32],
				in_port = ["13", "32", "lft"],
				out_port = ["13", "32", "top"],
				habitat_con = "not specified",
				freq_gen_con = "not specified",
				pop_size = 3,
				generations = 1,
				crossover_prob = 0.7,
				mutation_prob = 0.001756,
				eval_mode = "ALL",
			)
		else:
			try:
				driver_sn, target_sn, meter_sn = self.detect_osci_setup()
			except DetectSetupError:
				self.skipTest("Couldn't detect FPGA hardware setup.")
			
			args = Namespace(
				output = hdf5_filename,
				dummy = False,
				generator = driver_sn,
				target = target_sn,
				meter = meter_sn,
				temperature = None,
				freq_gen_type = "FPGA",
				freq_gen = os.path.join(self.app_path, "freq_gen.asc"),
				habitat = os.path.join(self.app_path, "nhabitat.asc"),
				area = [13, 32, 13, 32],
				in_port = ["13", "32", "lft"],
				out_port = ["13", "32", "top"],
				habitat_con = "not specified",
				freq_gen_con = "not specified",
				pop_size = 3,
				generations = 1,
				crossover_prob = 0.7,
				mutation_prob = 0.001756,
				eval_mode = "ALL",
			)
		
		run(args)
		
		return args
	
	def check_hdf5(self, hdf5_filename, entries):
		with h5py.File(hdf5_filename, "r") as hdf5_file:
			missing = missing_hdf5_entries(hdf5_file, entries)
			self.assertEqual(0, len(missing), f"Missing entries: {missing}")
			unknown = unknown_hdf5_entries(hdf5_file, entries)
			if len(unknown):
				print(f"Warning: unknonw entries {unknown}")
	
	def test_run_fpga(self):
		hdf5_filename = "tmp.test_run_fpga.h5"
		
		self.run_run(hdf5_filename, False)
	
	def test_run_mcu(self):
		hdf5_filename = "tmp.test_run_mcu.h5"
		
		self.run_run(hdf5_filename, True)
	
	def run_remeasure(self, base_name, use_mcu):
		run_filename = f"tmp.{base_name}.run.h5"
		out1_filename = f"tmp.{base_name}.out1.h5"
		out2_filename = f"tmp.{base_name}.out2.h5"
		
		del_files([run_filename, out1_filename, out2_filename])
		
		self.run_run(run_filename, use_mcu)
		
		# check
		self.check_hdf5(run_filename, ENTRIES_RUN)
		
		args = Namespace(
			output = out1_filename,
			dummy = False,
			generator = None,
			target = None,
			meter = None,
			temperature = None,
			freq_gen = None,
			freq_gen_type = None,
			data_file = run_filename,
			index = 3,
			rounds = 2,
			comb_index = None,
		)
		remeasure(args)
		
		# check
		self.check_hdf5(out1_filename, ENTRIES_REMEASURE)
		
		# remeasure the result of remeasure
		args.output = out2_filename
		args.data_file = out1_filename
		args.index = 0
		remeasure(args)
		
		# check
		self.check_hdf5(out2_filename, ENTRIES_REMEASURE)
		
		del_files([run_filename, out1_filename, out2_filename])
	
	def test_remeasure_fpga(self):
		self.run_remeasure("test_remeasure_fpga", False)
	
	def test_remeasure_mcu(self):
		self.run_remeasure("test_remeasure_fpga", True)
	
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
			driver_sn, target_sn, meter_sn = self.detect_osci_setup()
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
					data = measure_uc(req).measurement
				finally:
					man.release(gen)
	
	def check_fpga(self, fpga):
		# flash echo
		self.flash_device(fpga, "echo.asc", app_path=False)

		# prepare test data
		test_data = [[b"\x3f"], [b"\xff"]]
		for part_size, part_count in (list(itertools.product([1, 2, 3, 4, 15, 16], range(1, 3)))
		+ list(itertools.product([32, 1024], (1, 2)))):
			test_data.append([bytes(random.getrandbits(8) for _ in range(part_size)) for _ in range(part_count)])

		# write and read data
		for part_list in test_data:
			part_size = len(part_list[0])
			part_count = len(part_list)
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
			driver_sn, target_sn, meter_sn = self.detect_osci_setup()
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
			driver_sn, target_sn, meter_sn = self.detect_osci_setup()
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
				
				data = measure_uc(req).measurement
				
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

