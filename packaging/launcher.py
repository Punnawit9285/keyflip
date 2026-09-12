"""Frozen-app entry point.

PyInstaller runs the entry script as a top-level module, so it cannot be
src/keyflip/__main__.py - the relative imports in there have no package to
resolve against.  Import absolutely instead.
"""

import sys

from keyflip.app import main

if __name__ == "__main__":
    sys.exit(main())
