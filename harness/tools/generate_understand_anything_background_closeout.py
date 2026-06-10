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

from understand_anything_background_closeout import auto_closeout_understand_anything_background


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="~/.solar/harness")
    parser.add_argument("--target-repo", default="~/Solar")
    args = parser.parse_args()

    result = auto_closeout_understand_anything_background(
        runtime_root=Path(args.runtime_root),
        target_repo=Path(args.target_repo),
    )
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print("ok: generated understand-anything background closeout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
