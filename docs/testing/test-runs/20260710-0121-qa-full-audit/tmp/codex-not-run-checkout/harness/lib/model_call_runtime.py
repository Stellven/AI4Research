#!/usr/bin/env python3
"""Model-call event bridge for Solar-Harness panes.

Claude Code and third-party Claude-compatible CLIs do not expose private
per-token reasoning events. This module records the observable runtime boundary:
what dispatch was submitted to which pane/model, whether the TUI accepted it,
and whether the pane process exited cleanly. These events make model use
auditable without pretending to see hidden model internals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

from session_log import DuplicateEventError, SessionLog

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))


def _pane_safe(pane: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pane or "unknown")


def _pane_env(pane: str) -> dict[str, Any]:
    path = HARNESS_DIR / "run" / "pane-env" / f"{_pane_safe(pane)}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _file_info(path: str) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return {
            "instruction_file": str(p),
            "instruction_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "instruction_bytes": len(text.encode("utf-8")),
            "instruction_preview": re.sub(r"\s+", " ", text)[:500],
        }
    except Exception as exc:
        return {"instruction_file": str(p), "instruction_error": f"{type(exc).__name__}: {exc}"}


def record_model_event(
    event_type: str,
    *,
    session_id: str,
    pane: str,
    dispatch_id: str = "",
    instruction_file: str = "",
    actor: str = "coordinator",
    status: str = "",
    error: str = "",
    tries: int = 0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in {"model_call_requested", "model_call_succeeded", "model_call_failed", "model_session_started", "model_session_ended"}:
        raise ValueError(f"unsupported model event: {event_type}")
    log = SessionLog(session_id)
    pane_env = _pane_env(pane)
    payload: dict[str, Any] = {
        "pane": pane,
        "dispatch_id": dispatch_id,
        "status": status,
        "error": error,
        "tries": tries,
        "observability_boundary": "pane_tui_submission_and_process_lifecycle",
        "private_reasoning_visible": False,
        "model": {
            "persona": pane_env.get("persona", ""),
            "builder_slot": pane_env.get("builder_slot", ""),
            "auth_source": pane_env.get("auth_source", ""),
            "base_url_host": pane_env.get("base_url_host", ""),
            "model_flag": pane_env.get("model_flag", ""),
            "extra_flags": pane_env.get("extra_flags", ""),
            "claude_bin": pane_env.get("claude_bin", ""),
        },
    }
    payload.update(_file_info(instruction_file))
    if extra:
        payload.update(extra)

    digest_source = json.dumps(
        {
            "event_type": event_type,
            "session_id": session_id,
            "pane": pane,
            "dispatch_id": dispatch_id,
            "instruction_file": instruction_file,
            "status": status,
            "error": error,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
    idem = f"{event_type}:{session_id}:{dispatch_id or _pane_safe(pane)}:{digest}"
    try:
        event_id = log.append(
            event_type,
            actor=actor,
            source="model_call_runtime",
            sprint_id=session_id,
            activity_id=dispatch_id or None,
            correlation_id=dispatch_id or None,
            idempotency_key=idem,
            payload=payload,
        )
        duplicate = False
    except DuplicateEventError:
        event_id = ""
        duplicate = True
    return {
        "ok": True,
        "duplicate": duplicate,
        "event_id": event_id,
        "event_type": event_type,
        "session_id": session_id,
        "pane": pane,
        "dispatch_id": dispatch_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="record model-call runtime events")
    parser.add_argument("event", choices=["request", "succeeded", "failed", "session-started", "session-ended"])
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--pane", default="")
    parser.add_argument("--dispatch-id", default="")
    parser.add_argument("--instruction-file", default="")
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--status", default="")
    parser.add_argument("--error", default="")
    parser.add_argument("--tries", type=int, default=0)
    parser.add_argument("--exit-code", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    mapping = {
        "request": "model_call_requested",
        "succeeded": "model_call_succeeded",
        "failed": "model_call_failed",
        "session-started": "model_session_started",
        "session-ended": "model_session_ended",
    }
    extra: dict[str, Any] = {"recorded_at_unix": int(time.time())}
    if args.exit_code is not None:
        extra["exit_code"] = args.exit_code
    result = record_model_event(
        mapping[args.event],
        session_id=args.session_id,
        pane=args.pane,
        dispatch_id=args.dispatch_id,
        instruction_file=args.instruction_file,
        actor=args.actor,
        status=args.status,
        error=args.error,
        tries=args.tries,
        extra=extra,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
