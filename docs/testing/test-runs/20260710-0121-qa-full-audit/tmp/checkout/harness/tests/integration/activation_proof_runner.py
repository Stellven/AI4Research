"""Activation-proof runner — computes broker_coverage from event ledger.

S03 N9: sprint-20260519-solar-harness-vnext-code-as-harness-runtime-s03-core-runtime

Replays the EventLedger for a sprint and emits a broker_coverage report
conforming to harness/schemas/broker_coverage.schema.json (8 required
fields) plus an event_ledger_lag_seconds observability metric.

Usage:
    python3 -m harness.tests.integration.activation_proof_runner \\
        --sid sprint-foo \\
        [--base-dir /path/to/run] [--out report.json]

Exits 0 when broker_coverage.health == "PASS" (uncontracted=0,
unscoped=0, coverage_ratio=1.0). Exits 1 otherwise.

The computation is event-driven and purely additive — it never mutates
the ledger. It can be invoked against any sprint whose events have been
appended via the N3 ExecutionBroker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Dual import path: package style (production) + legacy sys.path (tests).
try:
    from harness.lib.event_ledger import EventLedger
except ModuleNotFoundError:  # pragma: no cover - legacy direct import path
    _HARNESS_LIB = str(Path(__file__).resolve().parents[2] / "lib")
    if _HARNESS_LIB not in sys.path:
        sys.path.insert(0, _HARNESS_LIB)
    from event_ledger import EventLedger  # type: ignore[no-redef]


SCHEMA_FIELDS = (
    "uncontracted_action_count",
    "unscoped_write_count",
    "total_actions",
    "contracted_actions",
    "coverage_ratio",
    "legacy_path_actions",
    "by_kind",
    "health",
)


def compute_broker_coverage(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the 8-field broker_coverage payload from a replayed event list.

    See harness/schemas/broker_coverage.schema.json for the contract.
    health == "PASS" iff uncontracted == 0 AND unscoped == 0 AND
    coverage_ratio == 1.0.
    """
    proposed_ids: set[str] = set()
    contracted_ids: set[str] = set()
    executed_ids: set[str] = set()
    legacy_ids: set[str] = set()
    unscoped_write_count = 0
    by_kind: Dict[str, int] = {}

    for ev in events:
        event_type = ev.get("event_type") or ev.get("type") or ""
        payload = ev.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        action_id = payload.get("action_id")

        if event_type == "action.proposed" and action_id:
            proposed_ids.add(action_id)
            kind = str(payload.get("kind") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if payload.get("legacy") is True:
                legacy_ids.add(action_id)
        elif event_type == "policy.verdict" and action_id:
            verdict = str(payload.get("verdict") or "").upper()
            reason = str(payload.get("reason") or "")
            detail = str(payload.get("detail") or "")
            if verdict == "PASS":
                contracted_ids.add(action_id)
            elif reason == "policy_denied" and detail.startswith("write_scope"):
                unscoped_write_count += 1
        elif event_type in {"action.executed", "action.failed"} and action_id:
            executed_ids.add(action_id)

    total_actions = len(proposed_ids)
    contracted_actions = len(contracted_ids)
    uncontracted_action_count = len(executed_ids - contracted_ids)
    coverage_ratio = (
        float(contracted_actions) / float(total_actions) if total_actions else 1.0
    )
    if coverage_ratio > 1.0:
        coverage_ratio = 1.0

    health = (
        "PASS"
        if (
            uncontracted_action_count == 0
            and unscoped_write_count == 0
            and coverage_ratio >= 1.0
        )
        else "FAIL"
    )

    return {
        "uncontracted_action_count": uncontracted_action_count,
        "unscoped_write_count": unscoped_write_count,
        "total_actions": total_actions,
        "contracted_actions": contracted_actions,
        "coverage_ratio": coverage_ratio,
        "legacy_path_actions": len(legacy_ids),
        "by_kind": by_kind,
        "health": health,
    }


def compute_ledger_lag_seconds(
    events: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> float:
    """Return seconds between the last event's created_at and `now` (default: utcnow)."""
    if not events:
        return 0.0
    last_ts = events[-1].get("created_at")
    if not last_ts:
        return 0.0
    try:
        if last_ts.endswith("Z"):
            last_ts = last_ts[:-1] + "+00:00"
        last_dt = datetime.fromisoformat(last_ts)
    except ValueError:
        return 0.0
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return max((reference - last_dt).total_seconds(), 0.0)


def build_report(
    sprint_id: str,
    *,
    base_dir: Optional[str] = None,
    ledger: Optional[EventLedger] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Construct the activation-proof JSON report for a sprint."""
    if ledger is None:
        ledger = EventLedger(base_dir=base_dir)
    events = ledger.replay(sprint_id)
    coverage = compute_broker_coverage(events)
    lag = compute_ledger_lag_seconds(events, now=now)
    return {
        "sprint_id": sprint_id,
        "event_count": len(events),
        "event_ledger_lag_seconds": lag,
        "broker_coverage": coverage,
    }


def _exit_code(report: Dict[str, Any]) -> int:
    return 0 if report.get("broker_coverage", {}).get("health") == "PASS" else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="activation_proof_runner",
        description="Compute broker_coverage from EventLedger for a sprint.",
    )
    parser.add_argument("--sid", required=True, help="sprint_id to replay")
    parser.add_argument(
        "--base-dir",
        default=None,
        help="EventLedger base dir (default: harness/run)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write report JSON to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    report = build_report(args.sid, base_dir=args.base_dir)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        sys.stdout.write(rendered + "\n")
    return _exit_code(report)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
