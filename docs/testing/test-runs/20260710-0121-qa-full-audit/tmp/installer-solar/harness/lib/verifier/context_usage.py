#!/usr/bin/env python3
"""Verify runtime context sidecar source usage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def required_sources_for_task(task_kind: str) -> list[str]:
    if task_kind == "code":
        return ["cocoindex"]
    if task_kind in {"paper", "doc"}:
        return ["understanding"]
    return []


def verify_sidecar(sidecar: dict[str, Any], *, task_kind: str | None = None) -> dict[str, Any]:
    effective_kind = task_kind or str(sidecar.get("task_kind") or "general")
    required = list(sidecar.get("required_sources") or required_sources_for_task(effective_kind))
    counts = sidecar.get("context_sources") or sidecar.get("source_counts") or {}
    used = set(sidecar.get("used_sources") or [k for k, v in counts.items() if int(v or 0) > 0])
    missing = [source for source in required if source not in used]
    degraded = list(sidecar.get("degraded_sources") or [])
    lineage_refs = list(sidecar.get("lineage_refs") or [])
    source_hash_refs = list(sidecar.get("source_hash_refs") or [])
    ok = not missing and bool(lineage_refs or source_hash_refs or not required)
    return {
        "ok": ok,
        "task_kind": effective_kind,
        "required_sources": required,
        "used_sources": sorted(used),
        "missing_sources": missing,
        "degraded_sources": degraded,
        "lineage_refs_count": len(lineage_refs),
        "source_hash_refs_count": len(source_hash_refs),
        "replayable": bool(lineage_refs or source_hash_refs),
    }


def verify_sidecar_file(path: Path, *, task_kind: str | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = verify_sidecar(data, task_kind=task_kind)
    result["sidecar"] = str(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="verify runtime context usage sidecar")
    parser.add_argument("sidecar")
    parser.add_argument("--task-kind", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify_sidecar_file(Path(args.sidecar), task_kind=args.task_kind)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("ok" if result["ok"] else "error")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
