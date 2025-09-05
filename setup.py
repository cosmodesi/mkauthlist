import sys
import os
try: from setuptools import setup
except ImportError: from distutils.core import setup

import versioneer

if sys.version_info[:2] < (2, 7):
    raise RuntimeError("Python version >= 2.7 required.")

setup(
    name='mkauthlist',
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description="A simple script for making latex author lists from the csv file produced by the DES/DESI Publication Database (PubDB)",
    long_description="See README on GitHub: https://github.com/cosmodesi/mkauthlist",
    url='https://github.com/cosmodesi/mkauthlist',
    author='Alex Drlica-Wagner',
    author_email='kadrlica@fnal.gov',
    license='MIT',
    scripts = ['bin/mkauthlist'],
    packages = ['mkauthlist'],
    install_requires=[
        'numpy >= 1.6.1',
        'pylatexenc'
    ],
    platforms='any',
    keywords='latex des',
    classifiers = [
        'Programming Language :: Python',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Intended Audience :: Science/Research',
    ]
)
