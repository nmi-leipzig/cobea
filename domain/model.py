#!/usr/bin/env python3

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Tuple, TypeVar, Generic, Union, Any

class InputData(tuple):
	pass

class OutputData(tuple):
	pass

FitnessFunctionImpl = Callable[[InputData, OutputData], float]

@dataclass(frozen=True)
class FitnessFunction:
	identifier: str
	description: str
	implementation: FitnessFunctionImpl
	
	def __call__(self, input_data: InputData, output_data: OutputData) -> float:
		return self.implementation(input_data, output_data)

PreprocessingImpl = Callable[[InputData, OutputData], Tuple[InputData, OutputData]]

@dataclass(frozen=True)
class Preprocessing:
	identifier: str
	description: str
	implementation: PreprocessingImpl
	
	def __call__(self, input_data: InputData, output_data: OutputData) -> Tuple[InputData, OutputData]:
		return self.implementation(input_data, output_data)
