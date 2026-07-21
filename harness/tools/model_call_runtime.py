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
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

from session_log import DuplicateEventError, SessionLog

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))


def _pane_safe(pane: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pane or "unknown")


def _read_pane_env(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_pane_id(pane: str) -> str:
    if str(pane or "").startswith("%"):
        return str(pane)
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", str(pane), "#{pane_id}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return str(result.stdout or "").strip()
    except Exception:
        pass
    return ""


def _provider_from_pane_env(data: dict[str, Any]) -> str:
    base = str(data.get("base_url_host") or "").strip().lower()
    if "z.ai" in base or "zhipu" in base:
        return "zhipu"
    if "deepseek" in base:
        return "deepseek"
    if "google" in base or "gemini" in base:
        return "google"
    if "openai" in base:
        return "openai"
    if "anthropic" in base:
        return "anthropic"

    auth = str(data.get("auth_source") or "").strip().lower()
    if auth in {"openai", "codex"}:
        return "openai"
    if auth in {"anthropic", "claude"}:
        return "anthropic"
    if auth in {"zhipu", "zhipuai", "glm"}:
        return "zhipu"
    if auth in {"google", "gemini"}:
        return "google"

    runtime = str(data.get("pane_runtime") or "").strip().lower()
    if runtime == "codex":
        return "openai"
    if runtime == "claude":
        return "anthropic"
    return ""


def _model_from_flag(value: Any) -> str:
    try:
        tokens = shlex.split(str(value or ""))
    except ValueError:
        tokens = str(value or "").split()
    for index, token in enumerate(tokens):
        if token == "--model" and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--model="):
            return token.split("=", 1)[1]
    return ""


def pane_runtime_metadata(pane: str) -> dict[str, Any]:
    """Read the launch marker for a tmux target without confusing target and pane id.

    pane-launcher stores markers by immutable tmux pane id (for example ``%2``),
    while dispatchers normally address panes by a target such as
    ``solar-harness:0.2``. Resolve that target before falling back to an empty
    record so model-call and route evidence retain the runtime/provider.
    """
    pane_dir = HARNESS_DIR / "run" / "pane-env"
    candidates: list[tuple[str, Path]] = [
        (str(pane or ""), pane_dir / f"{_pane_safe(pane)}.json"),
    ]
    resolved = _resolve_pane_id(pane)
    if resolved and resolved != str(pane or ""):
        candidates.append((resolved, pane_dir / f"{_pane_safe(resolved)}.json"))

    for resolved_pane, path in candidates:
        if not path.is_file():
            continue
        data = _read_pane_env(path)
        if not data:
            continue
        result = dict(data)
        result["pane_target"] = str(pane or "")
        result["resolved_pane_id"] = resolved_pane
        result["metadata_source"] = str(path)
        result["provider"] = _provider_from_pane_env(result)
        result["model"] = _model_from_flag(result.get("model_flag"))
        return result
    return {
        "pane_target": str(pane or ""),
        "resolved_pane_id": resolved,
        "metadata_source": "",
        "provider": "",
        "model": "",
    }


def _pane_env(pane: str) -> dict[str, Any]:
    """Backward-compatible private alias."""
    return pane_runtime_metadata(pane)


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
    pane_env = pane_runtime_metadata(pane)
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
            "pane_runtime": pane_env.get("pane_runtime", ""),
            "runtime_bin": pane_env.get("runtime_bin", ""),
            "provider": pane_env.get("provider", ""),
            "model": pane_env.get("model", ""),
            "auth_source": pane_env.get("auth_source", ""),
            "base_url_host": pane_env.get("base_url_host", ""),
            "model_flag": pane_env.get("model_flag", ""),
            "extra_flags": pane_env.get("extra_flags", ""),
            "claude_bin": pane_env.get("claude_bin", ""),
            "metadata_source": pane_env.get("metadata_source", ""),
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
