#!/usr/bin/env python3
"""Mine Solar events into failure clusters for the evolution engine."""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))

FAIL_RE = re.compile(r"fail|failed|error|warn|deadlock|stall|timeout|blocked|rejected|degraded", re.I)


def _event_paths() -> list[Path]:
    paths = [
        HARNESS_DIR / "events" / "all.jsonl",
        HARNESS_DIR / "events.jsonl",
        HARNESS_DIR / "sprints" / "warn.events.jsonl",
    ]
    paths.extend(sorted((HARNESS_DIR / "sprints").glob("*.events.jsonl"))[-20:])
    return [p for p in paths if p.exists()]


def _iter_events(paths: list[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        try:
            for line in path.read_text(errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                item["_source_path"] = str(path)
                events.append(item)
        except OSError:
            continue
    return events


def _is_failure(event: dict[str, Any]) -> bool:
    severity = str(event.get("severity", event.get("sev", "")))
    name = str(event.get("event", event.get("event_type", "")))
    status = str(event.get("status", ""))
    reason = str(event.get("reason", event.get("degraded_reason", "")))
    return severity in {"warn", "error"} or bool(FAIL_RE.search(" ".join([name, status, reason])))


def _cluster_key(event: dict[str, Any]) -> str:
    name = str(event.get("event", event.get("event_type", "unknown")))
    actor = str(event.get("actor", event.get("source", "unknown")))
    reason = str(event.get("reason", event.get("degraded_reason", ""))).strip()
    if reason:
        reason = re.sub(r"\s+", " ", reason)[:80]
        return f"{actor}:{name}:{reason}"
    return f"{actor}:{name}"


def mine(limit: int = 10) -> dict[str, Any]:
    events = _iter_events(_event_paths())
    failures = [e for e in events if _is_failure(e)]
    counts = Counter(_cluster_key(e) for e in failures)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in failures:
        key = _cluster_key(event)
        if len(examples[key]) < 3:
            examples[key].append({
                "ts": event.get("ts", event.get("time", "")),
                "event": event.get("event", event.get("event_type", "")),
                "severity": event.get("severity", event.get("sev", "")),
                "source_path": event.get("_source_path", ""),
            })
    clusters = [
        {"id": f"cluster-{idx + 1}", "key": key, "count": count, "examples": examples[key]}
        for idx, (key, count) in enumerate(counts.most_common(limit))
    ]
    return {
        "ok": True,
        "events_scanned": len(events),
        "failures": len(failures),
        "cluster_count": len(clusters),
        "clusters": clusters,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="failure_miner.py")
    ap.add_argument("cmd", nargs="?", default="mine", choices=["mine"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = mine(limit=args.limit)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"Failure clusters: {data['cluster_count']} from {data['failures']} failures")
        for item in data["clusters"]:
            print(f"  {item['id']} x{item['count']} {item['key']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
