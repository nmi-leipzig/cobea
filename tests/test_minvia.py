from unittest import TestCase

from adapters.minvia import MinviaDriver
from domain.request_model import ResponseObject, RequestObject, Parameter

from tests.common import check_parameter_user


class MinviaDriverTest(TestCase):
	def test_create(self):
		dut = MinviaDriver()
	
	def test_empty(self):
		dut = MinviaDriver()
		
		req = RequestObject()
		res = dut.drive(req)
		self.assertEqual(0, len(res))
		
		req = RequestObject()
		res = dut.clean_up(req)
		self.assertEqual(0, len(res))
		
	
	def test_drive(self):
		def drive_func(request: RequestObject) -> ResponseObject:
			return ResponseObject(sq=request.drv_param**2)
		
		drv_params = (Parameter("drv_param", int), )
		dut = MinviaDriver(drive_params=drv_params, drive_func=drive_func)
		for p in drv_params:
			self.assertIn(p, dut.parameters["drive"])
		
		req = RequestObject(drv_param=7)
		res = dut.drive(req)
		self.assertIn("sq", res)
		self.assertEqual(49, res.sq)
	
	def test_clean_up(self):
		def clean_up_func(request: RequestObject) -> ResponseObject:
			return ResponseObject(sq=request.cu_param**2)
		
		cu_params = (Parameter("cu_param", int), )
		dut = MinviaDriver(clean_up_params=cu_params, clean_up_func=clean_up_func)
		for p in cu_params:
			self.assertIn(p, dut.parameters["clean_up"])
		
		req = RequestObject(cu_param=7)
		res = dut.clean_up(req)
		self.assertIn("sq", res)
		self.assertEqual(49, res.sq)
	
	def test_parameter_user(self):
		dut = MinviaDriver()
		check_parameter_user(self, dut)
