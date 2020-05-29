#!/usr/bin/env python3

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

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
