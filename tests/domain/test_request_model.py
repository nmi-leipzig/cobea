import unittest

from typing import Mapping, Iterable, NamedTuple, List

from domain.request_model import Parameter, NO_DEFAULT, ParameterValues, RequestObject, ParameterUser

from ..common import check_parameter_user

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
	

class ParameterUserTest(unittest.TestCase):
	class PUImpl(ParameterUser):
		def __init__(self, params=None):
			if params is None:
				params = {}
			self._params = params
		
		@property
		def parameters(self) -> Mapping[str, Iterable[Parameter]]:
			return self._params
		
		def take_request(self, request: RequestObject) -> None:
			pass
	
	def test_creation(self):
		dut = self.PUImpl()
	
	def test_parameter_user(self):
		params = {"take_request": (
			Parameter("some_val", int, 2),
		)}
		dut = self.PUImpl(params)
		check_parameter_user(self, dut)
	
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
