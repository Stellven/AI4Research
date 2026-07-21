"""Autopilot finding emitters for benchmark subsystem.

S04 N2 / AP-1: provides `check_benchmark_findings()` which reads the latest
benchmark run summary and emits Finding records for autopilot. Per design.md
§2.2 AP-1 and D3, finding type values are restricted to:

  - benchmark_run_pending   (severity=warn)   verdict in {"pending"}
  - benchmark_run_failed    (severity=error)  verdict in {"error", "failed"}
  - benchmark_run_ok        (severity=info)   verdict in {"ok", "pass", "passed"}

If no run summary exists, the hook returns an empty list (silent — no spurious
findings). The Finding dataclass mirrors the shape used by autopilot's existing
inspect_* scanners (type/severity/message/source) without introducing new
fields (D3 / C3 compliance).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


FINDING_TYPE_PENDING: str = "benchmark_run_pending"
FINDING_TYPE_FAILED: str = "benchmark_run_failed"
FINDING_TYPE_OK: str = "benchmark_run_ok"

SEVERITY_WARN: str = "warn"
SEVERITY_ERROR: str = "error"
SEVERITY_INFO: str = "info"

LATEST_REPORT_RELATIVE: str = "reports/benchmark/latest-terminal-bench-2.json"

_PENDING_VERDICTS: frozenset[str] = frozenset({"pending"})
_FAILED_VERDICTS: frozenset[str] = frozenset({"error", "failed", "fail"})
_OK_VERDICTS: frozenset[str] = frozenset({"ok", "pass", "passed", "success"})


@dataclass(frozen=True)
class Finding:
    type: str
    severity: str
    message: str
    source: str = "benchmark.orchestration"
    details: dict[str, Any] = field(default_factory=dict)


def _resolve_report_path(state_dir: str) -> Path:
    base = Path(state_dir).expanduser()
    return base / LATEST_REPORT_RELATIVE


def _load_report(report_path: Path) -> dict[str, Any] | None:
    if not report_path.exists():
        return None
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _summary_message(verdict: str, report: dict[str, Any]) -> str:
    score = report.get("score")
    pass_count = report.get("pass_count")
    fail_count = report.get("fail_count")
    benchmark = report.get("benchmark", "terminal-bench")
    parts = [f"verdict={verdict}", f"benchmark={benchmark}"]
    if score is not None:
        parts.append(f"score={score}")
    if pass_count is not None and fail_count is not None:
        parts.append(f"passed={pass_count}/{(pass_count or 0) + (fail_count or 0)}")
    return " ".join(parts)


def _details(report: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "run_id",
        "benchmark",
        "benchmark_version",
        "dataset",
        "adapter",
        "agent",
        "model",
        "env",
        "verdict",
        "score",
        "pass_count",
        "fail_count",
        "pending_count",
        "started_at",
        "completed_at",
        "duration_sec",
    )
    return {k: report[k] for k in keep if k in report}


def check_benchmark_findings(state_dir: str | None = None) -> list[Finding]:
    """Inspect the latest benchmark run summary and return findings.

    Args:
        state_dir: Solar harness root (HARNESS_DIR). Defaults to
            ``$HARNESS_DIR`` env var or ``~/.solar/harness``.

    Returns:
        A list of Finding records. Empty list when no run summary exists
        or the file cannot be parsed.
    """
    if state_dir is None:
        state_dir = os.environ.get("HARNESS_DIR") or str(Path.home() / ".solar" / "harness")
    report_path = _resolve_report_path(state_dir)
    report = _load_report(report_path)
    if report is None:
        return []
    verdict_raw = report.get("verdict")
    if not isinstance(verdict_raw, str):
        return []
    verdict = verdict_raw.strip().lower()
    details = _details(report)
    message = _summary_message(verdict, report)
    if verdict in _PENDING_VERDICTS:
        return [Finding(FINDING_TYPE_PENDING, SEVERITY_WARN, message, details=details)]
    if verdict in _FAILED_VERDICTS:
        return [Finding(FINDING_TYPE_FAILED, SEVERITY_ERROR, message, details=details)]
    if verdict in _OK_VERDICTS:
        return [Finding(FINDING_TYPE_OK, SEVERITY_INFO, message, details=details)]
    return []
