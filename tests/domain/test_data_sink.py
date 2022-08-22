from dataclasses import dataclass
from typing import Iterable, Mapping
from unittest import TestCase

from domain.data_sink import sink_request, DataSink, DataSinkUser
from domain.request_model import Parameter, ParameterUser, RequestObject, set_req_defaults

from tests.mocks import MockDataSink

class SinkRequestTest(TestCase):
	
	def test_wrapping(self):
		def req_func(obj, req: RequestObject) -> None:
			pass
		
		res = sink_request(req_func)
	
	def test_wrapped_call(self):
		# construct an object that has data_sink 
		@dataclass
		class DSU(DataSinkUser):
			sink: DataSink
			parameters: Mapping[str, Iterable[Parameter]]
			
			@property
			def data_sink(self) -> DataSink:
				return self.sink
		
		sink = MockDataSink()
		params = {"req_func": []}
		
		obj = DSU(sink, params)
		
		def req_func(obj, req: RequestObject) -> None:
			pass
		
		dut = sink_request(req_func)
		
		req = RequestObject()
		dut(obj, req)
		
		self.assertEqual(1, len(sink.write_list), "Wrong number of calls to data sink")
		source, values = sink.write_list[0]
		self.assertEqual({"return": None}, values)
		self.assertEqual("DSU.req_func", source)
		
		# test None as sink
		obj = DSU(None, params)
		dut(obj, req)
	
	def test_full_class(self):
		class FullDSU(ParameterUser, DataSinkUser):
			def __init__(self, data_sink: DataSink) -> None:
				self._data_sink = data_sink
			
			@property
			def data_sink(self) -> DataSink:
				return self._data_sink
			
			@property
			def parameters(self) -> Mapping[str, Iterable[Parameter]]:
				return {
					"sink_req": [Parameter("num", int)],
					"def_sink_req": [Parameter("base", float), Parameter("power", int, 2)],
				}
			
			@sink_request
			def sink_req(self, req: RequestObject) -> int:
				return req.num
			
			@set_req_defaults
			@sink_request
			def def_sink_req(self, req: RequestObject) -> float:
				return req.base**req.power
		
		sink = MockDataSink()
		dut = FullDSU(sink)
		
		with self.subTest(desc="call with sink"):
			sink.clear()
			
			num = 5
			other = "abc"
			req = RequestObject(num=num, other=other)
			res = dut.sink_req(req)
			self.assertEqual(num, res)
			
			exp = ("FullDSU.sink_req", {"num": num, "other": other, "return": num})
			self.assertEqual(1, len(sink.write_list), "Wrong number of calls to data sink")
			self.assertEqual([exp], sink.write_list)
		
		with self.subTest(desc="call with sink and default"):
			sink.clear()
			
			base = 3
			req = RequestObject(base=base)
			res = dut.def_sink_req(req)
			self.assertEqual(9, res)
			
			exp = ("FullDSU.def_sink_req", {"base": base, "power": 2, "return": 9})
			self.assertEqual(1, len(sink.write_list), "Wrong number of calls to data sink")
			self.assertEqual([exp], sink.write_list)
			
			power = 4
			req = RequestObject(base=base, power=power)
			res = dut.def_sink_req(req)
			self.assertEqual(81, res)
			
			exp2 = ("FullDSU.def_sink_req", {"base": base, "power": 4, "return": 81})
			self.assertEqual(2, len(sink.write_list), "Wrong number of calls to data sink")
			self.assertEqual([exp, exp2], sink.write_list)
		
		with self.subTest(desc="sink is None"):
			dut_none = FullDSU(None)
			
			base = 7
			req = RequestObject(base=base)
			res = dut_none.def_sink_req(req)
			self.assertEqual(49, res)
			

