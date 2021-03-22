import sys
import os

sys.path.append(
	os.path.dirname(
		os.path.dirname(
			os.path.dirname(os.path.abspath(__file__))
		)
	)
)

from applications.discern_frequency.cli import create_arg_parser

arg_parser = create_arg_parser()
print("1 kHz")
