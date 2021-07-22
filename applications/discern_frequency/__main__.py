import sys
import os

from argparse import Namespace

sys.path.append(
	os.path.dirname(
		os.path.dirname(
			os.path.dirname(os.path.abspath(__file__))
		)
	)
)

import applications.discern_frequency.action as action

from applications.discern_frequency.cli import create_arg_parser

arg_parser = create_arg_parser()
args = arg_parser.parse_args()

action.run(args)
