[![Build](https://github.com/DarkEnergySurvey/mkauthlist/actions/workflows/python-package.yml/badge.svg)](https://github.com/DarkEnergySurvey/mkauthlist/actions/workflows/python-package.yml)
[![PyPI](https://img.shields.io/pypi/v/mkauthlist.svg)](https://pypi.python.org/pypi/mkauthlist)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../../)

mkauthlist
==========

Make long latex author lists from csv files.

Installation
------------

Get the latest version of DESI's mkauthlist from the DESI Publication Board wiki page.

Do no use "pip install mkauthlist" because that will use the DES code.

After uncompressing it, you may want to set an enviroment to run it using

```text
> cd mkauthlist
> python3 -m venv mkauthlistDESI
> source mkauthlistDESI/bin/activate
```

Then you can simply install it by

```text
> python3 setup.py install
```

Usage
-----

In the directory DESItests you may find examples for KP (alphabetical) and first tier papers. For KPs in jcap format and considering ORCID numbers run


```text
> mkauthlist -f --sort --orcid -j jcap example_alphabetical.csv example_alphabetical.tex
```

For firs tier papers, edit the csv file to add a new column called FirstTier, and assign natural numbers to the first tier according to their ordering (see example_firsttier.csv). For first tier papers in jcap with orcid numbers run

```text
> mkauthlist -f --sort-firsttier --orcid -j jcap example_firsttier.csv example_firsttier.tex
```

