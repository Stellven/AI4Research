#!/usr/bin/env python3
"""Fail-open, opt-in developer observations for Solar-Harness.

The trace is diagnostic evidence only.  Callers must never branch on the
return value, and this module deliberately refuses to retain prompt, command,
credential, or tool-output bodies.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "solar.observability.event.v1"
_MAX_EVENT_BYTES = 64 * 1024
_IDENTIFIERS = (
    "run_id", "session_id", "sprint_id", "node_id", "task_id",
    "dispatch_id", "attempt_id", "invocation_id", "span_id",
    "parent_span_id", "correlation_id", "causation_id",
)
_UNSAFE_KEY = re.compile(
    r"(?:authorization|credential|secret|password|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|api[_-]?key|raw[_-]?(?:prompt|command|output)|tool[_-]?output)",
    re.IGNORECASE,
)
_UNSAFE_EXACT_KEYS = {
    "prompt", "command", "stdout", "stderr", "output", "tool_output",
    "dispatch_text", "instruction", "instructions",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])gh[psou]_[A-Za-z0-9]{16,}"),
    re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(?:token|secret|password|credential)\s*[:=]\s*[^\s,;]{8,}"),
)
_PLAIN_DATA_STRING_KEYS = {
    "actor", "config_key", "failure_class", "fallback_reason", "hook",
    "lease_state", "logical_operator", "model", "operator_id", "provider",
    "provenance", "reason", "reasoning_effort", "requested_role",
    "result_filename", "selection_mode", "severity", "signal", "status",
    "structured_stream_reason", "submit_mode", "task_type", "terminal_reason",
    "verdict", "selected_operator_id", "preferred_operator", "decision",
    "runtime_state", "graph_revision_sha256", "eval_dispatch_id",
}


def _unsafe_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _UNSAFE_EXACT_KEYS or bool(_UNSAFE_KEY.search(key))


def _safe_text(value: Any, limit: int = 1000) -> str | None:
    text = str(value)
    if any(pattern.search(text) for pattern in _SECRET_VALUE_PATTERNS):
        return None
    return text[:limit]


def _hashed_text(value: str) -> dict[str, Any]:
    encoded = value.encode("utf-8", errors="replace")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded)}


def stable_id(kind: str, *parts: Any) -> str:
    material = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"{kind}-{digest}"


def enabled() -> bool:
    return os.environ.get("SOLAR_DEVELOPER_OBSERVABILITY", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def trace_path() -> Path:
    configured = os.environ.get("SOLAR_OBSERVABILITY_TRACE", "").strip()
    if configured:
        return Path(configured).expanduser()
    harness = Path(
        os.environ.get("HARNESS_DIR")
        or os.environ.get("SOLAR_HARNESS_DIR")
        or Path.home() / ".solar" / "harness"
    )
    return harness / "run" / "observability" / "run_trace.jsonl"


def _utc_from_ns(value: int) -> str:
    seconds, nanos = divmod(value, 1_000_000_000)
    base = dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
    return f"{base:%Y-%m-%dT%H:%M:%S}.{nanos:09d}Z"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _safe_value(key: str, value: Any, depth: int = 0) -> Any:
    if _unsafe_key(key):
        return None
    if depth > 5:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        safe = _safe_text(value)
        if safe is None:
            return None
        if key.strip().lower().replace("-", "_") in _PLAIN_DATA_STRING_KEYS:
            return safe
        return _hashed_text(value)
    if isinstance(value, Mapping):
        return {
            str(child_key): _safe_value(str(child_key), child_value, depth + 1)
            for child_key, child_value in value.items()
            if not _unsafe_key(str(child_key))
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(key, item, depth + 1) for item in list(value)[:100]]
    return _hashed_text(str(value))


def build_event(
    event: str,
    *,
    component: str,
    operation: str = "",
    operation_id: str | None = None,
    phase: str = "point",
    terminal: bool = False,
    operator: str | None = None,
    status: str = "",
    provenance: str = "observed",
    identifiers: Mapping[str, Any] | None = None,
    data: Mapping[str, Any] | None = None,
    observed_time_ns: int | None = None,
    monotonic_ns: int | None = None,
) -> dict[str, Any]:
    wall_ns = time.time_ns() if observed_time_ns is None else int(observed_time_ns)
    mono_ns = time.monotonic_ns() if monotonic_ns is None else int(monotonic_ns)
    supplied = dict(identifiers or {})
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "observed_at": _utc_from_ns(wall_ns),
        "observed_time_ns": wall_ns,
        "monotonic_ns": mono_ns,
        "event": _safe_text(event, 256),
        "component": _safe_text(component, 256),
        "operator": _safe_text(operator, 256) if operator not in {None, ""} else None,
        "operation": _safe_text(operation or event, 256),
        "operation_id": _safe_text(operation_id, 512) if operation_id else None,
        "phase": phase if phase in {"started", "progress", "completed", "point"} else "point",
        "terminal": bool(terminal),
        "status": _safe_text(status, 256) if status not in {None, ""} else None,
        "provenance": provenance if provenance in {"observed", "reported", "derived"} else "observed",
    }
    env_defaults = {
        "run_id": os.environ.get("SOLAR_OBSERVABILITY_RUN_ID") or os.environ.get("UAT_RUN_ID"),
        "session_id": os.environ.get("SESSION_ID"),
        "sprint_id": os.environ.get("SID") or os.environ.get("SPRINT_ID"),
        "node_id": os.environ.get("NODE_ID"),
        "task_id": os.environ.get("TASK_ID"),
        "dispatch_id": os.environ.get("DISPATCH_ID"),
        "attempt_id": os.environ.get("ATTEMPT_ID"),
        "invocation_id": os.environ.get("INVOCATION_ID"),
        "span_id": os.environ.get("SOLAR_OBSERVABILITY_SPAN_ID"),
        "parent_span_id": os.environ.get("SOLAR_OBSERVABILITY_PARENT_SPAN_ID"),
        "correlation_id": os.environ.get("CORRELATION_ID") or os.environ.get("SOLAR_OBSERVABILITY_CORRELATION_ID"),
        "causation_id": os.environ.get("CAUSATION_ID") or os.environ.get("SOLAR_OBSERVABILITY_CAUSATION_ID"),
    }
    for name in _IDENTIFIERS:
        if name == "parent_span_id" and "span_id" in supplied and name not in supplied:
            # A caller creating a child span may supply only the new span ID;
            # the process's current span is then its causal parent.
            value = env_defaults.get("span_id")
        else:
            value = supplied.get(name, env_defaults.get(name))
        record[name] = _safe_text(value, 512) if value not in {None, ""} else None
    record["data"] = _safe_value("data", dict(data or {}))
    return record


def _lock_file(file_descriptor: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
        import msvcrt

        if os.fstat(file_descriptor).st_size == 0:
            os.write(file_descriptor, b"\0")
            os.fsync(file_descriptor)
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_EX)


def _unlock_file(file_descriptor: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
        import msvcrt

        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)


def _write_all(file_descriptor: int, encoded: bytes) -> None:
    remaining = memoryview(encoded)
    while remaining:
        written = os.write(file_descriptor, remaining)
        if written <= 0:
            raise OSError("observability append made no progress")
        remaining = remaining[written:]


def observe(event: str, **kwargs: Any) -> bool:
    """Append one observation. Any failure is intentionally swallowed."""
    if not enabled():
        return False
    try:
        record = build_event(event, **kwargs)
        encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > _MAX_EVENT_BYTES:
            record["data"] = {"observation_error": "event_too_large", "encoded_bytes": len(encoded)}
            encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        path = trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(f".{path.name}.lock")
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock_file(lock_fd)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                _write_all(fd, encoded)
            finally:
                os.close(fd)
        finally:
            try:
                _unlock_file(lock_fd)
            finally:
                os.close(lock_fd)
        return True
    except Exception:
        return False
