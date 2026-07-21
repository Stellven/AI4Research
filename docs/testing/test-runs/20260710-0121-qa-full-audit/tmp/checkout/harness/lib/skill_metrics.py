#!/usr/bin/env python3
"""skill_metrics.py — Skill usage event emission and metrics aggregation.

Events are written to $HARNESS_DIR/run/events.jsonl (append-only).

CLI:
  python3 skill_metrics.py emit  --skill SKILL [--event TYPE] [--sprint SID] [--score N]
  python3 skill_metrics.py stats --skill SKILL [--since ISO_DATE]
  python3 skill_metrics.py summary [--since ISO_DATE] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
EVENTS_FILE = HARNESS_DIR / "run" / "events.jsonl"

EVENT_TYPES = {"invoke", "complete", "fail", "promote", "rollback", "eval_pass", "eval_fail"}


def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_events_file() -> None:
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not EVENTS_FILE.exists():
        EVENTS_FILE.touch()


def emit(skill: str, event_type: str = "invoke", sprint_id: str = "",
         score: "float | None" = None, extra: "dict | None" = None) -> dict:
    """Append a skill event to events.jsonl."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type!r}, valid: {sorted(EVENT_TYPES)}")
    _ensure_events_file()
    record: dict = {
        "ts": _now(),
        "source": "skill_metrics",
        "event": f"skill.{event_type}",
        "skill": skill,
    }
    if sprint_id:
        record["sprint_id"] = sprint_id
    if score is not None:
        record["score"] = score
    if extra:
        record.update(extra)
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def _load_events(skill: "str | None" = None,
                 since: "str | None" = None) -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    records: list[dict] = []
    for line in EVENTS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not str(r.get("event", "")).startswith("skill."):
            continue
        if skill and r.get("skill") != skill:
            continue
        if since and r.get("ts", "") < since:
            continue
        records.append(r)
    return records


def stats(skill: str, since: "str | None" = None) -> dict:
    records = _load_events(skill=skill, since=since)
    counts: dict[str, int] = {}
    scores: list[float] = []
    for r in records:
        ev = r.get("event", "").removeprefix("skill.")
        counts[ev] = counts.get(ev, 0) + 1
        if "score" in r:
            scores.append(float(r["score"]))
    return {
        "skill": skill,
        "counts": counts,
        "total_invocations": counts.get("invoke", 0),
        "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
        "since": since,
    }


def summary(since: "str | None" = None) -> dict:
    records = _load_events(since=since)
    by_skill: dict[str, dict] = {}
    for r in records:
        sk = r.get("skill", "unknown")
        ev = r.get("event", "").removeprefix("skill.")
        entry = by_skill.setdefault(sk, {"counts": {}, "scores": []})
        entry["counts"][ev] = entry["counts"].get(ev, 0) + 1
        if "score" in r:
            entry["scores"].append(float(r["score"]))

    result: dict[str, dict] = {}
    for sk, data in by_skill.items():
        scores = data["scores"]
        result[sk] = {
            "invocations": data["counts"].get("invoke", 0),
            "completions": data["counts"].get("complete", 0),
            "failures": data["counts"].get("fail", 0),
            "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
        }
    return {"skills": result, "since": since, "generated_at": _now()}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="skill_metrics.py")
    sub = ap.add_subparsers(dest="cmd")

    em = sub.add_parser("emit")
    em.add_argument("--skill", required=True)
    em.add_argument("--event", default="invoke")
    em.add_argument("--sprint", default="")
    em.add_argument("--score", type=float, default=None)

    st = sub.add_parser("stats")
    st.add_argument("--skill", required=True)
    st.add_argument("--since")

    su = sub.add_parser("summary")
    su.add_argument("--since")
    su.add_argument("--json", action="store_true", dest="as_json")

    args = ap.parse_args()
    if args.cmd == "emit":
        record = emit(args.skill, args.event, args.sprint, args.score)
        print(json.dumps({"ok": True, "record": record}))
    elif args.cmd == "stats":
        print(json.dumps(stats(args.skill, args.since), indent=2))
    elif args.cmd == "summary":
        data = summary(args.since)
        if args.as_json:
            print(json.dumps(data, indent=2))
        else:
            for sk, info in data["skills"].items():
                print(f"{sk:20s}  invoke={info['invocations']}  "
                      f"ok={info['completions']}  fail={info['failures']}  "
                      f"avg_score={info['avg_score']}")
    else:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
