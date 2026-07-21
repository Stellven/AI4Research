#!/usr/bin/env python3
"""
mirage_events.py — Standalone event writer for Mirage VFS events.
Sprint: sprint-20260508-mirage-unified-vfs S3

Event types:
  mirage_installed          — SDK/mirage tool installed
  mirage_workspace_created  — workspace state file written
  mirage_command_executed   — exec subcommand completed (no stdout)
  mirage_mount_degraded     — a mount is unavailable or has issues
  mirage_secret_redacted    — redaction applied to stdout
  mirage_write_denied       — write attempt blocked by boundary policy
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Optional

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(HOME / ".solar" / "harness")))
STATE_DIR = HARNESS_DIR / "state" / "mirage"
EVENTS_JSONL = STATE_DIR / "events.jsonl"
WARN_EVENTS = HARNESS_DIR / "sprints" / "warn.events.jsonl"

_WARN_EVENT_TYPES = {
    "mirage_write_denied",
    "mirage_mount_degraded",
    "mirage_secret_redacted",
}


def emit(
    event_type: str,
    data: Optional[dict] = None,
    severity: str = "info",
    workspace_id: str = "solar-default",
) -> dict:
    """Append a mirage event to events.jsonl (and warn.events.jsonl for warn-level events).

    Returns the event dict that was written.
    """
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    event: dict = {
        "ts": ts,
        "event": event_type,
        "actor": "mirage",
        "severity": severity,
        "workspace_id": workspace_id,
    }
    if data:
        event.update({k: v for k, v in data.items() if k not in event})

    line = json.dumps(event) + "\n"

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(EVENTS_JSONL, "a") as f:
            f.write(line)
    except OSError:
        pass

    if event_type in _WARN_EVENT_TYPES or severity in ("warn", "error"):
        try:
            with open(WARN_EVENTS, "a") as f:
                f.write(line)
        except OSError:
            pass

    return event


# ── Convenience wrappers for each event type ──

def installed(sdk_kind: str = "none", version: str = "") -> dict:
    return emit(
        "mirage_installed",
        {"sdk_kind": sdk_kind, "version": version},
        severity="info",
    )


def workspace_created(workspace_id: str, mounts_count: int = 0) -> dict:
    return emit(
        "mirage_workspace_created",
        {"mounts_count": mounts_count},
        severity="info",
        workspace_id=workspace_id,
    )


def command_executed(
    verb: str,
    logical_path: str,
    exit_code: int,
    elapsed_ms: int,
    workspace_id: str = "solar-default",
) -> dict:
    return emit(
        "mirage_command_executed",
        {"verb": verb, "logical_path": logical_path, "exit_code": exit_code, "elapsed_ms": elapsed_ms},
        severity="info",
        workspace_id=workspace_id,
    )


def mount_degraded(mount_path: str, reason: str, workspace_id: str = "solar-default") -> dict:
    return emit(
        "mirage_mount_degraded",
        {"mount_path": mount_path, "reason": reason},
        severity="warn",
        workspace_id=workspace_id,
    )


def secret_redacted(mount_path: str, pattern_count: int, workspace_id: str = "solar-default") -> dict:
    return emit(
        "mirage_secret_redacted",
        {"mount_path": mount_path, "pattern_count": pattern_count},
        severity="warn",
        workspace_id=workspace_id,
    )


def write_denied(logical_path: str, reason: str, workspace_id: str = "solar-default") -> dict:
    return emit(
        "mirage_write_denied",
        {"logical_path": logical_path, "reason": reason},
        severity="warn",
        workspace_id=workspace_id,
    )


_DEFAULT_SEVERITY: dict = {
    "mirage_installed": "info",
    "mirage_workspace_created": "info",
    "mirage_command_executed": "info",
    "mirage_mount_degraded": "warn",
    "mirage_secret_redacted": "warn",
    "mirage_write_denied": "warn",
}

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Emit a mirage event")
    p.add_argument("event_type", choices=list(_DEFAULT_SEVERITY.keys()))
    p.add_argument("--data", default="{}", help="JSON dict of extra fields")
    p.add_argument("--severity", default=None)
    p.add_argument("--workspace-id", default="solar-default")
    args = p.parse_args()
    sev = args.severity or _DEFAULT_SEVERITY.get(args.event_type, "info")
    try:
        extra = json.loads(args.data)
    except json.JSONDecodeError:
        extra = {}
    result = emit(args.event_type, extra, sev, args.workspace_id)
    print(json.dumps(result, indent=2))
