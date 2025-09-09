#!/usr/bin/env python
"""A simple script for making latex author lists from the csv file
produced by the DES Publication Database (PubDB).

Some usage notes:
(1) By default, the script preserves the order of the input file. The
'--sort' option does not respect tiers (use '--sort-builder' instead).
(2) An exact match is required to group affiliations. This should not
be a problem for affiliations provided by the DES PubDB; however, be
careful if you are editing affiliations by hand.
(3) The script parses quoted CSV format. LaTeX umlauts cause problems
(i.e., '\"') and must be escaped in the CSV file. The PubDB should do
this by default.
(4) There are some authors in the database with blank
affiliations. These need to be corrected by hand in the CSV file.
(5) Auxiliary author ordering (i.e, '-a, --aux') preserves the rest
of the author list. For example, the author list will become:
Ordered authors - Tier 1 authors - Tier 2 authors
"""

__author__  = "Alex Drlica-Wagner"
__email__   = "kadrlica@fnal.gov"
try:
    # Module is in the python path
    from mkauthlist import __version__
except ImportError:
    # This file still lives in the source directory
    from _version import get_versions
    __version__ = get_versions()['version']
except:
    # This file is alone
    __version__ = "UNKNOWN"

import os,sys
import csv
from collections import OrderedDict as odict
import re
import logging

import numpy as np

from datetime import date
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pylatexenc.latex2text import LatexNodes2Text

#MUNICH HACK (shouldn't be necessary any more)
HACK = odict([
    #('Ludwig-Maximilians-Universit',r'Department of Physics, Ludwig-Maximilians-Universit\"at, Scheinerstr.\ 1, 81679 M\"unchen, Germany')
])

def check_umlaut(lines):
    """Check for unescaped umlaut characters in quoted strings."""
    #This is a problem:
    #  ...,"Universit\"ats-Sternwarte, Fakult\"at f\"ur Physik"
    #While this is not:
    #  Gruen,Daniel,D.~Gr\"un,...

    # The unescaped umlaut pattern: \" and not \""
    umlaut = re.compile(r'\\"(?!")')
    # The start of a quoted string: ,"
    quote = re.compile(r',"')

    for line in lines:
        if umlaut.search(line) is None or quote.search(line) is None: continue
        if umlaut.search(line).start() > quote.search(line).start():
            msg =  "Found unescaped umlaut: " + line.strip()
            logging.warning(msg)
    return lines

def clean_latex_to_text(s):
    "Removal of LaTeX commands suitable for arXiv. Leaves accent commands"
    return re.sub(r'(?<!\\)~',' ', s).replace(r'\ ', ' ').replace('{', '').replace('}', '')

def letter_numeric(N: int):
    """
    Some journals (as far as we know, JCAP) like to make affiliation marks in lowercase letters and not numbers.
    Numbers may be more readable, but using the same convention should help to prevent and catch mistakes.
    For consistency with numeric markers in other journals, we begin counting from 1, so clearly 1 -> a and so on until 26 -> z.
    As evidenced in DESI 2024 JCAP batch proofs/published versions, 27 -> aa, 28 -> ab and so on, presumably until 702 -> zz.
    We presume the pattern continues indefinitely (with e.g. 703 -> aaa), although two letters will probably be sufficient in practice.
    """
    if N <= 0: logging.warning("A letter-numeric representation for a non-positive integer %d will be empty."%N)
    # these letter representations are not exactly like a simple N_LETTER-based positional system with digits mapped to letters
    # in a positional system without leading zeros, the first digit can not be 0 but here it can evidently be 'a'
    # just shifting by 1 does not work because in multi-letter representations 0 still needs to be reflected in positions except the first
    FIRST_LETTER_CODE = ord('a'); N_LETTERS = 26 # English/ASCII lowercase letters
    s = "" # the result string to be built in the reverse order
    n = N - 1 # seems easier to shift from one-based to zero-based counting
    while n >= 0: # loop over digits in the reverse order - starting from the trailing/smallest
        d = n % N_LETTERS # current digit, 0 to N_LETTERS - 1
        s = chr(FIRST_LETTER_CODE + d) + s # prepend the letter representation of the current digit (ASCII letters have sequential codes) to the string
        n = n // N_LETTERS - 1 # move on to the next digit, subtracting the N_LETTERS combinations that can be expressed without adding another digit
        # probably a better explanation of this loop:
        # there is a hidden variable n_digits, starting from 1 at the first iteration
        # numbers strictly less than N_LETTERS**n_digits can be represented with n_digits digits (with leading zeros, i.e. 'a's)
        # numbers greater or equal than that need more digits, but with each additional digit counting can restart from zero with leading zeros ('a's) without the risk of confusion with shorter representations, and in fact it should according to the rules JCAP seems to follow
        # so at each step we need to subtract N_LETTERS**n_digits from n. when it becomes negative, we found the necessary number of digits
        # just before it becomes negative, we need to build a 26-base positional representation of n (with all those things subtracted) of length n_digits with leading zeros (converting digits to letters)
        # but subtracting N_LETTERS**k does not change the last k digits in the N_LETTER-base positional system!
        # as a result, we can find the number of digits and iteratively compute the digits (in the reverse order) at the same time by using the integer division and subtraction together
        # since we are dividing by N_LETTERS each time, N_LETTERS**n_digits turns into 1, thus we do not need the n_digits variable explicitly
    return s

def get_builders(data):
    """ Get a boolean array of the authors that are builders. """
    if 'AuthorType' in data.dtype.names:
        builders = (np.char.lower(data['AuthorType']) == 'builder')
    elif 'JoinedAsBuilder' in data.dtype.names:
        builders = (np.char.lower(data['JoinedAsBuilder']) == 'true')
    else:
        msg = "No builder column found."
        raise ValueError(msg)

    return builders

def get_firsttier(data):
    """ Get a boolean array of the authors that are first tier. """
    if 'FirstTier' in data.dtype.names:
        firsttiers = np.char.isdigit(data['FirstTier']) # basically strings that can be converted to natural numbers (non-negative integers); empty strings can not and are excluded
        if np.any(np.char.str_len(data['FirstTier'][~firsttiers]) > 0):
            logging.warning("Found strings in the FirstTier column that are not empty and do not represent natural numbers (non-negative integers), they will be ignored (affected authors will NOT be considered first-tier).")
        return firsttiers
    else:
        logging.warning("First-tier column (FirstTier) not found. Proceeding without first-tier authors.")
        return np.zeros(len(data), dtype=bool) # no first-tier authors


def write_contributions(filename,data):
    """ Write a file of author contributions. """
    logging.info("Creating contribution list...")
    if 'Contribution' not in data.dtype.names:
        logging.error("No 'Contribution' field.")
        raise Exception()

    cntrbdict = odict()
    for d in data:
        if cntrbdict.get(d['Authorname'],d['Contribution']) != d['Contribution']:
            logging.warning("Non-unique contribution for '%(Authorname)s'"%d)

        cntrbdict[d['Authorname']]=d['Contribution']

    output = r'Author contributions are listed below. \\'+'\n'
    for name, cntrb in cntrbdict.items():
        if cntrb == '':
            logging.warning("Blank contribution for '%s'"%name)

        output += r'%s: %s \\'%(name,cntrb) + '\n'

    logging.info('Writing contribution file: %s'%filename)

    out = open(filename,'w')
    out.write(output)
    out.close()


journal2class = odict([
    ('tex','aastex6'),
    ('revtex','revtex'),
    ('prl','revtex'),
    ('prd','revtex'),
    ('aastex','aastex6'),     # This is for aastex v6.*
    ('aastex5','aastex'),     # This is for aastex v5.*
    ('aastex61','aastex6'),   # This is for aastex v6.1
    ('apj','aastex6'),
    ('apjl','aastex6'),
    ('aj','aastex6'),
    ('mnras','mnras'),
    ('elsevier','elsevier'),
    ('jcap','jcap'),
    ('jcap.appendix','jcap.appendix'),
    ('emulateapj','emulateapj'),
    ('arxiv','arxiv'),
    ('aanda', 'aanda'),
    ('author.xml', 'author.xml'),
    ('inspire', 'author.xml')
])

defaults = dict(
    title = "Publication Title",
    abstract=r"This is a sample document created by \texttt{%s v%s}."%(os.path.basename(__file__),__version__),
    collaboration="DESI Collaboration"
)

### REVTEX ###
revtex_authlist = r"""
%(authors)s

\collaboration{%(collaboration)s}
"""

revtex_document = r"""
\documentclass[reprint,superscriptaddress]{revtex4-1}
\pagestyle{empty}
\begin{document}
\title{%(title)s}

%(authlist)s

\begin{abstract}
%(abstract)s
\end{abstract}
\maketitle
\end{document}
"""

### AASTEX ###
aastex_authlist = r"""
\def\andname{}

\author{
%(authors)s
\\ \vspace{0.2cm} (%(collaboration)s) \\
}

%(affiliations)s
"""

aastex_document = r"""
\documentclass[preprint]{aastex}

\begin{document}
\title{%(title)s}

%(authlist)s

\begin{abstract}
%(abstract)s
\end{abstract}
\maketitle
\end{document}
"""

### AASTEX 6.X ###
aastex6_authlist = r"""
%(authors)s

\collaboration{(%(collaboration)s)}
"""

aastex6_document = r"""
\documentclass[twocolumn]{aastex61}

\begin{document}
\title{%(title)s}

%(authlist)s

\begin{abstract}
%(abstract)s
\end{abstract}
\maketitle
\end{document}
"""

### EMULATEAPJ ###
emulateapj_document = r"""
\documentclass[iop]{emulateapj}

\begin{document}
\title{%(title)s}

%(authlist)s

\begin{abstract}
%(abstract)s
\end{abstract}
\maketitle
\end{document}
"""

### MNRAS ###
mnras_authlist = r"""
\author[%(collaboration)s]{
\parbox{\textwidth}{
\Large
%(authors)s
\begin{center} (%(collaboration)s) \end{center}
}
\vspace{0.4cm}
\\
\parbox{\textwidth}{
%%\scriptsize
%(affiliations)s
}
}
"""

mnras_document = r"""
\documentclass{mnras}
\pagestyle{empty}
\begin{document}
\title{%(title)s}

%(authlist)s

\maketitle
\begin{abstract}
%(abstract)s
\end{abstract}

\end{document}
"""

### JCAP.appendix ###
jcapappendix_authlist = r"""
%(authors)s
"""

jcapappendix_affilist = r"""
%(affiliations)s
"""


### ELSEVIER ###
elsevier_authlist = r"""
%(authors)s

%(affiliations)s
"""

elsevier_document = r"""
\documentclass[final,5p]{elsarticle}
\begin{document}

\begin{frontmatter}
\title{%(title)s}

%(authlist)s

\begin{abstract}
%(abstract)s
\end{abstract}
\end{frontmatter}

\end{document}
"""

### ARXIV ###
arxiv_authlist = r"""%(authors)s"""
arxiv_document = arxiv_authlist

### AANDA ###
aanda_authlist = r"""
\author{
%(authors)s,
%%\begin{center} (%(collaboration)s) \end{center}
}
%%\vspace{0.4cm}

\scriptsize
\institute{
%(affiliations)s
}
"""

aanda_document = r"""
%% If you have a really long author list, you can read A&A style manual and
%% use the \documentclass[longauth]{aa} document style, as well as \longauthor
%% for many collaborators.
%% The Collaboration is included but commented out for same reasons

\documentclass{aa}
%%\pagestyle{empty}

\begin{document}
\title{%(title)s}

%(authlist)s

\abstract{%(abstract)s}

%%\keywords{ -- }


\maketitle
\end{document}
"""

#JCAP

jcap_document = r"""
\documentclass[a4paper,11pt]{article}
\usepackage{jcappub}

\title{%(title)s}

%(authlist)s

\abstract{%(abstract)s}

\begin{document}
\maketitle
\flushbottom

\end{document}
"""

jcap_appendix_document = r"""
\documentclass[a4paper,11pt]{article}
\usepackage{jcappub}

\title{%(title)s}

%(authlist)s

\abstract{%(abstract)s}

\begin{document}
\maketitle
\flushbottom

\appendix

%(affilist)s

\end{document}
"""


if __name__ == "__main__":
    import argparse
    description = __doc__
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=formatter)
    parser.add_argument('infile', metavar='DESI-XXXX-XXXX_author_list.csv',
                        help="input csv file from PubDB")
    parser.add_argument('outfile', metavar='DESI-XXXX-XXXX_author_list.tex',
                        nargs='?', default=None, help="output latex file (optional).")
    parser.add_argument('-a','--aux', metavar='order.csv',
                        help="auxiliary author ordering file (one name per line).")
    parser.add_argument('-c','--collab','--collaboration',
                        default='DESI Collaboration', help="collaboration name.")
    parser.add_argument('-cid', '--collab-id', default='c1',
                        help="The ID for the collaboration (e.g., c1) for INSPIRE author.xml.")
    parser.add_argument('--cntrb','--contributions', nargs='?',
                        const='contributions.tex', help="contribution file.")
    parser.add_argument('-d','--doc', action='store_true',
                        help="create standalone latex document.")
    parser.add_argument('-f','--force', action='store_true',
                        help="force overwrite of output.")
    parser.add_argument('-i','--idx', default=1, type=int,
                        help="starting index for aastex author list \
                        (useful for multi-collaboration papers).")
    parser.add_argument('-j','--journal', default='apj',
                        choices=sorted(journal2class.keys()),
                        help="journal name or latex document class.")
    parser.add_argument('-nc','--nocollab','--nocollaboration', action='store_true',
                        help="exclude the collaboration name (may be desirable in first-tier papers).")
    parser.add_argument('--orcid', action='store_true',
                        help="include ORCID information (elsevier, revtex, aastex, mnras, emulateapj, aanda, inspire or author.xml).")
    parser.add_argument('-pr', '--pubref', metavar='https://arxiv.org/abs/YYMM.XXXXX',
                        help="The publication reference URL (e.g., arXiv link). Needed for INSPIRE author.xml.")
    parser.add_argument('-s','--sort', action='store_true',
                        help="alphabetize the author list (you know you want to...).")
    parser.add_argument('-s1','--sort-firsttier', action='store_true',
                        help="alphabetize the non first tier list. first-tier authors and their order are determined by natural numbers in the FirstTier column that should be added.")
    parser.add_argument('-sb','--sort-builder', action='store_true',
                        help="alphabetize the builder list.")
    parser.add_argument('-sn','--sort-nonbuilder', action='store_true',
                        help="alphabetize the non-builder list.")
    parser.add_argument('-v','--verbose', action='count', default=0,
                        help="verbose output.")
    parser.add_argument('-V','--version', action='version',
                        version='%(prog)s '+__version__,
                        help="print version number and exit.")
    args = parser.parse_args()

    if args.verbose == 1: level = logging.INFO
    elif args.verbose >= 2: level = logging.DEBUG
    else: level = logging.WARNING
    logging.basicConfig(format="%% %(levelname)s: %(message)s", level=level)

    if args.nocollab: args.collab = ""
    defaults['collaboration'] = args.collab

    readlines = open(args.infile).readlines()
    # Check for unescaped umlauts
    lines = check_umlaut(readlines)
    rows = []
    for arow in csv.reader(lines, skipinitialspace=True):
        if len(arow)!=0 and not arow[0].startswith('#'):
            rows.append(arow)

    data = np.rec.fromrecords(rows[1:], names=rows[0])

    isbuilder  = get_builders(data)
    builder    = data[isbuilder]
    nonbuilder = data[~isbuilder]

    if args.sort_builder:
        idx = np.lexsort((np.char.upper(builder['Firstname']),
                          np.char.upper(builder['Lastname'])))
        builder = builder[idx]

    if args.sort_nonbuilder:
        idx = np.lexsort((np.char.upper(nonbuilder['Firstname']),
                          np.char.upper(nonbuilder['Lastname'])))
        nonbuilder = nonbuilder[idx]

    data = np.hstack([nonbuilder,builder])


    if args.sort_firsttier:
        isfirsttier  = get_firsttier(data)
        firsttier    = data[isfirsttier]
        nonfirsttier = data[~isfirsttier]

        idx = np.lexsort((np.char.upper(nonfirsttier['Firstname']),
                          np.char.upper(nonfirsttier['Lastname'])))
        nonfirsttier = nonfirsttier[idx]

        idx = np.lexsort((np.char.upper(firsttier['Firstname']),
                          np.char.upper(firsttier['Lastname']),
                          np.asarray(firsttier['FirstTier'], dtype=int)))
        firsttier = firsttier[idx]

        data = np.hstack([firsttier,nonfirsttier])


    if args.sort:
        idx = np.lexsort((np.char.upper(data['Firstname']),
                          np.char.upper(data['Lastname'])))
        data = data[idx]
        #data = data[np.argsort(np.char.upper(data['Lastname']))]

    cls = journal2class[args.journal.lower()]
    affidict = odict()
    authdict = odict()

    # Hack for umlauts in affiliations...
    for k, v in HACK.items():
        logging.warning("Hacking '%s' ..."%k)
        select = (np.char.count(data['Affiliation'],k) > 0)
        data['Affiliation'][select] = v

    # Pre-sort the csv file by the auxiliary file
    if args.aux is not None:
        auxcols = ['Lastname','Firstname']
        # aux = [[r[c] for c in auxcols] for r in
        #        csv.DictReader(open(args.aux),fieldnames=auxcols)
        #        if not r[auxcols[0]].startswith('#')]
        aux = []
        for r in csv.DictReader(open(args.aux), fieldnames=auxcols):
            if not r[auxcols[0]].startswith('#'):
                aux.append([r[c] for c in auxcols])

        aux = np.rec.fromrecords(aux,names=auxcols)
        if len(np.unique(aux)) != len(aux):
            logging.error('Non-unique names in aux file.')
            print(open(args.aux).read())
            raise Exception()

        # This is probably not the cleanest way to do this...
        raw_auth = [data['Lastname'],data['Firstname'],np.arange(len(data))]
        raw = np.vstack(raw_auth).T

        order = np.empty((0, raw.shape[-1]), dtype=raw.dtype)
        for r in aux:
            lastname = r['Lastname'].strip()
            firstname = r['Firstname']
            match = (raw[:,0] == lastname)

            if firstname:
                firstname = r['Firstname'].strip()
                match &= (raw[:,1] == firstname)

            # Check that match found
            if np.sum(match) < 1:
                msg = "Auxiliary name not found: %s"%(lastname)
                if firstname: msg += ', %s'%firstname
                logging.warning(msg)
                continue

            # Check unique firstname
            if not len(np.unique(raw[match][:,1])) == 1:
                msg = "Non-unique name: %s"%(lastname)
                if firstname: msg += ', %s'%firstname
                logging.error(msg)
                raise ValueError(msg)

            order = np.vstack([order,raw[match]])
            raw = raw[~match]
        order = np.vstack([order,raw])
        data = data[order[:,-1].astype(int)]

    ### REVTEX ###
    if cls in ['revtex','aastex6']:
        if cls == 'revtex':
            document = revtex_document
            authlist = revtex_authlist
        elif cls in ['aastex6']:
            document = aastex6_document
            authlist = aastex6_authlist
        else:
            msg = "Unrecognized latex class: %s"%cls
            raise Exception(msg)

        for d in data:
            if d['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%d['Authorname'])
            if d['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(d['Firstname'],
                                                                d['Lastname']))

            authorkey = '{%s}'%(d['Authorname'])

            if args.orcid and d['ORCID']:
                authorkey = '[%s]'%d['ORCID'] + authorkey

            if authorkey not in authdict.keys():
                authdict[authorkey] = [d['Affiliation']]
            else:
                authdict[authorkey].append(d['Affiliation'])
            #if d['Authorname'] not in authdict.keys():
            #    authdict[d['Authorname']] = [d['Affiliation']]
            #else:
            #    authdict[d['Authorname']].append(d['Affiliation'])

        authors = []
        for key,val in authdict.items():
            #author = r'\author{%s}'%key+'\n'
            author = r'\author%s'%key+'\n'
            for v in val:
                author += r'\affiliation{%s}'%v+'\n'
            author += '\n'
            authors.append(author)
        params = dict(defaults,authors=''.join(authors))

    ### Separate author and affiliation ###
    if cls in ['aastex','mnras','emulateapj', 'aanda']:
        if cls == 'aastex':
            document = aastex_document
            authlist = aastex_authlist
            affilmark = r'\altaffilmark{%s},'
            affiltext = r'\altaffiltext{%s}{%s}'
        elif cls == 'emulateapj':
            document = emulateapj_document
            authlist = aastex_authlist
            affilmark = r'\altaffilmark{%s},'
            affiltext = r'\affil{$^{%s}$ %s}'
        elif cls == 'mnras':
            document = mnras_document
            authlist = mnras_authlist
            affilmark = r',$^{%s}$'
            affiltext = r'$^{%s}$ %s\\'
        elif cls == 'aanda':
            document = aanda_document
            authlist = aanda_authlist
            affilmark = r' \inst{%s},'
            affiltext = r'\and %s '
        else:
            msg = "Unrecognized latex class: %s"%cls
            raise Exception(msg)

        for dat_auth in data:
            authorkey = dat_auth['Authorname']
            if args.orcid and dat_auth['ORCID']: authorkey += r'\orcidlink{%s}'%dat_auth['ORCID']
            print(authorkey)
            if dat_auth['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%dat_auth['Authorname'])
            if dat_auth['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(dat_auth['Firstname'],
                                                                dat_auth['Lastname']))

            if (dat_auth['Affiliation'] not in affidict.keys()):
                affidict[dat_auth['Affiliation']] = str(len(affidict.keys()) + args.idx) # format as string right away for all future usage
            affidx = affidict[dat_auth['Affiliation']]

            if authorkey not in authdict.keys():
                authdict[authorkey] = [affidx]
            else:
                authdict[authorkey].append(affidx)

        affiliations = []
        authors=[]
        for i, (k,v) in enumerate(authdict.items()):
            affmark = affilmark % (','.join(v))
            if i+1==len(authdict):
                # Strip trailing comma from last entry (note MNRAS comma position)
                affmark = affmark.strip(',')
                # Prefix 'and' on last entry (seems robust)
                k = 'and ' + k
            author = k + affmark
            authors.append(author)

        if cls == 'aanda':
            for i, k in enumerate(affidict.keys()):
                institution = k.rstrip(' ').lstrip(' ')
                if institution == '':
                    logging.warning("Blank affiliation in position %d" % (i+1))
                affiliation = affiltext%(institution)
                if i == 0:
                    affiliation = affiliation.lstrip('\\and ')
                affiliations.append(affiliation)
        else:
            for k,v in affidict.items():
                affiliation = affiltext % (v, k)
                affiliations.append(affiliation)

        params = dict(defaults,authors='\n'.join(authors),affiliations='\n'.join(affiliations))

    ### ELSEVIER ###
    if cls in ['elsevier']:
        document = elsevier_document
        authlist = elsevier_authlist
        affiltext = r'\address[%s]{%s}'
        for d in data:
            if d['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%d['Authorname'])
            if d['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(d['Firstname'],
                                                                d['Lastname']))

            if (d['Affiliation'] not in affidict.keys()):
                affidict[d['Affiliation']] = str(len(affidict.keys()) + args.idx) # format as string right away for all future usage
            affidx = affidict[d['Affiliation']]

            if d['Authorname'] not in authdict.keys():
                authdict[d['Authorname']] = [affidx]
            else:
                authdict[d['Authorname']].append(affidx)

        affiliations = []
        authors=[]
        for k,v in authdict.items():
            author = r'\author[%s]{%s}' % (','.join(v), k)
            authors.append(author)

        for k,v in affidict.items():
            affiliation = affiltext % (v, k)
            affiliations.append(affiliation)

        params = dict(defaults,authors='\n'.join(authors).strip(','),affiliations='\n'.join(affiliations))


    ### JCAP ###
    if cls in ['jcap', 'jcap.appendix']:
        if cls == 'jcap':
            document = jcap_document
            authlist = elsevier_authlist
            affiltext = r'\affiliation[%s]{%s}'
            affilsep = '\n'
        elif cls == 'jcap.appendix':
            document = jcap_appendix_document
            authlist = jcapappendix_authlist
            affilist = jcapappendix_affilist
            affiltext = r'\noindent \hangindent=.5cm $^{%s}${%s}'
            affilsep = '\n\n'
        else:
            msg = "Unrecognized latex class: %s"%cls
            raise Exception(msg)
        
        for d in data:
            if d['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%d['Authorname'])
            if d['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(d['Firstname'],
                                                                d['Lastname']))

            authorkey = '{%s}'%(d['Authorname'])

            if args.orcid and d['ORCID']:
                authorkey = authorkey + '\\orcidlink{%s}'%d['ORCID'] 

            if d['Affiliation'] not in affidict.keys():
                affidict[d['Affiliation']] = letter_numeric(len(affidict.keys()) + args.idx) # format as string right away for all future usage
            affidx = affidict[d['Affiliation']]

            if authorkey not in authdict.keys():
                authdict[authorkey] = [affidx]
            else:
                authdict[authorkey].append(affidx)


        affiliations = []
        authors=[]
        for k,v in authdict.items():
            author = r'\author[%s]{%s,}' % (','.join(v), k)
            authors.append(author)

        for k,v in affidict.items():
            affiliation = affiltext % (v, k)
            affiliations.append(affiliation)

        params = dict(defaults, authors='\n'.join(authors).strip(','), affiliations=affilsep.join(affiliations))



    ### ARXIV ###
    if cls in ['arxiv']:
        document = arxiv_document
        if args.sort:
            authlist = '%(collaboration)s: ' + arxiv_authlist
        elif args.nocollab: # do not add the collaboration
            authlist = arxiv_authlist
        else:
            authlist = arxiv_authlist + ' (%(collaboration)s)'

        for d in data:
            if d['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(d['Firstname'],
                                                                d['Lastname']))
            if (d['Affiliation'] not in affidict.keys()):
                affidict[d['Affiliation']] = len(affidict.keys())
            affidx = affidict[d['Affiliation']]

            if d['Authorname'] not in authdict.keys():
                authdict[d['Authorname']] = [affidx]
            else:
                authdict[d['Authorname']].append(affidx)

        authors=[]
        for k,v in authdict.items():
            authors.append(clean_latex_to_text(k))

        params = dict(defaults,authors=', '.join(authors).strip(','),affiliations='')
    
    # INSPIRE author.xml
    # Based on mkauthorxml.py by Paul Martini
    # The format is explained at https://github.com/inspirehep/author.xml
    if cls in ['author.xml']:
        authors_data = {}
        affidict = {}
        converter = LatexNodes2Text()
        for dat_auth in data:
            authorkey = converter.latex_to_text(clean_latex_to_text(dat_auth['Authorname']))
            # converter.latex_to_text converts the LaTeX accented characters (probably unwanted in XML) to Unicode
            # clean_latex_to_text should safely remove "~" designating non-breakable spaces, which we probably do not want in XML
            if authorkey not in authors_data.keys(): authors_data[authorkey] = {'affiliations': []}
            if args.orcid and dat_auth['ORCID']: authors_data[authorkey]['orcid'] = dat_auth['ORCID']
            if dat_auth['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%dat_auth['Authorname'])
            if dat_auth['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(dat_auth['Firstname'],
                                                                dat_auth['Lastname']))
            authors_data[authorkey]['familyName'] = dat_auth['Lastname'] # hopefully this is not simplifying too much
            affikey = converter.latex_to_text(clean_latex_to_text(dat_auth['Affiliation']))
            # converter.latex_to_text converts the LaTeX accented characters (probably unwanted in XML) to Unicode
            # clean_latex_to_text should safely remove "~" designating non-breakable spaces, which we probably do not want in XML
            if affikey not in affidict.keys(): affidict[affikey] = "a%d" % (len(affidict.keys()) + args.idx) # IDs are assigned as a%d right away, by default starting from a1
            affidx = affidict[affikey]
            authors_data[authorkey]['affiliations'].append(affidx)

        ET.register_namespace('foaf', "http://xmlns.com/foaf/0.1/")
        ET.register_namespace('cal', "http://inspirehep.net/info/HepNames/tools/authors_xml/")

        # --- Build the XML structure ---
        ns = {'foaf': 'http://xmlns.com/foaf/0.1/', 'cal': 'http://inspirehep.net/info/HepNames/tools/authors_xml/'}
        root = ET.Element('collaborationauthorlist')

        ET.SubElement(root, f"{{{ns['cal']}}}creationDate").text = date.today().isoformat()
        if not args.pubref:
            logging.warning("Publication reference must be included for valid author.xml. Use `-pr ...` or `--pubref ...` to provide, e.g., an arXiv number, collaboration internal publication identifier, or DOI.")
        ET.SubElement(root, f"{{{ns['cal']}}}publicationReference").text = args.pubref
        if args.nocollab:
            logging.warning("Collaboration information must be included for valid author.xml.")
        else:
            collaborations = ET.SubElement(root, f"{{{ns['cal']}}}collaborations")
            collaboration = ET.SubElement(collaborations, f"{{{ns['cal']}}}collaboration", {'id': args.collab_id})
            ET.SubElement(collaboration, f"{{{ns['foaf']}}}name").text = defaults['collaboration']
        organizations = ET.SubElement(root, f"{{{ns['cal']}}}organizations")
        for text, org_id in affidict.items():
            org = ET.SubElement(organizations, f"{{{ns['foaf']}}}Organization", {'id': org_id})
            ET.SubElement(org, f"{{{ns['foaf']}}}name").text = text
        authors_xml = ET.SubElement(root, f"{{{ns['cal']}}}authors")
        for name, data in authors_data.items():
            person = ET.SubElement(authors_xml, f"{{{ns['foaf']}}}Person")
            ET.SubElement(person, f"{{{ns['foaf']}}}familyName").text = data['familyName']
            ET.SubElement(person, f"{{{ns['cal']}}}authorNamePaper").text = name
            affs = ET.SubElement(person, f"{{{ns['cal']}}}authorAffiliations")
            for aff_id in data['affiliations']:
                ET.SubElement(affs, f"{{{ns['cal']}}}authorAffiliation", {'organizationid': aff_id})
            if 'orcid' in data.keys():
                ids = ET.SubElement(person, f"{{{ns['cal']}}}authorids")
                ET.SubElement(ids, f"{{{ns['cal']}}}authorid", {'source': 'ORCID'}).text = data['orcid']

        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
        doctype_header = '<!DOCTYPE collaborationauthorlist SYSTEM "author.dtd">\n'

        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        # Return the XML split into lines, and replace the header
        string_list = [xml_header, doctype_header] + reparsed.toprettyxml(indent="  ").splitlines(True)[1:]

        if args.outfile is None:
            print("".join(string_list), end="")
        else:
            outfile = args.outfile
            if os.path.exists(outfile) and not args.force:
                logging.warning("Found %s; skipping..."%outfile)
            with open(outfile, 'w', encoding='utf-8') as f:
                f.writelines(string_list)

        sys.exit(0) # this is a special case, which does not need the further processing
    
    if args.nocollab: # exclude the collaboration. beware of the following hacks when adding/editing journal templates
        authlist = authlist.replace("[%(collaboration)s]", "") # remove the optional collaboration argument (from the MNRAS template)
        authlist = "".join([line for line in authlist.splitlines(keepends=True) if "collaboration" not in line]) # now, should be safe to remove any lines mentioning the collaboration

    output  = "%% Author list file generated with: %s %s \n"%(parser.prog, __version__ )
    output += "%% %s %s \n"%(os.path.basename(sys.argv[0]),' '.join(sys.argv[1:]))
    if cls not in ['arxiv']: # non-TeX "journal(s)" for which the following lines are not relevant; author.xml case does not get to this point exiting above
        if args.orcid: output += "%% Orcid numbers may need \\usepackage{orcidlink}.\n"
        if not args.doc: output += "%% Use \\input{%s} to call the file\n"%(args.outfile if args.outfile is not None else '...')
    output += "\n"

    if cls in ['jcap.appendix']:
        if args.sort_firsttier: authlist = "\\emailAdd{firstauthor@email}\n" + authlist
        else: authlist = "\\author{{DESI Collaboration}:}\n\\emailAdd{spokespersons@desi.lbl.gov}\n" + authlist
        authlist = "\\affiliation{Affiliations are in Appendix \\ref{sec:affiliations}}\n" + authlist
        affilist = "\\section{Author Affiliations}\n\\label{sec:affiliations}\n\n" + affilist


    if args.doc:
        params['authlist'] = authlist%params
        if cls in ['jcap.appendix']: params['affilist'] = affilist % params
        output += document%params
    else:
        output += authlist%params
        if cls in ['jcap.appendix']: 
            output2  = "%% Author list file generated with: %s %s \n"%(parser.prog, __version__ )
            output2 += "%% Affiliations file. Use \\input to call it after \\appendix\n\n\n"
            output2 += affilist % params


    if args.outfile is None:
        print(output)
        if cls in ['jcap.appendix'] and not args.doc:
            print()
            print(output2)
    else:
        outfile = args.outfile
        if os.path.exists(outfile) and not args.force:
            logging.warning("Found %s; skipping..."%outfile)
        out = open(outfile,'w')
        out.write(output)
        out.close()
        if cls in ['jcap.appendix'] and not args.doc:
            outfile2 = outfile.removesuffix(".tex") + ".affiliations.tex"
            out2 = open(outfile2,'w')
            out2.write(output2)
            out2.close()

    if args.cntrb:
        write_contributions(args.cntrb,data)
