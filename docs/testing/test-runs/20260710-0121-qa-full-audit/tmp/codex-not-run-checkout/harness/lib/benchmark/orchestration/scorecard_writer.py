"""AP-5 scorecard writer (opt-in) and AP-7 monitor read-only surface helper.

S04 N4: provides ``update_scorecard()`` which writes benchmark run results to
``sys_favorites`` or ``cortex_sources`` when explicitly opted-in via ``force=True``.
Also provides ``monitor_summary()`` for read-only surface display.

AP-5 behaviour (per acceptance):
  - ``update_scorecard(run_result)`` returns ``{"updated": False}`` by default.
  - ``update_scorecard(run_result, force=True)`` writes to ``sys_favorites`` or
    ``cortex_sources``.
  - No API key values appear in written data (sanitizer strips sensitive keys).

AP-7 behaviour:
  - ``monitor_summary()`` returns a read-only dict summarizing the latest
    benchmark run for autopilot monitor consumption. No write side effects.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .event_bridge import _sanitize

_SOLAR_DB_ENV: str = "SOLAR_DB"
_DEFAULT_DB: str = str(Path.home() / ".solar" / "solar.db")

_CAPABILITY_IDS: tuple[str, ...] = (
    "benchmark.run.terminal_bench",
    "agent.terminal_task.executor",
    "sandbox.docker.local",
    "harbor.adapter.v1",
)

_SENSITIVE_VALUE_RE: re.Pattern[str] = re.compile(
    r"(?:api[_-]?key|token|secret|password|passwd|credential)",
    re.IGNORECASE,
)


def _db_path() -> str:
    return os.environ.get(_SOLAR_DB_ENV) or _DEFAULT_DB


def _open_db(readonly: bool = True) -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    if readonly:
        conn.execute("PRAGMA query_only=1")
    return conn


def _strip_secrets(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str) and _SENSITIVE_VALUE_RE.search(v):
            out[k] = "<redacted>"
        elif isinstance(v, dict):
            out[k] = _strip_secrets(v)
        elif isinstance(v, (list, tuple)):
            out[k] = [
                _strip_secrets(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            out[k] = v
    return out


def _result_to_record(run_result: dict[str, Any]) -> dict[str, Any]:
    safe = _sanitize(run_result)
    safe = _strip_secrets(safe)
    return safe


def update_scorecard(
    run_result: dict[str, Any],
    *,
    force: bool = False,
    target: str = "sys_favorites",
    harness_dir: str | None = None,
) -> dict[str, Any]:
    """Write benchmark run result to the knowledge base.

    Args:
        run_result: Dict matching BenchmarkRunResult schema.
        force: Must be True to perform any write. Default False returns
            ``{"updated": False}`` immediately.
        target: ``"sys_favorites"`` or ``"cortex_sources"``.
        harness_dir: Unused; reserved for future path-based targets.

    Returns:
        A dict with ``updated`` (bool) and optional metadata.
    """
    if not force:
        return {"updated": False}

    safe = _result_to_record(run_result)
    run_id = safe.get("run_id", "unknown")
    verdict = safe.get("verdict", "unknown")
    score = safe.get("score")
    agent = safe.get("agent", "unknown")
    benchmark = safe.get("benchmark", "terminal-bench")
    adapter = safe.get("adapter", "unknown")
    pass_count = safe.get("pass_count", 0)
    fail_count = safe.get("fail_count", 0)
    pending_count = safe.get("pending_count", 0)
    started_at = safe.get("started_at", "")

    title = f"Benchmark: {benchmark} run {run_id} verdict={verdict}"
    question = f"What was the result of benchmark run {run_id}?"
    answer_parts = [
        f"Benchmark: {benchmark}",
        f"Adapter: {adapter}",
        f"Agent: {agent}",
        f"Verdict: {verdict}",
    ]
    if score is not None:
        answer_parts.append(f"Score: {score}")
    answer_parts.append(f"Tasks: {pass_count} passed, {fail_count} failed, {pending_count} pending")
    if started_at:
        answer_parts.append(f"Started: {started_at}")
    answer = "; ".join(answer_parts)

    tags = json.dumps(["benchmark", benchmark, verdict, adapter, agent])

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if target == "cortex_sources":
        return _write_cortex(safe, run_id, title, now_iso)
    return _write_favorites(title, question, answer, tags, run_id, now_iso, verdict)


def _write_favorites(
    title: str,
    question: str,
    answer: str,
    tags: str,
    run_id: str,
    now_iso: str,
    verdict: str,
) -> dict[str, Any]:
    importance = 7 if verdict in ("ok", "pass", "passed") else 5
    try:
        conn = sqlite3.connect(_db_path(), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        cursor = conn.execute(
            """INSERT INTO sys_favorites (title, question, answer, tags, session_id, importance, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, question, answer, tags, f"benchmark:{run_id}", importance, now_iso),
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
    except Exception as exc:
        return {"updated": False, "error": str(exc), "target": "sys_favorites"}

    return {
        "updated": True,
        "target": "sys_favorites",
        "row_id": row_id,
        "run_id": run_id,
    }


def _write_cortex(
    safe: dict[str, Any],
    run_id: str,
    title: str,
    now_iso: str,
) -> dict[str, Any]:
    adapter = safe.get("adapter", "unknown")
    try:
        conn = sqlite3.connect(_db_path(), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        citation_key = f"bench-{run_id}"
        finding = f"Benchmark run {run_id}: verdict={safe.get('verdict', '?')}, score={safe.get('score', 'N/A')}"
        cursor = conn.execute(
            """INSERT INTO cortex_sources (task_id, citation_key, title, finding, credibility, expert_model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                f"benchmark:{run_id}",
                citation_key,
                title,
                finding,
                0.8 if safe.get("verdict") in ("ok", "pass") else 0.5,
                adapter,
                now_iso,
            ),
        )
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
    except Exception as exc:
        return {"updated": False, "error": str(exc), "target": "cortex_sources"}

    return {
        "updated": True,
        "target": "cortex_sources",
        "row_id": row_id,
        "run_id": run_id,
    }


def monitor_summary(harness_dir: str | None = None) -> dict[str, Any]:
    """AP-7: read-only surface helper for autopilot monitor.

    Returns a summary dict of the latest benchmark run without any write
    side effects. Safe to call on every autopilot scan cycle.

    Args:
        harness_dir: Solar harness root. Defaults to ``$HARNESS_DIR``
            or ``~/.solar/harness``.

    Returns:
        Dict with keys: latest_verdict, latest_run_id, latest_score,
        capabilities (list of AP-5 capability IDs), last_updated.
        Returns zeros/empty if no run exists.
    """
    if harness_dir is None:
        harness_dir = os.environ.get("HARNESS_DIR") or str(Path.home() / ".solar" / "harness")
    report_path = Path(harness_dir) / "reports" / "benchmark" / "latest-terminal-bench-2.json"

    summary: dict[str, Any] = {
        "latest_verdict": None,
        "latest_run_id": None,
        "latest_score": None,
        "capabilities": list(_CAPABILITY_IDS),
        "last_updated": None,
    }

    if not report_path.is_file():
        return summary

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return summary

    if not isinstance(data, dict):
        return summary

    summary["latest_verdict"] = data.get("verdict")
    summary["latest_run_id"] = data.get("run_id")
    summary["latest_score"] = data.get("score")
    summary["last_updated"] = data.get("completed_at") or data.get("started_at")

    return summary
