#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from compiled_sprint_planner import generate_planner_artifacts


def _render_html(runtime_root: Path, sprint_id: str, kind: str) -> dict[str, object]:
    script = runtime_root / "lib" / "render_sprint_html.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "render",
            "--sid",
            sprint_id,
            "--kind",
            kind,
            "--register",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="~/.solar/harness")
    parser.add_argument("--sprint-id", required=True)
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root)
    result = generate_planner_artifacts(runtime_root=runtime_root, sprint_id=args.sprint_id)
    if not result.get("ok"):
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    result["design_html"] = _render_html(runtime_root, args.sprint_id, "design")
    result["planning_html"] = _render_html(runtime_root, args.sprint_id, "planning")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
