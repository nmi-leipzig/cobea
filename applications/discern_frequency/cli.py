import argparse

from .action import run

def create_arg_parser():
	arg_parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
	
	arg_parser.add_argument("-g", "--generator", type=str, help="serial number of the frequency generator")
	arg_parser.add_argument("-t", "--target", type=str, help="serial number of the target FPGA")
	
	sub_parsers = arg_parser.add_subparsers()
	run_parser = sub_parsers.add_parser("run", help="run an EA")
	run_parser.set_defaults(function=run)
	
	return arg_parser
