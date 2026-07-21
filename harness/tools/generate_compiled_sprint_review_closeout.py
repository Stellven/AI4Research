#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from compiled_sprint_review_closeout import closeout_compiled_sprint


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="~/.solar/harness")
    parser.add_argument("--sprint-id", required=True)
    args = parser.parse_args()

    result = closeout_compiled_sprint(Path(args.runtime_root), args.sprint_id)
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
