"""Event ledger bridge for benchmark subsystem.

S04 N2 / AP-6: provides `emit_benchmark_event()` which appends a sanitized
JSON line to ``$HARNESS_DIR/state/events.jsonl`` for any of the 6 locked
benchmark event names (design.md §2.2 AP-6 / parent PRD §9):

  - benchmark.doctor
  - benchmark.plan
  - benchmark.run.started
  - benchmark.run.completed
  - benchmark.run.pending
  - benchmark.run.failed

Sanitizer enforces C7: any key matching ``*_key``, ``*_token``, or ``*_secret``
(case-insensitive) has its value replaced with ``"<redacted>"`` recursively.
Event names outside the locked set raise ``ValueError``.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Any


BENCHMARK_EVENT_NAMES: tuple[str, ...] = (
    "benchmark.doctor",
    "benchmark.plan",
    "benchmark.run.started",
    "benchmark.run.completed",
    "benchmark.run.pending",
    "benchmark.run.failed",
)

EVENTS_RELATIVE: str = "state/events.jsonl"
REDACTED: str = "<redacted>"

_SENSITIVE_SUFFIX_RE: re.Pattern[str] = re.compile(
    r"(?:_key|_token|_secret|_password|_passwd|_apikey)$",
    re.IGNORECASE,
)


def _is_sensitive_key(key: str) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in {"key", "token", "secret", "password", "apikey", "api_key"}:
        return True
    return bool(_SENSITIVE_SUFFIX_RE.search(lowered))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_sensitive_key(k):
                out[k] = REDACTED
            else:
                out[k] = _sanitize(v)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _resolve_events_path(harness_dir: str | None) -> Path:
    if harness_dir is None:
        harness_dir = os.environ.get("HARNESS_DIR") or str(Path.home() / ".solar" / "harness")
    return Path(harness_dir).expanduser() / EVENTS_RELATIVE


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_benchmark_event(
    event_type: str,
    payload: dict[str, Any],
    harness_dir: str | None = None,
) -> str:
    """Append a sanitized JSON event line to events.jsonl.

    Args:
        event_type: Must be one of ``BENCHMARK_EVENT_NAMES``.
        payload: Arbitrary JSON-serializable dict. Sensitive keys are
            redacted recursively before write.
        harness_dir: Solar harness root. Defaults to ``$HARNESS_DIR`` or
            ``~/.solar/harness``.

    Returns:
        The absolute path of the events.jsonl file that was written.

    Raises:
        ValueError: If ``event_type`` is not in the locked event-name set.
        TypeError: If ``payload`` is not a dict.
    """
    if event_type not in BENCHMARK_EVENT_NAMES:
        raise ValueError(
            f"unknown benchmark event_type: {event_type!r}; "
            f"allowed: {BENCHMARK_EVENT_NAMES}"
        )
    if not isinstance(payload, dict):
        raise TypeError(f"payload must be dict, got {type(payload).__name__}")

    sanitized = _sanitize(payload)
    record = {
        "ts": _utc_now_iso(),
        "event": event_type,
        "source": "benchmark.orchestration",
        "payload": sanitized,
    }
    events_path = _resolve_events_path(harness_dir)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return str(events_path)
