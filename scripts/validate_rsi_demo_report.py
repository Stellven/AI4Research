#!/usr/bin/env python3
"""Delegator — the canonical RSI demo report validator ships INSIDE the
harness tree (harness/scripts/validate_rsi_demo_report.py) so installed and
sandboxed harnesses carry it: the workflow-contract D3/D6 gates run
`python3 scripts/validate_rsi_demo_report.py ...` with cwd == HARNESS_DIR.
This repo-root shim keeps dev/CI invocations (cwd == a demo workspace)
working; it forwards argv and inherits cwd."""
import os
import sys
import pathlib

_CANONICAL = pathlib.Path(__file__).resolve().parents[1] / "harness" / "scripts" / "validate_rsi_demo_report.py"
os.execv(sys.executable, [sys.executable, str(_CANONICAL), *sys.argv[1:]])
