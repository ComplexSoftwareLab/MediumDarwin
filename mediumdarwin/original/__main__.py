#!/usr/bin/env python3

"""
__main__ script for littledarwin package
"""

from mediumdarwin.original import LittleDarwin
import sys


def entryPoint():
    LittleDarwin.main()


if __name__ == "__main__":
    sys.exit(entryPoint())
