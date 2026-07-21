#!/usr/bin/env python3
"""Bridge Claude Code hook events into Solar-Harness session logs.

This records the observable tool boundary from pane-local Claude Code hooks.
It intentionally does not claim to see hidden model reasoning; it captures the
tool name, hook phase, redacted hook payload, pane, persona, and cwd.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

from session_log import DuplicateEventError, SessionLog


SECRET_PATTERNS = [
    r"(?i)api[_-]?key\s*[=:]\s*\S+",
    r"(?i)token\s*[=:]\s*\S{8,}",
    r"(?i)password\s*[=:]\s*\S+",
    r"(?i)secret\s*[=:]\s*\S+",
    r"(?i)credential\s*[=:]\s*\S+",
    r"(?i)auth[_-]?token\s*[=:]\s*\S+",
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[0-9a-zA-Z]{36}",
    r"sk-[0-9a-zA-Z]{20,}",
]


def _redact_text(text: str) -> str:
    out = text
    for pattern in SECRET_PATTERNS:
        out = re.sub(pattern, "[REDACTED]", out)
    return out


def _redact_obj(obj: Any) -> Any:
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    text = _redact_text(text)
    if len(text) > 8000:
        text = text[:8000] + "...[TRUNCATED]"
    try:
        return json.loads(text)
    except Exception:
        return text


def _read_hook_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"raw": data}
    except Exception:
        return {"raw": raw[:8000]}


def _first(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def _nested_tool_name(data: dict[str, Any]) -> str:
    direct = _first(data, "tool_name", "toolName", "tool", "name")
    if direct:
        return direct
    for key in ("tool_use", "toolUse", "message", "request"):
        child = data.get(key)
        if isinstance(child, dict):
            direct = _first(child, "name", "tool_name", "toolName", "tool")
            if direct:
                return direct
    return "unknown"


def _activity_id(phase: str, data: dict[str, Any], tool_name: str) -> str:
    explicit = _first(data, "tool_use_id", "toolUseID", "tool_use_id", "id")
    if explicit:
        return explicit
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return f"tool:{tool_name}:{phase}:{digest}"


def record(phase: str, data: dict[str, Any]) -> dict[str, Any]:
    session_id = os.environ.get("SOLAR_RUNTIME_SESSION_ID") or f"pane-{os.environ.get('TMUX_PANE', 'unknown')}"
    pane = os.environ.get("TMUX_PANE", "")
    persona = os.environ.get("SOLAR_PERSONA", "")
    tool_name = _nested_tool_name(data)
    activity_id = _activity_id(phase, data, tool_name)
    event_type = {
        "pre-tool": "tool_call_requested",
        "post-tool": "tool_call_succeeded",
        "tool-error": "tool_call_failed",
    }.get(phase, "tool_call_requested")
    if phase == "post-tool":
        status = str(data.get("status") or data.get("result_status") or "").lower()
        if status in {"error", "failed", "failure"} or data.get("error"):
            event_type = "tool_call_failed"

    payload = {
        "pane": pane,
        "persona": persona,
        "tool_name": tool_name,
        "phase": phase,
        "cwd": os.getcwd(),
        "observability_boundary": "claude_code_hook_payload",
        "private_reasoning_visible": False,
        "hook_payload": _redact_obj(data),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    idem = f"{event_type}:{session_id}:{activity_id}:{digest}"
    log = SessionLog(session_id)
    try:
        event_id = log.append(
            event_type,
            actor=persona or "claude-hook",
            source="claude_hook_event_bridge",
            sprint_id=session_id,
            activity_id=activity_id,
            correlation_id=activity_id,
            idempotency_key=idem,
            payload=payload,
        )
        duplicate = False
    except DuplicateEventError:
        event_id = ""
        duplicate = True
    return {"ok": True, "duplicate": duplicate, "event_id": event_id, "event_type": event_type}


def main() -> int:
    parser = argparse.ArgumentParser(description="record Claude Code hook events into session log")
    parser.add_argument("phase", choices=["pre-tool", "post-tool", "tool-error"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = record(args.phase, _read_hook_payload())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
