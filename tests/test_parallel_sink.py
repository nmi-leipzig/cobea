from unittest import TestCase

from adapters.parallel_sink import ParallelSink
from adapters.dummies import DummyDataSink

class ParallelSinkTest(TestCase):
	def test_creation(self):
		dut = ParallelSink(DummyDataSink)
	
	def test_dummy_write(self):
		dut = ParallelSink(DummyDataSink)
		with dut:
			dut.write("bla.bla", {"bla": 4})
