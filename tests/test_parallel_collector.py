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
	def creats_dummy_details(self):
		return CollectorDetails(
			InitDetails(DummyDriver),
			InitDetails(DummyMeter),
			DummyDataSink(),
			0.01,
		)
	
	def test_creation(self):
		det = self.creats_dummy_details()
		dut = ParallelCollector(det)
	
	def test_dummy_run(self):
		det = self.creats_dummy_details()
		with ParallelCollector(det) as dut:
			time.sleep(0.1)
	
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
			time.sleep(0.1)
		
		with open(filename, "r") as res_file:
			exp = res_file.readline()
			for c, line in enumerate(res_file):
				self.assertEqual(exp, line)
			
			self.assertGreater(c, 5)
		
		# clean up
		os.remove(filename)