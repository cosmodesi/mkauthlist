import sys
import re
from pylatexenc.latex2text import LatexNodes2Text

infile = sys.argv[1]
outfile = sys.argv[2]

authorlist = []
converter = LatexNodes2Text()
with open(infile) as f:
    for l in f.readlines():
        if m := re.fullmatch(r"\\author\[\d+(,\d+)*\]\{\{(?P<name>.+?)\}(\\orcidlink\{\w{4}(-\w{4}){3}\s?\})*,?\}", l.rstrip()):
            name = re.sub(r"\s+", " ", converter.latex_to_text(m["name"]))
            print(m["name"], name)
            authorlist.append(name)

print(len(authorlist))
with open(outfile, "w") as f:
    f.write(", ".join(authorlist))