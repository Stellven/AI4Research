#!/usr/bin/env python3
"""
solar-autopilot-monitor.py

Detects Solar Harness coordination dead-ends and applies safe default repairs.
It is intentionally conservative: it does not delete data, call external APIs,
or spend model tokens. It updates local sprint status/events and can dispatch
clear instructions to tmux panes when requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS = HARNESS / "sprints"
EVENTS = HARNESS / "events" / "all.jsonl"
SESSION = os.environ.get("SOLAR_HARNESS_SESSION", "solar-harness")
STATE = HARNESS / "state" / "autopilot-state.json"
LOCK = HARNESS / "run" / "autopilot.lock"
QUEUE = HARNESS / "run" / "autopilot-queue.jsonl"
NO_DISPATCH_FLAG = HARNESS / "run" / "no-dispatch.flag"
PANE_ASSIGNMENTS = HARNESS / ".pane-assignments"
PANE_LEASE_DIR = HARNESS / "run" / "pane-leases"
QUEUE_TTL_SEC = 3600
KB_PROBE_SCRIPT = HARNESS / "tests" / "test-knowledge-probe-coverage.sh"
KB_PROBE_HEALTH = HARNESS / "state" / "knowledge-probe-health.json"
KB_PROBE_INTERVAL_SEC = int(os.environ.get("SOLAR_KB_PROBE_INTERVAL_SEC", "1800"))
KB_PROBE_TRIGGER_COOLDOWN_SEC = int(os.environ.get("SOLAR_KB_PROBE_TRIGGER_COOLDOWN_SEC", "300"))
KB_PROBE_TIMEOUT_SEC = int(os.environ.get("SOLAR_KB_PROBE_TIMEOUT_SEC", "120"))
MODEL_DOCTOR_HEALTH = HARNESS / "state" / "model-registry-doctor-health.json"
MODEL_DOCTOR_INTERVAL_SEC = int(os.environ.get("SOLAR_MODEL_DOCTOR_INTERVAL_SEC", "1800"))
MODEL_DOCTOR_TIMEOUT_SEC = int(os.environ.get("SOLAR_MODEL_DOCTOR_TIMEOUT_SEC", "120"))
PM_INBOX_DIR = HARNESS / "run" / "pm-inbox"
ROLE_HANDOFF_RETRY_COOLDOWN_SEC = int(os.environ.get("SOLAR_ROLE_HANDOFF_RETRY_COOLDOWN_SEC", "30"))
try:
    PLANNER_DISPATCH_CLAIM_TTL_SEC = max(
        1,
        int(os.environ.get("SOLAR_PLANNER_DISPATCH_CLAIM_TTL_SEC", "180") or "180"),
    )
except (TypeError, ValueError):
    PLANNER_DISPATCH_CLAIM_TTL_SEC = 180

REAL_HARNESS = Path(os.environ.get("REAL_HARNESS_DIR", HARNESS))
sys.path.insert(0, str(REAL_HARNESS / "lib"))
if REAL_HARNESS != HARNESS:
    sys.path.insert(1, str(HARNESS / "lib"))
try:
    from runtime_bridge import record_legacy_event
except Exception:  # pragma: no cover - monitor must fail open
    record_legacy_event = None  # type: ignore
try:
    from workflow_guard import route as workflow_route
except Exception:  # pragma: no cover - older harness installs may not have it
    workflow_route = None  # type: ignore
QMD_PROXY_HEALTH = HARNESS / "state" / "qmd-mcp-ipv4-health.json"
TELEMETRY_ONLY_FINDINGS = {
    "epic_activation_backpressure",
    "knowledge_context_sqlite_only",
    "knowledge_context_timeout",
    "knowledge_probe_failed",
    "model_registry_doctor_failed",
    "runtime_soak_failed",
}


ASK_BOSS_RE = re.compile(r"拍板|要走哪条|你决定|老板.*决定|等.*确认|是否.*继续")
COMPACTING_RE = re.compile(r"Compacting conversation|压缩上下文|Compacting", re.I)
PROMPT_IDLE_RE = re.compile(r"Press up to edit queued messages|❯\s*$|Try \"", re.M)
SURVEY_PROMPT_RE = re.compile(
    r"How is Claude doing this session\?|1:\s*Bad\s+2:\s*Fine\s+3:\s*Good\s+0:\s*Dismiss",
    re.I,
)
PERMISSIONS_PROMPT_RE = re.compile(
    r"Press up to edit queued messages[\s\S]{0,160}bypass permissions on|"
    r"Do you want to make this edit|allow all edits during this session",
    re.I,
)
PANE_BUSY_RE = re.compile(
    r"Compacting conversation|Compacting|✳|✶|✽|✢|⏺ Bash|Running|Effecting|Swooping|thinking|Cogitating|Churning|Ruminating|"
    r"Working|Mustering|Herding|Baking|Reticulating|Scurrying|Roosting|Whirring|Smooshing|"
    r"Unhandled node type|Do you want to proceed\?|Enter to confirm|Esc to cancel|Bash command|"
    r"[·✳✶✽✢]\s+[A-Za-z][A-Za-z-]*…",
    re.I,
)
PANE_BOTTOM_BUSY_RE = re.compile(
    r"Compacting conversation|Compacting|Press up to edit queued messages|✳|✶|✽|✢|Mustering|Herding|Baking|Cogitating|Churning|Ruminating|Thinking|"
    r"Reticulating|Scurrying|Roosting|Whirring|Smooshing|"
    r"Unhandled node type|Do you want to proceed\?|Enter to confirm|Esc to cancel|Bash command|"
    r"[·✳✶✽✢]\s+[A-Za-z][A-Za-z-]*…",
    re.I,
)
PANE_UNAVAILABLE_RE = re.compile(
    r"You(?:'|’)ve hit your limit|rate[- ]limit|rate limit|"
    r"resets\s+\d|/rate-limit-options|Upgrade your plan|"
    r"API Error:\s*400|Invalid API parameter|error\"\s*:\s*\{",
    re.I,
)
RATE_LIMIT_OPTIONS_MODAL_RE = re.compile(
    r"What do you want to do\?[\s\S]{0,260}(?:/rate-limit-options|Upgrade your plan|Stop and wait for limit to reset)[\s\S]{0,120}Esc to cancel",
    re.I,
)
PANE_PROMPT_RESIDUE_RE = re.compile(r"^\s*❯(?![\s\u00a0]+Try\\s+\")[\s\u00a0]+[^\s\u00a0─]", re.M)
SAFE_CONTINUE_PROMPT_RE = re.compile(r"^\s*❯[\s\u00a0]*(继续|continue|继续\s+N\d+|continue\s+N\d+)\s*$", re.I | re.M)
SQLITE_ONLY_RE = re.compile(r"sqlite3\s+~?/?.*\.solar/solar\.db", re.I)
CONTEXT_INJECT_RE = re.compile(r"solar-harness\s+context\s+inject|Solar Unified Context", re.I)
CONTEXT_TIMEOUT_RE = re.compile(r"context inject[\s\S]{0,240}timeout\s+\d+s|timeout\s+\d+s[\s\S]{0,240}context inject", re.I)
ACTIVE_STATUSES = {"drafting", "queued", "active", "planning", "approved", "reviewing", "ready_for_review", "failed_review"}
TERMINAL_STATUSES = {"passed", "completed", "finalized", "done", "cancelled", "archived"}
GRAPH_READY_HANDOFFS = {"builder", "builder_main", "builder_parallel", "builder-lab"}
GRAPH_EVAL_HANDOFFS = {"evaluator", "reviewer"}
BUILDER_QUEUE_FINDINGS = {"ready_for_builder", "active_without_handoff", "pane_idle_with_pending_artifact"}
EPIC_ACTIVE_CHILD_LIMIT = int(os.environ.get("SOLAR_EPIC_ACTIVE_CHILD_LIMIT", "12"))
EPIC_ACTIVE_CHILD_STATUSES = {"active", "approved", "reviewing", "ready_for_review"}
EPIC_ACTIVE_CHILD_PHASES = {"prd_ready", "planning_complete", "graph_dispatch_active", "handoff_ready", "builder_in_progress"}

import sys
sys.path.insert(0, str(HARNESS / "lib"))
try:
    from pane_overlay_state import pane_overlay_detail, prompt_match_is_stale, tail_has_idle_prompt_footer as shared_tail_has_idle_prompt_footer
except Exception:  # pragma: no cover - monitor must fail open on older installs
    pane_overlay_detail = None  # type: ignore
    prompt_match_is_stale = None  # type: ignore
    shared_tail_has_idle_prompt_footer = None  # type: ignore
try:
    from graph_scheduler import (
        load_graph,
        save_graph,
        enqueue_ready,
        parent_ready_check,
        validate_graph,
        blocked_external_prerequisites,
        doctor_graph,
        node_status,
        sync_status_cache_from_graph,
    )
except Exception:  # pragma: no cover - fallback for partially installed harnesses
    load_graph = save_graph = enqueue_ready = parent_ready_check = validate_graph = blocked_external_prerequisites = doctor_graph = node_status = sync_status_cache_from_graph = None
try:
    from prerequisite_resolver import iter_blocked
except Exception:  # pragma: no cover - fallback for partially installed harnesses
    iter_blocked = None
try:
    from requirement_coverage import evaluate_sid as evaluate_requirement_coverage_sid
except Exception:  # pragma: no cover - fallback for partially installed harnesses
    evaluate_requirement_coverage_sid = None  # type: ignore
try:
    from graph_node_dispatcher import dispatch_ready as graph_dispatch_ready
    from graph_node_dispatcher import dispatch_node_evals as graph_dispatch_node_evals
except Exception:  # pragma: no cover - graph dispatcher may be absent in scheduler-only tests
    graph_dispatch_ready = graph_dispatch_node_evals = None
try:
    from pane_lease import read_lease as read_runtime_lease
except Exception:  # pragma: no cover - fallback for partially installed harnesses
    read_runtime_lease = None  # type: ignore
try:
    from pane_role_pool import discover_role_pool
except Exception:  # pragma: no cover - fallback for partially installed harnesses
    discover_role_pool = None  # type: ignore


def node_requires_deepresearch_quality_gate(node: dict) -> bool:
    explicit = node.get("research_quality_gate_required")
    if explicit is False:
        return False
    if explicit is True:
        return True
    caps: set[str] = set()
    for key in ("required_capabilities", "capabilities"):
        raw = node.get(key, [])
        if isinstance(raw, str):
            caps.add(raw)
        elif isinstance(raw, list):
            caps.update(str(item) for item in raw if str(item))
    gate_capability_re = re.compile(
        r"^research\.(?:"
        r"factuality|citation|claim(?:[_\.]|$)|evidence(?:[_\.]|$)|"
        r"report(?:[_\.](?:ast|finalize|quality|review)|_ast)|"
        r"survey(?:[_\.](?:chief_editor|finalize|quality|review))"
        r")",
        re.I,
    )
    if caps & {"citation.verify", "factuality.evaluate"}:
        return True
    if any(gate_capability_re.match(cap) for cap in caps):
        return True
    artifact_values: list[str] = []
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    artifact_values.extend(str(value) for value in artifacts.values())
    for key in (
        "research_eval",
        "research_eval_json",
        "eval_artifacts_json",
        "report_ast",
        "final_report",
        "final_md",
    ):
        if node.get(key):
            artifact_values.append(str(node.get(key)))
    raw_scope = node.get("write_scope", [])
    if isinstance(raw_scope, str):
        artifact_values.append(raw_scope)
    elif isinstance(raw_scope, list):
        artifact_values.extend(str(item) for item in raw_scope)
    artifact_text = " ".join(artifact_values).lower()
    return bool(re.search(r"research_eval|report_ast|final\.md|final_report|evidence\.jsonl|claims\.jsonl", artifact_text))


def deepresearch_quality_gate_ok(gate: dict) -> bool:
    return bool(gate.get("ok")) or str(gate.get("verdict") or "").upper() == "PASS"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def epic_child_slice_from_sid(sid: str) -> str:
    match = re.search(r"-s\d{2}-([a-z0-9-]+)$", sid)
    return match.group(1) if match else "unknown"


def is_active_epic_child_status(status: dict) -> bool:
    if not (status.get("epic_id") or status.get("dependency_policy") == "activated_by_epic_dag"):
        return False
    state = str(status.get("status") or "").lower()
    phase = str(status.get("phase") or "").lower()
    if state in {"passed", "completed", "eval_passed", "cancelled", "canceled", "closed", "superseded", "interrupted"}:
        return False
    return state in EPIC_ACTIVE_CHILD_STATUSES or phase in EPIC_ACTIVE_CHILD_PHASES


def epic_activation_pressure(limit: int | None = None) -> dict:
    cap = max(0, int(EPIC_ACTIVE_CHILD_LIMIT if limit is None else limit))
    active = []
    for path in sorted(SPRINTS.glob("sprint-*.status.json")):
        status = load_json(path)
        if not is_active_epic_child_status(status):
            continue
        sid = str(status.get("sprint_id") or status.get("id") or path.name.removesuffix(".status.json"))
        active.append(
            {
                "sid": sid,
                "epic_id": str(status.get("epic_id") or ""),
                "slice": str(status.get("slice") or epic_child_slice_from_sid(sid)),
                "status": str(status.get("status") or ""),
                "phase": str(status.get("phase") or ""),
            }
        )
    remaining = max(0, cap - len(active))
    return {
        "limit": cap,
        "active_count": len(active),
        "remaining": remaining,
        "active_sample": active[:12],
        "backpressure": remaining <= 0,
    }


def load_state() -> dict:
    _ensure_graph_status_caches()
    state = load_json(STATE)
    state.setdefault("pane", {})
    state.setdefault("actions", {})
    state.setdefault("target_actions", {})
    state.setdefault("started_at", utc_now())
    # State is cache/projection, not the source of truth. If a sprint was
    # quarantined or deleted, stale action cache entries must not keep nudging
    # panes with dead dispatch text.
    for key in list(state.get("actions", {})):
        sid = key.split(":", 1)[0]
        if sid.startswith("sprint-") and not (SPRINTS / f"{sid}.status.json").exists():
            state["actions"].pop(key, None)
    for key in list(state.get("target_actions", {})):
        result = (state["target_actions"].get(key) or {}).get("result") or {}
        sid = str(result.get("sid") or "")
        if sid.startswith("sprint-") and not (SPRINTS / f"{sid}.status.json").exists():
            state["target_actions"].pop(key, None)
    return state


def _ensure_graph_status_caches() -> list[str]:
    if load_graph is None or sync_status_cache_from_graph is None:
        return []
    created: list[str] = []
    for graph_path in sorted(SPRINTS.glob("sprint-*.task_graph.json")):
        sid = graph_path.name.removesuffix(".task_graph.json")
        try:
            graph = load_graph(graph_path)
        except Exception:
            continue
        try:
            sync = sync_status_cache_from_graph(
                graph,
                graph_path,
                actor="solar-autopilot",
                event="autopilot_missing_status_cache_backfill",
            )
        except Exception:
            continue
        status_path = SPRINTS / f"{sid}.status.json"
        if sync.get("created") and status_path.exists():
            created.append(sid)
        _refresh_requirement_coverage_if_stale(sid, graph_path)
    return created


def _refresh_requirement_coverage_if_stale(sid: str, graph_path: Path) -> bool:
    if evaluate_requirement_coverage_sid is None:
        return False
    req_path = SPRINTS / f"{sid}.requirement_ir.json"
    if not req_path.exists():
        return False
    trace_path = SPRINTS / f"{sid}.requirement_trace.json"
    coverage_path = SPRINTS / f"{sid}.coverage_report.json"
    verdict_path = SPRINTS / f"{sid}.acceptance_verdict.json"
    artifact_paths = [trace_path, coverage_path, verdict_path]
    needs_refresh = any(not path.exists() for path in artifact_paths)
    if not needs_refresh:
        try:
            source_mtime = max(graph_path.stat().st_mtime, req_path.stat().st_mtime)
            artifact_mtime = min(path.stat().st_mtime for path in artifact_paths)
            needs_refresh = artifact_mtime < source_mtime
        except OSError:
            needs_refresh = True
    if not needs_refresh and trace_path.exists():
        try:
            trace_payload = json.loads(trace_path.read_text())
            mapped_nodes = {
                str(node_id)
                for item in (trace_payload.get("items") or [])
                for node_id in (item.get("mapped_nodes") or [])
            }
            graph_nodes = {
                str(node.get("id") or "")
                for node in (load_graph(graph_path).get("nodes") or [])
                if str(node.get("id") or "")
            }
            if mapped_nodes and not mapped_nodes.issubset(graph_nodes):
                needs_refresh = True
        except Exception:
            needs_refresh = True
    if not needs_refresh:
        return False
    try:
        evaluate_requirement_coverage_sid(
            sid,
            sprints_dir=SPRINTS,
            requested_verdict="pass",
            write=True,
            require_pass=False,
        )
    except Exception:
        return False
    return True


def save_state(state: dict) -> None:
    state["updated_at"] = utc_now()
    save_json(STATE, state)


def append_event(sid: str, event: str, severity: str = "info", data: dict | None = None) -> None:
    obj = {
        "ts": utc_now(),
        "sprint_id": sid,
        "actor": "solar-autopilot",
        "event": event,
        "severity": severity,
        "data": data or {},
    }
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    if sid:
        with (SPRINTS / f"{sid}.events.jsonl").open("a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        if record_legacy_event is not None:
            try:
                record_legacy_event(sid, event, "solar-autopilot", data or {}, harness_dir=HARNESS)
            except Exception:
                pass


def ensure_qmd_mcp_ipv4(reason: str) -> dict:
    """Keep the QMD MCP reachable from strict IPv4 clients before KB probes.

    QMD itself may listen only on ::1. Some Solar-Harness context paths probe
    127.0.0.1:8181, so a healthy QMD can look unavailable unless the local
    IPv4 proxy is running. This helper is best-effort and token-free.
    """
    harness_sh = HARNESS / "solar-harness.sh"
    checked_at_epoch = time.time()
    if os.environ.get("SOLAR_SKIP_QMD_MCP_HEAL") == "1":
        result = {
            "ok": True,
            "status": "skipped",
            "reason": reason,
            "skipped": "env_SOLAR_SKIP_QMD_MCP_HEAL",
            "checked_at": utc_now(),
            "checked_at_epoch": checked_at_epoch,
        }
        save_json(QMD_PROXY_HEALTH, result)
        return result
    if not harness_sh.exists():
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": "solar_harness_sh_missing",
            "path": str(harness_sh),
            "checked_at": utc_now(),
            "checked_at_epoch": checked_at_epoch,
        }
        save_json(QMD_PROXY_HEALTH, result)
        append_event("", "autopilot_qmd_mcp_ipv4_unavailable", "warn", result)
        return result
    try:
        proc = subprocess.run(
            [str(harness_sh), "wiki", "qmd-mcp", "start"],
            cwd=str(HARNESS),
            text=True,
            capture_output=True,
            timeout=15,
        )
        ok = proc.returncode == 0 and "127.0.0.1:8181" in ((proc.stdout or "") + (proc.stderr or ""))
        result = {
            "ok": ok,
            "status": "ok" if ok else "warn",
            "reason": reason,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
            "checked_at": utc_now(),
            "checked_at_epoch": checked_at_epoch,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "status": "warn",
            "reason": reason,
            "error": "qmd_mcp_start_timeout",
            "timeout_sec": 15,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
            "checked_at": utc_now(),
            "checked_at_epoch": checked_at_epoch,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "warn",
            "reason": reason,
            "error": f"{type(exc).__name__}: {exc}",
            "checked_at": utc_now(),
            "checked_at_epoch": checked_at_epoch,
        }
    save_json(QMD_PROXY_HEALTH, result)
    append_event(
        "",
        "autopilot_qmd_mcp_ipv4_ready" if result.get("ok") else "autopilot_qmd_mcp_ipv4_unavailable",
        "info" if result.get("ok") else "warn",
        result,
    )
    return result


def run_kb_probe(reason: str, force: bool = False) -> dict:
    """Run the default knowledge retrieval regression probe.

    This is intentionally local and token-free. It proves the default
    Mirage/QMD/Obsidian context path still answers the common probe set instead
    of silently degrading to sqlite-only lookups.
    """
    last = load_json(KB_PROBE_HEALTH)
    now_epoch = time.time()
    last_age = now_epoch - float(last.get("checked_at_epoch", 0) or 0) if last else 0
    last_status = str(last.get("status") or ("ok" if last.get("ok") else "error")) if last else ""
    last_stable = last_status in {"ok", "warn"}
    if force and last and last_stable and last.get("reason") == reason and last_age < KB_PROBE_TRIGGER_COOLDOWN_SEC:
        last["skipped"] = "trigger_cooldown"
        last["reason"] = reason
        return last
    if not force and last and (last_stable and last_age < KB_PROBE_INTERVAL_SEC):
        last["skipped"] = "cooldown"
        last["reason"] = reason
        return last
    # Successful probes and degraded coverage warnings both use the normal
    # cooldown window. Only hard KB errors bypass the long cache because
    # recovery is often external (QMD MCP restart, index refresh, Mirage route
    # repair), and keeping the stale failure makes every pane look broken even
    # after the default context path is healthy again.
    if not KB_PROBE_SCRIPT.exists():
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": "kb_probe_script_missing",
            "script": str(KB_PROBE_SCRIPT),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
        }
        save_json(KB_PROBE_HEALTH, result)
        append_event("", "autopilot_kb_probe_missing", "error", result)
        return result
    qmd_proxy = ensure_qmd_mcp_ipv4(reason)
    try:
        proc = subprocess.run(
            [str(KB_PROBE_SCRIPT)],
            cwd=str(HARNESS),
            text=True,
            capture_output=True,
            timeout=KB_PROBE_TIMEOUT_SEC,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        passed = re.search(r"PROBES_PASSED=(\d+)\s+PROBES_FAILED=(\d+)", output)
        passed_count = int(passed.group(1)) if passed else None
        failed_count = int(passed.group(2)) if passed else None
        ok = proc.returncode == 0 and failed_count == 0
        result = {
            "ok": ok,
            "status": "ok" if ok else "error",
            "reason": reason,
            "returncode": proc.returncode,
            "probes_passed": passed_count,
            "probes_failed": failed_count,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
            "script": str(KB_PROBE_SCRIPT),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
            "qmd_mcp_ipv4": qmd_proxy,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": "kb_probe_timeout",
            "timeout_sec": KB_PROBE_TIMEOUT_SEC,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "script": str(KB_PROBE_SCRIPT),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
            "qmd_mcp_ipv4": qmd_proxy,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": f"{type(exc).__name__}: {exc}",
            "script": str(KB_PROBE_SCRIPT),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
            "qmd_mcp_ipv4": qmd_proxy,
        }
    qmd_ok = bool((result.get("qmd_mcp_ipv4") or {}).get("ok"))
    passed_count = result.get("probes_passed")
    failed_count = result.get("probes_failed")
    if (
        not result.get("ok")
        and result.get("status") == "error"
        and qmd_ok
        and isinstance(passed_count, int)
        and isinstance(failed_count, int)
    ):
        result["status"] = "warn"
        result["failure_class"] = "coverage_miss"
        result["transport_ok"] = True
        result["content_ok"] = failed_count == 0
        result["degraded"] = True
        result["degraded_reason"] = "knowledge_coverage_incomplete"
    save_json(KB_PROBE_HEALTH, result)
    event_type = "autopilot_kb_probe_passed"
    event_severity = "info"
    if not result.get("ok"):
        if result.get("status") == "warn":
            event_type = "autopilot_kb_probe_degraded"
            event_severity = "warn"
        else:
            event_type = "autopilot_kb_probe_failed"
            event_severity = "error"
    append_event(
        "",
        event_type,
        event_severity,
        result,
    )
    return result


def run_model_registry_doctor(reason: str = "periodic", force: bool = False) -> dict:
    """Run model routing single-source guard without touching panes."""
    last = load_json(MODEL_DOCTOR_HEALTH)
    now_epoch = time.time()
    if not force and last and now_epoch - float(last.get("checked_at_epoch", 0)) < MODEL_DOCTOR_INTERVAL_SEC:
        last["skipped"] = "cooldown"
        last["reason"] = reason
        return last

    harness_cmd = HARNESS / "solar-harness.sh"
    if not harness_cmd.exists():
        harness_cmd = HOME / ".solar" / "bin" / "solar-harness"
    if not harness_cmd.exists():
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": "solar_harness_command_missing",
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
        }
        save_json(MODEL_DOCTOR_HEALTH, result)
        append_event("", "autopilot_model_registry_doctor_failed", "error", result)
        return result

    try:
        proc = subprocess.run(
            [str(harness_cmd), "models", "doctor"],
            cwd=str(HARNESS),
            text=True,
            capture_output=True,
            timeout=MODEL_DOCTOR_TIMEOUT_SEC,
        )
        ok = proc.returncode == 0
        result = {
            "ok": ok,
            "status": "ok" if ok else "error",
            "reason": reason,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
            "command": str(harness_cmd),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": "model_doctor_timeout",
            "timeout_sec": MODEL_DOCTOR_TIMEOUT_SEC,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "command": str(harness_cmd),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "error",
            "reason": reason,
            "error": f"{type(exc).__name__}: {exc}",
            "command": str(harness_cmd),
            "checked_at": utc_now(),
            "checked_at_epoch": now_epoch,
        }

    save_json(MODEL_DOCTOR_HEALTH, result)
    append_event(
        "",
        "autopilot_model_registry_doctor_passed" if result.get("ok") else "autopilot_model_registry_doctor_failed",
        "info" if result.get("ok") else "error",
        result,
    )
    return result


def tmux_capture(target: str) -> str:
    try:
        r = subprocess.run(
            ["tmux", "capture-pane", "-t", target, "-p", "-S", "-80"],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def pane_current_prompt_line(tail: str) -> str:
    """Return the current Claude prompt line if the visible pane is at prompt.

    Capture-pane includes scrollback. A plain regex over the whole tail can
    confuse old "thinking" text with current work. The live prompt is always in
    the last few non-empty visible lines, often followed by a border/status line.
    """
    lines = [line.rstrip() for line in tail.splitlines() if line.strip()]
    for line in reversed(lines[-10:]):
        if "❯" in line:
            return line
    return ""


def pane_at_prompt(tail: str) -> bool:
    return bool(pane_current_prompt_line(tail))


def pane_safe_continue_prompt(tail: str) -> bool:
    bottom = "\n".join(tail.splitlines()[-12:])
    return bool(SAFE_CONTINUE_PROMPT_RE.search(bottom))


def _tail_has_idle_prompt_footer(text: str) -> bool:
    if shared_tail_has_idle_prompt_footer:
        return bool(shared_tail_has_idle_prompt_footer(text))
    lines = [line.rstrip() for line in text.splitlines()]
    footer_prefixes = (
        "⏵",
        "●",
        "esc ",
        "Esc ",
        "Tab ",
        "Interrupt",
        "bypass permissions on",
        "accept edits on",
        "plan mode on",
    )
    for line in reversed(lines[-12:]):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if stripped.startswith("────────────────") or stripped.isdigit():
            continue
        if stripped.startswith("❯"):
            remainder = stripped[1:].strip()
            return not remainder or remainder.startswith("Try ")
        if lowered.startswith(footer_prefixes) or "tokens" in lowered or "/effort" in lowered:
            continue
        return False
    return False


def pane_survey_blocked(tail: str) -> bool:
    if pane_overlay_detail:
        detail = pane_overlay_detail(tail)
        return detail.get("state") == "pane_overlay_blocked" and detail.get("type") == "survey"
    # Survey text can remain in tmux scrollback after it has been dismissed.
    # Treat it as blocking only when it is still near the live prompt/footer.
    lines = tail.splitlines()[-16:]
    bottom = "\n".join(lines)
    if not SURVEY_PROMPT_RE.search(bottom):
        return False
    survey_idx = -1
    prompt_idx = -1
    for idx, line in enumerate(lines):
        if "How is Claude doing this session?" in line or re.search(r"1:\s*Bad\s+2:\s*Fine\s+3:\s*Good\s+0:", line):
            survey_idx = idx
        if line.strip().startswith("❯"):
            prompt_idx = idx
    return not (prompt_idx > survey_idx >= 0)


def pane_permissions_prompt_blocked(tail: str) -> bool:
    if pane_overlay_detail:
        detail = pane_overlay_detail(tail)
        if detail.get("state") == "stale_scrollback_ignored":
            return False
        if detail.get("state") == "pane_overlay_blocked" and detail.get("type") in {"permission", "proceed", "queued_input"}:
            return True
    bottom = "\n".join(tail.splitlines()[-40:])
    if _tail_has_idle_prompt_footer(bottom):
        return False
    if bool(PERMISSIONS_PROMPT_RE.search(bottom)):
        return True
    lower = bottom.lower()
    return (
        "what should claude do" in lower
        or "do you want to proceed?" in lower
    )


def clear_current_prompt(target: str) -> bool:
    tail = tmux_capture(target)
    if not pane_at_prompt(tail):
        return False
    try:
        subprocess.run(["tmux", "send-keys", "-t", target, "C-u"], timeout=1.5)
        return True
    except Exception:
        return False


def tmux_send(target: str, text: str) -> bool:
    if no_dispatch_enabled():
        return False
    try:
        clear_current_prompt(target)
        r = subprocess.run(["tmux", "send-keys", "-t", target, text, "Enter"], timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def dismiss_survey_prompt(target: str) -> bool:
    try:
        r = subprocess.run(["tmux", "send-keys", "-t", target, "0", "Enter"], timeout=2)
        return r.returncode == 0
    except Exception:
        return False


def dismiss_permissions_prompt(target: str) -> bool:
    try:
        first = subprocess.run(["tmux", "send-keys", "-t", target, "BTab"], timeout=2)
        second = subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], timeout=2)
        return first.returncode == 0 and second.returncode == 0
    except Exception:
        return False


def tmux_title(target: str) -> str:
    try:
        r = subprocess.run(
            ["tmux", "display-message", "-p", "-t", target, "#{pane_title}"],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def pane_title_matches_role(target: str, role: str, title: str | None = None) -> bool:
    if os.environ.get("SOLAR_AUTOPILOT_ALLOW_ANY_ROLE_PANE") == "1":
        return True
    title = tmux_title(target) if title is None else title
    # Ignore transient status suffixes like
    # `| 状态:working/...:sprint-...pm-pane-...` so sprint ids do not
    # accidentally trip role-conflict checks (`pm-pane` contains `PM`).
    title = re.split(r"\s+\|\s+状态:", title or "", maxsplit=1)[0].strip()
    if role in ("builder", "lab-builder"):
        if (
            target.startswith("solar-harness-lab:")
            or target.startswith("solar-harness-multi-task:")
        ):
            return bool(re.search(r"Builder|建设者|lab-builder", title, re.I)) and not bool(
                re.search(r"PM|产品经理|Planner|规划者|Evaluator|审判官", title, re.I)
            )
        return False
    if role == "evaluator":
        if not (
            target == f"{SESSION}:0.3"
            or target.startswith("solar-harness-multi-task:")
        ):
            return False
        non_role_title = re.sub(r"Evaluator|审判官", "", title, flags=re.I)
        return bool(re.search(r"Evaluator|审判官", title, re.I)) and not bool(
            re.search(r"PM|产品经理|Planner|规划者|Builder|建设者", non_role_title, re.I)
        )
    if role == "planner":
        if target != f"{SESSION}:0.1":
            return False
        non_role_title = re.sub(r"Planner|规划者", "", title, flags=re.I)
        return bool(re.search(r"Planner|规划者", title, re.I)) and not bool(
            re.search(r"PM|产品经理|Builder|建设者|Evaluator|审判官", non_role_title, re.I)
        )
    if role == "pm":
        if target != f"{SESSION}:0.0":
            return False
        non_role_title = re.sub(r"PM|产品经理", "", title, flags=re.I)
        return bool(re.search(r"PM|产品经理", title, re.I)) and not bool(
            re.search(r"Planner|规划者|Builder|建设者|Evaluator|审判官", non_role_title, re.I)
        )
    return False


def pane_execution_priority(target: str) -> tuple[int, str]:
    if target.startswith("solar-harness-multi-task:"):
        return (0, target)
    if target.startswith("solar-harness-lab:"):
        return (1, target)
    if target.startswith(f"{SESSION}:"):
        return (2, target)
    return (9, target)


def tmux_set_title(target: str, title: str) -> bool:
    try:
        r = subprocess.run(["tmux", "select-pane", "-t", target, "-T", title], timeout=1.5)
        return r.returncode == 0
    except Exception:
        return False


def normalize_idle_title(title: str) -> str:
    """Strip stale dispatch capability text and mark the pane as truly idle."""
    base = re.split(r"\s+\|\s+(?:能力|状态):", title or "", maxsplit=1)[0].strip()
    if not base:
        base = "Solar Pane"
    return f"{base} | 状态:idle/no active sprint"


def normalize_work_title(title: str, sid: str, action: str) -> str:
    base = re.split(r"\s+\|\s+(?:能力|状态):", title or "", maxsplit=1)[0].strip()
    if not base:
        base = "Solar Pane"
    short_sid = sid
    if short_sid.startswith("sprint-"):
        short_sid = short_sid[len("sprint-"):]
    if len(short_sid) > 54:
        short_sid = short_sid[:51] + "..."
    return f"{base} | 状态:working/{action}:{short_sid}"


def update_work_pane_title(target: str, sid: str, action: str) -> None:
    if not target or not sid:
        return
    current = tmux_title(target)
    if not current:
        return
    desired = normalize_work_title(current, sid, action or "dispatch")
    if current != desired:
        tmux_set_title(target, desired)


def update_idle_pane_titles(state: dict) -> list[dict]:
    """Make no-work state visible in tmux instead of leaving old task residue.

    This does not send text into Claude. It only updates pane border titles, so
    it is safe when all sprint/queue sources say there is no active work.
    """
    if active_statuses() or load_queue():
        return []
    updated: list[dict] = []
    targets = [
        f"{SESSION}:0.0",
        f"{SESSION}:0.1",
        f"{SESSION}:0.2",
        f"{SESSION}:0.3",
        "solar-harness-lab:0.0",
        "solar-harness-lab:0.1",
        "solar-harness-lab:0.2",
        "solar-harness-lab:0.3",
    ]
    for target in targets:
        current = tmux_title(target)
        if not current:
            continue
        desired = normalize_idle_title(current)
        if current == desired:
            continue
        if tmux_set_title(target, desired):
            updated.append({"target": target, "title": desired})
    if updated:
        state.setdefault("idle_title_updates", []).append({"ts": utc_now(), "panes": updated})
        state["idle_title_updates"] = state["idle_title_updates"][-20:]
        append_event("", "autopilot_idle_titles_updated", "info", {"panes": updated})
    return updated


def no_dispatch_enabled() -> bool:
    return os.environ.get("SOLAR_NO_DISPATCH") == "1" or NO_DISPATCH_FLAG.exists()


def pane_safe(target: str) -> str:
    return target.replace(":", "_").replace(".", "_")


def parse_utc(ts: str) -> float:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def pane_lease(target: str) -> dict:
    path = PANE_LEASE_DIR / f"{pane_safe(target)}.json"
    d = load_json(path)
    if not d:
        return {}
    now = time.time()
    exp = parse_utc(d.get("expires_at", ""))
    if exp and exp > now:
        d["active"] = True
        d["seconds_left"] = int(exp - now)
        return d
    return {}


def pane_assignments() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not PANE_ASSIGNMENTS.exists():
        return out
    now = time.time()
    for raw in PANE_ASSIGNMENTS.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        pane, rest = line.split("=", 1)
        parts = rest.rsplit(":", 1)
        sid = parts[0]
        ts = float(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0.0
        out[pane] = {"sid": sid, "assigned_at": ts, "age_sec": int(now - ts) if ts else None}
    return out


def pane_assignment(target: str) -> dict:
    return pane_assignments().get(target, {})


def _rewrite_pane_assignments(assignments: dict[str, dict]) -> None:
    PANE_ASSIGNMENTS.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for pane, meta in assignments.items():
        sid = str(meta.get("sid") or "").strip()
        if not pane or not sid:
            continue
        assigned_at = meta.get("assigned_at")
        ts = int(float(assigned_at)) if assigned_at else 0
        lines.append(f"{pane}={sid}:{ts}")
    payload = ("\n".join(lines) + "\n") if lines else ""
    PANE_ASSIGNMENTS.write_text(payload)


def clear_pane_assignment(target: str, reason: str = "") -> bool:
    assignments = pane_assignments()
    if target not in assignments:
        return False
    removed = assignments.pop(target)
    try:
        _rewrite_pane_assignments(assignments)
        append_event(
            str(removed.get("sid") or ""),
            "autopilot_reconcile_assignment_cleared",
            "info",
            {"pane": target, "reason": reason, "assignment": removed},
        )
        return True
    except Exception:
        return False


def clear_pane_lease(target: str, reason: str = "") -> bool:
    path = PANE_LEASE_DIR / f"{pane_safe(target)}.json"
    if not path.exists():
        return False
    lease = load_json(path)
    try:
        path.unlink(missing_ok=True)
        append_event(
            str(lease.get("sid") or ""),
            "autopilot_reconcile_lease_cleared",
            "info",
            {"pane": target, "reason": reason, "lease": lease},
        )
        return True
    except Exception:
        return False


def reconcile_pane_runtime_claims(target: str) -> dict:
    lease = pane_lease(target)
    assignment = pane_assignment(target)
    graph_node = assigned_graph_node_for_pane(target)
    busy = pane_is_busy(target)
    reconciled: dict[str, bool] = {}

    # A live graph node is the strongest proof of occupancy; keep both lease and
    # assignment intact in that case, even if the pane is currently at a prompt.
    if graph_node:
        return {
            "lease": lease,
            "assignment": assignment,
            "graph_node": graph_node,
            "busy": busy,
            "reconciled": reconciled,
        }

    if lease and not busy:
        if clear_pane_lease(target, "stale_live_lease_without_active_graph_node"):
            lease = {}
            reconciled["lease_cleared"] = True

    if assignment and not lease and not busy:
        if clear_pane_assignment(target, "stale_assignment_without_active_graph_node"):
            assignment = {}
            reconciled["assignment_cleared"] = True

    return {
        "lease": lease,
        "assignment": assignment,
        "graph_node": graph_node,
        "busy": busy,
        "reconciled": reconciled,
    }


def enqueue_action(finding: dict, reason: str, detail: dict | None = None) -> None:
    if is_telemetry_only_finding(finding):
        append_event(
            finding.get("sid", ""),
            "autopilot_queue_skip_telemetry_only",
            "info",
            {"target": finding.get("target", ""), "type": finding.get("type"), "reason": reason},
        )
        return
    existing_key = f"{finding.get('sid','')}:{finding.get('type','')}:{finding.get('target','')}"
    for old in load_queue():
        old_key = f"{old.get('sid','')}:{old.get('type','')}:{old.get('target','')}"
        if old_key == existing_key:
            return
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "ts": utc_now(),
        "created_at_epoch": time.time(),
        "sid": finding.get("sid", ""),
        "type": finding.get("type", ""),
        "target": finding.get("target", ""),
        "message": finding.get("message", ""),
        "reason": reason,
        "detail": detail or {},
        "attempts": int(finding.get("attempts", 0)),
    }
    with QUEUE.open("a") as q:
        q.write(json.dumps(item, ensure_ascii=False) + "\n")


def is_telemetry_only_finding(finding: dict) -> bool:
    """Signals that must never become pane work items.

    PM pane 0 is the user's intake surface. Autopilot can record PM residue and
    health failures, but must not push remediation prompts into that pane.
    """
    ftype = finding.get("type")
    target = finding.get("target", "")
    role = finding.get("role", "")
    if ftype in TELEMETRY_ONLY_FINDINGS:
        return True
    return ftype == "pane_asks_boss" and (role == "pm" or target == f"{SESSION}:0.0")


def load_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    items: list[dict] = []
    for raw in QUEUE.read_text(errors="ignore").splitlines():
        try:
            item = json.loads(raw)
        except Exception:
            continue
        if item.get("done") or item.get("expired"):
            continue
        items.append(item)
    return items


def save_queue(items: list[dict]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE.with_suffix(".jsonl.tmp")
    with tmp.open("w") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    tmp.replace(QUEUE)


def sprint_epic_id_for_sid(sid: str) -> str:
    sid = str(sid or "")
    if not sid:
        return ""
    status_path = SPRINTS / f"{sid}.status.json"
    if not status_path.exists():
        return ""
    try:
        status = load_json(status_path)
    except Exception:
        return ""
    return str(status.get("epic_id") or "")


def finding_matches_epic(finding: dict, epic_id: str) -> bool:
    epic_id = str(epic_id or "")
    if not epic_id:
        return True
    sid = str(finding.get("sid") or "")
    if sid == epic_id:
        return True
    if str(finding.get("epic_id") or "") == epic_id:
        return True
    if sprint_epic_id_for_sid(sid) == epic_id:
        return True
    ready_children = finding.get("ready_children")
    if isinstance(ready_children, list):
        for child in ready_children:
            if not isinstance(child, dict):
                continue
            child_sid = str(child.get("sid") or "")
            if child_sid and sprint_epic_id_for_sid(child_sid) == epic_id:
                return True
    return False


def filter_findings_by_epic(findings: list[dict], epic_id: str) -> list[dict]:
    if not epic_id:
        return findings
    return [finding for finding in findings if finding_matches_epic(finding, epic_id)]


def retry_queue(state: dict, dispatch: bool, cooldown: int, epic_filter: str = "") -> list[dict]:
    now_epoch = time.time()
    retained: list[dict] = []
    actions: list[dict] = []
    for item in load_queue():
        sid = item.get("sid", "")
        target = maybe_reroute_builder_target(item, sid)
        if epic_filter and not finding_matches_epic(item, epic_filter):
            retained.append(item)
            continue
        if sid and not (SPRINTS / f"{sid}.status.json").exists():
            append_event(
                sid,
                "autopilot_queue_drop_stale_sprint",
                "warn",
                {"target": target, "type": item.get("type"), "reason": "status_missing"},
            )
            actions.append({"sid": sid, "action": item.get("type"), "dropped": "stale_sprint", "target": target})
            continue
        if sid:
            status = load_json(SPRINTS / f"{sid}.status.json")
            status_value = str(status.get("status") or "").lower()
            if status_value in TERMINAL_STATUSES or status_value not in ACTIVE_STATUSES:
                append_event(
                    sid,
                    "autopilot_queue_drop_terminal_sprint",
                    "info",
                    {"target": target, "type": item.get("type"), "status": status.get("status"), "phase": status.get("phase")},
                )
                actions.append(
                    {
                        "sid": sid,
                        "action": item.get("type"),
                        "dropped": "terminal_sprint",
                        "target": target,
                        "status": status.get("status"),
                    }
                )
                continue
            if item.get("type") == "graph_node_idle_assigned":
                graph_node = item.get("graph_node") or {}
                node_id = str(graph_node.get("node_id") or item.get("node_id") or "")
                if node_id:
                    graph_path = graph_path_for(sid)
                    node_state = ""
                    handoff_exists = (SPRINTS / f"{sid}.{node_id}-handoff.md").exists()
                    try:
                        graph = load_graph(graph_path) if load_graph and graph_path.exists() else {}
                        for node in graph.get("nodes", []):
                            if str(node.get("id") or "") == node_id:
                                node_state = str(node_status(graph, node) if node_status else node.get("status") or "").lower()
                                break
                    except Exception:
                        node_state = ""
                    if handoff_exists or (node_state and node_state not in {"assigned", "dispatched", "in_progress", "running"}):
                        append_event(
                            sid,
                            "autopilot_queue_drop_completed_graph_node",
                            "info",
                            {
                                "target": target,
                                "type": item.get("type"),
                                "node_id": node_id,
                                "node_state": node_state,
                                "handoff_exists": handoff_exists,
                            },
                        )
                        actions.append(
                            {
                                "sid": sid,
                                "action": item.get("type"),
                                "dropped": "completed_graph_node",
                                "target": target,
                                "node_id": node_id,
                                "node_state": node_state,
                            }
                        )
                        continue
        if is_telemetry_only_finding(item):
            append_event(sid, "autopilot_queue_drop_telemetry_only", "info", {"target": target, "type": item.get("type")})
            actions.append({"sid": sid, "action": item.get("type"), "dropped": "telemetry_only", "target": target})
            continue
        age = now_epoch - float(item.get("created_at_epoch", now_epoch))
        if age > QUEUE_TTL_SEC:
            append_event(sid, "autopilot_queue_expired", "warn", {"target": target, "type": item.get("type"), "age_sec": int(age)})
            actions.append({"sid": sid, "action": item.get("type"), "expired": True, "target": target})
            continue
        role_pool_handoff = finding_uses_operator_role_pool(str(item.get("type") or ""))
        if not role_pool_handoff and target_recently_dispatched(state, target, cooldown):
            retained.append(item)
            actions.append({"sid": sid, "action": item.get("type"), "queued": True, "reason": "target_cooldown", "target": target})
            continue
        if not role_pool_handoff:
            allowed, gate_reason, gate_detail = pane_gate(target, sid)
            if not allowed:
                item["reason"] = gate_reason
                item["detail"] = gate_detail
                retained.append(item)
                actions.append({"sid": sid, "action": item.get("type"), "queued": True, "reason": gate_reason, "target": target})
                continue
        # Planner work has coordinator-level role routing and fallback
        # candidates (architect/lab-builder).  Do not let the autopilot's fixed
        # target probe (solar-harness:0.1) deadhead planner dispatch before
        # wake_sid() can ask the coordinator to choose an available role pane.
        if not role_pool_handoff and pane_is_busy(target):
            item["reason"] = "pane_busy"
            retained.append(item)
            actions.append({"sid": sid, "action": item.get("type"), "queued": True, "reason": "pane_busy", "target": target})
            continue
        sent = False
        if dispatch and target and not role_pool_handoff and item.get("type") != "pane_safe_continue_prompt":
            clear_current_prompt(target)
        role_dispatch_detail: dict = {}
        if dispatch and sid and role_pool_handoff:
            sent, role_dispatch_detail = dispatch_role_handoff(sid, str(item.get("type") or ""))
            if not sent:
                append_event(sid, "autopilot_role_pool_dispatch_failed", "warn", {"target": target, "type": item.get("type"), **role_dispatch_detail})
                item["reason"] = "role_pool_unavailable"
                item["detail"] = role_dispatch_detail
                retained.append(item)
                actions.append({
                    "sid": sid,
                    "action": item.get("type"),
                    "queued": True,
                    "reason": "role_pool_unavailable",
                    "target": target,
                    "role_pool_dispatch": role_dispatch_detail,
                })
                continue
        elif dispatch and sid:
            sent = wake_sid(sid)
        elif dispatch and target and item.get("message"):
            sent = tmux_send(target, item["message"])
        item["attempts"] = int(item.get("attempts", 0)) + 1
        if sent:
            append_event(sid, "autopilot_queue_dispatched", "info", {"target": target, "type": item.get("type"), "attempts": item["attempts"]})
            result = {"sid": sid, "action": item.get("type"), "dispatched_from_queue": True, "target": target}
            if role_pool_handoff:
                result["role_pool_dispatch"] = role_dispatch_detail or {"fallback": "wake_sid"}
            mark_action(state, {"sid": sid, "type": item.get("type", ""), "target": target}, result)
            actions.append(result)
        else:
            item["reason"] = "dispatch_failed"
            retained.append(item)
            append_event(sid, "autopilot_queue_dispatch_failed", "warn", {"target": target, "type": item.get("type"), "attempts": item["attempts"]})
            actions.append({"sid": sid, "action": item.get("type"), "queued": True, "reason": "dispatch_failed", "target": target})
    save_queue(retained)
    return actions


def pane_gate(target: str, sid: str) -> tuple[bool, str, dict]:
    state = reconcile_pane_runtime_claims(target)
    lease = state.get("lease", {})
    if lease and lease.get("sid") != sid:
        return False, "pane_leased", state
    assignment = state.get("assignment", {})
    if assignment and assignment.get("sid") != sid:
        age = assignment.get("age_sec")
        if age is None or age < 1800:
            return False, "pane_assigned", state
    return True, "ok", state


def solar_harness_command() -> Path:
    harness_cmd = HARNESS / "solar-harness.sh"
    if harness_cmd.exists():
        return harness_cmd
    return HOME / ".solar" / "bin" / "solar-harness"


def wake_sid(sid: str) -> bool:
    try:
        env = os.environ.copy()
        env["HARNESS_DIR"] = str(HARNESS)
        env["SOLAR_HARNESS_DIR"] = str(HARNESS)
        env.setdefault("SOLAR_HARNESS_SESSION", SESSION)
        r = subprocess.run(
            ["bash", str(solar_harness_command()), "wake", sid],
            capture_output=True,
            env=env,
            text=True,
            timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


ROLE_POOL_HANDOFF_FINDINGS = {"ready_for_planner", "ready_for_builder", "active_without_handoff", "pane_idle_with_pending_artifact", "ready_for_evaluator"}
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
ROLE_POOL_UNAVAILABLE_CACHE_TTL_SEC = int(os.environ.get("SOLAR_ROLE_POOL_UNAVAILABLE_CACHE_TTL_SEC", "120"))
ROLE_POOL_UNAVAILABLE_CACHE: dict[str, dict] = {}


def _role_pool_cache_get(role: str) -> dict | None:
    entry = ROLE_POOL_UNAVAILABLE_CACHE.get(role)
    if not isinstance(entry, dict):
        return None
    cached_at = float(entry.get("_cached_at_epoch") or 0)
    ttl = float(entry.get("_ttl_sec") or ROLE_POOL_UNAVAILABLE_CACHE_TTL_SEC)
    if cached_at and (time.time() - cached_at) > ttl:
        ROLE_POOL_UNAVAILABLE_CACHE.pop(role, None)
        return None
    return entry


def _role_pool_cache_put(role: str, detail: dict, *, ttl_sec: int | None = None) -> None:
    payload = dict(detail)
    payload["_cached_at_epoch"] = time.time()
    payload["_ttl_sec"] = int(ttl_sec or ROLE_POOL_UNAVAILABLE_CACHE_TTL_SEC)
    ROLE_POOL_UNAVAILABLE_CACHE[role] = payload


def _last_history_event(status: dict) -> str:
    hist = status.get("history")
    if not isinstance(hist, list) or not hist:
        return ""
    last = hist[-1]
    if not isinstance(last, dict):
        return ""
    return str(last.get("event") or "")


def _append_status_history_once(status: dict, event: str, note: str = "", **extra: object) -> bool:
    hist = status.setdefault("history", [])
    if not isinstance(hist, list):
        return False
    if _last_history_event(status) == event:
        return False
    payload = {"ts": utc_now(), "event": event, "by": "solar-autopilot"}
    if note:
        payload["note"] = note
    payload.update(extra)
    hist.append(payload)
    return True


def _pm_status_is_terminal(status: str) -> bool:
    value = str(status or "").strip().lower()
    if not value:
        return False
    return value in {"completed", "cancelled"} or value.startswith("failed")


def _active_pm_task_ids() -> set[str]:
    active: set[str] = set()
    for directory in (HARNESS / "run" / "operator-status", HARNESS / "run" / "operator-leases"):
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for key in ("task_id", "current_task_id", "lease_id"):
                value = str(payload.get(key) or "").strip()
                if value.startswith("pm-"):
                    active.add(value)
            lease = payload.get("lease")
            if isinstance(lease, dict):
                value = str(lease.get("task_id") or "").strip()
                if value.startswith("pm-"):
                    active.add(value)
    return active


def _pm_record_age_seconds(record: dict) -> float:
    for key in ("submitted_at", "created_at", "updated_at", "ts"):
        parsed = parse_utc(str(record.get(key) or ""))
        if parsed:
            return max(0.0, time.time() - parsed)
    return 0.0


def _pm_inbox_records_for_sprint_role(sid: str, role: str) -> list[dict]:
    if not sid or not role or not PM_INBOX_DIR.exists():
        return []
    records: list[dict] = []
    for path in PM_INBOX_DIR.glob("pm-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("sprint_id") or "") != sid:
            continue
        if str(payload.get("requested_role") or "").strip().lower() != role:
            continue
        payload["_path"] = str(path)
        records.append(payload)
    records.sort(key=lambda item: str(item.get("submitted_at") or item.get("created_at") or item.get("updated_at") or ""), reverse=True)
    return records


def _live_pm_task_for_sprint_role(sid: str, role: str) -> dict | None:
    active_ids = _active_pm_task_ids()
    for record in _pm_inbox_records_for_sprint_role(sid, role):
        task_id = str(record.get("task_id") or "")
        status = str(record.get("status") or "")
        age_sec = _pm_record_age_seconds(record)
        if task_id and task_id in active_ids:
            return record
        if not _pm_status_is_terminal(status) and age_sec <= 300:
            return record
    return None


def _latest_pm_record_for_sprint_role(sid: str, role: str) -> dict | None:
    records = _pm_inbox_records_for_sprint_role(sid, role)
    return records[0] if records else None


def _role_handoff_action_cooldown(finding: dict, default_cooldown: int) -> int:
    role = role_for_handoff_finding(str(finding.get("type") or ""))
    sid = str(finding.get("sid") or "")
    if not sid or not role:
        return default_cooldown
    if _live_pm_task_for_sprint_role(sid, role):
        return default_cooldown
    latest = _latest_pm_record_for_sprint_role(sid, role)
    if not latest:
        return default_cooldown
    if str(latest.get("status") or "").startswith("failed"):
        return min(default_cooldown, ROLE_HANDOFF_RETRY_COOLDOWN_SEC)
    return default_cooldown


def finding_uses_operator_role_pool(ftype: str) -> bool:
    """PM handoffs should consume physical operator pools, not fixed panes.

    The legacy wake path still targets the canonical 4-pane layout.  For planner
    and evaluator handoffs, prefer pm_dispatch/operator_runtime so multiple
    configured physical operators can be leased independently.
    """
    if codex_pane_runtime_suppresses_pm_operator_dispatch():
        return False
    return ftype in ROLE_POOL_HANDOFF_FINDINGS


def codex_pane_runtime_suppresses_pm_operator_dispatch() -> bool:
    runtime = os.environ.get("SOLAR_PANE_RUNTIME", "").strip().lower()
    allow = os.environ.get("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", "").strip().lower()
    return runtime == "codex" and allow not in TRUE_ENV_VALUES


def role_for_handoff_finding(ftype: str) -> str:
    if ftype == "ready_for_planner":
        return "planner"
    if ftype in {"ready_for_builder", "active_without_handoff", "pane_idle_with_pending_artifact"}:
        return "builder"
    if ftype == "ready_for_evaluator":
        return "evaluator"
    return ""


def _transition_planner_dispatch_claim(
    status: dict,
    state: str,
    detail: dict | None = None,
) -> bool:
    """Persist the operator-pool planner claim lifecycle on sprint status."""
    now = utc_now()
    before = json.dumps(status.get("planner_dispatch_claim"), sort_keys=True, default=str)
    existing = status.get("planner_dispatch_claim")
    claim = dict(existing) if isinstance(existing, dict) else {}
    claim["owner"] = "operator_pool"
    claim.setdefault("source", "solar_autopilot")
    claim.setdefault("claimed_at", now)
    claim.setdefault("ttl_seconds", PLANNER_DISPATCH_CLAIM_TTL_SEC)
    if state in {"pending", "submitting"}:
        expires = datetime.fromtimestamp(
            time.time() + PLANNER_DISPATCH_CLAIM_TTL_SEC,
            timezone.utc,
        )
        claim["expires_at"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
    claim["state"] = state
    claim["updated_at"] = now
    detail = detail or {}
    task_id = str(detail.get("task_id") or "").strip()
    if task_id:
        claim["task_id"] = task_id
    if state == "submitted":
        claim["submitted_at"] = now
        claim.pop("released_at", None)
        claim.pop("failure_reason", None)
        claim.pop("returncode", None)
    elif state == "failed":
        claim["released_at"] = now
        reason = str(detail.get("reason") or detail.get("error") or "").strip()
        if not reason:
            output = f"{detail.get('stderr') or ''}\n{detail.get('stdout') or ''}"
            no_operator = re.search(
                r"no_dispatchable_operator_for_role\s*:\s*([a-z0-9_.-]+)",
                output,
                re.IGNORECASE,
            )
            if no_operator:
                reason = f"no_dispatchable_operator_for_role: {no_operator.group(1).lower()}"
        if detail.get("returncode") is not None:
            claim["returncode"] = detail.get("returncode")
        else:
            claim.pop("returncode", None)
        reason = reason or "role_pool_dispatch_failed"
        claim["failure_reason"] = reason[-300:]
    status["planner_dispatch_claim"] = claim
    return before != json.dumps(claim, sort_keys=True, default=str)


def objective_for_role_handoff(sid: str, role: str) -> str:
    base = str(SPRINTS / sid)
    if role == "planner":
        return (
            f"请接手 {sid}：读取 {base}.prd.md、{base}.contract.md、"
            f"{base}.product-brief.md、{base}.requirement_ir.json、{base}.task_graph.json（存在即读）。"
            f"产出 {base}.design.md 和 {base}.plan.md；如 task_graph 还只是粗粒度需求图，"
            "请细化为可执行 DAG。不得跳过 PM->Planner->task_graph 主链直接交 Builder。"
            "完成所有 artifact 写入后结束本次受约束调用；不要运行 plan compiler，不要修改 status.json。"
            "Solar 会在 durable operator result 成功后独立验收、签证并推进生命周期；"
            "如果证据不足或需求不完整，写明 blocker 和下一步。"
        )
    if role == "evaluator":
        return (
            f"请接手 {sid} 的评审：读取 {base}.handoff.md、{base}.plan.md、"
            f"{base}.design.md、{base}.task_graph.json（存在即读）。"
            f"产出 {base}.eval.md 或对应节点 eval artifact。"
            "必须核查验收条件、实际命令证据、风险和未验证项；不要自证通过。"
        )
    if role == "builder":
        return (
            f"请接手 {sid} 的 Builder 执行：优先读取 {base}.task_graph.json，"
            f"再读取 {base}.plan.md、{base}.design.md、{base}.handoff.md（存在即读）。"
            "按 DAG/graph-dispatch 执行 ready nodes；不要绕过节点验收，也不要在缺少 DAG 时直接写 parent handoff。"
            "完成节点后必须写对应 handoff/evidence，并通过 graph node verdict 或状态 artifact 回写进度。"
        )
    return f"请接手 {sid} 的 {role} handoff，并按 Solar Harness 标准产出对应 artifact。"


def dispatch_role_handoff(sid: str, ftype: str) -> tuple[bool, dict]:
    role = role_for_handoff_finding(ftype)
    if not sid or not role:
        return False, {"reason": "not_role_pool_handoff"}
    cached = _role_pool_cache_get(role)
    if cached is not None:
        return False, {**cached, "cached": True}
    node = "N0" if role == "planner" else ("B0" if role == "builder" else "E0")
    task_type = "planning" if role == "planner" else ("implementation" if role == "builder" else "evaluation")
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(HARNESS)
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    cmd = [
        sys.executable,
        str(HARNESS / "tools" / "pm_dispatch.py"),
        "submit",
        "--role",
        role,
        "--sprint",
        sid,
        "--node",
        node,
        "--task-type",
        task_type,
        "--objective",
        objective_for_role_handoff(sid, role),
        "--context",
        "source=solar-autopilot role_pool_handoff=1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    except Exception as exc:
        return False, {"role": role, "error": f"{type(exc).__name__}: {exc}"}
    detail = {
        "role": role,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }
    ok = proc.returncode == 0
    if ok:
        ROLE_POOL_UNAVAILABLE_CACHE.pop(role, None)
    elif "no_dispatchable_operator_for_role" in (proc.stderr or ""):
        _role_pool_cache_put(role, detail)
    return ok, detail


def pane_is_busy(target: str) -> bool:
    tail = tmux_capture(target)
    bottom = "\n".join(tail.splitlines()[-12:])
    if RATE_LIMIT_OPTIONS_MODAL_RE.search("\n".join(tail.splitlines()[-40:])):
        if recover_pane_blocker(target):
            tail = tmux_capture(target)
            bottom = "\n".join(tail.splitlines()[-12:])
            if not RATE_LIMIT_OPTIONS_MODAL_RE.search("\n".join(tail.splitlines()[-40:])):
                return False
        return True
    if PANE_UNAVAILABLE_RE.search(bottom):
        return True
    if PANE_BOTTOM_BUSY_RE.search(bottom):
        if pane_at_prompt(tail) and not PANE_PROMPT_RESIDUE_RE.search(bottom):
            return False
        return True
    if PANE_PROMPT_RESIDUE_RE.search(bottom) and not pane_safe_continue_prompt(tail):
        return True
    if pane_at_prompt(tail):
        return False
    return bool(PANE_BUSY_RE.search(tail)) and not bool(PROMPT_IDLE_RE.search(tail))


def recover_pane_blocker(target: str) -> bool:
    """Best-effort cleanup for stale TUI blockers before marking a pane busy.

    This only dismisses overlays or idle prompt residue. It does not select paid
    upgrade/wait options, and it avoids active generation states.
    """
    tail = tmux_capture(target)
    bottom40 = "\n".join(tail.splitlines()[-40:])
    bottom12 = "\n".join(tail.splitlines()[-12:])
    try:
        if SURVEY_PROMPT_RE.search("\n".join(tail.splitlines()[-16:])):
            for keys in (("0", "Enter"), ("Escape",), ("C-u",)):
                subprocess.run(["tmux", "send-keys", "-t", target, *keys], timeout=2)
                time.sleep(0.4)
                after = tmux_capture(target)
                if not pane_survey_blocked(after):
                    append_event("", "autopilot_pane_recover_succeeded", "info", {"pane": target, "reason": "survey_prompt"})
                    return True
            append_event("", "autopilot_pane_recover_failed", "warn", {"pane": target, "reason": "survey_prompt"})
            return False
        if RATE_LIMIT_OPTIONS_MODAL_RE.search(bottom40):
            for keys in (("Escape",), ("C-c",)):
                subprocess.run(["tmux", "send-keys", "-t", target, *keys], timeout=2)
                time.sleep(0.4)
                after = "\n".join(tmux_capture(target).splitlines()[-40:])
                if not RATE_LIMIT_OPTIONS_MODAL_RE.search(after):
                    append_event("", "autopilot_pane_recover_succeeded", "info", {"pane": target, "reason": "rate_limit_options_modal"})
                    return True
            append_event("", "autopilot_pane_recover_failed", "warn", {"pane": target, "reason": "rate_limit_options_modal"})
            return False
        if "Press up to edit queued messages" in bottom12 or PANE_PROMPT_RESIDUE_RE.search(bottom12):
            for keys in (("Escape",), ("C-a", "C-k"), ("C-u",), ("C-c",), ("Escape", "C-u")):
                subprocess.run(["tmux", "send-keys", "-t", target, *keys], timeout=2)
                time.sleep(0.2)
                after = "\n".join(tmux_capture(target).splitlines()[-12:])
                if "Press up to edit queued messages" not in after and not PANE_PROMPT_RESIDUE_RE.search(after):
                    append_event("", "autopilot_pane_recover_succeeded", "info", {"pane": target, "reason": "prompt_residue"})
                    return True
            append_event("", "autopilot_pane_recover_failed", "warn", {"pane": target, "reason": "prompt_residue"})
        if PANE_BOTTOM_BUSY_RE.search(bottom12):
            return False
    except Exception as exc:
        append_event("", "autopilot_pane_recover_failed", "warn", {"pane": target, "error": str(exc)})
        return False
    return False


def sprint_files(sid: str) -> dict[str, bool]:
    def artifact_exists(suffix: str, *, node_level: bool = True) -> bool:
        direct = SPRINTS / f"{sid}.{suffix}"
        if direct.exists():
            return True
        if not node_level:
            return False
        return any(path.exists() for path in SPRINTS.glob(f"{sid}.*-{suffix}"))

    return {
        "status": (SPRINTS / f"{sid}.status.json").exists(),
        "prd": artifact_exists("prd.md", node_level=False),
        "contract": artifact_exists("contract.md", node_level=False),
        "design": artifact_exists("design.md"),
        "plan": artifact_exists("plan.md"),
        "task_graph": (SPRINTS / f"{sid}.task_graph.json").exists(),
        "handoff": artifact_exists("handoff.md"),
        "eval": artifact_exists("eval.md") or artifact_exists("eval.json"),
    }


def artifact_signature(sid: str) -> dict:
    names = ["status.json", "prd.md", "contract.md", "design.md", "plan.md", "handoff.md", "eval.md", "eval.json", "events.jsonl"]
    items = {}
    max_mtime = 0.0
    for suffix in names:
        candidates = [SPRINTS / f"{sid}.{suffix}"]
        if suffix in {"design.md", "plan.md", "handoff.md", "eval.md", "eval.json"}:
            candidates.extend(sorted(SPRINTS.glob(f"{sid}.*-{suffix}")))
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            continue
        st = path.stat()
        max_mtime = max(max_mtime, st.st_mtime)
        items[path.name] = {"mtime": int(st.st_mtime), "size": st.st_size}
    return {"items": items, "max_mtime": int(max_mtime)}


def tail_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def active_statuses() -> list[dict]:
    _ensure_graph_status_caches()
    rows = []
    for path in sorted(SPRINTS.glob("sprint-*.status.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        d = load_json(path)
        sid = d.get("sprint_id") or d.get("id") or path.name.removesuffix(".status.json")
        if d.get("status") in ACTIVE_STATUSES:
            d["_sid"] = sid
            d["_mtime"] = path.stat().st_mtime
            rows.append(d)
    return rows


def candidate_sid_for_role(role: str) -> str:
    for st in active_statuses():
        handoff = st.get("handoff_to", "")
        phase = st.get("phase", "")
        sid = st.get("_sid", "")
        if role == "planner" and (handoff == "planner" or phase == "prd_ready"):
            return sid
        if role == "builder" and handoff in ("builder", "builder_main", "builder_parallel", "builder-lab"):
            return sid
        if role == "evaluator" and handoff in ("evaluator", "reviewer"):
            return sid
        if role == "pm" and handoff in ("pm", "") and st.get("status") in ("drafting", "queued"):
            return sid
    return ""


def _pooled_target_for_role(role: str, primary: str) -> str:
    candidates: list[str] = []
    if discover_role_pool is not None:
        try:
            candidates = [str(item.get("pane") or "") for item in discover_role_pool(role) if str(item.get("pane") or "")]
        except Exception:
            candidates = []
    ordered = [primary] + [pane for pane in candidates if pane != primary]
    for pane in ordered:
        allowed, _, _ = pane_gate(pane, "__probe__")
        if allowed and not pane_is_busy(pane):
            return pane
    return primary


def pane_target_for_handoff(handoff: str) -> str:
    if handoff in ("planner", "architect"):
        return _pooled_target_for_role("planner", f"{SESSION}:0.1")
    if handoff in ("builder", "builder_main", "builder_parallel", "builder-lab"):
        primary = f"{SESSION}:0.2"
        candidates = [pane for pane in discover_worker_panes() if pane_title_matches_role(pane, "builder")]
        ordered = [primary] + [pane for pane in candidates if pane != primary]
        for pane in ordered:
            allowed, _, _ = pane_gate(pane, "__probe__")
            if allowed and not pane_is_busy(pane):
                return pane
        return primary
    if handoff in ("evaluator", "reviewer"):
        return _pooled_target_for_role("evaluator", f"{SESSION}:0.3")
    return f"{SESSION}:0.0"


def discover_worker_panes() -> list[str]:
    try:
        r = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0:
            rows = [p.rstrip("\n").split("\t", 1) for p in r.stdout.splitlines() if p.strip()]
            builders = [
                row[0].strip()
                for row in rows
                if row
                and (
                    row[0].strip().startswith("solar-harness-lab:")
                    or row[0].strip().startswith("solar-harness-multi-task:")
                )
                and pane_title_matches_role(row[0].strip(), "builder", row[1].strip() if len(row) > 1 else "")
            ]
            return sorted(builders, key=pane_execution_priority)
    except Exception:
        pass
    return []


def infer_worker_models(pane: str) -> list[str]:
    title_lower = tmux_title(pane).lower()
    if "deepseek" in title_lower:
        return ["deepseek", "deepseek-v4-pro"]
    if "glm-5.1" in title_lower or "glm" in title_lower or "zhipu" in title_lower:
        return ["glm", "glm-5.1", "zhipu"]
    if "opus" in title_lower:
        return ["opus", "anthropic-opus", "claude-opus"]
    if "sonnet" in title_lower:
        return ["sonnet", "anthropic-sonnet", "claude-sonnet"]
    if pane.startswith("solar-harness-lab:"):
        if pane.endswith(".3"):
            return ["sonnet", "anthropic-sonnet", "claude-sonnet"]
        return ["glm", "glm-5.1", "zhipu"]
    if pane.endswith(".2"):
        return ["opus", "anthropic-opus", "claude-opus"]
    if pane.endswith(".3"):
        return ["opus", "anthropic-opus", "claude-opus"]
    return ["sonnet"]


def graph_workers() -> list[dict]:
    workers = []
    skills = [
        "bash", "shell", "python", "python-read", "dataclasses", "pytest", "subprocess", "sqlite3", "pure-functions", "time-injection", "timeouts", "concurrency", "io", "fsm", "integration", "integration-testing", "integration-tests", "regression", "regression-tests", "bash-tests", "jq", "json", "json-patch", "jsonl-tail", "typescript", "docs", "testing",
        "stub-llm", "e2e-test", "cli-view-assertion", "negative-control", "verifier", "registry-introspection",
        "solar-harness-verification", "solar-harness-compat-review", "harness.verification", "verification",
        "cli-audit", "cli-design", "argparse", "argparse-bridge", "json-schema", "json-shape-inspect", "validation",
        "technical-writing", "markdown", "regex", "markdown-parse", "evidence-aggregation", "handoff-authoring", "traceability-patch", "knowledge-raw-writeback",
        "architecture-writing", "solar-harness-control-plane", "algorithm_design",
        "code_impl", "test_generation", "test_execution",
        "frontend", "terminal-ui", "tvs", "vdl", "snapshot", "snapshot-testing", "flask", "http-routing", "http-endpoint", "autopilot-hooks", "json-traversal", "html", "javascript", "vanilla-dom",
        "product", "planning", "optimization", "runtime_design",
        "architecture", "schema", "state-machine", "state-schema-design", "distributed-systems",
        "code-audit", "docs-audit", "type-hints", "type-protocols", "refactor", "tmux-inspect", "data-aggregation", "shutil", "urllib", "atomic-writes", "hashing", "unittest-mock", "evidence-collection", "evaluator-summary",
        "api-design", "data-modeling", "compatibility", "compat-review",
        "spec.write", "provider.contract", "agent.inventory",
        "command.catalog", "rules.catalog",
        "routing", "diagnostics", "evaluation", "capability-graph", "event-sourcing", "debug.systematic",
        "lazy-import",
        "browser", "browser.automation", "web", "scraping", "crawler", "collector",
        "social", "social.monitor", "social.signal", "social_links", "entity.extract", "link.extract", "url.extract", "cross_source.dispatch",
        # Logical operator aliases so graph nodes expressed in logical classes
        # can still match the conservative builder worker catalog.
        "DeepArchitect", "ImplementationWorker", "Critic", "Verifier",
    ]
    capabilities = [
        "bash", "python", "typescript", "docs", "testing",
        "frontend", "observability", "evidence",
        "solar-harness-verification", "solar-harness-compat-review", "harness.verification", "verification",
        "env-passthrough", "metrics",
        "harness.context_preflight", "harness.intent", "harness.dispatch_visibility", "harness.contracts",
        "harness.dag", "harness.status", "harness.model_routing",
        "intent.match", "intent.audit", "dispatch.intent_telemetry",
        "models.show", "models.lab_matrix", "models.footer_labels",
        "context.inject", "wiki.status", "data_plane.audit",
        "dag.validate", "dag.ready_nodes", "dag.join_gate",
        "harness.testing", "harness.reporting", "harness.knowledge",
        "lazy-import", "cli",
        "activation.proof", "negative_control", "runtime_artifacts",
        "autopilot.monitor", "autopilot.safe_apply", "pane.deadlock_detection",
        "documentation", "schema", "state-machine", "storage", "sources",
        "algorithm_design", "solar-harness-control-plane", "architecture-writing",
        "code_impl", "test_generation", "test_execution",
        "code.review", "debug.systematic", "skill.methodology",
        "workflow.planning", "product.requirements", "test.tdd", "browser.browse", "browser.qa",
        "research.empirical_pipeline", "research.literature_review",
        "analysis.causal_inference",
        "architecture", "distributed-systems", "evaluation",
        "research.scope_rewrite", "research.source_matrix", "research.evidence.extract",
        "research.claim.mine", "research.citation.verify", "research.report.compile",
        "report.compile", "research.long_report_compiler", "research.report_ast",
        "document.convert", "document.markdown_extract",
        "ruflo.swarm", "ruflo.plugins", "ruflo.agent_catalog",
        "ruflo.memory", "ruflo.mcp", "ruflo.workflow_templates",
        # Requirement Compiler / quality-loop DAGs use these richer capability
        # labels. Keep them in the autopilot worker catalog so ready nodes are
        # not stranded as `no_matching_worker` while still routing through the
        # existing builder_main path.
        "schema_design", "fixture_design", "mapping_design",
        "compatibility_design", "feedback_design", "gate_design",
        "metric_design", "replay_design", "shell_design", "synthesis",
        "repair.pr-cot", "failure.structured_repair",
        "routing.complexity_budget", "security_review",
        "optimization", "runtime_design",
        "agent.inventory", "command.catalog", "rules.catalog",
        "codex.bridge", "codex.contract_ingest", "codex.review_handoff", "pane3.bridge",
        "browser", "browser.automation", "web", "web.capture", "scraping", "crawler", "collector",
        "social", "social.monitor", "social.signal", "social_links", "entity.extract", "link.extract", "url.extract", "cross_source.dispatch",
    ]
    schema_caps = {
        "schema_design", "fixture_design", "mapping_design",
        "compatibility_design", "feedback_design", "gate_design",
        "metric_design", "replay_design", "shell_design", "synthesis",
        "documentation", "schema", "architecture-writing", "architecture",
        "document.convert", "document.markdown_extract", "report.compile",
        "research.long_report_compiler", "research.report_ast"
    }
    schema_skills = {
        "architecture-writing", "json-schema", "technical-writing", "markdown",
        "architecture", "schema", "state-schema-design", "api-design", "data-modeling"
    }

    for pane in discover_worker_panes():
        lease = pane_lease(pane)
        is_busy_tui = pane_is_busy(pane)
        busy = bool(lease) or is_busy_tui
        
        if lease and not is_busy_tui:
            try:
                (PANE_LEASE_DIR / f"{pane_safe(pane)}.json").unlink(missing_ok=True)
                lease = {}
                busy = False
                append_event("", "autopilot_reconcile_lease_cleared", "info", {"pane": pane})
            except Exception:
                pass

        pane_skills = list(skills)
        pane_caps = list(capabilities)
        
        if not (pane.startswith("solar-harness-lab:") or pane.startswith("solar-harness-multi-task:")):
            pane_caps = [c for c in pane_caps if c not in schema_caps]
            pane_skills = [s for s in pane_skills if s not in schema_skills]

        workers.append(
            {
                "pane": pane,
                "models": infer_worker_models(pane),
                "skills": pane_skills,
                "capabilities": pane_caps,
                "busy": busy,
                "lease": lease,
            }
        )
    return workers


def graph_path_for(sid: str) -> Path:
    return SPRINTS / f"{sid}.task_graph.json"


def sprint_status_payload(sid: str) -> dict:
    path = SPRINTS / f"{sid}.status.json"
    if not path.exists():
        return {}
    return load_json(path)


def sprint_has_terminal_evidence(sid: str) -> bool:
    status = sprint_status_payload(sid)
    state = str(status.get("status", "")).lower()
    if state in {"passed", "completed", "eval_passed"}:
        return True
    handoff = (SPRINTS / f"{sid}.handoff.md").exists() or any(SPRINTS.glob(f"{sid}.*-handoff.md"))
    eval_exists = (
        (SPRINTS / f"{sid}.eval.md").exists()
        or (SPRINTS / f"{sid}.eval.json").exists()
        or any(SPRINTS.glob(f"{sid}.*-eval.md"))
        or any(SPRINTS.glob(f"{sid}.*-eval.json"))
    )
    return handoff and eval_exists


def sprint_passed(sid: str) -> bool:
    return str(sprint_status_payload(sid).get("status", "")).lower() in {"passed", "completed", "eval_passed"}


def _child_state_to_epic_node_projection(child_state: str) -> tuple[str | None, str | None]:
    state = str(child_state or "").lower()
    if state in {"passed", "completed", "eval_passed"}:
        return "passed", "passed"
    if state in {"active", "approved", "planning", "reviewing", "ready_for_review"}:
        return "active", None
    if state in {"queued", "drafting"}:
        return "pending", None
    if state == "needs_human_review":
        return "needs_human_review", None
    if state in {"failed", "failed_review", "blocked"}:
        return "failed", None
    if state in {"cancelled", "archived"}:
        return "cancelled", None
    return None, None


def sync_epic_child_projection(epic_id: str, graph: dict | None = None) -> tuple[dict, bool]:
    graph_path = SPRINTS / f"{epic_id}.task_graph.json"
    if graph is None:
        if not graph_path.exists():
            return {}, False
        graph = load_json(graph_path)
    changed = False
    for node in graph.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        child_sid = str(node.get("child_sprint_id") or "")
        if not child_sid:
            continue
        child_state = str(sprint_status_payload(child_sid).get("status", "")).lower()
        desired_status, desired_gate = _child_state_to_epic_node_projection(child_state)
        if desired_status and str(node.get("status") or "") != desired_status:
            node["status"] = desired_status
            node["updated_at"] = utc_now()
            changed = True
        current_gate = node.get("gate_status")
        if desired_gate:
            if str(current_gate or "") != desired_gate:
                node["gate_status"] = desired_gate
                node["updated_at"] = utc_now()
                changed = True
        elif current_gate is not None:
            node["gate_status"] = None
            node["updated_at"] = utc_now()
            changed = True
    if changed and graph_path.exists():
        save_json(graph_path, graph)
    return graph, changed


def epic_dep_passed(dep_node: dict) -> bool:
    dep_sid = str(dep_node.get("child_sprint_id") or "")
    dep_node_state = str(dep_node.get("status") or "").lower()
    return dep_node_state in {"passed", "completed", "eval_passed"} or (dep_sid and sprint_passed(dep_sid))


def epic_child_dependency_ready(sid: str) -> tuple[bool, list[str]]:
    status = sprint_status_payload(sid)
    epic_id = str(status.get("epic_id") or "")
    if not epic_id:
        return True, []
    graph_path = SPRINTS / f"{epic_id}.task_graph.json"
    if not graph_path.exists():
        return True, []
    graph = load_json(graph_path)
    graph, _changed = sync_epic_child_projection(epic_id, graph)
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    by_id = {str(n.get("id")): n for n in nodes if n.get("id")}
    child_node = None
    for node in nodes:
        if str(node.get("child_sprint_id") or "") == sid:
            child_node = node
            break
    if not child_node:
        return True, []
    blocked_by: list[str] = []
    for dep in child_node.get("depends_on", []) or []:
        dep_node = by_id.get(str(dep), {})
        dep_sid = str(dep_node.get("child_sprint_id") or "")
        if dep_sid and not epic_dep_passed(dep_node):
            blocked_by.append(dep_sid)
    return not blocked_by, blocked_by


def _fallback_graph_node_for_runtime_claim(
    target: str,
    *,
    lease: dict | None = None,
    assignment: dict | None = None,
) -> dict:
    if load_graph is None:
        return {}
    active_node_statuses = {"assigned", "dispatched", "in_progress", "running"}
    lease = lease if isinstance(lease, dict) else {}
    assignment = assignment if isinstance(assignment, dict) else {}
    dispatch_id = str(lease.get("dispatch_id") or assignment.get("dispatch_id") or "").strip()
    sid_hint = str(lease.get("sid") or lease.get("sprint_id") or assignment.get("sid") or "").strip()
    candidate_paths: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(path: Path) -> None:
        if path.exists() and path not in seen:
            seen.add(path)
            candidate_paths.append(path)

    if sid_hint:
        add_candidate(graph_path_for(sid_hint))
    for path in sorted(SPRINTS.glob("sprint-*.task_graph.json")):
        add_candidate(path)

    for path in candidate_paths:
        try:
            graph = load_graph(path)
        except Exception:
            continue
        sid = str(graph.get("sprint_id") or path.stem.replace(".task_graph", ""))
        for node in graph.get("nodes", []):
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            try:
                state = str(node_status(graph, node_id)).lower() if node_status is not None else str(node.get("status") or "").lower()
            except Exception:
                state = str(node.get("status") or "").lower()
            if state not in active_node_statuses:
                continue
            if str(node.get("assigned_to") or "") != target and (not dispatch_id or str(node.get("dispatch_id") or "") != dispatch_id):
                continue
            handoff = SPRINTS / f"{sid}.{node_id}-handoff.md"
            if handoff.exists():
                continue
            return {
                "sid": sid,
                "node_id": node_id,
                "status": state,
                "graph": str(path),
                "dispatch_file": str(SPRINTS / f"{sid}.{node_id}-dispatch.md"),
                "dispatch_id": str(node.get("dispatch_id") or dispatch_id),
                "recovered_from_runtime_evidence": True,
            }
    return {}


def child_graph_external_prerequisite_blocks(sid: str) -> list[dict]:
    graph_path = SPRINTS / f"{sid}.task_graph.json"
    if not graph_path.exists():
        return []
    graph = load_json(graph_path)
    if iter_blocked is None:
        return []
    return iter_blocked(graph, SPRINTS)


def set_epic_child_node_status(sid: str, node_status: str) -> bool:
    status = sprint_status_payload(sid)
    epic_id = str(status.get("epic_id") or "")
    if not epic_id:
        return False
    graph_path = SPRINTS / f"{epic_id}.task_graph.json"
    if not graph_path.exists():
        return False
    graph = load_json(graph_path)
    changed = False
    for node in graph.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        if str(node.get("child_sprint_id") or "") != sid:
            continue
        if str(node.get("status") or "") != node_status:
            node["status"] = node_status
            node["updated_at"] = utc_now()
            changed = True
    if changed:
        save_json(graph_path, graph)
    return changed


def inspect_epics() -> list[dict]:
    findings = []
    activation_pressure = epic_activation_pressure()
    backpressure_reported = False
    for meta_path in sorted(SPRINTS.glob("epic-*.epic.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = load_json(meta_path)
        epic_id = meta.get("epic_id") or meta_path.name.removesuffix(".epic.json")
        graph_path = SPRINTS / f"{epic_id}.task_graph.json"
        if not graph_path.exists():
            continue
        graph = load_json(graph_path)
        graph, _changed = sync_epic_child_projection(str(epic_id), graph)
        nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
        by_id = {str(n.get("id")): n for n in nodes if n.get("id")}
        ready = []
        blocked = []
        for node in nodes:
            child_sid = str(node.get("child_sprint_id") or "")
            if not child_sid:
                continue
            st = sprint_status_payload(child_sid)
            if str(st.get("status", "")).lower() not in {"queued", "drafting"}:
                continue
            missing = []
            for dep in node.get("depends_on", []) or []:
                dep_node = by_id.get(str(dep), {})
                dep_sid = str(dep_node.get("child_sprint_id") or "")
                if dep_sid and not epic_dep_passed(dep_node):
                    missing.append(dep_sid)
            if missing:
                blocked.append({"sid": child_sid, "blocked_by": missing})
            else:
                child_graph_blocked = child_graph_external_prerequisite_blocks(child_sid)
                route = workflow_guard_route(child_sid)
                if child_graph_blocked or route.get("reason") == "external_prerequisite_blocked":
                    blocked.append({
                        "sid": child_sid,
                        "blocked_by": child_graph_blocked or route.get("blocked_prerequisites", []),
                    })
                    continue
                ready.append({"sid": child_sid, "node_id": node.get("id")})
        if ready and activation_pressure and activation_pressure.get("backpressure"):
            if not backpressure_reported:
                findings.append(
                    {
                        "sid": str(epic_id),
                        "type": "epic_activation_backpressure",
                        "severity": "warn",
                        "target": "",
                        "message": "Global epic child WIP limit reached; suppressing new child activation.",
                        "ready_children_suppressed": ready,
                        "blocked_children": blocked,
                        "activation_pressure": activation_pressure,
                    }
                )
                backpressure_reported = True
            continue
        if ready:
            findings.append(
                {
                    "sid": str(epic_id),
                    "type": "epic_ready_children",
                    "severity": "info",
                    "target": "",
                    "message": f"{epic_id} has dependency-ready child sprints.",
                    "ready_children": ready,
                    "blocked_children": blocked,
                }
            )
    return findings


def inspect_epic_child_state_drift() -> list[dict]:
    """Find child sprints whose live state violates parent DAG dependencies."""
    findings: list[dict] = []
    for meta_path in sorted(SPRINTS.glob("epic-*.epic.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = load_json(meta_path)
        epic_id = str(meta.get("epic_id") or meta_path.name.removesuffix(".epic.json"))
        graph_path = SPRINTS / f"{epic_id}.task_graph.json"
        if not graph_path.exists():
            continue
        graph = load_json(graph_path)
        graph, _changed = sync_epic_child_projection(epic_id, graph)
        nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
        by_id = {str(n.get("id")): n for n in nodes if n.get("id")}
        for node in nodes:
            sid = str(node.get("child_sprint_id") or "")
            if not sid:
                continue
            status = sprint_status_payload(sid)
            child_state = str(status.get("status", "")).lower()
            if child_state not in {"active", "approved", "reviewing", "ready_for_review"}:
                continue
            blocked_by: list[str] = []
            for dep in node.get("depends_on", []) or []:
                dep_node = by_id.get(str(dep), {})
                dep_sid = str(dep_node.get("child_sprint_id") or "")
                if dep_sid and not epic_dep_passed(dep_node):
                    blocked_by.append(dep_sid)
            if blocked_by:
                findings.append(
                    {
                        "sid": sid,
                        "type": "epic_child_dependency_blocked",
                        "severity": "warn",
                        "target": "",
                        "message": f"{sid} is active before dependencies passed; autopilot will downgrade to queued.",
                        "blocked_by": blocked_by,
                        "epic_id": epic_id,
                    }
                )
    return findings


def graph_status(sid: str) -> dict:
    path = graph_path_for(sid)
    if not path.exists() or load_graph is None:
        return {"exists": path.exists(), "ready": False, "path": str(path)}
    try:
        graph = load_graph(path)
        doctor = {}
        if doctor_graph is not None:
            doctor = doctor_graph(graph, repair=True)
            if doctor.get("repaired") and save_graph is not None:
                save_graph(path, graph)
                append_event(sid, "autopilot_graph_doctor_repaired", "warn", doctor)
        validation = validate_graph(graph) if validate_graph else {"ok": False, "errors": ["graph_scheduler_unavailable"]}
        parent = parent_ready_check(graph) if parent_ready_check else {"ready": False}
        return {
            "exists": True,
            "path": str(path),
            "valid": bool(validation.get("ok")),
            "validation": validation,
            "doctor": doctor,
            "parent_ready": bool(parent.get("ready")),
            "parent": parent,
        }
    except Exception as exc:
        return {"exists": True, "ready": False, "path": str(path), "valid": False, "error": str(exc)}


def inspect_deepresearch_quality_gates(epic_filter: str = "") -> list[dict]:
    """Find DeepResearch nodes whose completed gate state needs repair.

    Missing gates on pending/reviewing nodes are visibility signals, not bugs.
    The repair path only targets terminal node states that would otherwise
    allow a bad parent closeout or leave a failed gate stranded.
    """
    findings: list[dict] = []
    for status in active_statuses():
        sid = str(status.get("_sid") or status.get("sprint_id") or status.get("id") or "")
        if not sid:
            continue
        if epic_filter and str(status.get("epic_id") or "") != epic_filter:
            continue
        graph_path = graph_path_for(sid)
        if not graph_path.exists():
            continue
        try:
            graph = load_graph(graph_path) if load_graph else load_json(graph_path)
        except Exception as exc:
            findings.append({
                "sid": sid,
                "type": "deepresearch_quality_gate_repair",
                "severity": "warn",
                "target": "",
                "node_id": "",
                "message": f"{sid} DeepResearch task_graph cannot be loaded for quality gate scan.",
                "gate_status": "graph_error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        for node in graph.get("nodes", []) or []:
            if not isinstance(node, dict) or not node_requires_deepresearch_quality_gate(node):
                continue
            node_id = str(node.get("id") or "")
            try:
                status_value = str(node_status(graph, node_id) if node_status else node.get("status") or "").lower()
            except Exception:
                status_value = str(node.get("status") or "").lower()
            if status_value not in {"passed", "failed"}:
                continue
            gate = node.get("research_quality_gate") if isinstance(node.get("research_quality_gate"), dict) else {}
            if gate and deepresearch_quality_gate_ok(gate):
                continue
            gate_status = "missing" if not gate else "failed"
            findings.append({
                "sid": sid,
                "type": "deepresearch_quality_gate_repair",
                "severity": "warn",
                "target": "",
                "node_id": node_id,
                "graph_path": str(graph_path),
                "node_status": status_value,
                "gate_status": gate_status,
                "gate": gate,
                "message": (
                    f"{sid}/{node_id} DeepResearch quality gate is {gate_status} after node status {status_value}; "
                    "autopilot will reopen node evaluation and dispatch evaluator."
                ),
            })
    return findings


def assigned_graph_node_for_pane(target: str) -> dict:
    if load_graph is None:
        return {}
    active_node_statuses = {"assigned", "dispatched", "in_progress", "running"}
    for status in active_statuses():
        sid = status.get("_sid") or status.get("sprint_id") or status.get("id")
        if not sid:
            continue
        path = graph_path_for(str(sid))
        if not path.exists():
            continue
        try:
            graph = load_graph(path)
        except Exception:
            continue
        for node in graph.get("nodes", []):
            node_id = str(node.get("id") or "")
            if node_status is not None:
                node_state = str(node_status(graph, node_id)).lower()
            else:
                node_state = str(node.get("status") or "").lower()
            if node.get("assigned_to") != target or node_state not in active_node_statuses:
                continue
            handoff = SPRINTS / f"{sid}.{node_id}-handoff.md"
            if handoff.exists():
                continue
            return {
                "sid": str(sid),
                "node_id": node_id,
                "status": node_state,
                "graph": str(path),
                "dispatch_file": str(SPRINTS / f"{sid}.{node_id}-dispatch.md"),
                "dispatch_id": node.get("dispatch_id", ""),
            }
    lease = pane_lease(target)
    assignment = pane_assignment(target)
    return _fallback_graph_node_for_runtime_claim(target, lease=lease, assignment=assignment)


def assigned_eval_graph_node_for_pane(target: str) -> dict:
    if load_graph is None:
        return {}
    active_node_statuses = {"reviewing", "ready_for_review", "failed_review"}
    for status in active_statuses():
        sid = status.get("_sid") or status.get("sprint_id") or status.get("id")
        if not sid:
            continue
        path = graph_path_for(str(sid))
        if not path.exists():
            continue
        try:
            graph = load_graph(path)
        except Exception:
            continue
        for node in graph.get("nodes", []):
            node_id = str(node.get("id") or "")
            if node_status is not None:
                node_state = str(node_status(graph, node_id)).lower()
            else:
                node_state = str(node.get("status") or "").lower()
            if node_state not in active_node_statuses:
                continue
            assignments = node.get("eval_assignments") if isinstance(node.get("eval_assignments"), list) else []
            matched = next((item for item in assignments if isinstance(item, dict) and str(item.get("pane") or "") == target), None)
            if not matched and str(node.get("eval_assigned_to") or "") != target:
                continue
            return {
                "sid": str(sid),
                "node_id": node_id,
                "status": node_state,
                "graph": str(path),
                "dispatch_id": str((matched or {}).get("dispatch_id") or node.get("eval_dispatch_id") or ""),
                "eval_dispatch_group_id": str(node.get("eval_dispatch_group_id") or ""),
            }
    return {}


def available_evaluator_targets(exclude: str = "") -> list[str]:
    if graph_dispatch_node_evals is None:
        return []
    try:
        import graph_node_dispatcher as gnd  # type: ignore
        evaluators = gnd._discover_evaluators(False)
    except Exception:
        return []
    out: list[str] = []
    for item in evaluators:
        pane = str(item.get("pane") or "")
        if not pane or pane == exclude or item.get("busy"):
            continue
        out.append(pane)
    return out


def reroute_survey_blocked_evaluator(finding: dict, dispatch: bool) -> dict:
    target = str(finding.get("target") or "")
    graph_node = finding.get("graph_node") if isinstance(finding.get("graph_node"), dict) else {}
    sid = str(finding.get("sid") or graph_node.get("sid") or "")
    node_id = str(graph_node.get("node_id") or "")
    graph_path = Path(str(graph_node.get("graph") or graph_path_for(sid)))
    lease = finding.get("lease") if isinstance(finding.get("lease"), dict) else {}
    if not sid or not node_id or not graph_path.exists() or load_graph is None or save_graph is None:
        return {"ok": False, "reason": "missing_graph_or_node", "sid": sid, "node_id": node_id, "target": target}
    alternates = available_evaluator_targets(exclude=target)
    if not alternates:
        return {"ok": False, "reason": "no_alternate_evaluator", "sid": sid, "node_id": node_id, "target": target}
    graph = load_graph(graph_path)
    node = next((n for n in graph.get("nodes", []) if isinstance(n, dict) and str(n.get("id") or "") == node_id), None)
    if not node:
        return {"ok": False, "reason": "node_not_found", "sid": sid, "node_id": node_id, "target": target}
    dispatch_id = str(lease.get("dispatch_id") or graph_node.get("dispatch_id") or node.get("eval_dispatch_id") or "")
    clear_pane_lease(target, "survey_prompt_blocked_reroute")
    node.pop("eval_dispatch_group_id", None)
    node.pop("eval_recovered_from_lease", None)
    node.pop("eval_retry_reason", None)
    node.pop("eval_md_path", None)
    node.pop("eval_json", None)
    node.pop("eval_json_path", None)
    node.pop("eval_dispatched_at", None)
    node.pop("eval_assigned_to", None)
    node.pop("eval_dispatch_id", None)
    node.pop("eval_assignments", None)
    save_graph(graph_path, graph)
    dispatch_result = graph_dispatch_node_evals(str(graph_path), dry_run=not dispatch, ttl=900, force=True, max_items=1) if graph_dispatch_node_evals is not None else {"ok": False, "reason": "graph_dispatcher_unavailable"}
    return {
        "ok": bool(dispatch_result.get("ok")),
        "sid": sid,
        "node_id": node_id,
        "target": target,
        "released_dispatch_id": dispatch_id,
        "alternate_candidates": alternates,
        "dispatch_result": dispatch_result,
    }


def recover_unavailable_graph_node(finding: dict, dispatch: bool) -> dict:
    target = str(finding.get("target") or "")
    graph_node = finding.get("graph_node") if isinstance(finding.get("graph_node"), dict) else {}
    sid = str(finding.get("sid") or graph_node.get("sid") or "")
    node_id = str(graph_node.get("node_id") or "")
    graph_path = Path(str(graph_node.get("graph") or graph_path_for(sid)))
    if not sid or not node_id or not graph_path.exists() or load_graph is None or save_graph is None:
        return {"ok": False, "reason": "missing_graph_or_node", "sid": sid, "node_id": node_id, "target": target}
    graph = load_graph(graph_path)
    node = next((n for n in graph.get("nodes", []) if isinstance(n, dict) and str(n.get("id") or "") == node_id), None)
    if not node:
        return {"ok": False, "reason": "node_not_found", "sid": sid, "node_id": node_id, "target": target}
    dispatch_id = str(graph_node.get("dispatch_id") or node.get("dispatch_id") or "")
    reason = str(finding.get("unavailable_reason") or "pane_unavailable")
    clear_pane_lease(target, f"pane_unavailable_reroute:{reason}")
    clear_pane_assignment(target, f"pane_unavailable_reroute:{reason}")
    node.pop("assigned_to", None)
    node.pop("dispatch_id", None)
    node["dispatch_retry_reason"] = reason
    node["status"] = "worker_blocked"
    node["updated_at"] = utc_now()
    save_graph(graph_path, graph)
    dispatch_result = dispatch_ready_graph_nodes(sid, lease=dispatch) if dispatch else {"ok": True, "dispatch": "dry_apply_disabled"}
    return {
        "ok": bool(dispatch_result.get("ok")),
        "sid": sid,
        "node_id": node_id,
        "target": target,
        "released_dispatch_id": dispatch_id,
        "dispatch_result": dispatch_result,
    }


def dispatch_ready_graph_nodes(sid: str, lease: bool = True) -> dict:
    if no_dispatch_enabled():
        return {"ok": False, "reason": "no_dispatch_flag", "sprint_id": sid, "dispatched": [], "skipped": []}
    path = graph_path_for(sid)
    if not path.exists():
        return {"ok": False, "reason": "task_graph_missing", "path": str(path)}
    if load_graph is None or validate_graph is None:
        return {"ok": False, "reason": "graph_scheduler_unavailable"}
    graph = load_graph(path)
    try:
        import plan_validator  # type: ignore

        plan_guard = plan_validator.check_planner_graph_dispatchable(
            graph, sprints_dir=SPRINTS, sid=sid
        )
    except Exception as guard_exc:
        if str(os.environ.get("SOLAR_PLAN_VALIDATOR") or "").strip().lower() not in {"0", "false", "no", "off"}:
            detail = " ".join(str(guard_exc).split())[:300]
            return {
                "ok": False,
                "reason": "plan_validator_dispatch_refused",
                "errors": [
                    f"PLAN_VALIDATOR_UNCHECKABLE:{type(guard_exc).__name__}"
                    + (f":{detail}" if detail else "")
                ],
                "sprint_id": sid,
            }
        plan_guard = {"ok": True}
    if not plan_guard.get("ok"):
        return {
            "ok": False,
            "reason": "plan_validator_dispatch_refused",
            "errors": plan_guard.get("errors") or [],
            "sprint_id": sid,
        }
    validation = validate_graph(graph) if validate_graph else {"ok": False, "errors": ["graph_scheduler_unavailable"]}
    if not validation.get("ok"):
        return {"ok": False, "reason": "task_graph_invalid", "validation": validation}
    if graph_dispatch_ready is not None and graph_dispatch_node_evals is not None:
        try:
            eval_max_items = max(1, int(os.environ.get("SOLAR_AUTOPILOT_EVAL_MAX_ITEMS", "1") or "1"))
        except Exception:
            eval_max_items = 1
        evals = graph_dispatch_node_evals(str(path), dry_run=not lease, ttl=900, max_items=eval_max_items)
        ready = graph_dispatch_ready(str(path), dry_run=not lease, ttl=900)
        # Evaluator availability is more volatile than builder readiness: pane
        # cleanup/reconciliation performed while dispatching ready builder work
        # can free lab panes in the same scan. Do not leave handoff-backed
        # `reviewing` nodes stranded until the next monitor tick after one
        # transient `no_available_evaluator`; immediately retry a small eval
        # batch after ready-node reconciliation.
        eval_skipped = evals.get("skipped") if isinstance(evals, dict) else []
        skipped_reasons = {
            str(item.get("reason") or "")
            for item in eval_skipped
            if isinstance(item, dict)
        }
        eval_retry = {}
        if "no_available_evaluator" in skipped_reasons:
            eval_retry = graph_dispatch_node_evals(
                str(path),
                dry_run=not lease,
                ttl=900,
                max_items=eval_max_items,
            )
            if (eval_retry.get("dispatched") or []) and not (eval_retry.get("skipped") or []):
                evals = eval_retry
        return {
            "ok": bool(evals.get("ok")) and bool(ready.get("ok")),
            "evals": evals,
            "eval_retry": eval_retry,
            "ready": ready,
        }
    if enqueue_ready is None:
        return {"ok": False, "reason": "graph_dispatcher_unavailable"}
    max_parallel = 8
    try:
        if str(HARNESS_DIR / "lib") not in sys.path:
            sys.path.insert(0, str(HARNESS_DIR / "lib"))
        import concurrency_policy  # type: ignore

        max_parallel = int(concurrency_policy.effective_max_parallel(8, scope="graph"))
    except Exception:
        max_parallel = 8
    result = enqueue_ready(graph, str(path), graph_workers(), max_parallel=max_parallel, lease=lease, ttl=900)
    from graph_scheduler import save_graph  # imported late so older installs can still inspect
    save_graph(path, graph)
    return {"ok": result.get("ok"), "ready": result}


def instruction_for(status: dict, files: dict[str, bool]) -> str:
    sid = status.get("sprint_id") or status.get("id") or ""
    handoff = status.get("handoff_to", "")
    if handoff == "pm" and files["contract"] and not files["prd"]:
        return (
            f"请接手 {sid}：先做 PM 需求分析，不要直接派 Builder。读取 {sid}.contract.md，"
            f"输出 {sid}.prd.md，必须包含用户目标、范围边界、验收标准、风险、拆分建议。"
            "完成后把 status 更新为 phase=prd_ready handoff_to=planner target_role=planner。"
        )
    if handoff == "planner" and files["prd"] and planner_outputs_missing(files):
        instruction = (
            f"请接手 {sid}：读取 .prd.md 和 .contract.md，产出 {sid}.design.md、{sid}.plan.md 和 {sid}.task_graph.json。"
            "task_graph 必须通过 solar-harness graph-scheduler validate。不要问用户拍板；这是 P0 reliability 默认推进。"
        )
        # P5 G2b: the legacy pane-wake path does not flow through pm_dispatch
        # submit, so it appends the compile-policy block itself (env-gated
        # inside the helper; "" when SOLAR_PLAN_VALIDATOR is off).
        try:
            import plan_validator  # type: ignore

            policy_block = plan_validator.planner_compile_policy_block(SPRINTS, str(sid))
        except Exception:
            policy_block = ""
        if policy_block:
            instruction = f"{instruction}\n\n{policy_block}"
        return instruction
    if (
        handoff in ("builder", "builder_main", "builder_parallel", "builder-lab")
        and files["plan"]
        and files["task_graph"]
        and not files["handoff"]
    ):
        return (
            f"请接手 {sid}：读取 task_graph.json，并按 DAG/graph-dispatch 执行 ready nodes；"
            "禁止在缺少 DAG 时直接写 parent handoff。"
        )
    if handoff in ("evaluator", "reviewer") and files["handoff"] and not files["eval"]:
        return f"请评审 {sid}：读取 handoff/contract，产出 eval.md/eval.json。"
    return ""


def planner_outputs_missing(files: dict[str, bool]) -> bool:
    """Planner handoff remains active until architecture outputs are complete.

    Multi-task operator routing now owns planner execution capacity.  The old
    fixed-pane mental model only retriggered planner when `plan.md` was absent,
    which silently stalled architecture slices that were still missing
    `design.md` or `task_graph.json`.
    """
    return not files["design"] or not files["plan"] or not files["task_graph"]


def workflow_guard_route(sid: str) -> dict:
    if workflow_route is None:
        return {}
    try:
        return workflow_route(sid)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def normalize_status_to_workflow_route(sid: str, status: dict, route: dict) -> bool:
    role = str(route.get("route_role") or "")
    stage = str(route.get("stage") or "")
    if role == "none" and stage == "done":
        fields = ("passed", "completed", "done", "done")
    elif not role or role == "pm":
        return False
    else:
        planner_status = "drafting"
        if str(status.get("status") or "").lower() == "active" or status.get("epic_id") or str(status.get("dependency_policy") or "") == "activated_by_epic_dag":
            planner_status = "active"
        fields = {
            "planner": (planner_status, "prd_ready", "planner", "planner"),
            "builder_main": ("active", "planning_complete", "builder_main", "builder_main"),
            "builder": ("active", "planning_complete", "builder", "builder"),
            "evaluator": ("reviewing", "handoff_ready", "evaluator", "evaluator"),
        }.get(role)
        if not fields:
            return False
        if role in {"builder", "builder_main"}:
            try:
                import plan_validator  # type: ignore

                compile_verdict = plan_validator.compile_planner_graph(
                    SPRINTS,
                    sid,
                    config_dir=HARNESS / "config",
                    workflows_dir=HARNESS / "config" / "workflows",
                )
            except Exception as exc:
                detail = " ".join(str(exc).split())[:300]
                compile_verdict = {
                    "ok": False,
                    "errors": [
                        f"PLAN_VALIDATOR_UNCHECKABLE:{type(exc).__name__}"
                        + (f":{detail}" if detail else "")
                    ],
                }
            if not compile_verdict.get("ok"):
                append_event(
                    sid,
                    "plan_compile_failed",
                    "warn",
                    {"route_role": role, "stage": stage, "verdict": compile_verdict},
                )
                return False
    new_status, new_phase, handoff, target_role = fields
    planner_claim_cleared = False
    if role != "planner":
        for key in ("planner_dispatch_claim", "plan_compile_required"):
            if key in status:
                status.pop(key, None)
                planner_claim_cleared = True
    changed = planner_claim_cleared or any(
        str(status.get(k, "")) != v
        for k, v in {
            "status": new_status,
            "phase": new_phase,
            "handoff_to": handoff,
            "target_role": target_role,
        }.items()
    )
    if not changed:
        return False
    status.update(
        {
            "status": new_status,
            "phase": new_phase,
            "handoff_to": handoff,
            "target_role": target_role,
            "updated_at": utc_now(),
        }
    )
    hist = status.setdefault("history", [])
    if isinstance(hist, list):
        _append_status_history_once(
            status,
            "autopilot_workflow_route_normalized",
            route_role=role,
            stage=stage,
            reason=route.get("reason", ""),
        )
    save_json(SPRINTS / f"{sid}.status.json", status)
    append_event(
        sid,
        "autopilot_workflow_route_normalized",
        "info",
        {
            "route_role": role,
            "stage": stage,
            "reason": route.get("reason", ""),
            "planner_claim_cleared": planner_claim_cleared,
        },
    )
    return True


def inspect_sprints(epic_filter: str = "") -> list[dict]:
    _ensure_graph_status_caches()
    raw_findings = []
    for path in sorted(SPRINTS.glob("sprint-*.status.json")):
        status = load_json(path)
        sid = status.get("sprint_id") or status.get("id") or path.name.removesuffix(".status.json")
        if epic_filter and str(status.get("epic_id") or "") != epic_filter:
            continue
        files = sprint_files(sid)
        st = status.get("status", "")
        phase = status.get("phase", "")
        handoff = status.get("handoff_to", "")
        priority = status.get("priority", "")
        blocked_but_routable = str(st).lower() == "blocked" and str(phase).lower() in {
            "external_dependency_waiting",
            "epic_waiting_dependency",
        }
        if st not in ACTIVE_STATUSES and not blocked_but_routable:
            continue
        dep_ready, blocked_by = epic_child_dependency_ready(str(sid))
        if not dep_ready:
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "epic_child_dependency_blocked",
                    "severity": "warn",
                    "target": "",
                    "blocked_by": blocked_by,
                    "message": "Epic child sprint dependency is not satisfied; keep queued and do not dispatch.",
                }
            )
            continue

        route = workflow_guard_route(str(sid))
        if route.get("reason") == "external_prerequisite_blocked":
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "epic_child_dependency_blocked",
                    "severity": "warn",
                    "target": "",
                    "blocked_by": route.get("blocked_prerequisites", []),
                    "message": "Child task_graph prerequisite is not satisfied; keep queued and do not dispatch.",
                }
            )
            continue
        if route.get("ok") and not route.get("violations"):
            if normalize_status_to_workflow_route(str(sid), status, route):
                status = load_json(path)
                st = status.get("status", "")
                phase = status.get("phase", "")
                handoff = status.get("handoff_to", "")

        if files["contract"] and not files["prd"] and handoff in ("", "pm"):
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "ready_for_pm",
                    "severity": "info",
                    "target": pane_target_for_handoff("pm"),
                    "message": instruction_for({**status, "handoff_to": "pm"}, files),
                }
            )
        if priority == "P0" and files["contract"] and not files["prd"]:
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "missing_prd",
                    "severity": "warn",
                    "safe_default": "write_prd_or_escalate_to_codex_pm",
                    "message": "P0 has contract/evidence but no PRD.",
                }
            )
        if files["prd"] and handoff == "planner" and planner_outputs_missing(files):
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "ready_for_planner",
                    "severity": "info",
                    "target": pane_target_for_handoff(handoff),
                    "message": instruction_for(status, files),
                }
            )
        if files["plan"] and not files["task_graph"] and handoff in GRAPH_READY_HANDOFFS:
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "missing_task_graph",
                    "severity": "warn",
                    "target": pane_target_for_handoff("planner"),
                    "message": (
                        f"{sid} 已有 plan.md 但缺 task_graph.json。请补机器可执行 DAG，"
                        "并运行 graph-scheduler validate；未补前禁止粗派发给 builder。"
                    ),
                }
            )
            continue
        if files["plan"] and files["task_graph"] and handoff in (GRAPH_READY_HANDOFFS | GRAPH_EVAL_HANDOFFS):
            gs = graph_status(sid)
            if gs.get("parent_ready"):
                raw_findings.append(
                    {
                        "sid": sid,
                        "type": "graph_parent_ready",
                        "severity": "info",
                        "target": pane_target_for_handoff("evaluator"),
                        "message": f"{sid} DAG 全部 gate 已通过，请做 parent eval/closeout。",
                        "graph": gs,
                    }
                )
            elif gs.get("valid"):
                raw_findings.append(
                    {
                        "sid": sid,
                        "type": "graph_ready_nodes",
                        "severity": "info",
                        "target": "",
                        "message": (
                            f"{sid} task_graph valid；autopilot 将派发 ready DAG nodes "
                            "并处理 reviewing node evaluator。"
                        ),
                        "graph": gs,
                    }
                )
            else:
                raw_findings.append(
                    {
                        "sid": sid,
                        "type": "invalid_task_graph",
                        "severity": "warn",
                        "target": pane_target_for_handoff("planner"),
                        "message": f"{sid} task_graph.json 无效，请修复后再派发 builder。",
                        "graph": gs,
                    }
                )
        if files["plan"] and files["task_graph"] and handoff in ("builder", "builder_main", "builder_parallel", "builder-lab") and not files["handoff"]:
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "ready_for_builder",
                    "severity": "info",
                    "target": pane_target_for_handoff(handoff),
                    "message": instruction_for(status, files),
                }
            )
        if st in ("active", "approved", "reviewing") and phase and not files["plan"] and not files["handoff"] and handoff in ("builder", "builder_main", "builder_parallel", "builder-lab"):
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "active_without_handoff",
                    "severity": "warn",
                    "target": pane_target_for_handoff(handoff),
                    "message": instruction_for(status, files),
                }
            )
        if files["handoff"] and not files["task_graph"] and handoff in ("evaluator", "reviewer") and not files["eval"]:
            raw_findings.append(
                {
                    "sid": sid,
                    "type": "ready_for_evaluator",
                    "severity": "info",
                    "target": pane_target_for_handoff(handoff),
                    "message": instruction_for(status, files),
                }
            )
    p0 = [f for f in raw_findings if load_json(SPRINTS / f"{f.get('sid')}.status.json").get("priority") == "P0"]
    return p0 or raw_findings


def inspect_panes(state: dict, stall_seconds: int) -> list[dict]:
    findings = []
    now_epoch = time.time()
    for idx, role in enumerate(("pm", "planner", "builder", "evaluator")):
        target = f"{SESSION}:0.{idx}"
        tail = tmux_capture(target)
        h = tail_hash(tail)
        prev = state["pane"].get(target, {})
        changed = h != prev.get("hash")
        unchanged_for = 0 if changed else int(now_epoch - float(prev.get("seen_at", now_epoch)))
        if changed:
            state["pane"][target] = {"hash": h, "seen_at": now_epoch, "role": role}
        if role == "evaluator" and pane_survey_blocked(tail):
            graph_node = assigned_eval_graph_node_for_pane(target)
            lease = pane_lease(target)
            if graph_node or lease:
                findings.append(
                    {
                        "sid": (graph_node or {}).get("sid") or str(lease.get("sid") or ""),
                        "type": "evaluator_survey_blocked",
                        "severity": "warn",
                        "target": target,
                        "role": role,
                        "graph_node": graph_node,
                        "lease": lease,
                        "message": "Evaluator pane is blocked by Claude survey prompt while an active eval lease/assignment exists; dismiss the survey before resuming eval.",
                    }
                )
                continue
        if ASK_BOSS_RE.search(tail):
            # PM pane is the user's intake surface. If it is stuck in Claude
            # Rewind/interrupt UI or contains old prompt residue, do not send
            # another auto-reply into the same pane. Record the signal only.
            if role == "pm" and ("Rewind" in tail or "Interrupted · What should Claude do instead?" in tail):
                findings.append(
                    {
                        "sid": "",
                        "type": "pm_pane_interrupt_residue",
                        "severity": "warn",
                        "target": target,
                        "role": role,
                        "message": "PM pane contains interrupt/Rewind residue; do not auto-dispatch into user intake pane.",
                    }
                )
                continue
            sid = candidate_sid_for_role(role)
            if sid:
                findings.append(
                    {
                        "sid": sid,
                        "type": "pane_asks_boss",
                        "severity": "warn",
                        "target": target,
                        "role": role,
                        "message": "不要等待用户拍板；按当前 sprint 合约和 safe default 继续推进。若需要交接，请写明 artifact 并更新 status.json。",
                    }
                )
        if COMPACTING_RE.search(tail) and unchanged_for >= stall_seconds:
            sid = candidate_sid_for_role(role)
            if sid:
                findings.append(
                    {
                        "sid": sid,
                        "type": "pane_compacting_stall",
                        "severity": "warn",
                        "target": target,
                        "role": role,
                        "unchanged_for_sec": unchanged_for,
                        "message": f"{role} pane compacting/stalled; re-wake sprint {sid} to continue missing artifact work.",
                    }
                )
        if pane_safe_continue_prompt(tail) and not PANE_BOTTOM_BUSY_RE.search("\n".join(tail.splitlines()[-12:])):
            graph_node = assigned_graph_node_for_pane(target)
            if graph_node:
                findings.append(
                    {
                        "sid": graph_node["sid"],
                        "type": "pane_safe_continue_prompt",
                        "severity": "info",
                        "target": target,
                        "role": role,
                        "graph_node": graph_node,
                        "message": "pane has safe continue prompt residue; submit Enter to resume assigned graph node.",
                    }
                )
                continue
        if pane_permissions_prompt_blocked(tail):
            graph_node = assigned_graph_node_for_pane(target)
            if graph_node:
                findings.append(
                    {
                        "sid": graph_node["sid"],
                        "type": "pane_permissions_prompt_blocked",
                        "severity": "warn",
                        "target": target,
                        "role": role,
                        "graph_node": graph_node,
                        "message": "pane 被 permissions prompt 挡住；发送 Shift+Tab + Enter 恢复当前已派发 DAG node。",
                    }
                )
                continue
        if pane_at_prompt(tail) and not pane_is_busy(target):
            graph_node = assigned_graph_node_for_pane(target)
            if graph_node:
                findings.append(
                    {
                        "sid": graph_node["sid"],
                        "type": "graph_node_idle_assigned",
                        "severity": "warn",
                        "target": target,
                        "role": role,
                        "graph_node": graph_node,
                        "message": (
                            f"继续执行 DAG node {graph_node['node_id']}，不要等待用户输入继续。"
                            f"读取并完成 {graph_node['dispatch_file']}；完成后写 handoff 并标记 reviewing。"
                        ),
                    }
                )
                continue
            sid = candidate_sid_for_role(role)
            if sid:
                status = load_json(SPRINTS / f"{sid}.status.json")
                files = sprint_files(sid)
                if files.get("task_graph"):
                    continue
                msg = instruction_for(status, files)
                if msg:
                    findings.append(
                        {
                            "sid": sid,
                            "type": "pane_idle_with_pending_artifact",
                            "severity": "info",
                            "target": target,
                            "role": role,
                            "message": msg,
                        }
                    )
    # Lab builders also receive DAG nodes. They are not covered by the fixed
    # main-screen role loop above, so resume assigned lab nodes explicitly when
    # the pane returns to prompt without a node handoff.
    for target in discover_worker_panes():
        if not target.startswith("solar-harness-lab:"):
            continue
        tail = tmux_capture(target)
        graph_node = assigned_graph_node_for_pane(target)
        if graph_node and PANE_UNAVAILABLE_RE.search("\n".join(tail.splitlines()[-40:])):
            findings.append(
                {
                    "sid": graph_node["sid"],
                    "type": "graph_node_unavailable_assigned",
                    "severity": "warn",
                    "target": target,
                    "role": "lab-builder",
                    "graph_node": graph_node,
                    "unavailable_reason": "rate_limit_or_api_error",
                    "message": "Assigned builder pane is alive but blocked by provider usage limit/API error; release the stale dispatch and requeue the graph node.",
                }
            )
            continue
        if graph_node and pane_permissions_prompt_blocked(tail):
            findings.append(
                {
                    "sid": graph_node["sid"],
                    "type": "pane_permissions_prompt_blocked",
                    "severity": "warn",
                    "target": target,
                    "role": "lab-builder",
                    "graph_node": graph_node,
                    "message": "pane 被 permissions prompt 挡住；发送 Shift+Tab + Enter 恢复当前已派发 DAG node。",
                }
            )
            continue
        if not pane_at_prompt(tail) or pane_is_busy(target):
            continue
        if not graph_node:
            continue
        findings.append(
            {
                "sid": graph_node["sid"],
                "type": "graph_node_idle_assigned",
                "severity": "warn",
                "target": target,
                "role": "lab-builder",
                "graph_node": graph_node,
                "message": (
                    f"继续执行 DAG node {graph_node['node_id']}，不要等待用户输入继续。"
                    f"读取并完成 {graph_node['dispatch_file']}；完成后写 handoff 并标记 reviewing。"
                ),
            }
        )
    return findings


def inspect_knowledge_context(state: dict) -> list[dict]:
    """Detect default-context regressions and run the KB probe automatically.

    The user-facing failure mode is a pane answering with sqlite-only lookup or
    timing out on `solar-harness context inject`. Both mean the default
    knowledge path may be broken even if the underlying pages exist.
    """
    findings: list[dict] = []
    force_probe = False
    reasons: list[str] = []
    for idx, role in enumerate(("pm", "planner", "builder", "evaluator")):
        target = f"{SESSION}:0.{idx}"
        tail = tmux_capture(target)
        has_sqlite = bool(SQLITE_ONLY_RE.search(tail))
        has_context = bool(CONTEXT_INJECT_RE.search(tail))
        if has_sqlite and not has_context:
            force_probe = True
            reasons.append(f"{target}:sqlite_only")
            findings.append(
                {
                    "sid": "",
                    "type": "knowledge_context_sqlite_only",
                    "severity": "warn",
                    "target": target,
                    "role": role,
                    "message": "检测到 pane 使用 sqlite3 ~/.solar/solar.db 且未看到 solar-harness context inject；自动运行 KB probe。",
                }
            )
        if CONTEXT_TIMEOUT_RE.search(tail):
            force_probe = True
            reasons.append(f"{target}:context_timeout")
            findings.append(
                {
                    "sid": "",
                    "type": "knowledge_context_timeout",
                    "severity": "warn",
                    "target": target,
                    "role": role,
                    "message": "检测到 context inject timeout；自动运行 KB probe 并记录健康状态。",
                }
            )
    reason = ",".join(reasons) if reasons else "periodic"
    last_probe = load_json(KB_PROBE_HEALTH)
    if not force_probe and last_probe and (last_probe.get("status") == "error"):
        age = time.time() - float(last_probe.get("checked_at_epoch", 0) or 0)
        if age >= KB_PROBE_TRIGGER_COOLDOWN_SEC:
            force_probe = True
            reasons.append("previous_probe_failed")
            reason = ",".join(reasons) if reasons else "previous_probe_failed"
    probe = run_kb_probe(reason, force=force_probe)
    if probe.get("ok"):
        state["knowledge_probe"] = {
            "status": "ok",
            "checked_at": probe.get("checked_at"),
            "probes_passed": probe.get("probes_passed"),
            "probes_failed": probe.get("probes_failed"),
            "reason": probe.get("reason"),
        }
    else:
        probe_status = probe.get("status") or "error"
        probe_severity = "warn" if probe_status == "warn" else "error"
        if probe_status == "warn":
            probe_message = (
                "KB probe 显示默认知识链可达，但覆盖不完整；先不要把它当成 runtime 故障。"
                "请检查 state/knowledge-probe-health.json 与 tests/test-knowledge-probe-coverage.sh，补知识页或索引。"
            )
        else:
            probe_message = (
                "KB probe failed；默认知识路径可能不可用。先不要只查 sqlite，"
                "请检查 state/knowledge-probe-health.json 和 tests/test-knowledge-probe-coverage.sh 输出。"
            )
        findings.append(
            {
                "sid": "",
                "type": "knowledge_probe_failed",
                "severity": probe_severity,
                "target": f"{SESSION}:0.0",
                "role": "pm",
                "message": probe_message,
                "probe": probe,
            }
        )
        state["knowledge_probe"] = {
            "status": probe_status,
            "checked_at": probe.get("checked_at"),
            "probes_passed": probe.get("probes_passed"),
            "probes_failed": probe.get("probes_failed"),
            "reason": probe.get("reason"),
            "failure_class": probe.get("failure_class", ""),
        }
    return findings


def inspect_model_registry(state: dict) -> list[dict]:
    """Periodically verify model routing has not drifted back to hardcoding."""
    probe = run_model_registry_doctor("periodic", force=False)
    state["model_registry_doctor"] = {
        "status": "ok" if probe.get("ok") else "error",
        "checked_at": probe.get("checked_at"),
        "reason": probe.get("reason"),
        "skipped": probe.get("skipped", ""),
    }
    if probe.get("ok"):
        return []
    return [
        {
            "sid": "",
            "type": "model_registry_doctor_failed",
            "severity": "error",
            "target": "",
            "role": "autopilot",
            "message": "models doctor failed；模型路由单一事实源可能漂移。检查 state/model-registry-doctor-health.json。",
            "probe": probe,
        }
    ]


def should_act(state: dict, finding: dict, cooldown: int) -> bool:
    key = f"{finding.get('sid','')}:{finding.get('type','')}:{finding.get('target','')}"
    last = float(state["actions"].get(key, {}).get("at", 0))
    effective_cooldown = _role_handoff_action_cooldown(finding, cooldown)
    return (time.time() - last) >= effective_cooldown


def mark_action(state: dict, finding: dict, result: dict) -> None:
    key = f"{finding.get('sid','')}:{finding.get('type','')}:{finding.get('target','')}"
    state["actions"][key] = {"at": time.time(), "ts": utc_now(), "result": result}
    target = finding.get("target", "")
    if target and not result.get("role_pool_dispatch") and (result.get("dispatched") or result.get("dispatched_from_queue")):
        state["target_actions"][target] = {"at": time.time(), "ts": utc_now(), "result": result}
        update_work_pane_title(target, result.get("sid") or finding.get("sid", ""), result.get("action") or finding.get("type", "dispatch"))


def target_recently_dispatched(state: dict, target: str, cooldown: int) -> bool:
    if not target:
        return False
    last = float(state.get("target_actions", {}).get(target, {}).get("at", 0))
    return (time.time() - last) < cooldown


def maybe_reroute_builder_target(item: dict, sid: str) -> str:
    target = str(item.get("target") or "")
    if target != f"{SESSION}:0.2":
        return target
    if str(item.get("type") or "") not in BUILDER_QUEUE_FINDINGS:
        return target
    rerouted = pane_target_for_handoff("builder_main")
    if not rerouted or rerouted == target:
        return target
    item["target"] = rerouted
    append_event(
        sid,
        "autopilot_builder_target_rerouted",
        "info",
        {"from": target, "to": rerouted, "type": item.get("type")},
    )
    return rerouted


def apply_findings(findings: list[dict], dispatch: bool, state: dict, cooldown: int) -> list[dict]:
    actions = []
    used_targets = set()
    try:
        max_budgeted_actions = max(1, int(os.environ.get("SOLAR_AUTOPILOT_MAX_ACTIONS", "6") or "6"))
    except Exception:
        max_budgeted_actions = 6
    try:
        max_graph_actions = max(1, int(os.environ.get("SOLAR_AUTOPILOT_MAX_GRAPH_ACTIONS", "3") or "3"))
    except Exception:
        max_graph_actions = 3
    budgeted_actions = {
        "graph_ready_nodes",
        "graph_node_idle_assigned",
        "evaluator_survey_blocked",
        "pane_permissions_prompt_blocked",
        "graph_node_unavailable_assigned",
        "graph_parent_ready",
        "deepresearch_quality_gate_repair",
        "missing_task_graph",
        "invalid_task_graph",
        "ready_for_pm",
        "ready_for_planner",
        "ready_for_builder",
        "ready_for_evaluator",
        "active_without_handoff",
        "pane_compacting_stall",
        "pane_idle_with_pending_artifact",
        "pane_asks_boss",
        "pane_safe_continue_prompt",
    }
    graph_action_types = {
        "graph_ready_nodes",
        "evaluator_survey_blocked",
        "graph_node_unavailable_assigned",
        "deepresearch_quality_gate_repair",
    }
    budget_used = 0
    graph_budget_used = 0
    for f in findings:
        sid = f.get("sid", "")
        ftype = f.get("type", "")
        role_pool_handoff = finding_uses_operator_role_pool(ftype)
        target = f.get("target", "") if role_pool_handoff else maybe_reroute_builder_target(f, sid)
        if is_telemetry_only_finding(f):
            append_event(sid, f"autopilot_{ftype}", f.get("severity", "warn"), f)
            result = {
                "sid": sid,
                "action": ftype,
                "target": target,
                "dispatched": False,
                "recorded_only": True,
            }
            mark_action(state, f, result)
            actions.append(result)
            continue
        if target and target in used_targets and ftype != "pane_permissions_prompt_blocked" and not role_pool_handoff:
            actions.append({"sid": sid, "action": ftype, "skipped": "target_already_used_this_scan", "target": target})
            continue
        if not should_act(state, f, cooldown):
            actions.append({"sid": sid, "action": ftype, "skipped": "cooldown", "target": target})
            continue
        if not role_pool_handoff and target_recently_dispatched(state, target, cooldown) and ftype != "pane_permissions_prompt_blocked":
            actions.append({"sid": sid, "action": ftype, "skipped": "target_cooldown", "target": target})
            continue
        is_budgeted = ftype in budgeted_actions
        is_graph_action = ftype in graph_action_types
        if is_budgeted and budget_used >= max_budgeted_actions:
            actions.append({"sid": sid, "action": ftype, "skipped": "autopilot_action_budget", "target": target})
            continue
        if is_graph_action and graph_budget_used >= max_graph_actions:
            actions.append({"sid": sid, "action": ftype, "skipped": "autopilot_graph_action_budget", "target": target})
            continue
        if is_budgeted:
            budget_used += 1
        if is_graph_action:
            graph_budget_used += 1
        if dispatch and target and not role_pool_handoff:
            allowed, gate_reason, gate_detail = pane_gate(target, sid)
            if not allowed:
                enqueue_action(f, gate_reason, gate_detail)
                append_event(sid, "autopilot_dispatch_queued_pane_occupied", "warn", {"target": target, "type": ftype, "reason": gate_reason, "detail": gate_detail})
                result = {"sid": sid, "action": ftype, "queued": True, "reason": gate_reason, "target": target}
                mark_action(state, f, result)
                actions.append(result)
                continue
        # See retry_queue(): role-pool handoffs must be routed by coordinator,
        # not pre-blocked on a single fixed pane snapshot.
        if dispatch and target and not role_pool_handoff and pane_is_busy(target):
            append_event(sid, "autopilot_dispatch_deferred_pane_busy", "warn", {"target": target, "type": ftype})
            enqueue_action(f, "pane_busy", {})
            result = {"sid": sid, "action": ftype, "skipped": "pane_busy", "target": target}
            mark_action(state, f, result)
            actions.append(result)
            continue
        if dispatch and target and not role_pool_handoff and ftype not in {"pane_safe_continue_prompt", "evaluator_survey_blocked", "pane_permissions_prompt_blocked"}:
            clear_current_prompt(target)
        if ftype in ("graph_ready_nodes",):
            result = dispatch_ready_graph_nodes(sid, lease=dispatch)
            append_event(sid, "autopilot_graph_enqueue_ready", "info" if result.get("ok") else "warn", result)
            mark_action(state, f, {"sid": sid, "action": ftype, **result})
            actions.append({"sid": sid, "action": ftype, **result})
        elif ftype == "epic_ready_children":
            # This is a local metadata transition, not a pane dispatch. Use the
            # library entrypoint so tests and alternate HARNESS_DIR installs do
            # not accidentally activate the user's real sprint directory.
            cmd = [sys.executable, str(HARNESS / "lib" / "epic_decomposer.py"), "activate-ready", sid, "--max", "2", "--json"]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {"stdout": proc.stdout[-2000:]}
                result = {
                    "sid": sid,
                    "action": ftype,
                    "ok": proc.returncode == 0,
                    "returncode": proc.returncode,
                    "stderr": proc.stderr[-2000:],
                    **payload,
                }
            except Exception as exc:
                result = {"sid": sid, "action": ftype, "ok": False, "error": str(exc)}
            append_event(sid, "autopilot_epic_activate_ready", "info" if result.get("ok") else "warn", result)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "graph_node_idle_assigned":
            append_event(sid, "autopilot_graph_node_idle_resume", "warn", f.get("graph_node", {}))
            sent = False
            if dispatch and target and f.get("message"):
                sent = tmux_send(target, f["message"])
            result = {"sid": sid, "action": ftype, "target": target, "dispatched": sent, "graph_node": f.get("graph_node", {})}
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "evaluator_survey_blocked":
            append_event(sid, "autopilot_evaluator_survey_blocked", "warn", {"target": target, "lease": f.get("lease", {}), "graph_node": f.get("graph_node", {})})
            sent = False
            reroute = {"ok": False, "reason": "dispatch_disabled_or_missing_graph"}
            if dispatch:
                reroute = reroute_survey_blocked_evaluator(f, dispatch)
                sent = bool(reroute.get("ok"))
            if not sent and dispatch and target:
                sent = dismiss_survey_prompt(target)
            if dispatch and target:
                pass
            result = {
                "sid": sid,
                "action": ftype,
                "target": target,
                "dispatched": sent,
                "lease": f.get("lease", {}),
                "graph_node": f.get("graph_node", {}),
                "reroute": reroute,
            }
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "pane_permissions_prompt_blocked":
            append_event(
                sid,
                "autopilot_pane_permissions_prompt_blocked",
                "warn",
                {"target": target, "graph_node": f.get("graph_node", {})},
            )
            sent = False
            if dispatch and target:
                sent = dismiss_permissions_prompt(target)
            result = {
                "sid": sid,
                "action": ftype,
                "target": target,
                "dispatched": sent,
                "graph_node": f.get("graph_node", {}),
            }
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "graph_node_unavailable_assigned":
            append_event(
                sid,
                "autopilot_graph_node_unavailable_assigned",
                "warn",
                {
                    "target": target,
                    "graph_node": f.get("graph_node", {}),
                    "unavailable_reason": f.get("unavailable_reason", ""),
                },
            )
            recovered = {"ok": False, "reason": "dispatch_disabled_or_missing_graph"}
            if dispatch:
                recovered = recover_unavailable_graph_node(f, dispatch)
            result = {
                "sid": sid,
                "action": ftype,
                "target": target,
                "dispatched": bool(recovered.get("ok")),
                "graph_node": f.get("graph_node", {}),
                "recovered": recovered,
            }
            if result["dispatched"] and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "epic_child_dependency_blocked":
            status_path = SPRINTS / f"{sid}.status.json"
            status = load_json(status_path)
            if sprint_has_terminal_evidence(sid):
                append_event(
                    sid,
                    "autopilot_epic_child_dependency_blocked_skipped_terminal",
                    "info",
                    {"blocked_by": f.get("blocked_by", [])},
                )
                result = {
                    "sid": sid,
                    "action": ftype,
                    "queued": False,
                    "skipped": True,
                    "reason": "terminal_evidence_present",
                    "blocked_by": f.get("blocked_by", []),
                }
                mark_action(state, f, result)
                actions.append(result)
                continue
            status.update({
                "status": "queued",
                "phase": "epic_waiting_dependency",
                "handoff_to": "",
                "target_role": "",
                "updated_at": utc_now(),
            })
            hist = status.setdefault("history", [])
            if isinstance(hist, list):
                hist.append({
                    "ts": utc_now(),
                    "event": "autopilot_epic_child_dependency_blocked",
                    "by": "solar-autopilot",
                    "note": "Dependency not satisfied; dispatch suppressed.",
                    "blocked_by": f.get("blocked_by", []),
                })
            save_json(status_path, status)
            graph_updated = set_epic_child_node_status(sid, "pending")
            append_event(sid, "autopilot_epic_child_dependency_blocked", "warn", {"blocked_by": f.get("blocked_by", [])})
            result = {
                "sid": sid,
                "action": ftype,
                "queued": True,
                "blocked_by": f.get("blocked_by", []),
                "parent_graph_updated": graph_updated,
            }
            mark_action(state, f, result)
            actions.append(result)
        elif ftype in ("graph_parent_ready",):
            append_event(sid, "autopilot_graph_parent_ready", "info", f.get("graph", {}))
            sent = False
            if dispatch and sid:
                sent = wake_sid(sid)
            result = {"sid": sid, "action": ftype, "target": f.get("target", ""), "dispatched": sent}
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "deepresearch_quality_gate_repair":
            graph_path = Path(f.get("graph_path") or graph_path_for(sid))
            node_id = str(f.get("node_id") or "")
            result = {
                "sid": sid,
                "action": ftype,
                "node_id": node_id,
                "target": "",
                "queued": False,
                "dispatched": False,
            }
            try:
                if not graph_path.exists() or not node_id:
                    raise RuntimeError("missing_graph_or_node")
                graph = load_graph(graph_path) if load_graph else load_json(graph_path)
                target_node = next(
                    (
                        item
                        for item in (graph.get("nodes", []) or [])
                        if isinstance(item, dict) and str(item.get("id") or "") == node_id
                    ),
                    None,
                )
                raw_status = str((target_node or {}).get("status") or "").strip().lower()
                try:
                    current_status = str(
                        node_status(graph, node_id) if node_status else raw_status
                    ).strip().lower()
                except Exception:
                    current_status = raw_status
                if "needs_human_review" in {current_status, raw_status}:
                    result.update(
                        {
                            "ok": True,
                            "reopened": False,
                            "skipped": "needs_human_review_requires_explicit_resume",
                        }
                    )
                    append_event(
                        sid,
                        "autopilot_deepresearch_quality_gate_repair_deferred",
                        "info",
                        result,
                    )
                    mark_action(state, f, result)
                    actions.append(result)
                    continue
                repaired = False
                for node in graph.get("nodes", []) or []:
                    if not isinstance(node, dict) or str(node.get("id") or "") != node_id:
                        continue
                    node["status"] = "reviewing"
                    node["quality_gate_repair_requested_at"] = utc_now()
                    node["quality_gate_repair_reason"] = f.get("gate_status", "unknown")
                    node.pop("eval_assigned_to", None)
                    node.pop("eval_dispatch_id", None)
                    node.pop("eval_dispatched_at", None)
                    node.pop("research_quality_gate", None)
                    repaired = True
                    break
                if not repaired:
                    raise RuntimeError("node_not_found")
                node_results = graph.get("node_results") if isinstance(graph.get("node_results"), dict) else {}
                if node_id in node_results and isinstance(node_results[node_id], dict):
                    node_results[node_id]["status"] = "reviewing"
                    node_results[node_id]["gate_status"] = "reviewing"
                    node_results[node_id]["note"] = "autopilot reopened DeepResearch quality gate repair"
                graph["node_results"] = node_results
                if save_graph:
                    save_graph(graph_path, graph)
                else:
                    save_json(graph_path, graph)
                dispatch_result = dispatch_ready_graph_nodes(sid, lease=dispatch) if dispatch else {"ok": True, "dispatch": "dry_apply_disabled"}
                result.update({"ok": bool(dispatch_result.get("ok")), "reopened": True, "dispatch_result": dispatch_result})
                result["dispatched"] = bool((dispatch_result.get("evals") or {}).get("dispatched"))
                append_event(sid, "autopilot_deepresearch_quality_gate_repair", "warn", result)
            except Exception as exc:
                result.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                append_event(sid, "autopilot_deepresearch_quality_gate_repair_failed", "error", result)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype in ("missing_task_graph", "invalid_task_graph"):
            append_event(sid, f"autopilot_{ftype}", "warn", f.get("graph", {}))
            sent = False
            if dispatch and sid:
                sent = wake_sid(sid)
            elif dispatch and f.get("message") and f.get("target"):
                sent = tmux_send(f["target"], f["message"])
            result = {"sid": sid, "action": ftype, "target": f.get("target", ""), "dispatched": sent}
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype in ("ready_for_pm", "ready_for_planner", "ready_for_builder", "ready_for_evaluator", "active_without_handoff", "pane_compacting_stall", "pane_idle_with_pending_artifact"):
            status_path = SPRINTS / f"{sid}.status.json"
            status = load_json(status_path)
            status_changed = False
            if ftype == "ready_for_pm":
                desired = {
                    "status": status.get("status") or "drafting",
                    "phase": "spec",
                    "handoff_to": "pm",
                    "target_role": "pm",
                }
                for key, value in desired.items():
                    if status.get(key) != value:
                        status[key] = value
                        status_changed = True
            elif ftype == "ready_for_planner":
                desired = {"handoff_to": "planner", "target_role": "planner"}
                current_phase = str(status.get("phase") or "")
                if not current_phase:
                    desired["phase"] = "prd_ready"
                is_epic_child = bool(status.get("epic_id")) or str(status.get("dependency_policy") or "") == "activated_by_epic_dag"
                if is_epic_child and str(status.get("status") or "").lower() == "drafting":
                    desired["status"] = "active"
                for key, value in desired.items():
                    if status.get(key) != value:
                        status[key] = value
                        status_changed = True
            if _append_status_history_once(status, f"autopilot_{ftype}", str(f.get("message", ""))):
                status_changed = True
            if dispatch and role_pool_handoff and role_for_handoff_finding(ftype) == "planner":
                if _transition_planner_dispatch_claim(status, "submitting"):
                    status_changed = True
            if status_changed:
                status["updated_at"] = utc_now()
                save_json(status_path, status)
            append_event(sid, f"autopilot_{ftype}", f.get("severity", "info"), {"target": f.get("target", "")})
            sent = False
            role_dispatch_detail: dict = {}
            if dispatch and sid and role_pool_handoff:
                live_task = _live_pm_task_for_sprint_role(sid, role_for_handoff_finding(ftype))
                if live_task is not None:
                    if role_for_handoff_finding(ftype) == "planner":
                        _transition_planner_dispatch_claim(
                            status,
                            "submitted",
                            {
                                "task_id": str(live_task.get("task_id") or ""),
                                "pm_status": str(live_task.get("status") or ""),
                            },
                        )
                        status["updated_at"] = utc_now()
                        save_json(status_path, status)
                    result = {
                        "sid": sid,
                        "action": ftype,
                        "skipped": "live_pm_task_exists",
                        "target": f.get("target", ""),
                        "task_id": str(live_task.get("task_id") or ""),
                        "pm_status": str(live_task.get("status") or ""),
                    }
                    mark_action(state, f, result)
                    actions.append(result)
                    continue
                sent, role_dispatch_detail = dispatch_role_handoff(sid, ftype)
                if not sent:
                    if role_for_handoff_finding(ftype) == "planner":
                        _transition_planner_dispatch_claim(status, "failed", role_dispatch_detail)
                        status["updated_at"] = utc_now()
                        save_json(status_path, status)
                    append_event(sid, "autopilot_role_pool_dispatch_failed", "warn", {"target": target, "type": ftype, **role_dispatch_detail})
                    enqueue_action(f, "role_pool_unavailable", role_dispatch_detail)
                    result = {
                        "sid": sid,
                        "action": ftype,
                        "queued": True,
                        "reason": "role_pool_unavailable",
                        "target": target,
                        "role_pool_dispatch": role_dispatch_detail,
                    }
                    mark_action(state, f, result)
                    actions.append(result)
                    continue
                if role_for_handoff_finding(ftype) == "planner":
                    _transition_planner_dispatch_claim(status, "submitted", role_dispatch_detail)
                    status["updated_at"] = utc_now()
                    save_json(status_path, status)
            elif dispatch and sid:
                sent = wake_sid(sid)
            elif dispatch and f.get("message") and f.get("target"):
                sent = tmux_send(f["target"], f["message"])
            result = {"sid": sid, "action": ftype, "dispatched": sent, "target": f.get("target", "")}
            if role_pool_handoff:
                result["role_pool_dispatch"] = role_dispatch_detail or {"fallback": "wake_sid"}
            if sent and target and not role_pool_handoff:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "pane_asks_boss":
            append_event("", "autopilot_detected_boss_question", "warn", f)
            sent = False
            if f.get("role") == "pm" or f.get("target") == f"{SESSION}:0.0":
                sent = False
            elif dispatch and sid:
                sent = wake_sid(sid)
            elif dispatch and f.get("target"):
                sent = tmux_send(f["target"], f.get("message", "不要等待用户拍板；按 safe default 继续。"))
            result = {"sid": sid, "action": ftype, "target": f.get("target", ""), "dispatched": sent}
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "pm_pane_interrupt_residue":
            append_event("", "autopilot_pm_pane_interrupt_residue", "warn", f)
            result = {"sid": sid, "action": ftype, "target": f.get("target", ""), "dispatched": False, "recorded_only": True}
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "pane_safe_continue_prompt":
            sent = False
            role_ok = pane_title_matches_role(f.get("target", ""), f.get("role", ""))
            if dispatch and f.get("target") and role_ok:
                try:
                    sent = subprocess.run(["tmux", "send-keys", "-t", f["target"], "Enter"], timeout=2).returncode == 0
                except Exception:
                    sent = False
            append_event(f.get("sid", ""), "autopilot_submitted_safe_continue_prompt", "info" if sent else "warn", f)
            result = {"sid": sid, "action": ftype, "target": f.get("target", ""), "dispatched": sent}
            if not role_ok:
                result["skipped"] = "role_mismatch"
            if sent and target:
                used_targets.add(target)
            mark_action(state, f, result)
            actions.append(result)
        elif ftype == "missing_prd":
            append_event(sid, "autopilot_missing_prd", "warn", f)
            result = {"sid": sid, "action": ftype, "requires_codex_pm": True}
            mark_action(state, f, result)
            actions.append(result)
        elif ftype in TELEMETRY_ONLY_FINDINGS:
            append_event("", f"autopilot_{ftype}", f.get("severity", "warn"), f)
            # Probe failures are telemetry, not worker assignments. Sending a
            # remediation prompt to a live pane can leave stale text in the TUI
            # and block the next real dispatch. Keep the signal in events/state.
            result = {"sid": sid, "action": ftype, "target": f.get("target", ""), "dispatched": False, "recorded_only": True}
            mark_action(state, f, result)
            actions.append(result)
    return actions


def acquire_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            old = int(LOCK.read_text().strip() or "0")
            subprocess.run(["kill", "-0", str(old)], capture_output=True, timeout=1, check=True)
            return False
        except Exception:
            pass
    LOCK.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    try:
        if LOCK.exists() and LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()
    except Exception:
        pass


def reconcile_pm_inbox() -> dict:
    cmd = [
        sys.executable,
        str(HARNESS / "tools" / "pm_dispatch.py"),
        "reconcile",
        "--max-age-minutes",
        "30",
        "--apply",
        "--json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {"stdout": proc.stdout[-2000:]}
        return {"action": "pm_inbox_reconcile", "ok": proc.returncode == 0, **payload}
    except Exception as exc:
        return {"action": "pm_inbox_reconcile", "ok": False, "error": str(exc)}


def drain_builder_ready_backlog() -> dict:
    """Submit latent builder-ready DAG nodes into the PM builder pool."""
    cmd = [
        sys.executable,
        str(HARNESS / "tools" / "pm_dispatch.py"),
        "drain-builder-ready",
        "--json",
    ]
    env = os.environ.copy()
    env["HARNESS_DIR"] = str(HARNESS)
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    env["SOLAR_PM_DISPATCH_BACKPRESSURE_NO_RECORD"] = "1"
    timeout = int(os.environ.get("SOLAR_BUILDER_READY_DRAIN_TIMEOUT_SEC", "120"))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {"stdout": proc.stdout[-2000:]}
        ok = proc.returncode == 0 or bool(payload.get("backpressure"))
        return {"action": "builder_ready_drain", "ok": ok, "returncode": proc.returncode, **payload}
    except subprocess.TimeoutExpired:
        return {"action": "builder_ready_drain", "ok": False, "reason": "timeout", "timeout_sec": timeout}
    except Exception as exc:
        return {"action": "builder_ready_drain", "ok": False, "error": str(exc)}


def scan_once(args: argparse.Namespace, state: dict) -> dict:
    epic_filter = str(getattr(args, "epic", "") or "")
    reconcile_action = reconcile_pm_inbox() if args.apply else {}
    queue_actions = retry_queue(state, args.dispatch, args.cooldown, epic_filter=epic_filter) if args.apply else []
    if epic_filter:
        findings = (
            inspect_epics()
            + inspect_epic_child_state_drift()
            + inspect_sprints(epic_filter=epic_filter)
            + inspect_deepresearch_quality_gates(epic_filter=epic_filter)
        )
    else:
        findings = (
            inspect_epics()
            + inspect_epic_child_state_drift()
            + inspect_sprints()
            + inspect_deepresearch_quality_gates()
            + inspect_panes(state, args.stall_seconds)
            + inspect_knowledge_context(state)
            + inspect_model_registry(state)
        )
    findings_before_epic_filter = len(findings)
    if epic_filter:
        findings = filter_findings_by_epic(findings, epic_filter)
    actions = apply_findings(findings, args.dispatch, state, args.cooldown) if args.apply else []
    builder_ready_drain = drain_builder_ready_backlog() if args.apply and args.dispatch else {}
    idle_title_actions = update_idle_pane_titles(state) if args.apply else []
    action_log = ([reconcile_action] if reconcile_action else []) + queue_actions + actions
    if builder_ready_drain:
        action_log.append(builder_ready_drain)
    if idle_title_actions:
        action_log.append({"action": "idle_titles_updated", "panes": idle_title_actions, "dispatched": False})
    payload = {
        "ok": True,
        "apply": args.apply,
        "dispatch": args.dispatch,
        "loop": args.loop,
        "epic_filter": epic_filter,
        "findings_before_epic_filter": findings_before_epic_filter,
        "findings": findings,
        "actions": action_log,
        "queue_actions": queue_actions,
        "queue_depth": len(load_queue()),
        "state_path": str(STATE),
    }
    save_state(state)
    return payload


def epic_status_matrix(epic_id: str = "", output_json: bool = False) -> int:
    """Print epic child sprint state matrix for operator-visible progress checks."""
    rows: list[dict] = []
    for status_path in sorted(SPRINTS.glob("sprint-*.status.json")):
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        sid = str(data.get("sprint_id") or data.get("id") or status_path.name.removesuffix(".status.json"))
        sprint_epic = str(data.get("epic_id") or "")
        if epic_id and sprint_epic != epic_id:
            continue

        blocked_by = ""
        for entry in reversed(data.get("history") or []):
            if isinstance(entry, dict) and entry.get("blocked_by"):
                blockers = entry["blocked_by"]
                blocked_by = ", ".join(str(b) for b in blockers) if isinstance(blockers, list) else str(blockers)
                break

        capability = ""
        task_graph_path = status_path.parent / status_path.name.replace(".status.json", ".task_graph.json")
        if task_graph_path.exists():
            try:
                graph = json.loads(task_graph_path.read_text(encoding="utf-8"))
                caps: list[str] = []
                for node in (graph.get("nodes") or [])[:3]:
                    if not isinstance(node, dict):
                        continue
                    for cap in (node.get("required_capabilities") or [])[:2]:
                        if cap and cap not in caps:
                            caps.append(str(cap))
                capability = "; ".join(caps[:3])
            except Exception:
                pass

        rows.append({
            "sprint_id": sid,
            "status": str(data.get("status") or ""),
            "phase": str(data.get("phase") or ""),
            "handoff_to": str(data.get("handoff_to") or ""),
            "blocked_by": blocked_by,
            "capability": capability,
            "epic_id": sprint_epic,
        })

    if output_json:
        print(json.dumps({"ok": True, "count": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
        return 0

    print("| sprint_id | status | phase | handoff_to | blocked_by | capability |")
    print("|-----------|--------|-------|------------|------------|------------|")
    for row in rows:
        sid_short = row["sprint_id"][-40:] if len(row["sprint_id"]) > 40 else row["sprint_id"]
        print(
            f"| {sid_short} | {row['status']} | {row['phase']} | {row['handoff_to']}"
            f" | {row['blocked_by'] or '—'} | {row['capability'] or '—'} |"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    parser.add_argument("--once", action="store_true", help="run one scan cycle (explicit alias for default)")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-iterations", type=int, default=0, help="0 means forever")
    parser.add_argument("--cooldown", type=int, default=300, help="seconds between repeated actions for same finding")
    parser.add_argument("--stall-seconds", type=int, default=180, help="pane unchanged seconds before compact/stall recovery")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--epic-status-matrix", action="store_true", dest="epic_status_matrix",
                        help="Print epic child sprint state matrix and exit")
    parser.add_argument("--epic", default="", help="Filter --epic-status-matrix and apply/dispatch scans by epic_id")
    args = parser.parse_args()
    if args.epic_status_matrix:
        return epic_status_matrix(epic_id=args.epic, output_json=args.json)
    if args.once:
        args.loop = False

    if args.loop and not acquire_lock():
        payload = {"ok": False, "error": "autopilot already running", "lock": str(LOCK)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["error"])
        return 1

    state = load_state()
    iterations = 0
    try:
        while True:
            payload = scan_once(args, state)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
            else:
                print(f"findings={len(payload['findings'])} actions={len(payload['actions'])}", flush=True)
                for f in payload["findings"]:
                    print(f"- {f.get('severity')} {f.get('type')} {f.get('sid')} {f.get('target','')}", flush=True)
            iterations += 1
            if not args.loop or (args.max_iterations and iterations >= args.max_iterations):
                break
            time.sleep(max(5, args.interval))
    finally:
        if args.loop:
            release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
