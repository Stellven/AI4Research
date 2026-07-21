#!/usr/bin/env python3
"""
verify-workstream-ledger.py — Sprint ledger truth checker
Sprint: sprint-20260508-workstream-verification-closeout  A1

Scans sprint-20260507-* and sprint-20260508-* status files,
compares declared status against required artifact presence,
and reports discrepancies.

Usage:
  python3 verify-workstream-ledger.py [--json] [--sprint-glob PATTERN]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
SPRINTS_DIR = HARNESS_DIR / "sprints"


def _check_sprint(sf: Path) -> dict:
    try:
        d = json.loads(sf.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"sprint_id": sf.stem.replace(".status", ""), "status": "unreadable", "issues": [str(e)], "verdict": "error", "artifacts": {}, "priority": "", "lane": "", "title": ""}

    sid = d.get("id", d.get("sprint_id", sf.stem.replace(".status", "")))
    status = d.get("status", "unknown")
    issues = []
    artifacts = {}

    def has(suffix: str) -> bool:
        p = SPRINTS_DIR / f"{sid}{suffix}"
        exists = p.exists() and p.stat().st_size > 0
        artifacts[suffix] = "present" if exists else "missing"
        return exists

    if status in ("passed", "finalized"):
        if not has(".eval.md"):
            issues.append("PASS claimed but .eval.md missing")
        if not has(".finalized"):
            issues.append("PASS claimed but .finalized missing")

    elif status == "reviewing":
        if not has(".handoff.md") and not has(".handoff-s1.md"):
            issues.append("reviewing but no handoff artifact (handoff.md or handoff-s1.md)")

    elif status in ("active", "planning_complete"):
        if not has(".plan.md"):
            issues.append("active but .plan.md missing")

    elif status == "drafting":
        pass  # no artifact required for drafting

    elif status in ("queued", "contract_ready"):
        if not has(".contract.md") and not has(".prd.md"):
            issues.append("queued but neither .contract.md nor .prd.md present")

    # Check for orphan artifacts (handoff without eval)
    handoff_exists = (SPRINTS_DIR / f"{sid}.handoff.md").exists()
    eval_exists = (SPRINTS_DIR / f"{sid}.eval.md").exists()
    if handoff_exists and not eval_exists and status not in ("active", "reviewing", "drafting", "queued", "contract_ready", "planning_complete"):
        issues.append("handoff present but no eval (stale reviewing?)")

    result: dict = {
        "sprint_id": sid,
        "status": status,
        "issues": issues,
        "verdict": "warn" if issues else "ok",
        "artifacts": {k: v for k, v in artifacts.items()},
        "priority": d.get("priority", ""),
        "lane": d.get("lane", ""),
        "title": d.get("title", ""),
    }
    return result


def run(glob_pattern: str = "sprint-2026050[78]-*.status.json", json_out: bool = False) -> dict:
    sprints = sorted(SPRINTS_DIR.glob(glob_pattern), key=lambda p: p.name)
    if not sprints:
        # Fall back to broader glob
        sprints = sorted(SPRINTS_DIR.glob("sprint-2026050*.status.json"), key=lambda p: p.name)

    results = [_check_sprint(sf) for sf in sprints]

    checked = len(results)
    ok = sum(1 for r in results if r["verdict"] == "ok")
    warn = sum(1 for r in results if r["verdict"] == "warn")
    error = sum(1 for r in results if r["verdict"] not in ("ok", "warn"))

    summary = {
        "checked": checked,
        "ok": ok,
        "warn": warn,
        "error": error,
        "verdict": "ok" if warn == 0 and error == 0 else ("warn" if error == 0 else "error"),
    }

    output = {"sprints": results, "summary": summary}

    if json_out:
        print(json.dumps(output, indent=2))
    else:
        print(f"Sprint Ledger — {checked} sprints checked")
        print(f"  OK: {ok}  WARN: {warn}  ERROR: {error}")
        print()
        for r in results:
            icon = "✅" if r["verdict"] == "ok" else ("⚠️ " if r["verdict"] == "warn" else "❌")
            print(f"  {icon} [{r['status']:20s}] {r['sprint_id']}")
            for issue in r["issues"]:
                print(f"          ↳ {issue}")
        print()
        print(f"Verdict: {summary['verdict'].upper()}")

    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--sprint-glob", default="sprint-2026050[78]-*.status.json")
    args = p.parse_args()
    result = run(glob_pattern=args.sprint_glob, json_out=args.json)
    sys.exit(0 if result["summary"]["verdict"] == "ok" else 1)


if __name__ == "__main__":
    main()
