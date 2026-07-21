#!/usr/bin/env python3
"""Session log tools for Solar-Harness runtime.

These commands make the append-only log operationally useful:

  replay    materialize a session into status/context-friendly facts
  diff      compare two sessions or the same session across harness dirs
  evaluate  run a log-native evaluator without relying on final artifacts

The tools intentionally consume `sessions/<session_id>/events.jsonl` as the
source of truth.  Files such as status.json are projection caches only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))

from projection_engine import ProjectionEngine  # type: ignore
from session_log import SessionLog  # type: ignore


HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
REPORTS_DIR = HARNESS_DIR / "reports"


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_events(session_id: str, harness_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    path = harness_dir / "sessions" / session_id / "events.jsonl"
    events: List[Dict[str, Any]] = []
    bad_lines = 0
    seq_gaps: List[int] = []
    last_seq = 0
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    bad_lines += 1
                    continue
                seq = int(ev.get("seq") or 0)
                if events and seq != last_seq + 1:
                    seq_gaps.append(seq)
                last_seq = seq
                events.append(ev)
    meta = {
        "path": str(path),
        "exists": path.exists(),
        "event_count": len(events),
        "bad_lines": bad_lines,
        "seq_gaps": seq_gaps,
    }
    return events, meta


def project_session(session_id: str, harness_dir: Path) -> Dict[str, Any]:
    try:
        state = ProjectionEngine(session_id, harness_dir=str(harness_dir)).project()
        return {
            "ok": True,
            "sprint_id": state.sprint_id,
            "status": state.status,
            "round": state.round,
            "event_count": state.event_count,
            "last_event_ts": state.last_event_ts,
            "drift_detected": state.drift_detected,
            "drift_reason": state.drift_reason,
            "duplicate_commands": state.duplicate_commands,
            "stale_activities": state.stale_activities,
            "activities": [
                {
                    "activity_id": a.activity_id,
                    "status": a.status,
                    "last_event_type": a.last_event_type,
                    "last_event_ts": a.last_event_ts,
                    "error_count": a.error_count,
                    "retry_count": a.retry_count,
                }
                for a in state.activities
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def event_type_counts(events: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counter: Dict[str, int] = collections.Counter(str(ev.get("type") or "") for ev in events)
    return dict(sorted(counter.items()))


def stable_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Return event content suitable for semantic diff.

    event_id and ts are intentionally excluded so two harnesses can be compared
    without false divergence from append-time metadata.
    """
    return {
        "seq": ev.get("seq"),
        "session_id": ev.get("session_id"),
        "type": ev.get("type"),
        "actor": ev.get("actor"),
        "source": ev.get("source"),
        "sprint_id": ev.get("sprint_id"),
        "activity_id": ev.get("activity_id"),
        "correlation_id": ev.get("correlation_id"),
        "causation_id": ev.get("causation_id"),
        "idempotency_key": ev.get("idempotency_key"),
        "payload": ev.get("payload") or {},
    }


def event_fingerprint(ev: Dict[str, Any]) -> str:
    text = json.dumps(stable_event(ev), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def first_divergence(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    max_len = max(len(a), len(b))
    for idx in range(max_len):
        if idx >= len(a):
            return {"index": idx, "reason": "missing_in_a", "a": None, "b": summarize_event(b[idx])}
        if idx >= len(b):
            return {"index": idx, "reason": "missing_in_b", "a": summarize_event(a[idx]), "b": None}
        if stable_event(a[idx]) != stable_event(b[idx]):
            return {
                "index": idx,
                "reason": "event_content_differs",
                "a": summarize_event(a[idx]),
                "b": summarize_event(b[idx]),
            }
    return {"index": None, "reason": "none", "a": None, "b": None}


def summarize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    return {
        "seq": ev.get("seq"),
        "type": ev.get("type"),
        "actor": ev.get("actor"),
        "activity_id": ev.get("activity_id"),
        "status": payload.get("status") or payload.get("to") or "",
        "error": payload.get("error") or "",
    }


def pending_model_calls(events: Iterable[Dict[str, Any]]) -> List[str]:
    requested: Dict[str, Dict[str, Any]] = {}
    terminal = set()
    for ev in events:
        etype = ev.get("type")
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        dispatch_id = str(payload.get("dispatch_id") or ev.get("activity_id") or "")
        if not dispatch_id:
            continue
        if etype == "model_call_requested":
            requested[dispatch_id] = ev
        elif etype in {"model_call_succeeded", "model_call_failed"}:
            terminal.add(dispatch_id)
    return sorted(k for k in requested if k not in terminal)


def process_audit(events: List[Dict[str, Any]], projection: Dict[str, Any]) -> Dict[str, Any]:
    """Audit long-running process health from the event log, not artifacts."""
    command_ids: set[str] = set()
    started: set[str] = set()
    terminal: set[str] = set()
    failed: set[str] = set()
    legacy_command_ids: set[str] = set()
    legacy_started: set[str] = set()
    legacy_terminal: set[str] = set()
    tool_requested = tool_terminal = tool_failed = 0
    model_requested = model_terminal = model_failed = 0
    context_events = 0
    human_feedback = 0

    for ev in events:
        etype = str(ev.get("type") or "")
        act = str(ev.get("activity_id") or "")
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        dispatch_id = str(payload.get("dispatch_id") or act)
        is_legacy_activity = bool(payload.get("legacy_event"))
        if etype == "command_issued" and act:
            if is_legacy_activity:
                legacy_command_ids.add(act)
            else:
                command_ids.add(act)
        elif etype == "activity_started" and act:
            if is_legacy_activity:
                legacy_started.add(act)
            else:
                started.add(act)
        elif etype in {"activity_succeeded", "activity_failed", "activity_cancelled"} and act:
            if is_legacy_activity:
                legacy_terminal.add(act)
            else:
                terminal.add(act)
                if etype == "activity_failed":
                    failed.add(act)
        elif etype == "tool_call_requested":
            tool_requested += 1
        elif etype in {"tool_call_succeeded", "tool_call_failed"}:
            tool_terminal += 1
            if etype == "tool_call_failed":
                tool_failed += 1
        elif etype == "model_call_requested":
            model_requested += 1
        elif etype in {"model_call_succeeded", "model_call_failed"}:
            model_terminal += 1
            if etype == "model_call_failed":
                model_failed += 1
        elif etype == "context_injected":
            context_events += 1
        elif etype == "human_feedback":
            human_feedback += 1
        if etype in {"model_call_requested", "model_call_succeeded", "model_call_failed"} and dispatch_id:
            # model call lifecycle is counted separately; dispatch_id fallback
            # keeps future provider event formats comparable.
            pass

    unstarted_commands = sorted(command_ids - started - terminal)
    started_without_terminal = sorted(started - terminal)
    terminal_without_start = sorted(terminal - started)
    legacy_unstarted_commands = sorted(legacy_command_ids - legacy_started - legacy_terminal)
    legacy_started_without_terminal = sorted(legacy_started - legacy_terminal)
    legacy_terminal_without_start = sorted(legacy_terminal - legacy_started)
    stale_activities = list(projection.get("stale_activities") or [])
    duplicate_commands = list(projection.get("duplicate_commands") or [])

    risks: List[str] = []
    if unstarted_commands:
        risks.append("command_without_start")
    if started_without_terminal:
        risks.append("activity_without_terminal")
    if terminal_without_start:
        risks.append("terminal_without_start")
    if duplicate_commands:
        risks.append("duplicate_command_side_effect_risk")
    if stale_activities:
        risks.append("stale_activity")
    if model_requested and model_terminal < model_requested:
        risks.append("model_call_pending")
    if tool_requested and tool_terminal < tool_requested:
        risks.append("tool_call_pending")
    if not context_events:
        risks.append("context_projection_missing")
    if legacy_unstarted_commands or legacy_started_without_terminal or legacy_terminal_without_start:
        risks.append("legacy_unpaired_activity")

    return {
        "log_native": True,
        "side_effect_boundaries": {
            "commands": len(command_ids),
            "unstarted_commands": unstarted_commands,
            "started_without_terminal": started_without_terminal,
            "terminal_without_start": terminal_without_start,
            "legacy_commands": len(legacy_command_ids),
            "legacy_unstarted_commands": legacy_unstarted_commands,
            "legacy_started_without_terminal": legacy_started_without_terminal,
            "legacy_terminal_without_start": legacy_terminal_without_start,
            "duplicate_commands": duplicate_commands,
            "stale_activities": stale_activities,
        },
        "model_calls": {
            "requested": model_requested,
            "terminal": model_terminal,
            "failed": model_failed,
            "pending": max(model_requested - model_terminal, 0),
        },
        "tool_calls": {
            "requested": tool_requested,
            "terminal": tool_terminal,
            "failed": tool_failed,
            "pending": max(tool_requested - tool_terminal, 0),
            "observable": tool_requested > 0 or tool_terminal > 0,
        },
        "context_projection": {
            "context_injected_events": context_events,
            "default_path_observed": context_events > 0,
        },
        "human_feedback_events": human_feedback,
        "risks": risks,
    }


def replay_payload(session_id: str, harness_dir: Path, include_events: bool = False) -> Dict[str, Any]:
    events, meta = load_events(session_id, harness_dir)
    payload = {
        "ok": meta["exists"] and meta["bad_lines"] == 0,
        "generated_at": now_ts(),
        "session_id": session_id,
        "harness_dir": str(harness_dir),
        "log": meta,
        "event_type_counts": event_type_counts(events),
        "projection": project_session(session_id, harness_dir),
        "pending_model_calls": pending_model_calls(events),
        "event_summaries": [summarize_event(ev) for ev in events[-30:]],
        "source_of_truth": "sessions/<session_id>/events.jsonl",
        "projection_note": "status.json/UI/context are projections, not the source of truth",
    }
    if include_events:
        payload["events"] = events
    return payload


def diff_payload(session_a: str, session_b: str, harness_a: Path, harness_b: Path) -> Dict[str, Any]:
    events_a, meta_a = load_events(session_a, harness_a)
    events_b, meta_b = load_events(session_b, harness_b)
    fp_a = {event_fingerprint(ev) for ev in events_a}
    fp_b = {event_fingerprint(ev) for ev in events_b}
    proj_a = project_session(session_a, harness_a)
    proj_b = project_session(session_b, harness_b)
    diff = {
        "ok": meta_a["bad_lines"] == 0 and meta_b["bad_lines"] == 0,
        "generated_at": now_ts(),
        "source_of_truth": "append-only session event logs",
        "same_session_cross_harness": session_a == session_b and harness_a.resolve() != harness_b.resolve(),
        "a": {
            "session_id": session_a,
            "harness_dir": str(harness_a),
            "log": meta_a,
            "event_type_counts": event_type_counts(events_a),
            "projection": proj_a,
        },
        "b": {
            "session_id": session_b,
            "harness_dir": str(harness_b),
            "log": meta_b,
            "event_type_counts": event_type_counts(events_b),
            "projection": proj_b,
        },
        "summary": {
            "event_count_delta": len(events_a) - len(events_b),
            "only_in_a": len(fp_a - fp_b),
            "only_in_b": len(fp_b - fp_a),
            "projection_status_equal": proj_a.get("status") == proj_b.get("status"),
            "first_divergence": first_divergence(events_a, events_b),
        },
    }
    diff["ok"] = bool(diff["ok"] and diff["summary"]["only_in_a"] == 0 and diff["summary"]["only_in_b"] == 0)
    return diff


def projection_fingerprint(payload: Dict[str, Any]) -> str:
    projection = payload.get("projection") or {}
    stable = {
        "ok": projection.get("ok"),
        "status": projection.get("status"),
        "round": projection.get("round"),
        "event_count": projection.get("event_count"),
        "duplicate_commands": projection.get("duplicate_commands"),
        "stale_activities": projection.get("stale_activities"),
        "activities": projection.get("activities"),
        "pending_model_calls": payload.get("pending_model_calls") or [],
        "event_type_counts": payload.get("event_type_counts") or {},
    }
    text = json.dumps(stable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run(cmd: List[str], *, cwd: Optional[Path] = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout)


def export_git_ref(repo: Path, ref: str, dest: Path) -> Dict[str, Any]:
    if not (repo / ".git").exists():
        return {"ok": False, "error": f"not a git repository: {repo}"}
    rev = _run(["git", "rev-parse", "--verify", ref], cwd=repo)
    if rev.returncode != 0:
        return {"ok": False, "error": (rev.stderr or rev.stdout).strip(), "ref": ref}
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.Popen(["git", "-C", str(repo), "archive", rev.stdout.strip()], stdout=subprocess.PIPE)
    tar = subprocess.run(["tar", "-x", "-C", str(dest)], stdin=archive.stdout, text=False, capture_output=True)
    if archive.stdout:
        archive.stdout.close()
    rc = archive.wait()
    if rc != 0 or tar.returncode != 0:
        return {"ok": False, "error": (tar.stderr or b"git archive failed").decode("utf-8", errors="replace"), "ref": ref}
    return {"ok": True, "ref": ref, "rev": rev.stdout.strip(), "path": str(dest)}


def copy_session_inputs(source_harness: Path, dest_harness: Path, session_id: str) -> None:
    src_session = source_harness / "sessions" / session_id
    dst_session = dest_harness / "sessions" / session_id
    if src_session.exists():
        dst_session.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_session, dst_session, dirs_exist_ok=True)
    src_status = source_harness / "sprints" / f"{session_id}.status.json"
    if src_status.exists():
        dst_status = dest_harness / "sprints" / src_status.name
        dst_status.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_status, dst_status)


def run_version_replay(version_harness: Path, session_id: str) -> Dict[str, Any]:
    runner = version_harness / "lib" / "session_tools.py"
    if runner.exists():
        proc = _run([sys.executable, str(runner), "replay", session_id, "--harness-dir", str(version_harness), "--json"], timeout=90)
        if proc.returncode not in (0, 1):
            return {"ok": False, "error": (proc.stderr or proc.stdout)[-2000:], "runner": str(runner)}
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"json parse failed: {exc}", "stdout": proc.stdout[-2000:], "runner": str(runner)}
        payload["_runner"] = str(runner)
        payload["_runner_native"] = True
        return payload

    # Fallback for older refs that predate session_tools.py.  This is explicitly
    # marked non-native because it uses the current runner against old files.
    payload = replay_payload(session_id, version_harness)
    payload["_runner"] = str(Path(__file__))
    payload["_runner_native"] = False
    payload.setdefault("warnings", []).append("session_tools.py missing in ref; used current runner fallback")
    return payload


def compare_version_payload(session_id: str, ref_a: str, ref_b: str, repo: Path, source_harness: Path) -> Dict[str, Any]:
    tmp_root = Path(tempfile.mkdtemp(prefix="solar-session-compare-version-"))
    try:
        dir_a = tmp_root / "a"
        dir_b = tmp_root / "b"
        exp_a = export_git_ref(repo, ref_a, dir_a)
        exp_b = export_git_ref(repo, ref_b, dir_b)
        if not exp_a.get("ok") or not exp_b.get("ok"):
            return {
                "ok": False,
                "generated_at": now_ts(),
                "session_id": session_id,
                "repo": str(repo),
                "ref_a": exp_a,
                "ref_b": exp_b,
                "error": "git_ref_export_failed",
            }
        copy_session_inputs(source_harness, dir_a, session_id)
        copy_session_inputs(source_harness, dir_b, session_id)
        replay_a = run_version_replay(dir_a, session_id)
        replay_b = run_version_replay(dir_b, session_id)
        fp_a = projection_fingerprint(replay_a) if replay_a.get("ok") else ""
        fp_b = projection_fingerprint(replay_b) if replay_b.get("ok") else ""
        projection_equal = bool(fp_a and fp_b and fp_a == fp_b)
        status_equal = (replay_a.get("projection") or {}).get("status") == (replay_b.get("projection") or {}).get("status")
        payload = {
            "ok": bool(replay_a.get("ok") and replay_b.get("ok") and projection_equal),
            "generated_at": now_ts(),
            "session_id": session_id,
            "source_harness": str(source_harness),
            "repo": str(repo),
            "source_of_truth": "same append-only session log copied into both version harness dirs",
            "a": {
                "ref": ref_a,
                "rev": exp_a.get("rev"),
                "runner_native": replay_a.get("_runner_native", False),
                "projection_fingerprint": fp_a,
                "replay": replay_a,
            },
            "b": {
                "ref": ref_b,
                "rev": exp_b.get("rev"),
                "runner_native": replay_b.get("_runner_native", False),
                "projection_fingerprint": fp_b,
                "replay": replay_b,
            },
            "summary": {
                "projection_equal": projection_equal,
                "status_equal": status_equal,
                "a_status": (replay_a.get("projection") or {}).get("status"),
                "b_status": (replay_b.get("projection") or {}).get("status"),
                "a_event_count": (replay_a.get("log") or {}).get("event_count"),
                "b_event_count": (replay_b.get("log") or {}).get("event_count"),
            },
        }
        return payload
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def compare_version_doctor_payload(repo: Path, source_harness: Path) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}
    checks["repo_exists"] = {"ok": repo.exists(), "message": str(repo)}
    git_dir = _run(["git", "rev-parse", "--git-dir"], cwd=repo) if repo.exists() else None
    checks["repo_is_git"] = {
        "ok": bool(git_dir and git_dir.returncode == 0),
        "message": (git_dir.stdout or git_dir.stderr).strip() if git_dir else "repo does not exist",
    }
    git_archive = _run(["git", "archive", "--help"], cwd=repo if repo.exists() else None, timeout=10)
    checks["git_archive_available"] = {
        "ok": git_archive.returncode in {0, 129},
        "message": "available" if git_archive.returncode in {0, 129} else (git_archive.stderr or git_archive.stdout).strip()[:500],
    }
    checks["source_harness_exists"] = {"ok": source_harness.exists(), "message": str(source_harness)}
    checks["source_sessions_dir"] = {
        "ok": (source_harness / "sessions").exists(),
        "message": str(source_harness / "sessions"),
    }
    checks["current_runner_exists"] = {"ok": Path(__file__).exists(), "message": str(Path(__file__))}
    ok = all(c.get("ok") for c in checks.values())
    return {
        "ok": ok,
        "generated_at": now_ts(),
        "repo": str(repo),
        "source_harness": str(source_harness),
        "checks": checks,
        "usage": "solar-harness session compare-version <session_id> <git-ref-a> <git-ref-b> --repo <git-managed-harness-repo> --json",
        "action_if_not_git": "Run against a git-managed harness repo/export; ~/.solar/harness may be an installed runtime rather than a repository.",
    }


def evaluate_payload(session_id: str, harness_dir: Path) -> Dict[str, Any]:
    events, meta = load_events(session_id, harness_dir)
    projection = project_session(session_id, harness_dir)
    event_counts = event_type_counts(events)
    model_pending = pending_model_calls(events)
    audit = process_audit(events, projection)
    errors: List[str] = []
    warnings: List[str] = []

    if not meta["exists"]:
        errors.append("session_log_missing")
    if meta["bad_lines"]:
        errors.append("session_log_corrupt")
    if meta["seq_gaps"]:
        errors.append("session_seq_gap")
    if not events:
        warnings.append("session_has_no_events")
    if not projection.get("ok"):
        errors.append("projection_failed")
    if projection.get("drift_detected"):
        warnings.append("projection_drift")
    if projection.get("duplicate_commands"):
        errors.append("duplicate_commands")
    if projection.get("stale_activities"):
        warnings.append("stale_activities")
    if model_pending:
        warnings.append("pending_model_calls")
    for risk in audit.get("risks") or []:
        if risk == "context_projection_missing":
            # A bare historical session can be valid without context projection.
            # Default dispatch coverage is enforced by dedicated runtime tests.
            continue
        if risk in {"duplicate_command_side_effect_risk", "terminal_without_start"}:
            errors.append(risk)
        else:
            warnings.append(risk)

    status = str(projection.get("status") or "unknown")
    if status in {"error", "failed", "failed_review", "cancelled"}:
        errors.append("terminal_failure_status")
    elif status not in {"passed", "reviewing"}:
        warnings.append("non_terminal_status")

    verdict = "fail" if errors else ("warn" if warnings else "pass")
    return {
        "ok": verdict != "fail",
        "generated_at": now_ts(),
        "session_id": session_id,
        "harness_dir": str(harness_dir),
        "verdict": verdict,
        "log_native": True,
        "artifact_native": False,
        "private_reasoning_visible": False,
        "source_of_truth": str(Path(meta["path"])),
        "status": status,
        "event_count": meta["event_count"],
        "event_type_counts": event_counts,
        "projection": projection,
        "process_audit": audit,
        "pending_model_calls": model_pending,
        "errors": errors,
        "warnings": warnings,
        "note": "Evaluator consumed session events/projection only; final files are not required for this verdict.",
    }


def render_markdown(payload: Dict[str, Any], title: str) -> str:
    rows = []
    if "summary" in payload:
        summary = payload["summary"]
        rows = [
            ("event_count_delta", summary.get("event_count_delta")),
            ("only_in_a", summary.get("only_in_a")),
            ("only_in_b", summary.get("only_in_b")),
            ("projection_status_equal", summary.get("projection_status_equal")),
            ("first_divergence", (summary.get("first_divergence") or {}).get("reason")),
        ]
    elif "verdict" in payload:
        rows = [
            ("verdict", payload.get("verdict")),
            ("status", payload.get("status")),
            ("event_count", payload.get("event_count")),
            ("errors", ", ".join(payload.get("errors") or []) or "none"),
            ("warnings", ", ".join(payload.get("warnings") or []) or "none"),
        ]
    else:
        rows = [
            ("session_id", payload.get("session_id")),
            ("event_count", (payload.get("log") or {}).get("event_count")),
            ("projection_status", (payload.get("projection") or {}).get("status")),
            ("pending_model_calls", len(payload.get("pending_model_calls") or [])),
        ]
    table = ["| Key | Value |", "| --- | --- |"]
    table.extend(f"| {k} | `{v}` |" for k, v in rows)
    return "\n".join([
        f"# {title}",
        "",
        f"- Generated: `{payload.get('generated_at')}`",
        f"- Source of truth: `{payload.get('source_of_truth')}`",
        "",
        *table,
        "",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2)[:20000],
        "```",
        "",
    ])


def print_payload(payload: Dict[str, Any], as_json: bool, markdown_title: str = "") -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(render_markdown(payload, markdown_title or "Solar Session Report"))


def cmd_replay(args: argparse.Namespace) -> int:
    payload = replay_payload(args.session_id, Path(args.harness_dir), include_events=args.include_events)
    if args.out:
        write_json(Path(args.out), payload)
    print_payload(payload, args.json, f"Solar Session Replay: {args.session_id}")
    return 0 if payload["ok"] else 1


def cmd_diff(args: argparse.Namespace) -> int:
    payload = diff_payload(args.session_a, args.session_b, Path(args.harness_a), Path(args.harness_b))
    if args.out:
        write_json(Path(args.out), payload)
    print_payload(payload, args.json, "Solar Session Diff")
    return 0 if payload["ok"] else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    payload = evaluate_payload(args.session_id, Path(args.harness_dir))
    if args.out:
        write_json(Path(args.out), payload)
    print_payload(payload, args.json, f"Solar Log-Native Evaluation: {args.session_id}")
    return 0 if payload["ok"] else 1


def cmd_compare_version(args: argparse.Namespace) -> int:
    payload = compare_version_payload(
        args.session_id,
        args.ref_a,
        args.ref_b,
        Path(args.repo),
        Path(args.source_harness),
    )
    if args.out:
        write_json(Path(args.out), payload)
    print_payload(payload, args.json, f"Solar Session Compare Version: {args.session_id}")
    return 0 if payload["ok"] else 1


def cmd_compare_version_doctor(args: argparse.Namespace) -> int:
    payload = compare_version_doctor_payload(Path(args.repo), Path(args.source_harness))
    if args.out:
        write_json(Path(args.out), payload)
    print_payload(payload, args.json, "Solar Session Compare Version Doctor")
    return 0 if payload["ok"] else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="solar-harness session", description="Session log replay/diff/evaluation tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("replay", help="Replay one append-only session log")
    p.add_argument("session_id")
    p.add_argument("--harness-dir", default=str(HARNESS_DIR))
    p.add_argument("--include-events", action="store_true")
    p.add_argument("--out", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("diff", help="Diff two sessions or one session across harness dirs")
    p.add_argument("session_a")
    p.add_argument("session_b")
    p.add_argument("--harness-a", default=str(HARNESS_DIR))
    p.add_argument("--harness-b", default=str(HARNESS_DIR))
    p.add_argument("--out", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("evaluate", aliases=["eval"], help="Evaluate directly from session log")
    p.add_argument("session_id")
    p.add_argument("--harness-dir", default=str(HARNESS_DIR))
    p.add_argument("--out", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("compare-version", help="Replay the same session through two git refs")
    p.add_argument("session_id")
    p.add_argument("ref_a")
    p.add_argument("ref_b")
    p.add_argument("--repo", default=str(HARNESS_DIR))
    p.add_argument("--source-harness", default=str(HARNESS_DIR))
    p.add_argument("--out", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compare_version)

    p = sub.add_parser("compare-version-doctor", help="Check prerequisites for compare-version")
    p.add_argument("--repo", default=str(HARNESS_DIR))
    p.add_argument("--source-harness", default=str(HARNESS_DIR))
    p.add_argument("--out", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compare_version_doctor)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
