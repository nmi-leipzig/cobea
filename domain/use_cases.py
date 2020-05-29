from domain.model import FitnessFunction
from domain.interfaces import FitnessFunctionLibrary

class CreateFitnessFunction:
	def __init__(self, library: FitnessFunctionLibrary) -> None:
		self._library = library
	
	def __call__(self, identifier: str, description: str) -> FitnessFunction:
		implementation = self._library.get_implementation(identifier)
		return FitnessFunction(identifier, description, implementation)
