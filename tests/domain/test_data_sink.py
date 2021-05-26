from typing import Iterable, Mapping, NamedTuple
from unittest import TestCase

from domain.data_sink import sink_request, DataSink, DataSinkUser, DoneReq, ReqVal
from domain.request_model import Parameter, ParameterUser, RequestObject, set_req_defaults

from ..mocks import MockDataSink

class SinkRequestTest(TestCase):
	
	def test_wrapping(self):
		def req_func(obj, req: RequestObject) -> None:
			pass
		
		res = sink_request(req_func)
	
	def test_wrapped_call(self):
		# construct an object that has data_sink 
		class DSU(NamedTuple):
			data_sink: DataSink
			parameters: Mapping[str, Iterable[Parameter]]
		
		sink = MockDataSink()
		params = {"req_func": []}
		
		obj = DSU(sink, params)
		
		def req_func(obj, req: RequestObject) -> None:
			pass
		
		dut = sink_request(req_func)
		
		req = RequestObject()
		dut(obj, req)
		
		self.assertEqual(1, len(sink.all_list), "Wrong number of calls to data sink")
		self.assertEqual("req", sink.all_list[0][0])
		done_req = sink.all_map["req"][0]
		self.assertEqual(tuple(), done_req.values)
		self.assertEqual(None, done_req.result)
		self.assertEqual("DSU.req_func", done_req.creator)
		
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
			req = RequestObject(num=num)
			res = dut.sink_req(req)
			self.assertEqual(num, res)
			
			exp = DoneReq((ReqVal("num", num, int, False), ), num, "FullDSU.sink_req")
			self.assertEqual(1, len(sink.all_list), "Wrong number of calls to data sink")
			self.assertEqual([exp], sink.all_map["req"])
		
		with self.subTest(desc="call with sink and default"):
			sink.clear()
			
			base = 3
			req = RequestObject(base=base)
			res = dut.def_sink_req(req)
			self.assertEqual(9, res)
			
			exp = DoneReq(
				(ReqVal("base", base, float, False), ReqVal("power", 2, int, False)),
				9,
				"FullDSU.def_sink_req"
			)
			self.assertEqual(1, len(sink.all_list), "Wrong number of calls to data sink")
			self.assertEqual([exp], sink.all_map["req"])
			
			power = 4
			req = RequestObject(base=base, power=power)
			res = dut.def_sink_req(req)
			self.assertEqual(81, res)
			
			exp2 = DoneReq(
				(ReqVal("base", base, float, False), ReqVal("power", 4, int, False)),
				81,
				"FullDSU.def_sink_req"
			)
			self.assertEqual(2, len(sink.all_list), "Wrong number of calls to data sink")
			self.assertEqual([exp, exp2], sink.all_map["req"])
		
		with self.subTest(desc="sink is None"):
			dut_none = FullDSU(None)
			
			base = 7
			req = RequestObject(base=base)
			res = dut_none.def_sink_req(req)
			self.assertEqual(49, res)
			

