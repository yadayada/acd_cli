import os
import re

files = ('README.rst', 'CONTRIBUTING.rst')

# replace GitHub external links by :doc: links
replacements = (('`([^`]*?) <(docs/)?(.*?)\.rst>`_', ':doc:`\g<1> <\g<3>>`'),)


def read(fname: str) -> str:
        return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()

for file in files:
    c = read('../' + file)
    for r in replacements:
        c = re.sub(r[0], r[1], c)
    with open(file, 'w') as f:
        f.write(c)
