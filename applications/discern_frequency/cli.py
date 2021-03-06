import argparse

from adapters.deap.simple_ea import EvalMode

from .action import clamp, explain, extract, ExtractTarget, info, OutFormat, remeasure, restart, run, spectrum
from .misc import DriverType

def create_arg_parser():
	arg_parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
	
	arg_parser.add_argument("-g", "--generator", type=str, help="serial number of the frequency generator")
	arg_parser.add_argument("-t", "--target", type=str, help="serial number of the target FPGA")
	arg_parser.add_argument("-m", "--meter", type=str, help="serial number of the meter")
	arg_parser.add_argument("--temperature", type=str, help="serial number of the temperature reader; empty string for"
		" autodetect; leave out to deactivate temperature measurement")
	arg_parser.add_argument("-o", "--output", type=str, help="name of the output file")
	arg_parser.add_argument("--dummy", action="store_true", help="use dummies instead of real hardware")
	arg_parser.add_argument("--freq-gen-type", default="FPGA", type=str, choices=[d.name for d in DriverType], help="")
	
	sub_parsers = arg_parser.add_subparsers()
	run_parser = sub_parsers.add_parser("run", help="run an EA")
	run_parser.set_defaults(function=run)
	
	run_parser.add_argument("--area", nargs=4, type=int, required=True, help="evolvable area in the habitat; defined by"
		" corner points", metavar=("X_MIN", "Y_MIN", "X_MAX", "Y_MAX"))
	run_parser.add_argument("--in-port", nargs=3, type=str, required=True, help="input port for the frequency signal to"
		" the evolvable area", metavar=("X", "Y", "DIR"))
	run_parser.add_argument("--out-port", nargs=3, type=str, help="output port for the signal from the evolvable area",
		metavar=("X", "Y", "DIR"))
	run_parser.add_argument("--pop-size", type=int, required=True, help="size of the population")
	run_parser.add_argument("--generations", type=int, required=True, help="number of generation")
	run_parser.add_argument("--crossover-prob", type=float, required=True, help="probability that a crossover takes"
		" place")
	run_parser.add_argument("--mutation-prob", type=float, required=True, help="probability that a mutation takes"
		" place")
	run_parser.add_argument("--eval-mode", default="NEW", type=str, choices=[e.name for e in EvalMode], help="which individuals in each generation are evaluated; NEW -> ones without fitness value; ELITE -> without fitness value and elites; ALL -> all")
	run_parser.add_argument("--habitat", type=str, required=True, help="ASC file of the base configuration for the "
		"target FPGA; provides the periphery of the evolved area")
	run_parser.add_argument("--habitat-con", type=str, help="description of the connections of the habitat")
	run_parser.add_argument("--freq-gen", type=str, help="configuration file of the frequency generator;"
		" ASC format")
	run_parser.add_argument("--freq-gen-con", type=str, help="description of the connections of the frequency "
		"generator")
	
	rem_parser = sub_parsers.add_parser("remeasure", help="repeat measurement of an individual")
	rem_parser.set_defaults(function=remeasure)
	
	rem_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file contianing the original data")
	rem_parser.add_argument("-i", "--index", type=int, required=True, help="index of the measurement")
	rem_parser.add_argument("-r", "--rounds", default=1, type=int, help="how many times the measurement is repeated")
	rem_parser.add_argument("-c", "--comb-index", action="append", type=int, help="index of s-t-combination to be used")
	rem_parser.add_argument("--freq-gen", type=str, help="configuration file of the frequency generator;"
		" ASC format")
	
	restart_parser = sub_parsers.add_parser("restart", help="run EA with results of previous run")
	restart_parser.set_defaults(function=restart)
	
	restart_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file containing the original data")
	restart_parser.add_argument("-i", "--index", type=int, default=-1, help="Index of the generation to take as initial population")
	restart_parser.add_argument("--pop-size", type=int, help="size of the population")
	restart_parser.add_argument("--generations", type=int, help="number of generation")
	restart_parser.add_argument("--crossover-prob", type=float, help="probability that a crossover takes"
		" place")
	restart_parser.add_argument("--mutation-prob", type=float, help="probability that a mutation takes"
		" place")
	restart_parser.add_argument("--eval-mode", type=str, choices=[e.name for e in EvalMode], help="which individuals in each generation are evaluated; NEW -> ones without fitness value; ELITE -> without fitness value and elites; ALL -> all")
	restart_parser.add_argument("--freq-gen", type=str, help="configuration file of the frequency generator;"
		" ASC format")
	restart_parser.add_argument("--offset", nargs=2, type=int, help="offset to move the the evolvable area",
		metavar=("X", "Y"))
	restart_parser.add_argument("--habitat", type=str, help="ASC file of the base configuration for the target FPGA; "
		"provides the periphery of the evolvable area")
	
	clamp_parser = sub_parsers.add_parser("clamp", help="iteratively set function unit to fixed output")
	clamp_parser.set_defaults(function=clamp)
	
	clamp_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file containing the original data")
	clamp_parser.add_argument("-c", "--chromosome", type=int, required=True, help="id of the chromosome")
	clamp_parser.add_argument("-r", "--repeat", default=1, type=int, help="how many times the measurement is repeated "
		"per function unit")
	clamp_parser.add_argument("--freq-gen", type=str, help="configuration file of the frequency generator;"
		" ASC format")
	
	epl_parser = sub_parsers.add_parser("explain", help="transfer chromosome to more understandable form")
	epl_parser.set_defaults(function=explain)
	
	epl_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file containing the original data")
	epl_parser.add_argument("-c", "--chromosome", type=int, required=True, help="id of the chromosome")
	epl_parser.add_argument("-f", "--format", type=str, choices=[o.name for o in OutFormat], help="output format")
	
	info_parser = sub_parsers.add_parser("info",  help="Show information about an HDF5 file")
	info_parser.set_defaults(function=info)
	
	info_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file")
	info_parser.add_argument("-i", "--index", type=int, default=-1, help="index of the generation info is shown for")
	
	spectrum_parser = sub_parsers.add_parser("spectrum", help="measure average voltage over multiple frequencies")
	spectrum_parser.set_defaults(function=spectrum)
	
	spectrum_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file")
	spectrum_parser.add_argument("-c", "--chromosome", type=int, required=True, help="id of the chromosome")
	spectrum_parser.add_argument("--freq-gen-con", type=str, help="description of the connections of the frequency "
		"generator")
	
	extract_parser = sub_parsers.add_parser("extract", help="extract measurement data from HDF5 file")
	extract_parser.set_defaults(function=extract)
	extract_parser.add_argument("-d", "--data-file", type=str, required=True, help="HDF5 file")
	extract_parser.add_argument("-e", "--extract-target", type=str, default=ExtractTarget.MEASUREMENT.name,
		choices=[t.name for t in ExtractTarget], help="what to extract")
	extract_parser.add_argument("-i", "--index", type=int, help="index of the measurement")
	
	return arg_parser
