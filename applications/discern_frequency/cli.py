import argparse

from .action import remeasure, run

def create_arg_parser():
	arg_parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
	
	arg_parser.add_argument("-g", "--generator", type=str, help="serial number of the frequency generator")
	arg_parser.add_argument("-t", "--target", type=str, help="serial number of the target FPGA")
	arg_parser.add_argument("-m", "--meter", type=str, help="serial number of the meter")
	arg_parser.add_argument("--temperature", type=str, help="serial number of the temperature reader; empty string for"
		" autodetect; leave out to deactivate temperature measurement")
	
	sub_parsers = arg_parser.add_subparsers()
	run_parser = sub_parsers.add_parser("run", help="run an EA")
	run_parser.set_defaults(function=run)
	
	run_parser.add_argument("--area", nargs=4, type=int, required=True, help="evolvable area in the habitat; defined by"
		" corner points", metavar=("X_MIN", "Y_MIN", "X_MAX", "Y_MAX"))
	run_parser.add_argument("--in-port", nargs=3, type=str, required=True, help="input port for the frequency signal to"
		" the evolvable area", metavar=("X", "Y", "DIR"))
	run_parser.add_argument("--pop-size", type=int, required=True, help="size of the population")
	run_parser.add_argument("--generations", type=int, required=True, help="number of generation")
	
	rem_parser = sub_parsers.add_parser("remeasure", help="repeat measurement of an individual")
	rem_parser.set_defaults(function=remeasure)
	
	rem_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file contianing the original data")
	rem_parser.add_argument("-i", "--index", type=int, required=True, help="index of the measurement")
	rem_parser.add_argument("-r", "--rounds", default=1, type=int, help="how many times the measurement is repeated")
	rem_parser.add_argument("-c", "--comb-index", action="append", type=int, help="index of s-t-combination to be used")
	
	return arg_parser
