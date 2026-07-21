#!/usr/bin/env python3
"""Multi-task screen health aggregator (S04 N3).

Reads three existing probe files under ``~/.solar/harness/state/``:

  * ``model-registry-doctor-health.json``
  * ``knowledge-probe-health.json``
  * ``external-integrations-last-probe.json``

…and emits ``state/screen-health.json`` conforming to schema
``multi_task_screen.health.v1`` so the multi-task screen view model
gets a single, low-cost health source.

Run as module:
    python3 -m harness.tools.multi_task_screen_health --once
Run directly:
    python3 ~/.solar/harness/tools/multi_task_screen_health.py --once

Atomic write: temp file + os.replace, matching the autopilot's save_json()
pattern (per data-source-audit.md §5).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

SCHEMA = "multi_task_screen.health.v1"
DEFAULT_STATE_DIR = Path.home() / ".solar" / "harness" / "state"

VALID_STATES = {
    "ok",
    "warn",
    "error",
    "idle",
    "active",
    "blocked",
    "dry_run",
    "ready",
    "working",
    "pending",
}

# Severity order: higher number wins when aggregating verdict.
SEVERITY = {"ok": 0, "idle": 1, "warn": 2, "error": 3}

# Capsule definitions: id → (label, marker, input filename, kind).
# kind distinguishes "binary" (ok bool + status string) from "summary"
# (counts dict under .summary).
CAPSULE_SPECS = [
    ("models", "models", "M", "model-registry-doctor-health.json", "binary"),
    ("knowledge", "knowledge", "K", "knowledge-probe-health.json", "binary"),
    (
        "integrations",
        "integrations",
        "I",
        "external-integrations-last-probe.json",
        "summary",
    ),
]


def _iso_utc(epoch: float | None = None) -> str:
    if epoch is None:
        dt = datetime.datetime.utcnow()
    else:
        dt = datetime.datetime.utcfromtimestamp(epoch)
    return dt.replace(microsecond=0).isoformat() + "Z"


def _state_from_binary(payload: dict) -> tuple[str, str]:
    """Map a binary-style probe (`ok` bool + `status` str) to capsule state.

    Returns (state, reason).
    """
    ok = payload.get("ok")
    status = (payload.get("status") or "").lower()
    if ok is True:
        return "ok", ""
    if status == "warn":
        return "warn", payload.get("reason") or "status=warn"
    return "error", payload.get("reason") or f"ok={ok!r} status={status!r}"


def _state_from_summary(payload: dict) -> tuple[str, str]:
    """Map an integrations-style probe (summary counts) to capsule state."""
    summary = payload.get("summary") or {}
    errors = int(summary.get("error", 0) or 0)
    warns = int(summary.get("warn", 0) or 0)
    missing = int(summary.get("missing", 0) or 0)
    total = int(summary.get("total", 0) or 0)
    if errors > 0:
        return "error", f"error={errors}/{total}"
    if warns > 0 or missing > 0:
        bits = []
        if warns:
            bits.append(f"warn={warns}")
        if missing:
            bits.append(f"missing={missing}")
        return "warn", " ".join(bits) + f" total={total}"
    return "ok", f"ok={summary.get('ok', total)}/{total}"


def _build_capsule(state_dir: Path, spec: tuple) -> dict:
    cap_id, label, marker, filename, kind = spec
    path = state_dir / filename
    if not path.exists():
        return {
            "id": cap_id,
            "label": label,
            "state": "idle",
            "marker": marker,
            "mtime": None,
            "reason": f"file missing: state/{filename}",
            "source": f"state/{filename}",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "id": cap_id,
            "label": label,
            "state": "error",
            "marker": marker,
            "mtime": _iso_utc(path.stat().st_mtime),
            "reason": f"parse error: {type(exc).__name__}: {str(exc)[:120]}",
            "source": f"state/{filename}",
        }
    if kind == "binary":
        state, reason = _state_from_binary(payload)
    else:
        state, reason = _state_from_summary(payload)
    # Prefer the probe's own checked_at / generated_at if present so the
    # capsule mtime reflects the probe time (not the file's last os mtime,
    # which may be skewed by atomic rename).
    probe_ts = (
        payload.get("checked_at")
        or payload.get("generated_at")
        or _iso_utc(path.stat().st_mtime)
    )
    return {
        "id": cap_id,
        "label": label,
        "state": state,
        "marker": marker,
        "mtime": probe_ts,
        "reason": reason,
        "source": f"state/{filename}",
    }


def _aggregate_verdict(capsules: list[dict]) -> str:
    worst = 0
    label = "ok"
    for cap in capsules:
        sev = SEVERITY.get(cap["state"], 0)
        if sev > worst:
            worst = sev
            label = cap["state"]
    return label if label in {"ok", "warn", "error", "idle"} else "ok"


def aggregate(state_dir: Path) -> dict:
    capsules = [_build_capsule(state_dir, spec) for spec in CAPSULE_SPECS]
    return {
        "schema_version": SCHEMA,
        "generated_at": _iso_utc(),
        "verdict": _aggregate_verdict(capsules),
        "capsules": capsules,
    }


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def validate(payload: dict) -> list[str]:
    """Return a list of validation errors; empty means schema-clean."""
    errs: list[str] = []
    if payload.get("schema_version") != SCHEMA:
        errs.append(f"schema_version != {SCHEMA}")
    caps = payload.get("capsules")
    if not isinstance(caps, list) or len(caps) < 3:
        errs.append("capsules[] must be list of length >= 3")
        return errs
    for i, cap in enumerate(caps):
        for k in ("id", "label", "state", "marker", "mtime"):
            if k not in cap:
                errs.append(f"capsules[{i}] missing key: {k}")
        st = cap.get("state")
        if st not in VALID_STATES:
            errs.append(f"capsules[{i}].state={st!r} not in VALID_STATES")
        marker = cap.get("marker")
        if not isinstance(marker, str) or len(marker) != 1 or ord(marker) > 127:
            errs.append(f"capsules[{i}].marker must be single ASCII char (got {marker!r})")
    if payload.get("verdict") not in {"ok", "warn", "error", "idle"}:
        errs.append(f"verdict={payload.get('verdict')!r} invalid")
    return errs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="multi_task_screen_health",
        description="Aggregate three Solar health probes into screen-health.json.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Build, validate, and write state/screen-health.json (default action).",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Alias for --once (matches design.md verification commands).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print aggregated JSON to stdout; do not write.",
    )
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
        help="State directory containing the three probe files and output target.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override output path (default: <state-dir>/screen-health.json).",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir).expanduser()
    out_path = Path(args.output).expanduser() if args.output else state_dir / "screen-health.json"

    payload = aggregate(state_dir)
    errs = validate(payload)
    if errs:
        print("warning: aggregated payload failed validation:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if errs else 0

    _atomic_write(out_path, payload)
    print(f"screen-health: {out_path}  verdict={payload['verdict']}  capsules={len(payload['capsules'])}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
