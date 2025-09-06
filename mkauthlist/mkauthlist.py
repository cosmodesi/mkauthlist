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
    for i,d in enumerate(data):
        if cntrbdict.get(d['Authorname'],d['Contribution']) != d['Contribution']:
            logging.warning("Non-unique contribution for '%(Authorname)s'"%d)

        cntrbdict[d['Authorname']]=d['Contribution']

    output = r'Author contributions are listed below. \\'+'\n'
    for i,(name,cntrb) in enumerate(cntrbdict.items()):
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

        for i,d in enumerate(data):
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
            affiltext = r'\altaffiltext{%i}{%s}'
        elif cls == 'emulateapj':
            document = emulateapj_document
            authlist = aastex_authlist
            affilmark = r'\altaffilmark{%s},'
            affiltext = r'\affil{$^{%i}$ %s}'
        elif cls == 'mnras':
            document = mnras_document
            authlist = mnras_authlist
            affilmark = r',$^{%s}$'
            affiltext = r'$^{%i}$ %s\\'
        elif cls == 'aanda':
            document = aanda_document
            authlist = aanda_authlist
            affilmark = r' \inst{%s},'
            affiltext = r'\and %s '
        else:
            msg = "Unrecognized latex class: %s"%cls
            raise Exception(msg)

        for iauth, dat_auth in enumerate(data):
            authorkey = dat_auth['Authorname']
            if args.orcid and dat_auth['ORCID']: authorkey += r'\orcidlink{%s}'%dat_auth['ORCID']
            print(authorkey)
            if dat_auth['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%dat_auth['Authorname'])
            if dat_auth['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(dat_auth['Firstname'],
                                                                dat_auth['Lastname']))

            if (dat_auth['Affiliation'] not in affidict.keys()):
                affidict[dat_auth['Affiliation']] = len(affidict.keys())
            affidx = affidict[dat_auth['Affiliation']]

            if authorkey not in authdict.keys():
                authdict[authorkey] = [affidx]
            else:
                authdict[authorkey].append(affidx)

        affiliations = []
        authors=[]
        for i, (k,v) in enumerate(authdict.items()):
            affmark = affilmark%(','.join([str(_v+args.idx) for _v in v]))
            if i+1==len(authdict):
                # Strip trailing comma from last entry (note MNRAS comma position)
                affmark = affmark.strip(',')
                # Prefix 'and' on last entry (seems robust)
                k = 'and ' + k
            author = k + affmark
            authors.append(author)

        if cls == 'aanda':
            for k, v in affidict.items():
                institution = k.rstrip(' ').lstrip(' ')
                if institution == '':
                    pass #continue
                affiliation = affiltext%(institution)
                if v == 0:
                    affiliation = affiliation.lstrip('\\and ')
                affiliations.append(affiliation)
        else:
            for k,v in affidict.items():
                affiliation = affiltext%(v+args.idx,k)
                affiliations.append(affiliation)

        params = dict(defaults,authors='\n'.join(authors),affiliations='\n'.join(affiliations))

    ### ELSEVIER ###
    if cls in ['elsevier']:
        document = elsevier_document
        authlist = elsevier_authlist
        affilmark = r'%i,'
        affiltext = r'\address[%i]{%s}'
        for i,d in enumerate(data):
            if d['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%d['Authorname'])
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

        affiliations = []
        authors=[]
        for k,v in authdict.items():
            author = r'\author[%s]{%s}'%(','.join([str(_v+args.idx) for _v in v]),k)
            authors.append(author)

        for k,v in affidict.items():
            affiliation = affiltext%(v+args.idx,k)
            affiliations.append(affiliation)

        params = dict(defaults,authors='\n'.join(authors).strip(','),affiliations='\n'.join(affiliations))


    ### JCAP ###
    if cls in ['jcap']:
        document = elsevier_document
        authlist = elsevier_authlist
        affilmark = r'%i,'
        affiltext = r'\affiliation[%i]{%s}'
        for i,d in enumerate(data):
            if d['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%d['Authorname'])
            if d['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(d['Firstname'],
                                                                d['Lastname']))

            authorkey = '{%s}'%(d['Authorname'])

            if args.orcid and d['ORCID']:
                authorkey = authorkey + '\\orcidlink{%s}'%d['ORCID'] 

            if (d['Affiliation'] not in affidict.keys()):
                affidict[d['Affiliation']] = len(affidict.keys())
            affidx = affidict[d['Affiliation']]

            if authorkey not in authdict.keys():
                authdict[authorkey] = [affidx]
            else:
                authdict[authorkey].append(affidx)


        affiliations = []
        authors=[]
        for k,v in authdict.items():
            author = r'\author[%s]{%s,}'%(','.join([str(_v+args.idx) for _v in v]),k)
            authors.append(author)

        for k,v in affidict.items():
            affiliation = affiltext%(v+args.idx,k)
            affiliations.append(affiliation)

        params = dict(defaults,authors='\n'.join(authors).strip(','),affiliations='\n'.join(affiliations))


    ### JCAP.appendix ###
    if cls in ['jcap.appendix']:
        document = elsevier_document
        authlist = jcapappendix_authlist
        affilist = jcapappendix_affilist
        affilmark = r'%i,'
        affiltext = r'\noindent \hangindent=.5cm $^{%i}${%s}'
        for i,d in enumerate(data):
            if d['Affiliation'] == '':
                logging.warning("Blank affiliation for '%s'"%d['Authorname'])
            if d['Authorname'] == '':
                logging.warning("Blank authorname for '%s %s'"%(d['Firstname'],
                                                                d['Lastname']))

            authorkey = '{%s}'%(d['Authorname'])

            if args.orcid and d['ORCID']:
                authorkey = authorkey + '\\orcidlink{%s}'%d['ORCID'] 

            if (d['Affiliation'] not in affidict.keys()):
                affidict[d['Affiliation']] = len(affidict.keys())
            affidx = affidict[d['Affiliation']]

            if authorkey not in authdict.keys():
                authdict[authorkey] = [affidx]
            else:
                authdict[authorkey].append(affidx)


        affiliations = []
        authors=[]
        for k,v in authdict.items():
            author = r'\author[%s]{%s,}'%(','.join([str(_v+args.idx) for _v in v]),k)
            authors.append(author)

        for k,v in affidict.items():
            affiliation = affiltext%(v+args.idx,k)
            affiliations.append(affiliation)


        params = dict(authors='\n'.join(authors).strip(','), affiliations='\n\n'.join(affiliations))



    ### ARXIV ###
    if cls in ['arxiv']:
        document = arxiv_document
        if args.sort:
            authlist = '%(collaboration)s: ' + arxiv_authlist
        elif args.nocollab: # do not add the collaboration
            authlist = arxiv_authlist
        else:
            authlist = arxiv_authlist + ' (%(collaboration)s)'

        for i,d in enumerate(data):
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
        for iauth, dat_auth in enumerate(data):
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
            authors_data[authorkey]['familyName'] = dat_auth['Lastname']
            affikey = converter.latex_to_text(clean_latex_to_text(dat_auth['Affiliation']))
            # converter.latex_to_text converts the LaTeX accented characters (probably unwanted in XML) to Unicode
            # clean_latex_to_text should safely remove "~" designating non-breakable spaces, which we probably do not want in XML
            if (affikey not in affidict.keys()):
                affidict[affikey] = "aff%d"%len(affidict.keys())
            affidx = affidict[affikey]
            authors_data[authorkey]['affiliations'].append(affidx)

        ET.register_namespace('foaf', "http://xmlns.com/foaf/0.1/")
        ET.register_namespace('cal', "http://inspirehep.net/info/HepNames/tools/authors_xml/")

        # --- Build the XML structure ---
        ns = {'foaf': 'http://xmlns.com/foaf/0.1/', 'cal': 'http://inspirehep.net/info/HepNames/tools/authors_xml/'}
        root = ET.Element('collaborationauthorlist')

        ET.SubElement(root, f"{{{ns['cal']}}}creationDate").text = date.today().isoformat()
        ET.SubElement(root, f"{{{ns['cal']}}}publicationReference").text = args.pubref
        if not args.nocollab:
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
                ET.SubElement(affs, f"{{{ns['cal']}}}authorAffiliation", {'organizationid': aff_id, 'connection': ''})
            if 'orcid' in data.keys():
                ids = ET.SubElement(person, f"{{{ns['cal']}}}authorids")
                ET.SubElement(ids, f"{{{ns['cal']}}}authorid", {'source': 'ORCID'}).text = data['orcid']

        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
        doctype_header = '<!DOCTYPE collaborationauthorlist SYSTEM "author.dtd">\n'

        rough_string = ET.tostring(root, 'utf-8')
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

        sys.exit(0) # the templates are not set for the next formattijng
    
    if args.nocollab: # exclude the collaboration. beware of the following hacks when adding/editing journal templates
        authlist = authlist.replace("[%(collaboration)s]", "") # remove the optional collaboration argument (from the MNRAS template)
        authlist = "".join([line for line in authlist.splitlines(keepends=True) if "collaboration" not in line]) # now, should be safe to remove any lines mentioning the collaboration

    output  = "%% Author list file generated with: %s %s \n"%(parser.prog, __version__ )
    output += "%% %s %s \n"%(os.path.basename(sys.argv[0]),' '.join(sys.argv[1:]))
    if cls not in ['arxiv']: # non-TeX "journal(s)" for which the following lines are not relevant
        if args.orcid: output += "%% Orcid numbers may need \\usepackage{orcidlink}.\n"
        output += "%% Use \\input{%s} to call the file\n"%(args.outfile if args.outfile is not None else '...')
    output += "\n"

    if cls in ['jcap.appendix']: 
        if args.sort_firsttier: output += "\\emailAdd{firstauthor@email}\n\\affiliation{Affiliations are in Appendix \\ref{sec:affiliations}}\n"
        else: output += "\\author{{DESI Collaboration}:}\n\\emailAdd{spokespersons@desi.lbl.gov}\n\\affiliation{Affiliations are in Appendix \\ref{sec:affiliations}}\n"


    if args.doc:
        params['authlist'] = authlist%params
        output += document%params
    else:
        output += authlist%params
        if cls in ['jcap.appendix']: 
            output2  = "%% Author list file generated with: %s %s \n"%(parser.prog, __version__ )
            output2 += "%% Affiliations file. Use \\input to call it after \\appendix\n\n\n"
            output2 += "\\section{Author Affiliations}\n\\label{sec:affiliations}\n\n"
            output2 += affilist%params


    if args.outfile is None:
        print(output)
    else:
        outfile = args.outfile
        if os.path.exists(outfile) and not args.force:
            logging.warning("Found %s; skipping..."%outfile)
        out = open(outfile,'w')
        out.write(output)
        out.close()
        if cls in ['jcap.appendix']: 
#            import os
#            outfile2 = os.path.splitext(outfile)+".affiliations.tex"
            outfile2 = outfile[:-len(".tex")] + ".affiliations.tex"
            out2 = open(outfile2,'w')
            out2.write(output2)
            out2.close()

    if args.cntrb:
        write_contributions(args.cntrb,data)
