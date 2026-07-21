#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from thunderomlx_cache_warm_advisor_closeout import auto_closeout_thunderomlx_cache_warm_advisor  # noqa: E402


def _resolve_runtime_root() -> Path:
    repo_candidate = ROOT
    runtime_candidate = Path.home() / ".solar" / "harness"
    sprint_path = "sprints/sprint-20260520-thunderomlx-cache-warm-advisor.task_graph.json"
    if (repo_candidate / sprint_path).exists():
        return repo_candidate
    if (runtime_candidate / sprint_path).exists():
        return runtime_candidate
    return repo_candidate


def main() -> int:
    runtime_root = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else _resolve_runtime_root()
    result = auto_closeout_thunderomlx_cache_warm_advisor(runtime_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
