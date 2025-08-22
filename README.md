[![Build](https://github.com/cosmodesi/mkauthlist/actions/workflows/python-package.yml/badge.svg)](https://github.com/cosmodesi/mkauthlist/actions/workflows/python-package.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../../)

mkauthlist
==========

Make long latex author lists from csv files.

Installation
------------

Clone or download this GitHub repository: <https://github.com/cosmodesi/mkauthlist>.

Do not use `pip install mkauthlist`, because that will install the DES version.

You may want to set a virtual environment to run it using

```shell
python3 -m venv mkauthlistDESI
source mkauthlistDESI/bin/activate
```

Then you can simply install it by

```shell
python3 -m pip install .
```
If the code is changed/updated, you will need to reinstall for the changes to take effect.
The editable/developer installation (`pip install -e .`) does not seem to help avoid the re-installation in some cases.

You can also install from GitHub without cloning or downloading the repository:

```shell
python3 -m pip install git+https://github.com/cosmodesi/mkauthlist.git
```

If you do not worry about conflicts with the DES version, you can install the code with one of the commands above without setting up a virtual environment.

Usage
-----

If you download a CSV file from the DESI PubDB, you should **remove the empty lines with a CSV editor** before using this script.
For example, you may find the "Edit CSV" and "Rainbow CSV" extensions in VS Code helpful for this.

In the `DESItests` directory, you may find examples for KP (alphabetical) and first-tier papers.

For the key papers (KP) in JCAP format with ORCID numbers, run

```shell
mkauthlist -f --sort --orcid -j jcap example_alphabetical.csv example_alphabetical.tex
```

For first-tier author papers, edit the CSV file to add a new column called `FirstTier`, and assign natural numbers to the first-tier authors according to their ordering (see `example_firsttier.csv` in `DESItests`).
For first-tier papers in JCAP with ORCID numbers, run

```shell
mkauthlist -f --sort-firsttier --orcid -j jcap example_firsttier.csv example_firsttier.tex
```

You may also want to exclude the collaboration name by adding the `-nc`, `--nocollab` or `--nocollaboration` flag.
(The collaboration name does not appear for JCAP specifically, but this can be helpful with other journal formats.)

To send affiliations to an appendix, use
```shell
mkauthlist -f --sort --orcid -j jcap.appendix example_alphabetical.csv example_alphabetical_appendix.tex
```
or
```shell
mkauthlist -f --sort-firsttier --orcid -j jcap.appendix example_firsttier.csv example_firsttier_appendix.tex
```
respectively.

To generate the author list for arXiv, use `-j arxiv` with the same sorting options, i.e.
```shell
mkauthlist -f --sort -j arxiv example_alphabetical.csv example_alphabetical.txt
```
or
```shell
mkauthlist -f --sort-firsttier -j arxiv example_firsttier.csv example_firsttier.txt
```
respectively.
In the latter case, you may also want to exclude the collaboration name by adding the `-nc`, `--nocollab` or `--nocollaboration` flag.

Additional TeX packages
-----
The output with the `--orcid` option requires `\usepackage{orcidlink}` in the TeX preamble.


