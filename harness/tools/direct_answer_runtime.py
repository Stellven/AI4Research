#!/usr/bin/env python3
"""Run Solar's downstream no-DAG direct-answer path for one compiled sprint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


HARNESS_DIR = Path(os.environ.get("SOLAR_HARNESS_DIR", Path(__file__).resolve().parents[1]))
LIB_DIR = HARNESS_DIR / "lib"
if str(LIB_DIR) in sys.path:
    sys.path.remove(str(LIB_DIR))
sys.path.insert(0, str(LIB_DIR))

from direct_answer_runtime import run_direct_answer  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprint-id", required=True)
    args = parser.parse_args(argv)
    result = run_direct_answer(harness_dir=HARNESS_DIR, sprint_id=args.sprint_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
