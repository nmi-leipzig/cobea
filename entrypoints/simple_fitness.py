#!/usr/bin/env python3

"""
Simple program to measure ftiness with iCE40 devices
"""

import sys
import os
import argparse
import random

sys.path.append(
	os.path.dirname(
		os.path.dirname(os.path.abspath(__file__))
	)
)

from domain.model import InputData
from domain.use_cases import Measure, CreateFitnessFunction
from domain.request_model import RequestObject
from adapters.icecraft_target import IcecraftManager, IcecraftEmbedMeter, IcecraftConfiguration, TilePosition
from adapters.scipy_functions import SciPyFunctions

def create_arg_parser():
	arg_parser = argparse.ArgumentParser()
	
	#arg_parser.add_argument("-s", "--serial_number", type=str, help="requested serial number")
	arg_parser.add_argument("-a", "--asc", type=str, help="asc file containing the configuration that should be tested")
	
	return arg_parser

def main():
	arg_parser = create_arg_parser()
	args = arg_parser.parse_args()
	
	ice_man = IcecraftManager()
	ice_meter = IcecraftEmbedMeter()
	
	measure_case = Measure(ice_man, ice_meter)
	fit_func_fac = CreateFitnessFunction(SciPyFunctions())
	fit_func = fit_func_fac(RequestObject(identifier="pearsons_correlation", description="pc"))
	
	in_data = InputData([random.randint(0, 255) for _ in range(512)])
	
	req = RequestObject()
	req["serial_number"] = None
	req["configuration"] = IcecraftConfiguration.create_from_file(args.asc)
	req["ram_mode"] = "512x8"
	req["ram_blocks"] = [TilePosition(8, 27)]
	req["input_data"] = in_data
	req["prefix"] = None
	req["output_count"] = len(in_data)
	req["output_format"] = "B"
	
	out_data = measure_case(req)
	
	fitness = fit_func(in_data, out_data)
	
	print(f"fitness = {fitness}")


if __name__ == "__main__":
	main()
