import argparse

def create_arg_parser():
	arg_parser = argparse.ArgumentParser()
	
	arg_parser.add_argument("-g", "--generator", type=str, help="serial number of the frequency generator")
	arg_parser.add_argument("-t", "--target", type=str, help="serial number of the target FPGA")
	
	return arg_parser
