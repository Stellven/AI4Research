#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from gemini_deep_research_s05_closeout import auto_closeout_gemini_dr_s05_verification_release


def main() -> int:
    runtime_root = Path.home() / ".solar" / "harness"
    result = auto_closeout_gemini_dr_s05_verification_release(runtime_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
