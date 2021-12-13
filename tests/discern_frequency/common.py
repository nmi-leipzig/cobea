import os

TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def del_files(filename_list):
	for filename in filename_list:
		try:
			os.remove(filename)
		except FileNotFoundError:
			pass

