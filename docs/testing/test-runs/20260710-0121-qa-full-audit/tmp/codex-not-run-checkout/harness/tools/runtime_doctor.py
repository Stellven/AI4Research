"""Solar Harness — Runtime Doctor.

Diagnoses event log health, projection drift, duplicate commands,
stale activities, and pane/session ownership.

Usage::

    solar-harness runtime doctor --json
    python3 lib/runtime_doctor.py --json
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HARNESS_DIR = os.path.expanduser("~/.solar/harness")
SPRINTS_DIR = os.path.join(HARNESS_DIR, "sprints")
SESSIONS_DIR = os.path.join(HARNESS_DIR, "sessions")


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_minutes(ts_str: str) -> Optional[float]:
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except ValueError:
        return None


# ------------------------------------------------------------------
# Individual checks
# ------------------------------------------------------------------

def _check_event_log_health(sprint_id: str) -> Dict[str, Any]:
    log_path = os.path.join(SESSIONS_DIR, sprint_id, "events.jsonl")
    if not os.path.exists(log_path):
        return {"ok": True, "warn": False, "message": "no event log (no events yet)", "event_count": 0}

    event_count = 0
    bad_lines = 0
    last_seq = 0
    seq_gaps: List[int] = []
    last_ts: Optional[str] = None

    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                event_count += 1
                seq = ev.get("seq", 0)
                if seq != last_seq + 1 and event_count > 1:
                    seq_gaps.append(seq)
                last_seq = seq
                ts = ev.get("ts")
                if ts:
                    last_ts = ts
            except json.JSONDecodeError:
                bad_lines += 1

    warn = bad_lines > 0 or bool(seq_gaps)
    message = "ok"
    if bad_lines:
        message = f"{bad_lines} corrupt line(s)"
    elif seq_gaps:
        message = f"seq gaps at {seq_gaps[:5]}"

    return {
        "ok": bad_lines == 0,
        "warn": warn,
        "message": message,
        "event_count": event_count,
        "bad_lines": bad_lines,
        "seq_gaps": seq_gaps[:10],
        "last_ts": last_ts,
    }


def _check_projection_drift(sprint_id: str) -> Dict[str, Any]:
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from projection_engine import ProjectionEngine
        engine = ProjectionEngine(sprint_id, harness_dir=HARNESS_DIR)
        state = engine.project()
        return {
            "ok": not state.drift_detected,
            "warn": state.drift_detected,
            "message": state.drift_reason if state.drift_detected else "no drift",
            "projected_status": state.status,
            "event_count": state.event_count,
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"projection error: {exc}"}


def _check_duplicate_commands(sprint_id: str) -> Dict[str, Any]:
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from projection_engine import ProjectionEngine
        engine = ProjectionEngine(sprint_id, harness_dir=HARNESS_DIR)
        state = engine.project()
        dups = state.duplicate_commands
        return {
            "ok": len(dups) == 0,
            "warn": len(dups) > 0,
            "message": f"{len(dups)} duplicate(s): {dups[:5]}" if dups else "none",
            "duplicate_commands": dups,
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"error: {exc}"}


def _check_stale_activities(sprint_id: str) -> Dict[str, Any]:
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from projection_engine import ProjectionEngine
        engine = ProjectionEngine(sprint_id, harness_dir=HARNESS_DIR)
        state = engine.project()
        stale = state.stale_activities
        return {
            "ok": len(stale) == 0,
            "warn": len(stale) > 0,
            "message": f"{len(stale)} stale: {stale[:5]}" if stale else "none",
            "stale_activities": stale,
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"error: {exc}"}


def _check_status_json(sprint_id: str) -> Dict[str, Any]:
    path = os.path.join(SPRINTS_DIR, f"{sprint_id}.status.json")
    if not os.path.exists(path):
        return {"ok": False, "warn": True, "message": "status.json missing"}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        age = None
        ts = data.get("updated_at") or data.get("projected_at")
        if ts:
            age = _age_minutes(ts)
        return {
            "ok": True,
            "warn": False,
            "message": "ok",
            "status": data.get("status"),
            "age_minutes": round(age, 1) if age is not None else None,
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"corrupt: {exc}"}


def _check_interface_health(sprint_id: str) -> Dict[str, Any]:
    """Check runtime interface layer health: modules importable, adapters exist."""
    sys.path.insert(0, os.path.dirname(__file__))
    dimensions: Dict[str, Dict[str, Any]] = {}

    # Session API: get_events exists
    try:
        from session_log import SessionLog
        test_sid = f"_doctor-check-{os.getpid()}"
        log = SessionLog(test_sid, harness_dir=HARNESS_DIR)
        page = log.get_events(limit=1)
        ok = "next_cursor" in page and "returned_count" in page
        dimensions["session_api"] = {"ok": ok, "message": "ok" if ok else "get_events missing fields"}
        import shutil
        shutil.rmtree(os.path.join(HARNESS_DIR, "sessions", test_sid), ignore_errors=True)
    except Exception as exc:
        dimensions["session_api"] = {"ok": False, "message": str(exc)}

    # Hands runtime: adapters available
    try:
        from hands_runtime import available_hand_types
        types = available_hand_types()
        type_names = [t.value for t in types]
        ok = len(types) >= 3 and "sandbox" in type_names
        dimensions["hands_runtime"] = {
            "ok": ok,
            "message": f"{len(types)} adapters available; sandbox={'yes' if 'sandbox' in type_names else 'no'}",
            "adapters": type_names,
        }
    except Exception as exc:
        dimensions["hands_runtime"] = {"ok": False, "message": str(exc)}

    # Sandbox hand: lifecycle smoke plus evidence/disposal visibility.
    try:
        from hands_runtime import SandboxHand
        from runtime_interfaces import ResultStatus
        import tempfile
        hand = SandboxHand()
        ref = hand.provision(capabilities=["doctor"])
        guard_root = tempfile.mkdtemp(prefix="solar-runtime-doctor-guard-")
        result = hand.execute(
            ref,
            "doctor-smoke",
            {
                "argv": ["/bin/sh", "-c", "printf doctor-ok > doctor.txt; cat doctor.txt"],
                "write_guard_roots": [guard_root],
            },
            idempotency_key=f"runtime-doctor-sandbox-{os.getpid()}",
            timeout_seconds=15,
        )
        disposed = hand.dispose(ref)
        write_guard = result.metadata.get("write_guard") or {}
        write_guard_violations = write_guard.get("violations") or []
        execution_mode = result.metadata.get("execution_mode", "")
        ok = (
            result.status == ResultStatus.OK
            and result.output == "doctor-ok"
            and bool(result.metadata.get("evidence_file"))
            and bool(disposed.output.get("workspace_removed"))
            and execution_mode == "argv"
            and bool(write_guard.get("enabled"))
            and not write_guard_violations
        )
        dimensions["sandbox_runtime"] = {
            "ok": ok,
            "message": "argv/provision/execute/evidence/write-guard/dispose ok" if ok else "sandbox lifecycle smoke failed",
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "evidence_file": result.metadata.get("evidence_file", ""),
            "workspace_removed": bool(disposed.output.get("workspace_removed")),
            "execution_mode": execution_mode,
            "write_guard_enabled": bool(write_guard.get("enabled")),
            "write_guard_violations": len(write_guard_violations),
            "boundary": "local process sandbox, not VM/container isolation",
        }
        import shutil
        shutil.rmtree(guard_root, ignore_errors=True)
    except Exception as exc:
        dimensions["sandbox_runtime"] = {"ok": False, "message": str(exc)}

    # Compare-version requires a git-managed harness repo.  Installed runtimes
    # may legitimately be non-git; keep this diagnostic visible without failing
    # the whole doctor.
    try:
        from session_tools import compare_version_doctor_payload
        report = compare_version_doctor_payload(Path(HARNESS_DIR), Path(HARNESS_DIR))
        dimensions["compare_version_ready"] = {
            "ok": True,
            "warn": not bool(report.get("ok")),
            "message": "ready" if report.get("ok") else "not ready: harness dir is not a git-managed repo",
            "available": bool(report.get("ok")),
            "checks": report.get("checks", {}),
            "usage": report.get("usage", ""),
        }
    except Exception as exc:
        dimensions["compare_version_ready"] = {"ok": True, "warn": True, "message": str(exc), "available": False}

    # Worker runtime: register/lease
    try:
        from worker_runtime import WorkerRuntime
        safe_sid = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in sprint_id)
        tmp_harness = os.path.join(HARNESS_DIR, "run", "runtime-doctor", f"{os.getpid()}-{safe_sid}")
        wr = WorkerRuntime(harness_dir=tmp_harness)
        info = wr.register("_doctor-check")
        ok = info.worker_id == "_doctor-check"
        import shutil
        shutil.rmtree(tmp_harness, ignore_errors=True)
        dimensions["worker_runtime"] = {"ok": ok, "message": "ok" if ok else "register failed"}
    except Exception as exc:
        dimensions["worker_runtime"] = {"ok": False, "message": str(exc)}

    # Context projection
    try:
        from context_projection import ContextProjection
        cp = ContextProjection("_doctor-check", harness_dir=HARNESS_DIR)
        view = cp.build_context()
        ok = isinstance(view.token_estimate, int)
        dimensions["context_projection"] = {"ok": ok, "message": "ok" if ok else "build_context failed"}
    except Exception as exc:
        dimensions["context_projection"] = {"ok": False, "message": str(exc)}

    # Chaos suite
    try:
        from runtime_chaos_suite import CASES
        ok = len(CASES) >= 6
        dimensions["chaos_suite"] = {
            "ok": ok,
            "message": f"{len(CASES)} scenarios defined",
            "scenarios": [c[0] for c in CASES],
        }
    except Exception as exc:
        dimensions["chaos_suite"] = {"ok": False, "message": str(exc)}

    # Write-path audit: active legacy cache writes must be bridged or explicitly
    # classified as non-lifecycle telemetry.
    try:
        from runtime_write_path_audit import audit as audit_write_paths
        report = audit_write_paths(Path(HARNESS_DIR))
        counts = report.get("counts", {})
        ok = bool(report.get("ok")) and counts.get("warn", 0) == 0
        dimensions["write_path_audit"] = {
            "ok": ok,
            "message": f"ok={counts.get('ok', 0)} warn={counts.get('warn', 0)} error={counts.get('error', 0)}",
            "scanned_files": report.get("scanned_files", 0),
            "counts": counts,
        }
    except Exception as exc:
        dimensions["write_path_audit"] = {"ok": False, "message": str(exc)}

    all_ok = all(d.get("ok", False) for d in dimensions.values())
    any_warn = any(d.get("warn") for d in dimensions.values()) or (not all_ok and any(d.get("ok") for d in dimensions.values()))
    return {
        "ok": all_ok,
        "warn": any_warn,
        "message": f"{sum(1 for d in dimensions.values() if d['ok'])}/{len(dimensions)} interfaces healthy",
        "dimensions": dimensions,
    }


def _check_context_runtime(sprint_id: str) -> Dict[str, Any]:
    """Check that context projection is backed by real recall and audit state."""
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from context_projection import ContextProjection
        cp = ContextProjection(sprint_id, harness_dir=HARNESS_DIR)
        view = cp.build_context(query=sprint_id, budget_tokens=1200)
        real_hits = [
            h for h in view.kb_hits
            if h.get("source") not in {"context_projection", "solar-harness"}
            and "placeholder" not in str(h.get("note", "")).lower()
        ]
        context_events = [
            ev for ev in cp._log.all_events()  # noqa: SLF001 - doctor reads raw runtime evidence
            if ev.get("type") == "context_injected"
        ]
        latest_context = context_events[-1] if context_events else None
        has_text = bool(((latest_context or {}).get("payload") or {}).get("context_text"))
        ok = bool(real_hits)
        warn = not bool(context_events)
        msg = (
            f"recall_hits={len(real_hits)} context_events={len(context_events)}"
            if ok else
            f"no real recall hits; context_events={len(context_events)}"
        )
        return {
            "ok": ok,
            "warn": warn,
            "message": msg,
            "kb_hit_count": len(view.kb_hits),
            "real_recall_hit_count": len(real_hits),
            "context_injected_count": len(context_events),
            "latest_context_has_text": has_text,
            "degraded_hits": [h for h in view.kb_hits if h.get("degraded")][:5],
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"context runtime error: {exc}"}


def _check_model_call_runtime(sprint_id: str) -> Dict[str, Any]:
    """Check observable model-call boundary events for the session."""
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from session_log import SessionLog
        log = SessionLog(sprint_id, harness_dir=HARNESS_DIR)
        events = log.all_events()
        requested = [e for e in events if e.get("type") == "model_call_requested"]
        succeeded = [e for e in events if e.get("type") == "model_call_succeeded"]
        failed = [e for e in events if e.get("type") == "model_call_failed"]
        sessions_started = [e for e in events if e.get("type") == "model_session_started"]
        sessions_ended = [e for e in events if e.get("type") == "model_session_ended"]
        pending = []
        terminal_ids = {e.get("activity_id") for e in succeeded + failed if e.get("activity_id")}
        for ev in requested:
            aid = ev.get("activity_id")
            if aid and aid not in terminal_ids:
                pending.append(aid)
        ok = not pending
        # Historical sessions created before this bridge will not have model
        # call events. That is informational, not a health warning; pending
        # requests are the real runtime problem.
        warn = False
        message = (
            f"requested={len(requested)} succeeded={len(succeeded)} failed={len(failed)} pending={len(pending)}"
            if requested else
            f"no model_call_requested events; sessions={len(sessions_started)}/{len(sessions_ended)}"
        )
        return {
            "ok": ok,
            "warn": warn,
            "message": message,
            "requested": len(requested),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "pending_dispatch_ids": pending[:20],
            "model_sessions_started": len(sessions_started),
            "model_sessions_ended": len(sessions_ended),
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"model-call runtime error: {exc}"}


def _check_process_audit(sprint_id: str) -> Dict[str, Any]:
    """Run the log-native process evaluator as a doctor dimension.

    This catches distributed-systems failures that final artifacts cannot show:
    command issued but never started, activity started but never reached a
    terminal event, terminal event without a corresponding start, pending model
    call, pending tool call, and missing context projection evidence.
    """
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from session_tools import load_events, process_audit, project_session
        events, meta = load_events(sprint_id, Path(HARNESS_DIR))
        projection = project_session(sprint_id, Path(HARNESS_DIR))
        audit = process_audit(events, projection)
        risks = list(audit.get("risks") or [])
        # Historical/bridged sessions may legitimately predate fully paired
        # activity lifecycle events. Keep those visible as warn while enforcing
        # hard failure for native runtime command gaps and side-effect risks.
        soft_risks = {"context_projection_missing", "legacy_unpaired_activity"}
        hard_risks = [r for r in risks if r not in soft_risks]
        return {
            "ok": not hard_risks,
            "warn": bool(risks),
            "message": "ok" if not risks else ",".join(risks[:8]),
            "event_count": meta.get("event_count", 0),
            "risks": risks,
            "hard_risks": hard_risks,
            "audit": audit,
        }
    except Exception as exc:
        return {"ok": False, "warn": True, "message": f"process audit error: {exc}"}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def doctor_sprint(
    sprint_id: str,
    *,
    stale_threshold_minutes: int = 60,
) -> Dict[str, Any]:
    """Run all checks for one sprint and return a report dict."""
    # Default adoption path: every doctor pass first mirrors legacy sprint
    # artifacts into session-log v2. This makes doctor a runtime gate, not a
    # passive linter that can silently ignore old-only state.
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from runtime_bridge import adopt_sprint
        adopt_sprint(sprint_id, harness_dir=Path(HARNESS_DIR))
    except Exception:
        # Individual checks below will surface event/projection issues. Doctor
        # must remain fail-open enough to report corrupt legacy state.
        pass

    checks = {
        "event_log_health": _check_event_log_health(sprint_id),
        "projection_drift":  _check_projection_drift(sprint_id),
        "duplicate_commands": _check_duplicate_commands(sprint_id),
        "stale_activities":  _check_stale_activities(sprint_id),
        "status_json":       _check_status_json(sprint_id),
        "interface_health": _check_interface_health(sprint_id),
        "context_runtime": _check_context_runtime(sprint_id),
        "model_call_runtime": _check_model_call_runtime(sprint_id),
        "process_audit": _check_process_audit(sprint_id),
    }

    all_ok  = all(c.get("ok",   True) for c in checks.values())
    any_warn = any(c.get("warn", False) for c in checks.values())

    return {
        "sprint_id": sprint_id,
        "ok": all_ok,
        "warn": any_warn and all_ok,
        "ts": _now_ts(),
        "checks": checks,
    }


def doctor_all(*, active_only: bool = True) -> Dict[str, Any]:
    """Scan all sprints in SPRINTS_DIR and run checks."""
    pattern = os.path.join(SPRINTS_DIR, "*.status.json")
    sprint_ids: List[str] = []
    for p in sorted(glob.glob(pattern)):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            sid = data.get("sprint_id") or data.get("id") or data.get("sid")
            if not sid:
                continue
            if active_only:
                status = data.get("status", "")
                if status in ("passed", "cancelled", "finalized"):
                    continue
            sprint_ids.append(sid)
        except Exception:
            continue

    reports = [doctor_sprint(sid) for sid in sprint_ids]
    overall_ok = all(r["ok"] for r in reports)
    any_warn = any(r.get("warn") for r in reports)

    return {
        "ok": overall_ok,
        "warn": any_warn and overall_ok,
        "ts": _now_ts(),
        "sprint_count": len(reports),
        "sprints": reports,
    }


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="solar-harness runtime doctor — event log health report"
    )
    parser.add_argument("sprint_id", nargs="?", default=None,
                        help="Sprint ID (default: all active sprints)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--all", action="store_true", help="Include terminal sprints")
    args = parser.parse_args()

    if args.sprint_id:
        report = doctor_sprint(args.sprint_id)
    else:
        report = doctor_all(active_only=not args.all)

    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["ok"] else 1)

    # Human-readable output
    ok_sym = "✅" if report["ok"] else "❌"
    warn_sym = "⚠" if report.get("warn") else ""
    print(f"{ok_sym} {warn_sym} runtime doctor  {report['ts']}")

    if "sprints" in report:
        for r in report["sprints"]:
            _print_sprint_report(r)
    else:
        _print_sprint_report(report)

    sys.exit(0 if report["ok"] else 1)


def _print_sprint_report(r: Dict[str, Any]) -> None:
    sym = "✅" if r["ok"] else "❌"
    print(f"\n{sym} {r['sprint_id']}")
    for name, check in r.get("checks", {}).items():
        c_sym = "✅" if check.get("ok") else ("⚠" if check.get("warn") else "❌")
        print(f"  {c_sym} {name}: {check.get('message', '')}")


if __name__ == "__main__":
    main()
