from domain.request_model import Parameter

def check_parameter_user(test_case, parameter_user):
	for key in parameter_user.parameters:
		test_case.assertIsInstance(key, str)
		params = parameter_user.parameters[key]
		for p in params:
			test_case.assertIsInstance(p, Parameter)

