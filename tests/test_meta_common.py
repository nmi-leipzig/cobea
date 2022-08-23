from functools import partial
from operator import attrgetter, itemgetter
from unittest import TestCase

from adapters.hdf5_sink import compose, noop

from tests.common import check_func_eq

class MetaCommonTest(TestCase):
	def test_check_func_eq(self):
		# desc, a, b, res
		func1 = compose
		ig1 = itemgetter(0)
		tc_data = [
			("same itemgetter", ig1, ig1, True),
			("same func", func1, func1, True),
			("eq itemgetter", itemgetter(3), itemgetter(3), True),
			(
				"eq partial",
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), list]),
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), list]),
				True
			),
			("different func", compose, noop, False),
			("different non func", itemgetter(4), partial, False),
			("func vs non func", compose, itemgetter(5), False),
			(
				"different partial",
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), list]),
				partial(compose, funcs=[itemgetter(0), partial(map, attrgetter("index")), tuple]),
				False
			),
		]
		for desc, a, b, res in tc_data:
			with self.subTest(desc=desc):
				if res:
					check_func_eq(self, a, b)
					check_func_eq(self, b, a)
				else:
					with self.assertRaises(AssertionError):
						check_func_eq(self, a, b)
					with self.assertRaises(AssertionError):
						check_func_eq(self, b, a)
	
