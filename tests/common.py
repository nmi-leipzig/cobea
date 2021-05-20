import os

from inspect import getmembers, ismethod
from typing import get_type_hints

from domain.request_model import NO_DEFAULT, Parameter, RequestObject

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def is_request_function(function):
	if not ismethod(function):
		return False
	
	type_hints = get_type_hints(function)
	# exclude return value
	try:
		del type_hints["return"]
	except KeyError:
		pass
	
	return any(v==RequestObject for v in type_hints.values())

def check_parameter_defaults(test_case, parameters, defaults):
	"""Check defaults for a sequence of Parameters"""
	for param in parameters:
		if param.name in defaults:
			test_case.assertEqual(param.default, defaults[param.name])
		else:
			test_case.assertEqual(NO_DEFAULT, param.default)

def check_param_def_maps(test_case, param_map, def_map):
	"""Check mapping function_name -> defaults for a mapping function_name -> parameters"""
	test_case.assertEqual(set(param_map), set(def_map))
	for func_name in param_map:
		check_parameter_defaults(test_case, param_map[func_name], def_map[func_name])

def check_parameter_user(test_case, parameter_user):
	req_functions = getmembers(parameter_user, is_request_function)
	exp_names = set(n for n, _ in req_functions)
	test_case.assertEqual(
		exp_names,
		set(parameter_user.parameters.keys()),
		"mismatch between request functions and provided parameter lists"
	)
	
	for key in parameter_user.parameters:
		test_case.assertIsInstance(key, str)
		params = parameter_user.parameters[key]
		for p in params:
			test_case.assertIsInstance(p, Parameter)
		
		name_list = [p.name for p in params]
		test_case.assertEqual(len(name_list), len(set(name_list)), f"Parameter names are not unique: {name_list}")
	
	check_param_def_maps(test_case, parameter_user.parameters, parameter_user.default_parameters)

