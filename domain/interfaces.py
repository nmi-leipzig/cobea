from abc import ABC, abstractmethod

from domain.model import FitnessFunction, FitnessFunctionImpl

class FitnessFunctionLibrary(ABC):
	"""Interface for a library of fitness function implementations"""
	
	@abstractmethod
	def get_implementation(self, identifier: str) -> FitnessFunctionImpl:
		raise NotImplementedError()

