#!/usr/bin/env python3
"""Entry point for solar-harness experience <subcommand>."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from experience.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
