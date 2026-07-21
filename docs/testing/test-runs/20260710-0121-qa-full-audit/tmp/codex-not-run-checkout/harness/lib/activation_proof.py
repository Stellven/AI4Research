#!/usr/bin/env python3
"""activation_proof.py — activation proof with broker_coverage section.

Outputs activation proof JSON including a broker_coverage section that reports
constraint-broker telemetry for observable evaluation by evaluators.

broker_coverage subfields (7 required):
  total_actions         — total dispatched actions recorded in events.jsonl
  contracted_actions    — actions with an explicit write_scope contract entry
  coverage_pct          — float 0.0–100.0 (contracted/total * 100)
  unscoped_write_count  — write actions not covered by any write_scope
  policy_denied_count   — actions blocked by policy gate
  lease_denied_count    — actions blocked by pane-lease gate
  human_approval_pending — actions currently awaiting human approval

Source priority (fail-open at every level):
  1. harness/lib/observability/metrics.py  (N4 module — available after N4 passes)
  2. sprint events.jsonl lightweight parse  (when sprint_id is known)
  3. Zero defaults                          (always guarantees all fields present)
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SCHEMA_VERSION = "1.0"

BROKER_COVERAGE_FIELDS: tuple[str, ...] = (
    "total_actions",
    "contracted_actions",
    "coverage_pct",
    "unscoped_write_count",
    "policy_denied_count",
    "lease_denied_count",
    "human_approval_pending",
)

BROKER_COVERAGE_DEFAULTS: dict[str, Any] = {
    "total_actions": 0,
    "contracted_actions": 0,
    "coverage_pct": 0.0,
    "unscoped_write_count": 0,
    "policy_denied_count": 0,
    "lease_denied_count": 0,
    "human_approval_pending": 0,
}


def _try_metrics_module() -> dict[str, Any] | None:
    """Attempt to populate coverage from observability.metrics (N4). Fail-open."""
    obs_path = HARNESS_DIR / "lib" / "observability"
    if not obs_path.is_dir():
        return None
    lib_path = str(HARNESS_DIR / "lib")
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    try:
        metrics = importlib.import_module("observability.metrics")
    except Exception:
        return None
    result: dict[str, Any] = dict(BROKER_COVERAGE_DEFAULTS)
    try:
        if hasattr(metrics, "broker_coverage_pct"):
            result["coverage_pct"] = float(metrics.broker_coverage_pct() or 0.0)
        if hasattr(metrics, "policy_denied_rate"):
            result["policy_denied_count"] = int(metrics.policy_denied_rate() or 0)
        if hasattr(metrics, "approval_pending_count"):
            result["human_approval_pending"] = int(metrics.approval_pending_count() or 0)
    except Exception:
        pass
    return result


def _parse_events_jsonl(sprint_id: str) -> dict[str, Any]:
    """Lightweight fallback: count broker-relevant actions from events.jsonl."""
    result = dict(BROKER_COVERAGE_DEFAULTS)
    events_path = HARNESS_DIR / "sprints" / f"{sprint_id}.events.jsonl"
    if not events_path.exists():
        return result
    total = contracted = unscoped = policy_denied = lease_denied = pending = 0
    try:
        for raw in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            ev_type = str(ev.get("type") or ev.get("event") or "")
            data = ev.get("data") or ev.get("payload") or {}
            if ev_type in {"command_issued", "tool_called", "write_action", "graph_event"}:
                total += 1
                if data.get("write_scope") or data.get("contracted"):
                    contracted += 1
                else:
                    unscoped += 1
            elif ev_type == "policy_denied":
                policy_denied += 1
            elif ev_type in {"lease_denied", "lease_failed"}:
                lease_denied += 1
            elif ev_type == "human_approval_requested":
                pending += 1
    except Exception:
        pass
    result["total_actions"] = total
    result["contracted_actions"] = contracted
    result["coverage_pct"] = round(contracted / total * 100, 2) if total > 0 else 0.0
    result["unscoped_write_count"] = unscoped
    result["policy_denied_count"] = policy_denied
    result["lease_denied_count"] = lease_denied
    result["human_approval_pending"] = pending
    return result


def build_broker_coverage(sprint_id: str | None = None) -> dict[str, Any]:
    """Build broker_coverage dict with all required subfields.

    All 7 subfields are always present regardless of data source (fail-open).
    """
    coverage: dict[str, Any] = dict(BROKER_COVERAGE_DEFAULTS)
    source = "defaults"

    from_metrics = _try_metrics_module()
    if from_metrics is not None:
        coverage.update({k: from_metrics[k] for k in BROKER_COVERAGE_FIELDS if k in from_metrics})
        source = "observability.metrics"
    elif sprint_id:
        from_events = _parse_events_jsonl(sprint_id)
        coverage.update({k: from_events[k] for k in BROKER_COVERAGE_FIELDS if k in from_events})
        source = f"events.jsonl:{sprint_id}"

    coverage["_source"] = source
    for field in BROKER_COVERAGE_FIELDS:
        if field not in coverage:
            coverage[field] = BROKER_COVERAGE_DEFAULTS[field]
    return coverage


def build_activation_proof(sprint_id: str | None = None, *,
                           include_schema_path: bool = True) -> dict[str, Any]:
    """Build the full activation proof JSON dict with broker_coverage section."""
    broker_coverage = build_broker_coverage(sprint_id)
    proof: dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "broker_coverage": broker_coverage,
    }
    if include_schema_path:
        schema_path = HARNESS_DIR / "schemas" / "broker_coverage.schema.json"
        proof["broker_coverage_schema"] = str(schema_path)
        proof["broker_coverage_schema_exists"] = schema_path.exists()
    if sprint_id:
        proof["sprint_id"] = sprint_id
    proof["broker_enabled"] = os.environ.get("SOLAR_BROKER_ENABLED", "0") == "1"
    return proof


def validate_against_schema(broker_coverage: dict[str, Any]) -> dict[str, Any]:
    """Validate broker_coverage dict against broker_coverage.schema.json.

    Falls back to structural check if jsonschema is not installed.
    Returns {"ok": True/False, "validator": ..., ...}.
    """
    missing_fields = [f for f in BROKER_COVERAGE_FIELDS if f not in broker_coverage]
    if missing_fields:
        return {"ok": False, "reason": "missing_fields", "missing": missing_fields}

    schema_path = HARNESS_DIR / "schemas" / "broker_coverage.schema.json"
    if schema_path.exists():
        try:
            import jsonschema  # type: ignore
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(broker_coverage, schema)
            return {"ok": True, "validator": "jsonschema", "schema": str(schema_path)}
        except ImportError:
            pass
        except Exception as exc:
            return {"ok": False, "reason": "schema_validation_failed", "error": str(exc)}

    errors: list[str] = []
    try:
        pct = float(broker_coverage.get("coverage_pct", 0))
        if not (0.0 <= pct <= 100.0):
            errors.append(f"coverage_pct out of range: {pct}")
    except Exception:
        errors.append("coverage_pct not numeric")
    for count_field in (
        "total_actions", "contracted_actions", "unscoped_write_count",
        "policy_denied_count", "lease_denied_count", "human_approval_pending",
    ):
        try:
            val = int(broker_coverage.get(count_field, 0))
            if val < 0:
                errors.append(f"{count_field} negative: {val}")
        except Exception:
            errors.append(f"{count_field} not integer")
    if errors:
        return {"ok": False, "reason": "structural_check_failed", "errors": errors}
    return {"ok": True, "validator": "structural_check"}


def main() -> int:
    ap = argparse.ArgumentParser(prog="activation_proof.py",
                                 description="Output activation proof JSON with broker_coverage.")
    ap.add_argument("--sprint-id", "--sprint_id", default=None, metavar="SID")
    ap.add_argument("--validate", action="store_true",
                    help="Include schema validation result in output.")
    ap.add_argument("--no-schema-path", dest="schema_path", action="store_false",
                    help="Omit broker_coverage_schema / broker_coverage_schema_exists fields.")
    args = ap.parse_args()

    sprint_id = args.sprint_id or os.environ.get("SOLAR_BROKER_SPRINT_ID")
    proof = build_activation_proof(sprint_id, include_schema_path=args.schema_path)
    if args.validate:
        proof["schema_validation"] = validate_against_schema(proof["broker_coverage"])
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return 0 if proof.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
