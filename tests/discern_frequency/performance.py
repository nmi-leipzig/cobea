#!/usr/bin/env python3
"""Simplified version of discern frequency to measure and finetune performance

- keep setup to a minimum
- still flash an FPGA as it is an integral part
- mock measurement with random data
- store repeating data, skip datasets touched once
"""

import datetime
import os
import pickle
import sys

from contextlib import ExitStack
from functools import partial
from operator import attrgetter, itemgetter, methodcaller

sys.path.append(
	os.path.dirname(
		os.path.dirname(
			os.path.dirname(os.path.abspath(__file__))
		)
	)
)

import applications.discern_frequency

from adapters.deap.simple_ea import SimpleEA
from adapters.dummies import DummyDriver
from adapters.hdf5_sink import compose, HDF5Sink, ParamAim
from adapters.icecraft import IcecraftManager, IcecraftRawConfig, IcecraftRep, IcecraftStormConfig
from adapters.parallel_collector import CollectorDetails, InitDetails, ParallelCollector
from adapters.parallel_sink import ParallelSink
from adapters.prng import BuiltInPRNG
from adapters.temp_meter import TempMeter
from adapters.unique_id import SimpleUID
from applications.discern_frequency.action import create_write_map, create_xc6200_rep
from domain.use_cases import Measure
from tests.mocks import RandomMeter


LOCAL_PATH = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.dirname(os.path.abspath(applications.discern_frequency.__file__))
REP_FILENAME = "rep.pkl"

def pickle_rep(filename: str) -> None:
	rep = create_xc6200_rep((10, 23), (19, 32))
	with open(filename, "wb") as pkl_file:
		pickle.dump(rep, pkl_file)

def unpickle_rep(filename: str) -> IcecraftRep:
	with open(filename, "rb") as pkl_file:
		rep = pickle.load(pkl_file)
	
	return rep

def get_temp_details(sink: ParallelSink) -> CollectorDetails:
	return CollectorDetails(
		InitDetails(DummyDriver),
		InitDetails(TempMeter),
		sink.get_sub(),
		0,
		"temperature",
	)

def run_algo(rep: IcecraftRep) -> None:
	pop_size = 4
	chromo_bits = 16
	
	# no driver data
	write_map = create_write_map(rep, pop_size, chromo_bits)
	write_map["Measure.perform"] = write_map["Measure.perform"][1:]
	
	# WARNING: the HDF5 file gets really big really fast as it can't compress the random measurement data very well
	# that should not be an issue for real measurements as the Rigol basically provides only 256 different values
	cur_date = datetime.datetime.now(datetime.timezone.utc)
	sink = ParallelSink(HDF5Sink, (write_map, ), {filename: f"perf-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"})
	man = IcecraftManager()
	target = man.acquire()
	with ExitStack() as stack:
		stack.enter_context(sink)
		
		meter = RandomMeter(2**19, 1)
		driver = DummyDriver()
		
		temp_det = get_temp_details(sink)
		stack.enter_context(ParallelCollector(temp_det))
		
		try:
			measure_uc = Measure(driver, meter, sink)
			
			hab_path = os.path.join(APP_PATH, "nhabitat.asc")
			hab_config = IcecraftRawConfig.create_from_file(hab_path)
			
			ea = SimpleEA(rep, measure_uc, SimpleUID(), BuiltInPRNG(), hab_config, target, 437071, sink)
			
			ea.run(pop_size, 8, 0.7, 0.001756)
			#ea.run(50, 600, 0.7, 0.001756)
		finally:
			man.release(target)


if __name__ == "__main__":
	#pickle_rep(REP_FILENAME)
	rep = unpickle_rep(REP_FILENAME)
	run_algo(rep)
