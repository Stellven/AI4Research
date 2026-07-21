#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from browser_agent_research_operators_closeout import (  # noqa: E402
    auto_closeout_browser_agent_research_operators,
)


def main() -> int:
    runtime_root = ROOT
    result = auto_closeout_browser_agent_research_operators(runtime_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
