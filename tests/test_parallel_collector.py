import os
import random
import time

from contextlib import ExitStack
from unittest import TestCase

from adapters.dummies import DummyDataSink, DummyDriver, DummyMeter
from adapters.parallel_collector import CollectorDetails, InitDetails, ParallelCollector
from adapters.parallel_sink import ParallelSink
from adapters.simple_sink import TextfileSink
from domain.model import OutputData

from .mocks import MockMeter

class ParallelCollectorTest(TestCase):
	def create_dummy_details(self):
		return CollectorDetails(
			InitDetails(DummyDriver),
			InitDetails(DummyMeter),
			DummyDataSink(),
			0.01,
		)
	
	def test_creation(self):
		det = self.create_dummy_details()
		dut = ParallelCollector(det)
	
	def test_dummy_run(self):
		det = self.create_dummy_details()
		dut = ParallelCollector(det)
		self.assertFalse(dut.is_alive())
		with dut:
			time.sleep(0.1)

			self.assertTrue(dut.is_alive())

	def test_is_collecting(self):
		det = self.create_dummy_details()
		dut = ParallelCollector(det)
		self.assertFalse(dut.is_collecting())
		with dut:
			dut.wait_collecting(0.5)
			self.assertTrue(dut.is_collecting())	
	
	def test_text_run(self):
		meas_data = OutputData([random.randint(0, 255) for _ in range(11)])
		filename = "tmp.ParallelCollectorTest.test_text_run.txt"
		
		with ExitStack() as stack:
			data_sink = stack.enter_context(ParallelSink(TextfileSink, (filename, )))
			det = CollectorDetails(
				InitDetails(DummyDriver),
				InitDetails(MockMeter, (meas_data, 0)),
				data_sink.get_sub(),
				#None,
				0.001,
				"TextTest",
			)
			dut = stack.enter_context(ParallelCollector(det))
			if not dut.wait_collecting(1):
				self.fail("ParallelCollector did not start collecting.")
			time.sleep(0.05)
		
		with open(filename, "r") as res_file:
			time_line = res_file.readline()
			meas_line = res_file.readline()
			c = -1
			for c, line in enumerate(res_file):
				if c%2 == 0:
					self.assertEqual(time_line[:30], line[:30])
				else:
					self.assertEqual(meas_line, line)
			
			self.assertGreater(c, 10)
		
		# clean up
		os.remove(filename)
