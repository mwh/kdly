# Copyright 2025 Michael Homer. See LICENSE for details.
import sys
import pathlib

from .parser import parse


if len(sys.argv) > 1:
    source = pathlib.Path(sys.argv[1]).read_text()
else:
    print("Usage: python -m kdly <filename.kdl>")
    print("Reads the KDL file and prints its contents.")
    sys.exit(1)
document = parse(source)
print(document.stringify(), end='')
if len(document) == 0:
    print()
