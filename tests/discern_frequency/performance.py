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
from adapters.hdf5_sink import HDF5Sink, ParamAim
from adapters.icecraft import IcecraftManager, IcecraftRawConfig, IcecraftRep
from adapters.parallel_sink import ParallelSink
from adapters.prng import BuiltInPRNG
from adapters.unique_id import SimpleUID
from applications.discern_frequency.action import create_xc6200_rep
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

def run_algo(rep: IcecraftRep) -> None:
	chromo_bits = 16
	chromo_aim = [
		ParamAim(
			"return", f"uint{chromo_bits}", "chromosome", as_attr=False, shape=(len(rep.genes), ),
			alter=attrgetter("allele_indices")
		),
		ParamAim("return", "uint64", "chromo_id", as_attr=False, alter=attrgetter("identifier")),
	]
	
	write_map = {
		"Measure.perform": [
			#ParamAim("driver_data", "uint8", "s_t_index", as_attr=False),
			ParamAim("return", "float64", "measurement", as_attr=False, shape=(2**19, )),
		],
		"SimpleEA.fitness": [
			ParamAim("fit", "float64", "fitness", as_attr=False),
			ParamAim("fast_sum", "float64", "fast_sum", as_attr=False),
			ParamAim("slow_sum", "float64", "slow_sum", as_attr=False),
			ParamAim("chromo_index", "uint64", "fitness_chromo_id", as_attr=False),
			ParamAim(
				"carry_enable",
				bool,
				"carry_enable",
				as_attr=False,
				shape=(len(list(rep.iter_carry_bits())), )
			),
			ParamAim("time", "float64", "fitness_time", as_attr=False, alter=methodcaller("timestamp")),
		],
		"SimpleEA.ea_params": [
			ParamAim("pop_size", "uint64", "pop_size"),
			ParamAim("gen_count", "uint64", "gen_count"),
			ParamAim("crossover_prob", "float64", "crossover_prob"),
			ParamAim("mutation_prob", "float64", "mutation_prob"),
		],
		"RandomChromo.perform": chromo_aim,
		"GenChromo.perform": chromo_aim,
		"Individual.wrap.cxTwoPoint": [
			ParamAim("in", "uint64", "crossover_parents", as_attr=False, shape=(2, )),
			ParamAim("out", "uint64", "crossover_child", as_attr=False, alter=itemgetter(0)),
		],
		"Individual.wrap.mutUniformInt": [
			ParamAim("in", "uint64", "mutation_parent", as_attr=False, alter=itemgetter(0)),
			ParamAim("out", "uint64", "mutation_child", as_attr=False, alter=itemgetter(0)),
		],
	}
	
	cur_date = datetime.datetime.now(datetime.timezone.utc)
	sink = ParallelSink(HDF5Sink, (write_map, f"perf-{cur_date.strftime('%Y%m%d-%H%M%S')}.h5"))
	man = IcecraftManager()
	target = man.acquire()
	with sink:
		meter = RandomMeter(2**19, 1)
		driver = DummyDriver()
		
		try:
			measure_uc = Measure(driver, meter, sink)
			
			hab_path = os.path.join(APP_PATH, "nhabitat.asc")
			hab_config = IcecraftRawConfig.create_from_file(hab_path)
			
			ea = SimpleEA(rep, measure_uc, SimpleUID(), BuiltInPRNG(), hab_config, target, 437071, sink)
			
			ea.run(4, 8, 0.7, 0.001756)
			#ea.run(50, 600, 0.7, 0.001756)
		finally:
			man.release(target)


if __name__ == "__main__":
	#pickle_rep(REP_FILENAME)
	rep = unpickle_rep(REP_FILENAME)
	run_algo(rep)
