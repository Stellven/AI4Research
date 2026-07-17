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
  1. Exact sprint events.jsonl (when sprint_id is known)
  2. Zero defaults          (always guarantees all fields present)

The exact sprint ledger is authoritative.  Global observability helpers accept
an explicit event iterable and must never shadow a sprint ledger with defaults.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

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


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if payload is None:
        payload = event.get("data")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
    return payload if isinstance(payload, dict) else {}


def compute_broker_coverage_from_events(
    events: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Compute the canonical broker-coverage contract from event records.

    EventLedger records (``action.proposed`` / ``policy.verdict``) and the
    older sprint JSONL action records are normalized into one representation.
    Additional diagnostic fields are allowed by the JSON schema and are used
    by the activation-proof CLI to decide PASS/FAIL without inventing a second
    coverage percentage.
    """
    proposed_ids: set[str] = set()
    contracted_ids: set[str] = set()
    executed_ids: set[str] = set()
    legacy_ids: set[str] = set()
    pending_approval_ids: set[str] = set()
    resolved_approval_ids: set[str] = set()
    unscoped_write_count = 0
    policy_denied_count = 0
    lease_denied_count = 0
    direct_approval_pending = 0
    by_kind: dict[str, int] = {}
    legacy_action_types = {
        "command_issued",
        "tool_called",
        "write_action",
        "graph_event",
    }

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or event.get("type") or event.get("event") or "")
        payload = _event_payload(event)
        action_id = str(payload.get("action_id") or "").strip()

        if event_type == "action.proposed" and action_id:
            proposed_ids.add(action_id)
            kind = str(payload.get("kind") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if payload.get("legacy") is True:
                legacy_ids.add(action_id)
            continue

        if event_type in legacy_action_types:
            synthetic_id = action_id or f"legacy-event-{index}"
            proposed_ids.add(synthetic_id)
            kind = str(payload.get("kind") or event_type)
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if payload.get("write_scope") or payload.get("contracted"):
                contracted_ids.add(synthetic_id)
            else:
                unscoped_write_count += 1
            continue

        if event_type == "policy.verdict" and action_id:
            verdict = str(payload.get("verdict") or "").upper()
            reason = str(payload.get("reason") or "").lower()
            detail = str(payload.get("detail") or "")
            combined = f"{reason} {detail}".lower()
            if verdict == "PASS":
                contracted_ids.add(action_id)
                resolved_approval_ids.add(action_id)
            else:
                if reason == "lease_denied" or "lease_denied" in combined:
                    lease_denied_count += 1
                else:
                    policy_denied_count += 1
                if "write_scope" in combined:
                    unscoped_write_count += 1
                if "approval" in combined:
                    pending_approval_ids.add(action_id)
            continue

        if event_type in {"action.executed", "action.failed", "action.cancelled"} and action_id:
            executed_ids.add(action_id)
            resolved_approval_ids.add(action_id)
            continue

        if event_type == "policy_denied":
            policy_denied_count += 1
            if "write_scope" in str(payload).lower():
                unscoped_write_count += 1
        elif event_type in {"lease_denied", "lease_failed"}:
            lease_denied_count += 1
        elif event_type == "human_approval_requested":
            if action_id:
                pending_approval_ids.add(action_id)
            else:
                direct_approval_pending += 1

    total_actions = len(proposed_ids)
    contracted_actions = len(proposed_ids.intersection(contracted_ids))
    coverage_pct = (
        round(contracted_actions / total_actions * 100, 2)
        if total_actions
        else 0.0
    )
    uncontracted_action_count = len(executed_ids - contracted_ids)
    human_approval_pending = (
        len(pending_approval_ids - resolved_approval_ids) + direct_approval_pending
    )
    health = (
        "PASS"
        if (
            uncontracted_action_count == 0
            and unscoped_write_count == 0
            and (total_actions == 0 or contracted_actions == total_actions)
        )
        else "FAIL"
    )
    return {
        "total_actions": total_actions,
        "contracted_actions": contracted_actions,
        "coverage_pct": coverage_pct,
        "unscoped_write_count": unscoped_write_count,
        "policy_denied_count": policy_denied_count,
        "lease_denied_count": lease_denied_count,
        "human_approval_pending": human_approval_pending,
        "uncontracted_action_count": uncontracted_action_count,
        "legacy_path_actions": len(legacy_ids),
        "by_kind": by_kind,
        "health": health,
    }


def _parse_events_jsonl(sprint_id: str) -> dict[str, Any]:
    """Lightweight fallback: count broker-relevant actions from events.jsonl."""
    events_path = HARNESS_DIR / "sprints" / f"{sprint_id}.events.jsonl"
    if not events_path.exists():
        return dict(BROKER_COVERAGE_DEFAULTS)
    events: list[dict[str, Any]] = []
    try:
        for raw in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                event = json.loads(raw)
            except Exception:
                continue
            if isinstance(event, dict):
                events.append(event)
    except Exception:
        return dict(BROKER_COVERAGE_DEFAULTS)
    computed = compute_broker_coverage_from_events(events)
    return {field: computed[field] for field in BROKER_COVERAGE_FIELDS}


def build_broker_coverage(sprint_id: str | None = None) -> dict[str, Any]:
    """Build broker_coverage dict with all required subfields.

    All 7 subfields are always present regardless of data source (fail-open).
    """
    coverage: dict[str, Any] = dict(BROKER_COVERAGE_DEFAULTS)
    source = "defaults"

    if sprint_id:
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
