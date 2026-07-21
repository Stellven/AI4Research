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

from hf_s03_core_runtime_closeout import NODE_IDS, auto_closeout_hf_s03_nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="~/.solar/harness")
    parser.add_argument("--node", action="append", default=[])
    args = parser.parse_args()

    selected = tuple(args.node) if args.node else NODE_IDS
    result = auto_closeout_hf_s03_nodes(Path(args.runtime_root), selected)
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
