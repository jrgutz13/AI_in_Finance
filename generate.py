#!/usr/bin/env python3
"""Entry point: python3 generate.py --duration 3h --resolution 1920x1080"""
import sys

from portal_machine.cli import main

if __name__ == "__main__":
    sys.exit(main())
