#!/usr/bin/env python3
"""`solar-harness status [--json]` — observability metrics renderer (S04 N6).

Renders the six metrics published by ``harness.lib.observability.metrics``
together with their alert thresholds (``ALARM_THRESHOLDS``):

    1. broker_coverage_pct
    2. policy_denied_rate
    3. approval_pending_count
    4. event_ledger_lag_sec
    5. dispatcher_dead_letter
    6. sprint_blocked_count

Two output modes:

- default text: human-readable, one line per metric with ``OK | ALARM |
  CRITICAL`` alert flag derived from ``ALARM_THRESHOLDS``.
- ``--json``: emits a ``solar.status.metrics.v1`` payload.

LR-01 (import-time safety): the observability module is loaded **lazily**
inside ``_try_load_observability``. If the import fails (e.g. the package
was renamed, partially deleted, or transitively pulls in something that
crashes at import time), the renderer falls back to a clearly-marked
``status=unavailable`` notice and exits 0 — the legacy bash output emitted
by ``solar-harness.sh::show_status`` remains the source of truth for the
non-metrics portion of ``solar-harness status``.

Invocation paths:

- ``python3 -m harness.lib.cli.status_cmd [--json]``
- ``python3 harness/lib/cli/status_cmd.py [--json]``

This module deliberately uses stdlib only (json/os/argparse/pathlib).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "solar.status.metrics.v1"

HOME = Path.home()
DEFAULT_HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
DEFAULT_SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", DEFAULT_HARNESS_DIR / "sprints"))
DEFAULT_EVENTS_PATH = Path(
    os.environ.get("HARNESS_EVENTS_PATH", DEFAULT_HARNESS_DIR / "run" / "events.jsonl")
)


# ---------------------------------------------------------------------------
# LR-01 — lazy import. Never raise at module top level.
# ---------------------------------------------------------------------------
def _try_load_observability() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Lazily import the observability package.

    Returns ``(api, None)`` on success or ``(None, error_message)`` on failure.
    """
    try:
        from harness.lib.observability import (
            ALARM_THRESHOLDS,
            approval_pending_count,
            broker_coverage_pct,
            dispatcher_dead_letter,
            event_ledger_lag_sec,
            iter_events_from_jsonl,
            policy_denied_rate,
            sprint_blocked_count,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open per LR-01.
        return None, f"{type(exc).__name__}: {exc}"

    api: Dict[str, Any] = {
        "ALARM_THRESHOLDS": ALARM_THRESHOLDS,
        "broker_coverage_pct": broker_coverage_pct,
        "policy_denied_rate": policy_denied_rate,
        "approval_pending_count": approval_pending_count,
        "event_ledger_lag_sec": event_ledger_lag_sec,
        "dispatcher_dead_letter": dispatcher_dead_letter,
        "sprint_blocked_count": sprint_blocked_count,
        "iter_events_from_jsonl": iter_events_from_jsonl,
    }
    return api, None


# ---------------------------------------------------------------------------
# Threshold classification.
# ---------------------------------------------------------------------------
def _classify(metric_name: str, value: Any, thresholds: Dict[str, Dict[str, Any]]) -> str:
    rule = thresholds.get(metric_name)
    if not rule:
        return "OK"
    op = rule.get("op")
    threshold = rule.get("threshold")
    severity = str(rule.get("severity") or "ALARM").upper()
    if value is None or threshold is None:
        return "OK"
    try:
        if op == "<" and float(value) < float(threshold):
            return severity
        if op == ">" and float(value) > float(threshold):
            return severity
        if op == "<=" and float(value) <= float(threshold):
            return severity
        if op == ">=" and float(value) >= float(threshold):
            return severity
    except (TypeError, ValueError):
        return "OK"
    return "OK"


# ---------------------------------------------------------------------------
# Payload construction.
# ---------------------------------------------------------------------------
def compute_metrics(
    *,
    events_path: Path,
    sprints_dir: Path,
    api: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Compute the six metric records. The events iterator is consumed once
    and materialised into a list because the metric functions iterate
    repeatedly."""
    events: List[Dict[str, Any]] = list(api["iter_events_from_jsonl"](events_path))
    thresholds = api["ALARM_THRESHOLDS"]
    values: Dict[str, Any] = {
        "broker_coverage_pct":    api["broker_coverage_pct"](events),
        "policy_denied_rate":     api["policy_denied_rate"](events),
        "approval_pending_count": api["approval_pending_count"](events),
        "event_ledger_lag_sec":   api["event_ledger_lag_sec"](events),
        "dispatcher_dead_letter": api["dispatcher_dead_letter"](events),
        "sprint_blocked_count":   api["sprint_blocked_count"](sprints_dir),
    }
    metrics: Dict[str, Dict[str, Any]] = {}
    for name, value in values.items():
        metrics[name] = {
            "value": value,
            "alert": _classify(name, value, thresholds),
            "threshold": dict(thresholds.get(name, {})),
        }
    return metrics


def build_payload(
    *,
    events_path: Path,
    sprints_dir: Path,
    api: Optional[Dict[str, Any]],
    error: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "events_path": str(events_path),
        "sprints_dir": str(sprints_dir),
    }
    if api is None:
        payload["status"] = "unavailable"
        payload["note"] = "observability_module_unavailable"
        if error:
            payload["error"] = error
        payload["metrics"] = {}
        payload["fallback"] = (
            "Legacy text output remains available via `solar-harness status` "
            "(bash show_status)."
        )
        return payload
    payload["metrics"] = compute_metrics(
        events_path=events_path, sprints_dir=sprints_dir, api=api
    )
    payload["status"] = "ok"
    return payload


# ---------------------------------------------------------------------------
# Schema validation (hand-rolled, stdlib only).
# ---------------------------------------------------------------------------
def validate_payload(payload: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return [f"payload not object: {type(payload).__name__}"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version != {SCHEMA_VERSION!r}: {payload.get('schema_version')!r}")
    if "status" not in payload:
        errors.append("missing status")
    elif payload["status"] not in {"ok", "unavailable"}:
        errors.append(f"status not in {{ok, unavailable}}: {payload['status']!r}")
    if "metrics" not in payload or not isinstance(payload["metrics"], dict):
        errors.append("metrics missing or not object")
        return errors
    if payload["status"] == "ok":
        expected = {
            "broker_coverage_pct",
            "policy_denied_rate",
            "approval_pending_count",
            "event_ledger_lag_sec",
            "dispatcher_dead_letter",
            "sprint_blocked_count",
        }
        missing = expected - set(payload["metrics"].keys())
        if missing:
            errors.append(f"metrics missing names: {sorted(missing)}")
        for name, info in payload["metrics"].items():
            if not isinstance(info, dict):
                errors.append(f"metrics[{name}] not object")
                continue
            for key in ("value", "alert", "threshold"):
                if key not in info:
                    errors.append(f"metrics[{name}].{key} missing")
            if "alert" in info and info["alert"] not in {"OK", "ALARM", "CRITICAL"}:
                errors.append(f"metrics[{name}].alert invalid: {info['alert']!r}")
    return errors


# ---------------------------------------------------------------------------
# Text rendering.
# ---------------------------------------------------------------------------
_GLYPHS = {"OK": "✓", "ALARM": "!", "CRITICAL": "✖"}


def _glyph(alert: str) -> str:
    return _GLYPHS.get(alert, "?")


def _format_threshold(rule: Dict[str, Any]) -> str:
    if not rule:
        return "-"
    op = rule.get("op") or ""
    thr = rule.get("threshold")
    return f"{op}{thr}" if op or thr is not None else "-"


def render_text(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    if payload.get("status") == "unavailable":
        lines.append("Solar-Harness Observability Metrics  [unavailable]")
        if payload.get("error"):
            lines.append(f"  reason:   {payload['error']}")
        lines.append(
            "  fallback: legacy `solar-harness status` (bash show_status) "
            "remains available."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("Solar-Harness Observability Metrics")
    lines.append(f"  events:  {payload.get('events_path', '')}")
    lines.append(f"  sprints: {payload.get('sprints_dir', '')}")
    lines.append("")
    metrics: Dict[str, Dict[str, Any]] = payload.get("metrics") or {}
    if not metrics:
        lines.append("  (no metrics computed)")
        lines.append("")
        return "\n".join(lines)
    name_w = max((len(n) for n in metrics), default=24)
    for name, info in metrics.items():
        alert = str(info.get("alert", "?"))
        value = info.get("value")
        thr_str = _format_threshold(info.get("threshold") or {})
        value_str = f"{value!s}"
        lines.append(
            f"  [{_glyph(alert)}] {name:<{name_w}}  "
            f"value={value_str:<10}  alert={alert:<8}  threshold={thr_str}"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="solar-harness status",
        description=(
            "Render six Solar-Harness observability metrics with alert "
            "thresholds. Falls back to a clearly-marked notice when the "
            "observability package is unavailable."
        ),
    )
    parser.add_argument(
        "--json",
        dest="json_mode",
        action="store_true",
        help="Emit solar.status.metrics.v1 JSON to stdout.",
    )
    parser.add_argument(
        "--events-path",
        default=str(DEFAULT_EVENTS_PATH),
        help=f"events.jsonl path (default: {DEFAULT_EVENTS_PATH}).",
    )
    parser.add_argument(
        "--sprints-dir",
        default=str(DEFAULT_SPRINTS_DIR),
        help=f"Sprints directory containing *.status.json (default: {DEFAULT_SPRINTS_DIR}).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build payload, run schema validation, print result, exit 0/2.",
    )
    args = parser.parse_args(argv)

    events_path = Path(args.events_path)
    sprints_dir = Path(args.sprints_dir)

    api, error = _try_load_observability()
    payload = build_payload(
        events_path=events_path, sprints_dir=sprints_dir, api=api, error=error
    )

    if args.validate_only:
        errs = validate_payload(payload)
        if errs:
            for e in errs:
                print(f"schema_error: {e}", file=sys.stderr)
            return 2
        print("schema_ok")
        return 0

    if args.json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))
        return 0

    print(render_text(payload))
    return 0


__all__ = [
    "DEFAULT_EVENTS_PATH",
    "DEFAULT_HARNESS_DIR",
    "DEFAULT_SPRINTS_DIR",
    "SCHEMA_VERSION",
    "build_payload",
    "compute_metrics",
    "main",
    "render_text",
    "validate_payload",
]


if __name__ == "__main__":
    sys.exit(main())
