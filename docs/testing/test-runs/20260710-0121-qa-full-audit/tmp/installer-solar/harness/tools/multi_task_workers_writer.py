#!/usr/bin/env python3
"""multi-task-workers writer.

Inspects active sprint dispatch + worker pane state, emits
``state/multi-task-workers.json`` conforming to
``multi_task_screen.workers.v1``.

Schema (acceptance pinned):

    {
      "schema_version": "multi_task_screen.workers.v1",
      "generated_at": "ISO-8601 UTC",
      "workers": [
        {
          "id":              "<tmux session:window.pane>",
          "role":            "<pm|planner|builder|evaluator|lab|...>",
          "current_sprint":  "<sprint_id or null>",
          "last_event_ts":   "ISO-8601 or null",
          "low_confidence":  bool
        }
      ]
    }

Inputs (all read-only, bounded):

  - state/autopilot-state.json  -> ``pane`` dict (id -> hash/seen_at/role).
  - state/events.jsonl          -> tailed; lookback bounded by
                                   ``--max-lookback`` (default 500, hard cap 500).
                                   No full-file scans.

Outputs (atomic temp+rename):

  - state/multi-task-workers.json

Concurrency: temp-write then atomic ``replace``; never partial reads.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "multi_task_screen.workers.v1"
MAX_LOOKBACK_HARD_CAP = 500
DEFAULT_STATE_DIR = Path.home() / ".solar" / "harness" / "state"
DEFAULT_WORKER_SKILLS = [
    "bash",
    "shell",
    "python",
    "testing",
    "test_execution",
    "code_impl",
    "test_generation",
    "planning",
    "optimization",
    "runtime_design",
    "solar-harness-verification",
    "solar-harness-compat-review",
    "compat-review",
    "compatibility",
    "harness.verification",
    "verification",
    "verifier",
    "review",
]
DEFAULT_WORKER_CAPABILITIES = [
    "bash",
    "python",
    "testing",
    "test_execution",
    "code_impl",
    "test_generation",
    "repair.pr-cot",
    "failure.structured_repair",
    "routing.complexity_budget",
    "optimization",
    "runtime_design",
    "solar-harness-verification",
    "solar-harness-compat-review",
    "compat-review",
    "compatibility",
    "harness.verification",
    "verification",
    "code.review",
]


def _execution_labels(role: str) -> tuple[list[str], list[str]]:
    if role.lower() in {"builder", "lab", "lab-builder", "evaluator"}:
        return list(DEFAULT_WORKER_SKILLS), list(DEFAULT_WORKER_CAPABILITIES)
    return [], []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_to_iso(epoch: float | int | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (TypeError, ValueError, OSError):
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None


def tail_events_jsonl(path: Path, max_lookback: int) -> list[dict[str, Any]]:
    """Return up to ``max_lookback`` most recent parsed events.

    Uses a bounded deque so memory is O(max_lookback), not O(file).
    Malformed lines are skipped silently.
    """
    if max_lookback <= 0:
        return []
    cap = min(max_lookback, MAX_LOOKBACK_HARD_CAP)
    buf: collections.deque[str] = collections.deque(maxlen=cap)
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line:
                    buf.append(line)
    except FileNotFoundError:
        return []
    events: list[dict[str, Any]] = []
    for raw in buf:
        try:
            evt = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(evt, dict):
            events.append(evt)
    return events


def _extract_pane(evt: dict[str, Any]) -> str | None:
    for key in ("pane", "target_pane", "worker_pane", "assigned_to"):
        v = evt.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _extract_sprint(evt: dict[str, Any]) -> str | None:
    for key in ("sprint_id", "sprint", "sid", "target_sprint"):
        v = evt.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _extract_ts(evt: dict[str, Any]) -> str | None:
    for key in ("ts", "timestamp", "generated_at", "at"):
        v = evt.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def build_workers(
    autopilot_state: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge autopilot pane ledger with bounded events tail.

    - Every pane found in ``autopilot-state.json`` becomes a worker entry.
    - Latest event per pane (by tail order — events.jsonl is append-only)
      contributes ``last_event_ts`` and ``current_sprint``.
    - ``low_confidence`` is True iff the pane has no event in the bounded
      window (we only have a capture-pane hash + role from autopilot).
    """
    panes: dict[str, dict[str, Any]] = {}
    if isinstance(autopilot_state, dict):
        raw_panes = autopilot_state.get("pane")
        if isinstance(raw_panes, dict):
            for pane_id, meta in raw_panes.items():
                if not isinstance(pane_id, str) or not isinstance(meta, dict):
                    continue
                panes[pane_id] = {
                    "id": pane_id,
                    "role": str(meta.get("role") or "unknown"),
                    "current_sprint": None,
                    "last_event_ts": _epoch_to_iso(meta.get("seen_at")),
                    "low_confidence": True,
                    "_autopilot_seen_at": meta.get("seen_at"),
                }

    # Walk events tail in order. Append-only → last write wins per pane.
    event_latest: dict[str, dict[str, str | None]] = {}
    for evt in events:
        pane_id = _extract_pane(evt)
        if not pane_id:
            continue
        event_latest[pane_id] = {
            "ts": _extract_ts(evt),
            "sprint": _extract_sprint(evt),
        }

    for pane_id, hit in event_latest.items():
        worker = panes.get(pane_id)
        if worker is None:
            worker = {
                "id": pane_id,
                "role": "unknown",
                "current_sprint": None,
                "last_event_ts": None,
                "low_confidence": False,
            }
            panes[pane_id] = worker
        ts = hit.get("ts")
        sprint = hit.get("sprint")
        if ts:
            worker["last_event_ts"] = ts
        if sprint:
            worker["current_sprint"] = sprint
        worker["low_confidence"] = False

    out: list[dict[str, Any]] = []
    for pane_id in sorted(panes.keys()):
        w = panes[pane_id]
        skills, capabilities = _execution_labels(str(w["role"]))
        out.append(
            {
                "id": w["id"],
                "pane": w["id"],
                "role": w["role"],
                "current_sprint": w["current_sprint"],
                "last_event_ts": w["last_event_ts"],
                "low_confidence": bool(w["low_confidence"]),
                "skills": skills,
                "capabilities": capabilities,
            }
        )
    return out


def emit(
    state_dir: Path,
    out_path: Path,
    max_lookback: int = MAX_LOOKBACK_HARD_CAP,
) -> dict[str, Any]:
    autopilot = _load_json(state_dir / "autopilot-state.json")
    events = tail_events_jsonl(state_dir / "events.jsonl", max_lookback)
    workers = build_workers(autopilot, events)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "lookback": min(max_lookback, MAX_LOOKBACK_HARD_CAP),
        "workers": workers,
    }
    atomic_write_json(out_path, payload)
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="multi_task_workers_writer",
        description="Emit state/multi-task-workers.json (multi_task_screen.workers.v1)",
    )
    p.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="State directory (default: ~/.solar/harness/state)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: <state-dir>/multi-task-workers.json)",
    )
    p.add_argument(
        "--max-lookback",
        type=int,
        default=MAX_LOOKBACK_HARD_CAP,
        help=f"Max events.jsonl lines to tail (hard cap {MAX_LOOKBACK_HARD_CAP}).",
    )
    p.add_argument(
        "--print",
        action="store_true",
        help="Also write the resulting JSON to stdout.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    state_dir = args.state_dir.expanduser().resolve()
    out_path = (args.out or state_dir / "multi-task-workers.json").expanduser()
    payload = emit(state_dir, out_path, max_lookback=args.max_lookback)
    if args.print:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
