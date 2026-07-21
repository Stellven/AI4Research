#!/usr/bin/env python3
"""Normalize review routing for handoff-complete sprints.

Remote/lab builders occasionally set status=reviewing but leave handoff_to or
target_role pointed at builder. The coordinator should repair that state before
dispatching so review always goes to evaluator without manual intervention.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_status(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    status = data.get("status", "")
    phase = data.get("phase", "")
    handoff_to = data.get("handoff_to", "")
    target_role = data.get("target_role", "")

    if status not in {"reviewing", "ready_for_review"}:
        return data, False
    if phase not in {"implementation_complete", "build_complete", "builder_handoff_complete", ""}:
        return data, False
    if handoff_to not in {"builder", "builder_main", ""} and target_role not in {"builder", "builder_main", ""}:
        return data, False

    changed = False
    if handoff_to != "evaluator":
        data["handoff_to"] = "evaluator"
        changed = True
    if target_role != "evaluator":
        data["target_role"] = "evaluator"
        changed = True

    if changed:
        ts = _now()
        data["updated_at"] = ts
        data.setdefault("history", []).append(
            {
                "ts": ts,
                "event": "review_route_normalized",
                "by": "coordinator",
                "note": "status=reviewing with builder routing normalized to evaluator before review dispatch",
            }
        )
    return data, changed


def normalize_file(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    normalized, changed = normalize_status(data)
    if changed:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    return changed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: reviewing_route_normalizer.py <status.json>", file=sys.stderr)
        return 2
    changed = normalize_file(Path(argv[1]))
    print("normalized" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
