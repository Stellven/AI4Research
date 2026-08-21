#!/usr/bin/env python3
"""Run the fixed no-network evidence-lineage benchmark."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained(raw: str, root: Path, *, label: str) -> Path:
    path = (root / raw).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes work_dir") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file")
    return path


def _load(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def run(work_dir: Path, handoff_path: Path, plan_path: Path, output_path: Path) -> dict[str, Any]:
    started = time.monotonic_ns()
    handoff = _load(handoff_path, label="handoff")
    plan = _load(plan_path, label="plan")
    handoff_rows = {
        str(item.get("path") or ""): item
        for item in handoff.get("artifacts") or []
        if isinstance(item, dict) and str(item.get("path") or "")
    }
    checks: list[dict[str, Any]] = []
    for expected in (plan.get("benchmark") or {}).get("inputs") or []:
        if not isinstance(expected, dict):
            continue
        relative = str(expected.get("path") or "")
        expected_sha = str(expected.get("sha256") or "").lower()
        handoff_row = handoff_rows.get(relative) or {}
        path = _contained(relative, work_dir, label="benchmark input")
        actual_sha = _sha256(path)
        passed = (
            len(expected_sha) == 64
            and actual_sha == expected_sha
            and str(handoff_row.get("sha256") or "").lower() == expected_sha
        )
        checks.append(
            {
                "path": relative,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "handoff_sha256": str(handoff_row.get("sha256") or "").lower(),
                "passed": passed,
            }
        )
    passed_count = sum(1 for item in checks if item["passed"])
    completed = time.monotonic_ns()
    payload = {
        "schema": "solar.fixed_research.benchmark_raw.v1",
        "benchmark_id": "evidence-lineage-integrity-v1",
        "network_namespace": "isolated_by_unshare",
        "checks": checks,
        "metrics": {
            "checks_total": len(checks),
            "checks_passed": passed_count,
            "integrity_rate": (passed_count / len(checks)) if checks else 0.0,
            "duration_ms": round((completed - started) / 1_000_000, 3),
        },
        "passed": bool(checks) and passed_count == len(checks),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        work_dir = args.work_dir.resolve(strict=True)
        handoff = args.handoff.resolve(strict=True)
        plan = args.plan.resolve(strict=True)
        output = args.output.resolve(strict=False)
        output.parent.resolve(strict=True).relative_to(work_dir)
        result = run(work_dir, handoff, plan, output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(json.dumps({"ok": result["passed"], "metrics": result["metrics"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
