import unittest.mock as mock
import unittest

from domain.interfaces import CorrelationFunction, CorrelationFunctionLibrary
from domain.model import InputData, OutputData

class CorrelationFunctionTest(unittest.TestCase):
	class MockLibrary(CorrelationFunctionLibrary):
		def __init__(self):
			self.function = mock.MagicMock()
			self.function.return_value = 1.2
		
		def get_correlation_function(self, identifier: str) -> CorrelationFunction:
			return self.function
	
	def setUp(self):
		self.mock_lib = self.MockLibrary()
	
	def test_creation(self):
		ff_lib = self.mock_lib
		identifier = "my_ff"
		fitness_function = ff_lib.get_correlation_function(identifier)
		
		self.assertEqual(self.mock_lib.function, fitness_function)
	
	def test_call(self):
		ff_lib = self.mock_lib
		fitness_function = ff_lib.get_correlation_function("my_ff")
		
		input_data = InputData([2, 3, 4])
		output_data = OutputData([12, 13, 14])
		
		fitness_function(input_data, output_data)
		self.mock_lib.function.assert_called_once_with(input_data, output_data)
	
