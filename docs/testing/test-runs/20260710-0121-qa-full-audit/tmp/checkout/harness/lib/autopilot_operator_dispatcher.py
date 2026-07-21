"""
Autopilot Operator Dispatcher — hooks into the autopilot scheduling loop,
checks due lines per operator_schedules.json cron bindings,
dispatches via operator_router, handles GitHub dual-run.

Part of Solar Harness AI Influence operator consolidation (S04 N2).
Depends on: operator_schedule_binder (N1), operator_router (S03 N2),
            operator_state_machine (S03 N3).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import operator_router
from operator_router import ControlComparisonResult, DispatchResult, NoFallbackError
from operator_state_machine import OperatorRun, OperatorState, append_event_log

_HARNESS_ROOT = Path(
    os.environ.get("SOLAR_HARNESS_DIR", os.path.expanduser("~/.solar/harness"))
)
_SCHEDULES_PATH = _HARNESS_ROOT / "config" / "operator_schedules.json"
_EVENT_LOG_PATH = _HARNESS_ROOT / "run" / "operator_events.jsonl"
_METADATA_DIR = _HARNESS_ROOT / "run" / "operator_metadata"


class ScheduleLoadError(Exception):
    """Raised when operator_schedules.json cannot be loaded."""


# ── cron parsing ─────────────────────────────────────────────────────────────


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into the set of matching integer values.

    Supports: literal (``5``), wildcard (``*``), range (``1-5``),
    step (``*/15``, ``0-30/10``), and comma-separated combinations.
    """
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if base == "*":
                start = min_val
                end = max_val
            elif "-" in base:
                lo_s, hi_s = base.split("-", 1)
                start, end = int(lo_s), int(hi_s)
            else:
                start = int(base)
                end = max_val
            values.update(range(start, end + 1, step))
        elif "-" in part:
            lo_s, hi_s = part.split("-", 1)
            values.update(range(int(lo_s), int(hi_s) + 1))
        elif part == "*":
            values.update(range(min_val, max_val + 1))
        else:
            values.add(int(part))
    return values


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """Return True if *cron_expr* (5-field) matches *dt*.

    Cron day-of-week convention: 0 = Sunday .. 6 = Saturday.
    Python ``datetime.weekday()``: 0 = Monday .. 6 = Sunday.
    Conversion: ``(dt.weekday() + 1) % 7``.
    """
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False

    minute_set = _parse_cron_field(fields[0], 0, 59)
    hour_set = _parse_cron_field(fields[1], 0, 23)
    dom_set = _parse_cron_field(fields[2], 1, 31)
    month_set = _parse_cron_field(fields[3], 1, 12)
    dow_set = _parse_cron_field(fields[4], 0, 6)

    cron_dow = (dt.weekday() + 1) % 7  # Mon=1..Sat=6, Sun=0

    return (
        dt.minute in minute_set
        and dt.hour in hour_set
        and dt.day in dom_set
        and dt.month in month_set
        and cron_dow in dow_set
    )


# ── schedule loading ─────────────────────────────────────────────────────────


def load_schedules(path: str | Path | None = None) -> dict[str, Any]:
    """Load and return the parsed ``operator_schedules.json``.

    Raises:
        ScheduleLoadError: On missing file or invalid JSON.
    """
    p = Path(path) if path else _SCHEDULES_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ScheduleLoadError(f"Schedules file not found: {p}")
    except json.JSONDecodeError as e:
        raise ScheduleLoadError(f"Invalid JSON in schedules file {p}: {e}")


# ── due-line detection ───────────────────────────────────────────────────────


def find_due_lines(
    schedules: dict[str, Any] | None = None,
    now: datetime | None = None,
    schedules_path: str | Path | None = None,
) -> list[str]:
    """Return binding names whose cron expression matches *now*.

    Manual (``type != "cron"``) bindings are never due.
    """
    if schedules is None:
        schedules = load_schedules(schedules_path)
    if now is None:
        now = datetime.now(timezone.utc)

    due: list[str] = []
    for name, binding in schedules.get("bindings", {}).items():
        if binding.get("type") != "cron":
            continue
        cron_expr = binding.get("cron")
        if not cron_expr:
            continue
        if cron_matches(cron_expr, now):
            due.append(name)
    return due


# ── run-id generation ────────────────────────────────────────────────────────


def generate_run_id(line: str) -> str:
    """Generate a unique run ID: ``{line}-{timestamp}-{uuid8}``."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{line}-{ts}-{short}"


# ── metadata collection ──────────────────────────────────────────────────────


def _metadata_path(line: str, run_id: str, root: Path) -> Path:
    return root / "run" / "operator_metadata" / line / f"{run_id}.metadata.json"


def _build_single_metadata(
    line: str,
    run_id: str,
    result: DispatchResult,
) -> dict[str, Any]:
    return {
        "schema": "solar.operator_metadata.v1",
        "line": line,
        "run_id": run_id,
        "mode": "single",
        "dispatched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "primary": {
            "script": result.script,
            "role": result.role,
            "returncode": result.returncode,
            "success": result.success,
            "duration_s": result.duration_s,
        },
    }


def _build_dual_metadata(
    line: str,
    run_id: str,
    result: ControlComparisonResult,
) -> dict[str, Any]:
    return {
        "schema": "solar.operator_metadata.v1",
        "line": line,
        "run_id": run_id,
        "mode": "dual_run",
        "dispatched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "both_succeeded": result.both_succeeded,
        "primary": {
            "script": result.primary.script,
            "role": result.primary.role,
            "returncode": result.primary.returncode,
            "success": result.primary.success,
            "duration_s": result.primary.duration_s,
        },
        "control": {
            "script": result.control.script,
            "role": result.control.role,
            "returncode": result.control.returncode,
            "success": result.control.success,
            "duration_s": result.control.duration_s,
        },
    }


def _build_error_metadata(
    line: str,
    run_id: str,
    error: str,
) -> dict[str, Any]:
    return {
        "schema": "solar.operator_metadata.v1",
        "line": line,
        "run_id": run_id,
        "mode": "error",
        "dispatched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": error,
    }


def _write_metadata(
    line: str,
    run_id: str,
    metadata: dict[str, Any],
    root: Path,
) -> Path:
    """Write metadata dict to ``run/operator_metadata/{line}/{run_id}.metadata.json``."""
    p = _metadata_path(line, run_id, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


# ── single-line dispatch ─────────────────────────────────────────────────────


def dispatch_line(
    line: str,
    schedules: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    harness_root: str | Path | None = None,
    timeout: int = 300,
    event_log_path: str | Path | None = None,
) -> dict[str, Any]:
    """Dispatch a single operator line.

    Automatically uses ``dispatch_with_control`` when the binding has
    ``dual_run.enabled = true``.

    Returns a result dict with ``run_id``, ``line``, ``state``,
    ``dual_run``, and ``metadata_path``.
    """
    if schedules is None:
        schedules = load_schedules()

    binding = schedules.get("bindings", {}).get(line)
    if binding is None:
        raise KeyError(f"No schedule binding for line '{line}'")

    run_id = generate_run_id(line)
    root = Path(harness_root) if harness_root else _HARNESS_ROOT
    log_path = Path(event_log_path) if event_log_path else _EVENT_LOG_PATH

    run = OperatorRun(run_id=run_id, line=line)
    run.transition(OperatorState.RUNNING)

    dual_run_cfg = binding.get("dual_run", {})
    is_dual = dual_run_cfg.get("enabled", False)

    try:
        if is_dual:
            result = operator_router.dispatch_with_control(
                line=line,
                run_id=run_id,
                registry=registry,
                harness_root=harness_root,
                timeout=timeout,
            )
            metadata = _build_dual_metadata(line, run_id, result)

            if result.both_succeeded:
                run.transition(OperatorState.SUCCESS, metadata={"mode": "dual_run"})
            elif result.primary.success or result.control.success:
                run.transition(OperatorState.PARTIAL, metadata={"mode": "dual_run"})
            else:
                run.transition(OperatorState.FAILED, metadata={"mode": "dual_run"})
        else:
            result = operator_router.dispatch(
                line=line,
                run_id=run_id,
                registry=registry,
                harness_root=harness_root,
                timeout=timeout,
            )
            metadata = _build_single_metadata(line, run_id, result)
            # dispatch() only returns on success (raises NoFallbackError otherwise)
            run.transition(OperatorState.SUCCESS, metadata={"mode": "single"})

    except (NoFallbackError, ValueError) as exc:
        run.transition(OperatorState.FAILED, metadata={"error": str(exc)})
        metadata = _build_error_metadata(line, run_id, str(exc))

    meta_path = _write_metadata(line, run_id, metadata, root)
    append_event_log(log_path, run.events)

    return {
        "run_id": run_id,
        "line": line,
        "state": run.state.value,
        "dual_run": is_dual,
        "metadata_path": str(meta_path),
    }


# ── tick: check all due lines and dispatch ───────────────────────────────────


def tick(
    schedules: dict[str, Any] | None = None,
    registry: dict[str, Any] | None = None,
    now: datetime | None = None,
    harness_root: str | Path | None = None,
    timeout: int = 300,
    event_log_path: str | Path | None = None,
    schedules_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute one scheduling tick.

    1. Load schedules.
    2. Find lines whose cron expression matches *now*.
    3. Dispatch each due line (single or dual-run).
    4. Return a summary with per-line results.
    """
    if schedules is None:
        schedules = load_schedules(schedules_path)
    if now is None:
        now = datetime.now(timezone.utc)

    due = find_due_lines(schedules=schedules, now=now)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for line in due:
        try:
            r = dispatch_line(
                line=line,
                schedules=schedules,
                registry=registry,
                harness_root=harness_root,
                timeout=timeout,
                event_log_path=event_log_path,
            )
            results.append(r)
        except Exception as exc:
            errors.append({"line": line, "error": str(exc)})

    return {
        "ok": len(errors) == 0,
        "tick_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "due_count": len(due),
        "due_lines": due,
        "dispatched": results,
        "errors": errors,
    }
