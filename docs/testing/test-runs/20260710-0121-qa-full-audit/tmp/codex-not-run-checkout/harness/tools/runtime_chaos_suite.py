#!/usr/bin/env python3
"""Solar Harness runtime interface chaos suite.

Small, local, token-free failure tests for the managed-agent runtime
interfaces. The suite deliberately avoids destructive commands, external API
calls, and real credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(__file__))

from activity_runtime import ActivityRuntime
from context_projection import ContextProjection
from hands_runtime import MockHand, ShellHand
from runtime_interfaces import ResultStatus
from session_log import SessionLog
from worker_runtime import WorkerRuntime


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
REPORT_DIR = HARNESS / "reports" / "managed-agent-runtime-interfaces"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_id() -> str:
    return f"chaos-{int(time.time() * 1000)}-{os.getpid()}"


def _cleanup_session(session_id: str, harness_dir: Path) -> None:
    shutil.rmtree(harness_dir / "sessions" / session_id, ignore_errors=True)


def _case(name: str, fn: Callable[[Path], dict[str, Any]], harness_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        data = fn(harness_dir)
        ok = bool(data.pop("ok", False))
        return {
            "name": name,
            "ok": ok,
            "status": "ok" if ok else "error",
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            **data,
        }
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "status": "error",
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


def duplicate_command(harness_dir: Path) -> dict[str, Any]:
    hand = MockHand()
    ref = hand.provision()
    first = hand.execute(ref, "noop", {"x": 1}, idempotency_key="dup:1")
    second = hand.execute(ref, "noop", {"x": 2}, idempotency_key="dup:1")
    return {
        "ok": first.status == ResultStatus.OK and second.status == ResultStatus.DUPLICATE_SUPPRESSED,
        "first": first.status.value,
        "second": second.status.value,
    }


def shell_destructive_denied(harness_dir: Path) -> dict[str, Any]:
    hand = ShellHand()
    ref = hand.provision()
    result = hand.execute(ref, "deny", {"command": "rm -rf /"}, idempotency_key="deny:1")
    return {
        "ok": result.status == ResultStatus.ERROR and "denied" in (result.error or ""),
        "status_value": result.status.value,
        "error": result.error,
    }


def shell_secret_redacted(harness_dir: Path) -> dict[str, Any]:
    hand = ShellHand()
    ref = hand.provision()
    secret = "api_key=sk-abcdef12345678901234567890123456789012345678"
    result = hand.execute(ref, "secret", {"command": f"echo {secret}"}, idempotency_key="secret:1")
    output = result.output or ""
    return {
        "ok": result.status == ResultStatus.OK and "[REDACTED]" in output and "sk-abcdef" not in output,
        "status_value": result.status.value,
        "output": output,
        "redacted_count": len(result.redacted_secrets),
    }


def cancelled_activity_event(harness_dir: Path) -> dict[str, Any]:
    sid = _session_id()
    try:
        rt = ActivityRuntime(sid, harness_dir=str(harness_dir))
        rt.command_issued("act-cancel", target="builder")
        rt.activity_started("act-cancel")
        rt.activity_cancelled("act-cancel", reason="chaos test")
        types = [ev.get("type") for ev in SessionLog(sid, harness_dir=str(harness_dir)).all_events()]
        return {
            "ok": types == ["command_issued", "activity_started", "activity_cancelled"],
            "types": types,
        }
    finally:
        _cleanup_session(sid, harness_dir)


def worker_lease_expiry(harness_dir: Path) -> dict[str, Any]:
    workers_dir = harness_dir / "state" / "workers"
    shutil.rmtree(workers_dir, ignore_errors=True)
    wr = WorkerRuntime(harness_dir=str(harness_dir))
    wr.register("chaos-worker", capabilities=["bash"], location="local")
    lease = wr.acquire_lease("chaos-worker", "session", "activity", ttl_seconds=0)
    time.sleep(1)
    expired = wr.expire_leases()
    active = wr.get_active_leases()
    return {
        "ok": lease is not None and len(expired) == 1 and len(active) == 0,
        "lease_acquired": lease is not None,
        "expired_count": len(expired),
        "active_count": len(active),
    }


def context_projection_no_rewrite_and_redact(harness_dir: Path) -> dict[str, Any]:
    sid = _session_id()
    try:
        log = SessionLog(sid, harness_dir=str(harness_dir))
        log.append("activity_started", actor="builder", payload={"msg": "token=supersecret123456789"})
        before = len(log.all_events())
        text = ContextProjection(sid, harness_dir=str(harness_dir)).build_context_text()
        after = len(log.all_events())
        return {
            "ok": before == after and "[REDACTED]" in text and "supersecret" not in text,
            "before_count": before,
            "after_count": after,
            "redacted": "[REDACTED]" in text,
        }
    finally:
        _cleanup_session(sid, harness_dir)


CASES: list[tuple[str, Callable[[Path], dict[str, Any]]]] = [
    ("duplicate_command", duplicate_command),
    ("shell_destructive_denied", shell_destructive_denied),
    ("shell_secret_redacted", shell_secret_redacted),
    ("cancelled_activity_event", cancelled_activity_event),
    ("worker_lease_expiry", worker_lease_expiry),
    ("context_projection_no_rewrite_and_redact", context_projection_no_rewrite_and_redact),
]


def write_reports(result: dict[str, Any], report_dir: Path = REPORT_DIR) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "chaos-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    rows = "\n".join(
        f"| {case['name']} | {'ok' if case.get('ok') else 'error'} | {case.get('duration_ms')} |"
        for case in result["cases"]
    )
    md = f"""# Runtime Interface Chaos Report

Generated: {result['generated_at']}

| Case | Status | Duration ms |
|------|--------|-------------|
{rows}

Summary: {result['passed']}/{result['total']} passed.

This suite is local and token-free. It validates runtime interface failure
semantics without destructive shell commands or external credentials.
"""
    (report_dir / "chaos-report.md").write_text(md)


def run_suite(*, harness_dir: Path = HARNESS, write: bool = True) -> dict[str, Any]:
    work_dir = harness_dir / "run" / "runtime-chaos" / f"{int(time.time() * 1000)}-{os.getpid()}"
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        cases = [_case(name, fn, work_dir) for name, fn in CASES]
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    passed = sum(1 for c in cases if c.get("ok"))
    result = {
        "ok": passed == len(cases),
        "generated_at": _now(),
        "harness_dir": str(harness_dir),
        "isolated_work_dir": str(work_dir),
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
    }
    if write:
        write_reports(result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Solar Harness runtime interface chaos suite")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    result = run_suite(write=not args.no_write)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Runtime chaos: {result['passed']}/{result['total']} passed")
        for case in result["cases"]:
            print(f"- {case['name']}: {'ok' if case.get('ok') else 'error'}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
