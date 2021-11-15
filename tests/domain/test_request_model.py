import sys
import unittest


from typing import Any, Mapping, Iterable, NamedTuple, List

from domain.request_model import Parameter, NO_DEFAULT, ParameterValues, ResponseObject, RequestObject, ParameterUser,\
set_req_defaults

from ..common import check_param_def_maps, check_parameter_user

class ParameterTest(unittest.TestCase):
	
	def test_creation_default(self):
		name = "my_param"
		tpe = str
		
		param = Parameter(name, tpe)
		
		self.assertEqual(name, param.name)
		self.assertEqual(tpe, param.data_type)
		self.assertEqual(NO_DEFAULT, param.default)
		self.assertEqual(False, param.multiple)
	
	def test_creation_multiple(self):
		name = "my_param"
		tpe = str
		default = NO_DEFAULT
		multiple = True
		
		param = Parameter(name, tpe, multiple=True)
		
		self.assertEqual(name, param.name)
		self.assertEqual(tpe, param.data_type)
		self.assertEqual(default, param.default)
		self.assertEqual(multiple, param.multiple)
	
	def test_creation_full(self):
		name = "my_param"
		tpe = str
		default = "value"
		multiple = True
		
		param = Parameter(name, tpe, default, multiple)
		
		self.assertEqual(name, param.name)
		self.assertEqual(tpe, param.data_type)
		self.assertEqual(default, param.default)
		self.assertEqual(multiple, param.multiple)
		

class ParameterValuesTest(unittest.TestCase):
	target_cls = ParameterValues
	
	def test_creation(self):
		pv = self.target_cls()
	
	def test_initial_values(self):
		f_val = 4
		s_val = "2"
		pv = self.target_cls(first_val=f_val, second_val=s_val)
		self.assertIn("first_val", pv)
		self.assertIn("second_val", pv)
		self.assertEqual(pv["first_val"], f_val)
		self.assertEqual(pv["second_val"], s_val)
	
	def test_attr_access(self):
		pv = self.target_cls()
		val = 38
		pv["val_name"] = val
		self.assertEqual(pv.val_name, val)

class RequestObjectTest(ParameterValuesTest):
	target_cls = RequestObject

class ResponseObjectTest(ParameterValuesTest):
	target_cls = ResponseObject

class ParameterUserTest(unittest.TestCase):
	class PUImpl(ParameterUser):
		def __init__(self, params=None):
			if params is None:
				params = {}
			self._params = params
		
		@property
		def parameters(self) -> Mapping[str, Iterable[Parameter]]:
			return self._params
		
		def take_request(self, request: RequestObject) -> int:
			return request.some_val**2
		
		@set_req_defaults
		def take_with_default(self, request: RequestObject) -> str:
			return request.def_val
	
	def setUp(self):
		self.params = {
			"take_request": (Parameter("some_val", int, 2), ),
			"take_with_default": (Parameter("def_val", str, ""), ),
		}
	
	def test_creation(self):
		dut = self.PUImpl()
	
	def test_parameter_user(self):
		dut = self.PUImpl(self.params)
		check_parameter_user(self, dut)
	
	def test_defaults(self):
		dut = self.PUImpl(self.params)
		
		with self.subTest(desc="without setting defaults"):
			req = RequestObject()
			with self.assertRaises(AttributeError):
				dut.take_request(req)
		
		with self.subTest(desc="with setting defaults"):
			req = RequestObject()
			res = dut.take_with_default(req)
			
			self.assertIn("def_val", req)
			self.assertEqual(self.params["take_with_default"][0].default, req.def_val, res)
	
	def test_extract_defaults(self):
		test_data = [
			("empty", {}, {}),
			("no params", {"a": tuple()}, {"a": {}}),
			("no defaults", {"a": (Parameter("n", int), )}, {"a": {}}),
			("mixed", {"a": (Parameter("n", int), Parameter("d", int, 3))}, {"a": {"d": 3}}),
			("local", self.params, {"take_request": {"some_val": 2}, "take_with_default": {"def_val": ""}}),
		]
		
		for desc, params, exp in test_data:
			with self.subTest(desc=desc):
				res = ParameterUser.extract_defaults(params)
				
				check_param_def_maps(self, params, res)
				self.assertEqual(exp, res)
	
	def test_meld_parameters(self):
		class MeldTC(NamedTuple):
			desc: str
			a: Iterable[Parameter]
			b: Iterable[Parameter]
			exp: List[Parameter]
		
		test_cases = [
			MeldTC("a&b empty", [], [], []),
			MeldTC("b empty", [Parameter("one", str)], [], [Parameter("one", str)]),
			MeldTC("a empty", [], [Parameter("one", str)], [Parameter("one", str)]),
			MeldTC("same parameter", [Parameter("one", str, "1")], [Parameter("one", str)], [Parameter("one", str, "1")]),
			MeldTC(
				"normal",
				[Parameter("one", str)],
				[Parameter("two", str)],
				[Parameter("one", str), Parameter("two", str)]
			),
		]
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				res = ParameterUser.meld_parameters(tc.a, tc.b)
				self.assertEqual(tc.exp, res)
	
	def test_meld_parameters_error(self):
		class MeldErrorTC(NamedTuple):
			desc: str
			a: Iterable[Parameter]
			b: Iterable[Parameter]
			error: Exception
		
		test_cases = [
			MeldErrorTC("wrong type", [Parameter("one", str)], [Parameter("one", int)], ValueError),
			MeldErrorTC("wrong multiple", [Parameter("one", str, multiple=True)], [Parameter("one", str, multiple=False)], ValueError),
		]
		
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				with self.assertRaises(tc.error):
					res = ParameterUser.meld_parameters(tc.a, tc.b)
	
	def test_filter_parameters(self):
		class FilterTC(NamedTuple):
			desc: str
			params: Iterable[Parameter]
			names: Iterable[Parameter]
			exp: List[Parameter]
		
		test_cases = [
			FilterTC("empty filter list", [Parameter("fst", int), Parameter("scd", str)], [], 
			[Parameter("fst", int), Parameter("scd", str)], ),
			FilterTC("normal case", [Parameter("fst", int), Parameter("scd", str)], ["scd"], [Parameter("fst", int)]),
			FilterTC("no match", [Parameter("fst", int), Parameter("scd", str)], ["trd"], 
			[Parameter("fst", int), Parameter("scd", str)]),
			FilterTC("all match", [Parameter("fst", int), Parameter("scd", str)], ["fst", "scd"], []),
			FilterTC("tuple input", (Parameter("fst", int), Parameter("scd", str)), ("scd", ), [Parameter("fst", int)]),
		]
		for tc in test_cases:
			with self.subTest(desc=tc.desc):
				res = ParameterUser.filter_parameters(tc.params, tc.names)
				self.assertEqual(tc.exp, res)
	
	def check_def_in_req(self, def_map, req):
		"""check default values in request"""
		for name, val in def_map.items():
			self.assertIn(name, req)
			self.assertEqual(req[name], val)
	
	def test_set_req_defaults(self):
		class DummyDef(NamedTuple):
			default_parameters: Mapping[str, Mapping[str, Any]] = {}
		
		def_map = {"a": 3}
		dd = DummyDef({"func": def_map})
		
		# positional syntax doesn't work below Python 3.8
		#with self.subTest(desc="positional"):
		#	def func(s, req: RequestObject, /) -> None:
		#		# positional
		#		pass
		with self.subTest(desc="positional or keyword"):
			def func(s, req: RequestObject) -> RequestObject:
				# positional or keyword
				return req
			
			def_func = set_req_defaults(func)
			
			# positional
			req = RequestObject()
			res = def_func(dd, req)
			
			self.check_def_in_req(def_map, res)
			self.check_def_in_req(def_map, req)
			
			# keyword
			req = RequestObject()
			res = def_func(dd, req=req)
			
			self.check_def_in_req(def_map, res)
			self.check_def_in_req(def_map, req)
		
		with self.subTest(desc="keyword"):
			def func(s, *, req: RequestObject) -> RequestObject:
				# keyword
				return req
			
			def_func = set_req_defaults(func)
			
			req = RequestObject()
			res = def_func(dd, req=req)
			
			self.check_def_in_req(def_map, res)
			self.check_def_in_req(def_map, req)
		
		with self.subTest(desc="no req"):
			def func(s, req):
				return req
			
			with self.assertRaises(ValueError):
				def_func = set_req_defaults(func)
		
		with self.subTest(desc="two reqs"):
			def func(s, req: RequestObject, r2: RequestObject) -> RequestObject:
				return req
			
			with self.assertRaises(ValueError):
				def_func = set_req_defaults(func)
		
		with self.subTest(desc="args req"):
			def func(s, *args: RequestObject) -> RequestObject:
				return args[0]
			
			with self.assertRaises(ValueError):
				def_func = set_req_defaults(func)
		
		with self.subTest(desc="kwargs req"):
			def func(s, **kwargs: RequestObject) -> RequestObject:
				return kwargs[req]
			
			with self.assertRaises(ValueError):
				def_func = set_req_defaults(func)
			
