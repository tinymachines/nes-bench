#!/usr/bin/env python3
"""Load one of this repo's tools as a module, from source, every time.

Several tools here read another tool by path: the netlist and the parts
list import the schematic generator, the notebook imports the bring-up
tool. `importlib.util.spec_from_file_location` does that, and it also
consults `__pycache__`, which is where this bit me.

MEASURED 2026-09-09. A mutation test edited draw-schematics.py, ran, and
restored the file. The edit swapped "C2", "C3" for "C1", "C1": the same
number of characters. The edit and the restore happened inside the same
second. A .pyc is validated against the source's mtime **truncated to
whole seconds** and its size in bytes, and both matched, so Python kept
running the mutant's bytecode against the restored source. The mutation
test reported the restored file as still broken, which reads exactly
like a failed restore and sent me looking in the wrong place.

Compiling from source each time costs a few milliseconds on a 43 KB file
and removes the whole class. A tool that reads another tool should read
the file, not a memory of it.
"""
import sys
import types
from pathlib import Path


def load(path, name=None, argv=None):
    """Execute `path` as a fresh module. `argv` replaces sys.argv while
    it runs, because these tools parse arguments at import time."""
    path = Path(path)
    m = types.ModuleType(name or path.stem.replace("-", "_"))
    m.__file__ = str(path)
    saved, sys.argv = sys.argv, list(argv or [sys.argv[0]])
    try:
        exec(compile(path.read_text(), str(path), "exec"), m.__dict__)
    finally:
        sys.argv = saved
    return m
