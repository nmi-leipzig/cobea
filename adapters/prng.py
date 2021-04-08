from domain.interfaces import PRNG

import random

class BuiltInPRNG(PRNG):
	def seed(self, s: int) -> None:
		random.seed(s)
	
	def randint(self, a: int, b: int) -> int:
		return random.randint(a, b)
