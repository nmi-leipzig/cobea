import unittest
from typing import Mapping, Iterable

import domain.request_model as request_model

class ParameterTest(unittest.TestCase):
	
	def test_creation_default(self):
		name = "my_param"
		tpe = str
		
		param = request_model.Parameter(name, tpe)
		
		self.assertEqual(name, param.name)
		self.assertEqual(tpe, param.data_type)
		self.assertEqual(request_model.NO_DEFAULT, param.default)
		self.assertEqual(False, param.multiple)
	
	def test_creation_multiple(self):
		name = "my_param"
		tpe = str
		default = request_model.NO_DEFAULT
		multiple = True
		
		param = request_model.Parameter(name, tpe, multiple=True)
		
		self.assertEqual(name, param.name)
		self.assertEqual(tpe, param.data_type)
		self.assertEqual(default, param.default)
		self.assertEqual(multiple, param.multiple)
	
	def test_creation_full(self):
		name = "my_param"
		tpe = str
		default = "value"
		multiple = True
		
		param = request_model.Parameter(name, tpe, default, multiple)
		
		self.assertEqual(name, param.name)
		self.assertEqual(tpe, param.data_type)
		self.assertEqual(default, param.default)
		self.assertEqual(multiple, param.multiple)
		

class ParameterValuesTest(unittest.TestCase):
	target_cls = request_model.ParameterValues
	
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
	target_cls = request_model.RequestObject
	

def check_parameter_user(test_case, parameter_user):
	for key in parameter_user.parameters:
		test_case.assertIsInstance(key, str)
		params = parameter_user.parameters[key]
		for p in params:
			test_case.assertIsInstance(p, request_model.Parameter)

class ParameterUserTest(unittest.TestCase):
	class PUImpl(request_model.ParameterUser):
		def __init__(self, params={}):
			self._params = params
		
		@property
		def parameters(self) -> Mapping[str, Iterable[request_model.Parameter]]:
			return self._params
		
		def take_request(self, request:request_model.RequestObject) -> None:
			pass
	
	def test_creation(self):
		dut = self.PUImpl()
	
	def test_parameter_user(self):
		params = {"take_request": (
			request_model.Parameter("some_val", int, 2),
		)}
		dut = self.PUImpl(params)
		check_parameter_user(self, dut)
