#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from epic_projection_closeout import close_epic_projection


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epic_id")
    args = ap.parse_args()
    runtime_root = Path(__file__).resolve().parents[1]
    result = close_epic_projection(runtime_root, args.epic_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
