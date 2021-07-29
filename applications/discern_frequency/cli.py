import argparse

from .action import remeasure, run

def create_arg_parser():
	arg_parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
	
	arg_parser.add_argument("-g", "--generator", type=str, help="serial number of the frequency generator")
	arg_parser.add_argument("-t", "--target", type=str, help="serial number of the target FPGA")
	arg_parser.add_argument("-m", "--meter", type=str, help="serial number of the meter")
	
	sub_parsers = arg_parser.add_subparsers()
	run_parser = sub_parsers.add_parser("run", help="run an EA")
	run_parser.set_defaults(function=run)
	
	rem_parser = sub_parsers.add_parser("remeasure", help="repeat measurement of an individual")
	rem_parser.set_defaults(function=remeasure)
	
	rem_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file contianing the original data")
	rem_parser.add_argument("-i", "--index", type=int, required=True, help="index of the measurement")
	rem_parser.add_argument("-r", "--rounds", default=1, type=int, help="how many times the measurement is repeated")
	rem_parser.add_argument("-c", "--comb-index", action="append", type=int, help="index of s-t-combination to be used")
	
	return arg_parser
