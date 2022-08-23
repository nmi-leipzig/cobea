cover_all:
	coverage run -m unittest discover -v

report:
	coverage report -m
	coverage html

coverage: cover_all report