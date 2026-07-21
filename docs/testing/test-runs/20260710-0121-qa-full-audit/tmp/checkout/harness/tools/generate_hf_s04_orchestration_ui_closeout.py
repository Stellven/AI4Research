#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from hf_s04_orchestration_ui_closeout import auto_closeout_hf_s04_orchestration_ui  # noqa: E402


def main() -> int:
    result = auto_closeout_hf_s04_orchestration_ui(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
