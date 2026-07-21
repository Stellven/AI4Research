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

from hf_s02_architecture_closeout import auto_closeout_hf_s02_architecture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="~/.solar/harness")
    args = parser.parse_args()

    result = auto_closeout_hf_s02_architecture(Path(args.runtime_root))
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print("ok: generated HF S02 architecture closeout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
