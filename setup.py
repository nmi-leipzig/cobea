from setuptools import setup, find_packages
setup(name='cobea', packages=find_packages())

# using approach of https://stackoverflow.com/a/50194143 to manage module imports from parent directories
# remark that packaging is managed with pip! Switching to conda in a later stage of development may be favourable
