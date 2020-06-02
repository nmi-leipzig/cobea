#!/usr/bin/env python3

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Tuple, TypeVar, Generic, Union, Any

class TestInput(tuple):
	pass

class TestOutput(tuple):
	pass

FitnessFunctionImpl = Callable[[TestInput, TestOutput], float]

@dataclass(frozen=True)
class FitnessFunction:
	identifier: str
	description: str
	implementation: FitnessFunctionImpl
	
	def __call__(self, test_input: TestInput, test_output: TestOutput) -> float:
		return self.implementation(test_input, test_output)

PreprocessingImpl = Callable[[TestInput, TestOutput], Tuple[TestInput, TestOutput]]

@dataclass(frozen=True)
class Preprocessing:
	identifier: str
	description: str
	implementation: PreprocessingImpl
	
	def __call__(self, test_input: TestInput, test_output: TestOutput) -> Tuple[TestInput, TestOutput]:
		return self.implementation(test_input, test_output)
