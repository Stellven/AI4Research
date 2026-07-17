"""Orchestration routes for Solar-Harness status-server.

Five read-only endpoints:
  GET /orchestration/epics                  — list all epics
  GET /orchestration/epics/<epic_id>        — epic detail + child sprint table
  GET /orchestration/sprints/<sid>          — sprint detail + capability hit
  GET /orchestration/panes                  — pane capability map
  GET /orchestration/events                 — SSE stream (or poll fallback)

All responses use envelope: {ok, schema_version, generated_at, degraded_sources, data}
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Generator

try:
    from flask import Blueprint, jsonify, Response, request, stream_with_context
except ModuleNotFoundError:  # status-server.py uses the pure builders without Flask.
    class _NoopBlueprint:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def route(self, *args: Any, **kwargs: Any):
            def decorator(func):
                return func
            return decorator

    class Response:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

    class _Request:
        args: dict[str, str] = {}
        headers: dict[str, str] = {}

    def jsonify(value: Any):  # type: ignore[no-redef]
        return value

    def stream_with_context(value: Any):  # type: ignore[no-redef]
        return value

    Blueprint = _NoopBlueprint  # type: ignore[assignment]
    request = _Request()  # type: ignore[assignment]

HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or str(Path.home() / ".solar" / "harness")
).expanduser()
SCRIPT_HARNESS_DIR = Path(__file__).resolve().parents[2]
SPRINTS_DIR = Path(os.environ.get("HARNESS_SPRINTS_DIR") or (HARNESS_DIR / "sprints"))
SESSIONS_DIR = HARNESS_DIR / "sessions"
STATE_DIR = HARNESS_DIR / "state"
EVENTS_JSONL = HARNESS_DIR / "events.jsonl"

SCHEMA_VERSION = "solar.orchestration.v1"
SAFE_SPRINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,180}$")

orchestration_bp = Blueprint("orchestration", __name__, url_prefix="/orchestration")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(data: Any, degraded_sources: list[str] | None = None) -> dict:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "degraded_sources": degraded_sources or [],
        "data": data,
    }


def _read_json(path: Path) -> tuple[Any, bool]:
    """Return (parsed, ok). ok=False means file missing or parse error."""
    if not path.exists():
        return None, False
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace")), True
    except Exception:
        return None, False


def _clean_sprint_title(sid: str, fallback: str) -> str:
    """Human-friendly session title.

    The stored title comes from the PRD's first heading, which is the user's intent
    truncated mid-word at 80 chars (and is occasionally a non-English planner heading).
    Prefer the user's full original intent from raw_intent.json, then truncate at a
    word boundary. Falls back to the stored title when no raw intent is recorded.
    """
    fallback = re.sub(r"\s+", " ", str(fallback or "")).strip()
    full = ""
    data, ok = _read_json(SPRINTS_DIR / f"{sid}.raw_intent.json")
    if ok and isinstance(data, dict):
        candidate = data.get("raw")
        if candidate is None:
            candidate = data.get("text") or data.get("intent")
        if isinstance(candidate, dict):
            full = str(candidate.get("text") or candidate.get("prompt") or "")
        elif isinstance(candidate, str):
            s = candidate.strip()
            if s.startswith("{"):
                # raw is a stringified dict — JSON or a Python repr ({'text': "..."}).
                import ast

                parsed = None
                for loader in (json.loads, ast.literal_eval):
                    try:
                        parsed = loader(s)
                        break
                    except Exception:
                        parsed = None
                if isinstance(parsed, dict):
                    full = str(parsed.get("text") or parsed.get("prompt") or "")
            else:
                full = s
    title = re.sub(r"\s+", " ", full).strip() or fallback
    if not title:
        return sid
    limit = 76
    if len(title) > limit:
        head = title[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-—")
        title = (head or title[:limit].rstrip()) + "…"
    return title


def _sprint_created(sid: str, fallback_mtime: float) -> tuple[float, str]:
    """Real creation time from the sprint_id (sprint-YYYYMMDD-HHMMSS-…, UTC). Used
    for stable recency + display instead of the file mtime, which gets bumped by
    background re-projection / reads and pollutes ordering and timestamps."""
    import datetime as _dt
    m = re.match(r"^sprint-(\d{8})-(\d{6})-", sid or "")
    if m:
        try:
            dt = _dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=_dt.timezone.utc)
            return dt.timestamp(), dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    ts = float(fallback_mtime or 0.0)
    iso = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else ""
    return ts, iso


def _sprint_status_rows(limit: int = 80) -> list[dict]:
    active = {"active", "dispatched", "reviewing", "ready_for_review", "failed_review"}
    # Pass 1 (cheap): read ONLY status.json per sprint. The sidebar list needs just
    # id/title/status/phase/recency — no task-graph. The old code called _load_task_graph()
    # per sprint, which globs every file in sprints/ three times; with ~1.3k artifacts across
    # ~50 sprints that took 13s and left the sidebar stuck on skeletons.
    prelim: list[dict] = []
    for sf in SPRINTS_DIR.glob("*.status.json"):
        data, ok = _read_json(sf)
        if not ok or not isinstance(data, dict):
            continue
        if data.get("archived"):
            # Owner-archived sessions are kept on disk but hidden from the list.
            continue
        sid = str(data.get("sprint_id") or data.get("id") or sf.name.removesuffix(".status.json"))
        try:
            mtime = sf.stat().st_mtime
        except OSError:
            mtime = 0.0
        status = str(data.get("status") or "")
        created_ts, created_at = _sprint_created(sid, mtime)
        prelim.append({
            "sprint_id": sid,
            "title": data.get("title") or sid,
            "status": status,
            "phase": str(data.get("phase") or ""),
            "is_active": status.lower() in active,
            "mtime": mtime,
            "created_ts": created_ts,
            "created_at": created_at,
        })
    # Sort by true creation time (newest first). The old code sorted by file mtime,
    # which background re-projection bumps — pushing a brand-new session below stale
    # ones. created_ts comes from the sprint_id and is stable.
    prelim.sort(key=lambda item: (-float(item.get("created_ts") or 0), str(item.get("sprint_id") or "")))
    prelim = prelim[:limit]
    # Pass 2: node counts for the capped set only, via DIRECT path reads (no dir globbing).
    rows: list[dict] = []
    for item in prelim:
        sid = item["sprint_id"]
        nodes: list = []
        runtime_state: dict = {}
        tg_ok = False
        for name in (
            f"{sid}.task_graph.json",
            f"{sid}.task_dag.state.json",
            f"{sid}.task_graph.state.json",
            f"{sid}.closure.json",
        ):
            tg_data, tg_read = _read_json(SPRINTS_DIR / name)
            if tg_read and isinstance(tg_data, dict):
                tg = _normalize_task_graph_payload(tg_data)
                raw_nodes = tg.get("nodes")
                if isinstance(raw_nodes, list):
                    nodes = raw_nodes
                    runtime_state = tg.get("runtime_state") or {}
                    tg_ok = True
                    break
        node_counts: dict[str, int] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            st = _node_status(node, runtime_state)
            node_counts[st] = node_counts.get(st, 0) + 1
        rows.append({
            "sprint_id": sid,
            "title": _clean_sprint_title(sid, item["title"]),
            "status": item["status"],
            "phase": item["phase"],
            "is_active": item["is_active"],
            "mtime": item["mtime"],
            "created_ts": item.get("created_ts"),
            "created_at": item.get("created_at"),
            "node_count": len(nodes),
            "node_status_counts": node_counts,
            "task_graph_present": tg_ok,
        })
    return rows


def _active_sprint_ids(limit: int = 8) -> list[str]:
    active = {"active", "dispatched", "reviewing", "ready_for_review", "failed_review"}
    return [str(row.get("sprint_id") or "") for row in _sprint_status_rows(limit=limit * 3) if str(row.get("status") or "").lower() in active][:limit]


def _load_status_by_sprint(sid: str) -> dict:
    data, ok = _read_json(SPRINTS_DIR / f"{sid}.status.json")
    return data if ok and isinstance(data, dict) else {}


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _task_graph_candidate_paths(sid: str) -> list[Path]:
    """Return supported sprint DAG artifact paths, newest and legacy names.

    Sprint artifacts have not used one stable filename across all harness
    sprints. Keep this read-only dashboard tolerant: prefer canonical graph
    files, then state/closure/spec fallbacks, then narrow same-sprint globs.
    """
    sid = str(sid or "").strip()
    if not sid:
        return []
    top_level_names = [
        f"{sid}.task_graph.json",
        f"{sid}.task_graph.state.json",
        f"{sid}.task_graph.spec.json",
        f"{sid}.task_dag.json",
        f"{sid}.task_dag.state.json",
        f"{sid}.task_dag.closure.json",
        f"{sid}.closure.json",
    ]
    nested_names = [
        "task_graph.json",
        "task_graph.state.json",
        "task_graph.spec.json",
        "task_dag.json",
        "task_dag.state.json",
        "task_dag.closure.json",
        "closure.json",
    ]
    candidates = [SPRINTS_DIR / name for name in top_level_names]
    for root in (SPRINTS_DIR / sid, SPRINTS_DIR / sid / ".pm", SPRINTS_DIR / sid / "state"):
        candidates.extend(root / name for name in nested_names)
    for pattern in (
        f"{sid}*task_graph*.json",
        f"{sid}*task_dag*.json",
        f"{sid}*closure*.json",
    ):
        try:
            candidates.extend(sorted(SPRINTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True))
        except OSError:
            continue
    return _dedupe_paths(candidates)


def _normalize_task_graph_payload(data: Any) -> dict:
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("nodes"), list):
        return data
    for key in ("task_graph", "task_dag", "graph", "dag"):
        nested = data.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("nodes"), list):
            out = dict(nested)
            for inherited in ("sprint_id", "required_gates", "runtime_state"):
                if inherited not in out and inherited in data:
                    out[inherited] = data[inherited]
            return out
    if isinstance(data.get("node_results"), dict) or isinstance(data.get("gate_results"), dict):
        out = dict(data)
        out.setdefault("runtime_state", {
            "nodes": data.get("node_results") or {},
            "gates": data.get("gate_results") or {},
        })
        return out
    return data


def _existing_task_graph_path(sid: str) -> Path:
    for path in _task_graph_candidate_paths(sid):
        if path.exists() and path.is_file():
            return path
    return SPRINTS_DIR / f"{sid}.task_graph.json"


def _load_task_graph(sid: str) -> tuple[dict, bool]:
    for path in _task_graph_candidate_paths(sid):
        data, ok = _read_json(path)
        if ok and isinstance(data, dict):
            return _normalize_task_graph_payload(data), True
    return {}, False


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(HARNESS_DIR))
    except ValueError:
        return str(path)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _normalize_status(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value in {"passed", "completed"}:
        return "passed"
    if value in {"failed", "cancelled", "error"}:
        return "failed"
    if value in {"blocked", "dependency_blocked", "quota_blocked", "auth_blocked"}:
        return "blocked"
    if value in {"active", "dispatched", "reviewing", "ready_for_review", "in_progress"}:
        return "active"
    if value in {"queued", "drafting", "planned", "pending"}:
        return "pending"
    return value or "pending"


def _node_workflow_status(node: dict, status_state: dict | None = None) -> str:
    """Return the effective node state without collapsing workflow transitions.

    The dashboard still needs a normalized status for progress/tone, but
    `dispatched` and `reviewing` identify different active operators.  Preserve
    that distinction at the serialization boundary instead of asking the
    frontend to reverse-engineer it after normalization.
    """
    state_nodes = (status_state or {}).get("nodes") or {}
    nid = node.get("id", "")
    if isinstance(state_nodes, dict) and nid in state_nodes:
        nstate = state_nodes[nid]
        if isinstance(nstate, dict):
            raw = nstate.get("status")
        else:
            raw = nstate
    else:
        raw = node.get("status")
    return str(raw or "pending").strip().lower() or "pending"


def _node_status(node: dict, status_state: dict | None = None) -> str:
    return _normalize_status(_node_workflow_status(node, status_state))


def _load_routing_decisions() -> list[dict]:
    data, ok = _read_json(STATE_DIR / "autopilot-state.json")
    if not ok:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    decisions = data.get("routing_decisions", [])
    return [item for item in decisions if isinstance(item, dict)] if isinstance(decisions, list) else []


def _capability_counts(nodes: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        executable_node = node.get("executable_node") if isinstance(node.get("executable_node"), dict) else {}
        identity = executable_node or node
        for cap in identity.get("required_capabilities") or []:
            if isinstance(cap, str):
                counts[cap] = counts.get(cap, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _role_counts(nodes: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        executable_node = node.get("executable_node") if isinstance(node.get("executable_node"), dict) else {}
        role = (
            executable_node.get("dispatch_role")
            or executable_node.get("logical_operator")
            or node.get("target_role")
            or node.get("preferred_role")
            or node.get("logical_operator")
            or "unspecified"
        )
        if not isinstance(role, str) or not role:
            role = "unspecified"
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _provided_capability_names(provided: list[Any]) -> set[str]:
    names: set[str] = set()
    for item in provided:
        if not isinstance(item, str):
            continue
        names.add(item.removeprefix("inferred:"))
    return names


def _actorhost_for_pane(pane_id: str, required_capabilities: list[str] | None = None) -> dict[str, Any]:
    import sys

    canonical_host_types = {
        "claude_code_session",
        "tmux_pane",
        "operator_pool",
        "antigravity_managed_env",
        "browser_profile",
        "remote_shell",
        "api_worker",
        "local_process",
    }

    def _pane_matches(configured: str, pane: str) -> bool:
        if not configured or not pane:
            return False
        if configured == pane:
            return True
        if configured.endswith("*"):
            return pane.startswith(configured[:-1])
        return False

    def _operator_id_for_pane(pane: str) -> str:
        data, ok = _read_json(HARNESS_DIR / "config" / "physical-operators.json")
        operators = data.get("operators", {}) if ok and isinstance(data, dict) else {}
        if not isinstance(operators, dict):
            return ""
        for operator_id, cfg in operators.items():
            if isinstance(cfg, dict) and _pane_matches(str(cfg.get("pane") or ""), pane):
                return str(operator_id)
        return ""

    def _lease_state_for_actor(actor_id: str) -> str:
        data, ok = _read_json(HARNESS_DIR / "run" / "actor-leases" / f"{actor_id}.json")
        if not ok or not isinstance(data, dict):
            return "idle"
        if str(data.get("expires_at") or "") > _now():
            return str(data.get("state") or "leased")
        return "stale"

    def _capability_match(actor_cfg: dict[str, Any], required: list[str]) -> dict[str, Any]:
        profile = actor_cfg.get("capability_profile")
        if not isinstance(profile, dict):
            profile = actor_cfg.get("capability") if isinstance(actor_cfg.get("capability"), dict) else {}
        observed = sorted(str(k) for k, v in profile.items() if isinstance(v, (int, float)) and v)
        return {
            "required": required,
            "matched": sorted(set(required).intersection(observed)),
            "missing": sorted(set(required).difference(observed)),
            "observed": observed,
        }

    def _local_actorhost(operator_id: str, required: list[str], import_reason: str = "") -> dict[str, Any]:
        actors_data, actors_ok = _read_json(HARNESS_DIR / "config" / "agent-actors.json")
        hosts_data, hosts_ok = _read_json(HARNESS_DIR / "config" / "actor-hosts.json")
        actors = actors_data.get("actors", {}) if actors_ok and isinstance(actors_data, dict) else {}
        hosts = hosts_data.get("hosts", {}) if hosts_ok and isinstance(hosts_data, dict) else {}
        actor_cfg = actors.get(operator_id) if isinstance(actors, dict) else {}
        if isinstance(actor_cfg, dict) and actor_cfg:
            host_id = str(actor_cfg.get("host_id") or "unknown")
            host_cfg = hosts.get(host_id, {}) if isinstance(hosts, dict) else {}
            host_type = str(host_cfg.get("host_type") or "unknown")
            return {
                "actor_id": operator_id,
                "host_id": host_id,
                "host_type": host_type,
                "lease_state": _lease_state_for_actor(operator_id),
                "capability_match": _capability_match(actor_cfg, required),
                "compat_fallback": False,
                "compat_maps_to": None,
                "resolution_source": "actor_hosts",
                "canonical_host_type": host_type in canonical_host_types,
                "resolver_fallback_reason": import_reason,
            }

        physical_data, physical_ok = _read_json(HARNESS_DIR / "config" / "physical-operators.json")
        operators = physical_data.get("operators", {}) if physical_ok and isinstance(physical_data, dict) else {}
        op_cfg = operators.get(operator_id) if isinstance(operators, dict) else {}
        compat = op_cfg.get("compat_maps_to") if isinstance(op_cfg, dict) else None
        if isinstance(compat, dict):
            host_type = str(compat.get("host_type") or "unknown")
            return {
                "actor_id": operator_id or "N/A",
                "host_id": "N/A",
                "host_type": host_type,
                "lease_state": "unknown",
                "capability_match": {"required": required, "matched": [], "missing": required, "observed": []},
                "compat_fallback": True,
                "compat_maps_to": compat,
                "resolution_source": "physical_operators.compat_maps_to",
                "canonical_host_type": host_type in canonical_host_types,
                "resolver_fallback_reason": import_reason,
            }
        return {
            "actor_id": operator_id or "N/A",
            "host_id": "N/A",
            "host_type": "unknown",
            "lease_state": "unknown",
            "capability_match": {"required": required, "matched": [], "missing": required, "observed": []},
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": "unresolved",
            "canonical_host_type": False,
            "resolver_fallback_reason": import_reason,
        }

    operator_id = _operator_id_for_pane(pane_id)
    required = required_capabilities or []
    for lib_dir in (HARNESS_DIR / "lib", SCRIPT_HARNESS_DIR / "lib"):
        value = str(lib_dir)
        if value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)
    try:
        from multi_task_status import resolve_actorhost_status  # type: ignore
        if not callable(resolve_actorhost_status):
            raise ImportError("resolve_actorhost_status unavailable")

        return resolve_actorhost_status(
            actor_id=operator_id,
            operator_id=operator_id,
            pane=pane_id,
            actors_path=HARNESS_DIR / "config" / "agent-actors.json",
            hosts_path=HARNESS_DIR / "config" / "actor-hosts.json",
            physical_operators_path=HARNESS_DIR / "config" / "physical-operators.json",
            lease_dir=HARNESS_DIR / "run" / "actor-leases",
            required_capabilities=required,
        )
    except Exception as exc:
        return _local_actorhost(operator_id, required, f"resolver_error:{type(exc).__name__}")


def _build_node_cards(sid: str, nodes: list[dict], status_state: dict, routing: list[dict]) -> list[dict]:
    by_node = {r.get("node_id"): r for r in routing if r.get("sprint_id") == sid}
    cards: list[dict] = []
    for index, node in enumerate(nodes):
        nid = str(node.get("id") or f"N{index + 1}")
        decision = by_node.get(nid, {})
        executable_node = (
            node.get("executable_node")
            if isinstance(node.get("executable_node"), dict)
            else {}
        )
        identity = executable_node or node
        required = [c for c in (identity.get("required_capabilities") or []) if isinstance(c, str)]
        required_skills = [s for s in (identity.get("required_skills") or []) if isinstance(s, str)]
        provided = decision.get("provided_capabilities") or []
        missing = [cap for cap in required if cap not in _provided_capability_names(provided)]
        target_pane = str(decision.get("target_pane") or "")
        actorhost = _actorhost_for_pane(target_pane, required) if target_pane else {}
        physical_plan = node.get("physical_plan") if isinstance(node.get("physical_plan"), dict) else {}
        physical_plan_ir = node.get("physical_plan_ir") if isinstance(node.get("physical_plan_ir"), dict) else {}
        capsule_plan_ir = node.get("capsule_plan_ir") if isinstance(node.get("capsule_plan_ir"), dict) else {}
        selected_operator = (
            physical_plan.get("suggested_operator_id")
            or physical_plan.get("selected_operator_id")
            or physical_plan_ir.get("suggested_operator_id")
            or physical_plan_ir.get("selected_operator_id")
            or node.get("suggested_operator_id")
            or node.get("selected_operator_id")
            or ""
        )
        requested_role = (
            executable_node.get("dispatch_role")
            or decision.get("required_role")
            or node.get("target_role")
            or node.get("preferred_role")
            or node.get("role")
            or physical_plan_ir.get("role")
            or capsule_plan_ir.get("role")
            or ""
        )
        cards.append({
            "id": nid,
            "executable_node": dict(executable_node),
            "goal": identity.get("goal") or "",
            "status": _node_status(node, status_state),
            "workflow_status": _node_workflow_status(node, status_state),
            # Preserve the compiler-owned execution-role evidence end-to-end.
            # The React shell must not guess from opaque ids (S1/S2) after the
            # dashboard serializer has discarded the graph fields that already
            # answer which logical role owns the node.
            "owner": node.get("owner") or "",
            "task_type": identity.get("task_type") or identity.get("node_type") or "",
            "dispatch_task_type": identity.get("dispatch_task_type") or "",
            "depends_on": identity.get("depends_on") or [],
            "gate": identity.get("gate") or "",
            "estimated_cost": node.get("estimated_cost") or 0,
            "required_capabilities": required,
            "required_skills": required_skills,
            "missing_capabilities": missing,
            "missing_skills": [s for s in (decision.get("missing_skills") or node.get("missing_skills") or []) if isinstance(s, str)],
            "requested_role": requested_role,
            "logical_operator": executable_node.get("logical_operator") or node.get("logical_operator") or physical_plan_ir.get("logical_operator") or "",
            "preferred_model": node.get("preferred_model") or "",
            "selected_operator_id": selected_operator,
            "capability_capsule_id": executable_node.get("capability_capsule_id") or physical_plan_ir.get("capability_capsule_id") or capsule_plan_ir.get("capability_capsule_id") or "",
            "candidate_workers_seen": bool(decision.get("any_worker_seen") or decision.get("candidate_workers_seen")),
            "role_candidates_seen": bool(decision.get("role_candidates_seen")),
            "target_pane": target_pane,
            "pane_carrier": {"pane_id": target_pane, "source": "autopilot_routing"} if target_pane else {},
            "actorhost": actorhost,
            "actor_id": actorhost.get("actor_id", "N/A") if actorhost else "N/A",
            "host_id": actorhost.get("host_id", "N/A") if actorhost else "N/A",
            "host_type": actorhost.get("host_type", "unknown") if actorhost else "unknown",
            "lease_state": actorhost.get("lease_state", "unknown") if actorhost else "unknown",
            "route_decision": decision.get("decision") or "no_routing_record",
            "blocked_reason": decision.get("blocked_reason") or "",
            "decision": decision.get("decision") or "no_routing_record",
            "write_scope": identity.get("write_scope") or [],
            "read_scope": identity.get("read_scope") or [],
        })
    return cards


def _diagnostic_guidance(kind: str, subject: str) -> list[str]:
    if kind == "dependency":
        return [
            f"Inspect blocked dependency status: solar-harness status {subject}",
            "Confirm dependency handoff/eval artifact exists under sprints/ before redispatch.",
            "Run graph scheduler validation after dependency changes.",
        ]
    if kind == "node_dependency":
        return [
            f"Open upstream node handoff/eval for {subject}.",
            "Only move this node after upstream status is passed/completed.",
            "If upstream is stale, redispatch that node instead of bypassing the DAG.",
        ]
    if kind == "capability":
        return [
            "Check state/pane-state.json and state/autopilot-state.json for matching pane capabilities.",
            "Verify the selected operator advertises every required_capability.",
            "If no pane matches, update the operator capability registry before redispatch.",
        ]
    if kind == "task_graph":
        return [
            "Restore or regenerate the sprint DAG artifact (task_graph/task_dag/closure variants are accepted).",
            "Run solar-harness graph-scheduler validate --graph <task_graph.json>.",
            "Do not dispatch implementation work until the graph validates.",
        ]
    return [
        "Check status-server logs under run/status-server.log.",
        "Refresh /orchestration/dashboard to confirm whether the source recovered.",
    ]


def _build_blocker_diagnostics(sid: str, status: dict, nodes: list[dict], node_cards: list[dict], tg_ok: bool) -> list[dict]:
    diagnostics: list[dict] = []
    if not tg_ok:
        diagnostics.append({
            "severity": "error",
            "kind": "task_graph",
            "title": "Task graph missing",
            "detail": f"No supported task graph artifact was found for {sid}.",
            "guidance": _diagnostic_guidance("task_graph", sid),
        })

    for blocker in _extract_blocked_by(status):
        diagnostics.append({
            "severity": "warn",
            "kind": "dependency",
            "title": "Sprint dependency blocked dispatch",
            "detail": blocker,
            "guidance": _diagnostic_guidance("dependency", blocker),
        })

    status_by_id = {n["id"]: n["status"] for n in node_cards}
    for card in node_cards:
        unmet = [dep for dep in card["depends_on"] if status_by_id.get(dep) not in {"passed", "completed"}]
        if card["status"] in {"pending", "blocked"} and unmet:
            subject = ", ".join(unmet)
            diagnostics.append({
                "severity": "warn",
                "kind": "node_dependency",
                "title": f"{card['id']} waiting for upstream node",
                "detail": subject,
                "guidance": _diagnostic_guidance("node_dependency", subject),
            })
        if card["missing_capabilities"]:
            diagnostics.append({
                "severity": "warn",
                "kind": "capability",
                "title": f"{card['id']} capability mismatch",
                "detail": ", ".join(card["missing_capabilities"]),
                "guidance": _diagnostic_guidance("capability", card["id"]),
            })
    return diagnostics


def _recent_sprint_events(sid: str, limit: int = 24) -> list[dict]:
    """Tail of the sprint event log — used to tell 'actively working' from 'stuck looping'."""
    if not sid:
        return []
    try:
        lines = (SPRINTS_DIR / f"{sid}.events.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if isinstance(d, dict):
                out.append(d)
        except ValueError:
            continue
    return out


# Repeated low-level events that mean "retrying / can't start work", not progress.
_STALL_CHURN_REASONS = {
    "invalid_prd", "no_free_worker", "clear_gate_failed", "pane_not_idle",
    "worker_capacity_exhausted", "clear_gate", "duplicate",
}
_STALL_CHURN_EVENTS = {"gate_blocked", "dispatch_failed", "dispatch_queued", "planner_notified"}
_STALL_PROGRESS_HINTS = (
    "passed", "model_session", "prd_completed", "compiled_requirement",
    "node_dispatch", "graph_node", "eval_dispatch", "finalized", "completed",
)


def _loop_stall_reasons(events: list[dict]) -> list[str] | None:
    """Detect a sprint stuck in a dispatch/gate retry loop with no forward progress."""
    if not events:
        return None
    churn = 0
    progress = 0
    reasons: list[str] = []
    for e in events[-18:]:
        ev = str(e.get("event") or "")
        reason = str((e.get("payload") or {}).get("reason") or e.get("reason") or "").strip()
        if any(h in ev for h in _STALL_PROGRESS_HINTS):
            progress += 1
        elif ev in _STALL_CHURN_EVENTS or reason in _STALL_CHURN_REASONS:
            churn += 1
            if reason:
                reasons.append(reason)
    if churn >= 4 and progress == 0:
        return sorted(set(reasons))
    return None


def _stall_human_reason(reasons: list[str]) -> str:
    rs = set(reasons)
    if rs & {"no_free_worker", "worker_capacity_exhausted"}:
        return "No available worker — the runtime can't hand the task to an agent pane."
    if "invalid_prd" in rs:
        return "Stuck at the spec gate — the PRD isn't passing validation and isn't being repaired."
    if rs & {"clear_gate_failed", "pane_not_idle"}:
        return "Can't reach a worker pane to continue (pane busy or unresponsive)."
    return "Repeated retries with no forward progress."


def _build_stall_summary(
    status: dict,
    node_cards: list[dict],
    diagnostics: list[dict],
    tg_ok: bool,
    events: list[dict] | None = None,
    plan_governance: dict | None = None,
) -> dict:
    sprint_status = str(status.get("status") or "").strip().lower()
    phase = str(status.get("phase") or "").strip().lower()
    blocked = [card for card in node_cards if str(card.get("status") or "").lower() in {"blocked", "gate_blocked", "failed"} or card.get("blocked_reason")]
    active = [card for card in node_cards if str(card.get("status") or "").lower() in {"active", "running", "dispatched", "in_progress"}]
    reasons = sorted({str(card.get("blocked_reason") or card.get("decision") or "").strip() for card in blocked if str(card.get("blocked_reason") or card.get("decision") or "").strip()})

    if not tg_ok:
        return {
            "is_stalled": True,
            "state": "task_graph_missing",
            "severity": "error",
            "title": "DAG evidence missing",
            "detail": "The status file exists, but no supported task graph artifact was found.",
            "reasons": [],
        }
    if sprint_status in {"gate_blocked", "blocked", "failed_review"} or "gate_blocked" in phase:
        return {
            "is_stalled": True,
            "state": sprint_status or phase,
            "severity": "warn",
            "title": "Sprint is blocked at a gate",
            "detail": "Solar reported a blocked gate. The dashboard is showing the stall rather than treating the sprint as complete.",
            "reasons": reasons,
        }
    governance_state = str((plan_governance or {}).get("state") or "").strip().lower()
    if (
        "planning_complete" in phase
        and not active
        and blocked
        and governance_state != "compiling"
    ):
        state = "no_matching_worker" if any("no_matching_worker" in reason for reason in reasons) else "planning_complete_stalled"
        return {
            "is_stalled": True,
            "state": state,
            "severity": "warn",
            "title": "Planning is complete, dispatch is stalled",
            "detail": "The DAG has an explicit blocked node or routing decision, and no node is actively running.",
            "reasons": reasons,
        }
    if blocked:
        return {
            "is_stalled": True,
            "state": "node_blocked",
            "severity": "warn",
            "title": "One or more DAG nodes are blocked",
            "detail": "At least one node is blocked or failed. Check node details before expecting completion.",
            "reasons": reasons,
        }
    loop_reasons = _loop_stall_reasons(events or [])
    if loop_reasons is not None and sprint_status not in {"passed", "finalized", "completed", "done"}:
        return {
            "is_stalled": True,
            "state": "retry_loop",
            "severity": "warn",
            "title": "Stalled before execution could start",
            "detail": _stall_human_reason(loop_reasons),
            "reasons": loop_reasons,
        }
    return {
        "is_stalled": False,
        "state": "flowing" if active else "idle_or_waiting",
        "severity": "ok",
        "title": "No explicit stall reported",
        "detail": "No blocked gate or blocked DAG node is visible in the current status artifacts.",
        "reasons": [],
    }


def _artifact_kind(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name.endswith(".status.json"):
        return "status"
    if "requirement_trace" in name:
        return "requirement_trace"
    if "coverage" in name:
        return "coverage"
    if "acceptance_verdict" in name:
        return "acceptance_verdict"
    if "contract" in name:
        return "contract"
    if ".prd" in name or name.endswith("prd.md"):
        return "prd"
    if "design" in name:
        return "design"
    if "task_graph" in name or "task_dag" in name or "closure" in name:
        return "task_graph"
    if "plan" in name and suffix in {".md", ".json"}:
        return "plan"
    if "handoff" in name:
        return "handoff"
    if "eval" in name or "verdict" in name:
        return "eval"
    if suffix == ".jsonl" or "event" in name:
        return "event_log"
    if suffix in {".html", ".htm", ".pdf"} or "report" in name:
        return "report"
    if "evidence" in name:
        return "evidence"
    return suffix.lstrip(".") or "file"


def _artifact_stage(kind: str) -> str:
    return {
        "status": "runtime",
        "event_log": "runtime",
        "contract": "intake",
        "prd": "prd",
        "requirement_trace": "evaluation",
        "coverage": "evaluation",
        "acceptance_verdict": "evaluation",
        "design": "planning",
        "plan": "planning",
        "task_graph": "planning",
        "handoff": "build",
        "eval": "evaluation",
        "evidence": "evaluation",
        "report": "deliverable",
    }.get(kind, "artifact")


def _artifact_view_url(sid: str, rel_path: str, suffix: str) -> str:
    if suffix.lower() not in {".html", ".htm", ".md", ".markdown", ".json", ".txt", ".log", ".pdf", ".png", ".jpg", ".jpeg"}:
        return ""
    return f"/sprints/{urllib.parse.quote(sid)}/deliverables?path={urllib.parse.quote(rel_path)}"


def _projection_artifacts(sid: str) -> list[dict]:
    if not sid:
        return []
    candidates: list[Path] = []
    exact_names = [
        f"{sid}.status.json",
        f"{sid}.contract.md",
        f"{sid}.prd.md",
        f"{sid}.design.md",
        f"{sid}.plan.md",
        f"{sid}.task_graph.json",
        f"{sid}.task_graph.state.json",
        f"{sid}.task_dag.json",
        f"{sid}.handoff.md",
        f"{sid}.eval.md",
        f"{sid}.events.jsonl",
        f"{sid}.requirement_trace.json",
        f"{sid}.coverage_report.json",
        f"{sid}.acceptance_verdict.json",
    ]
    candidates.extend(SPRINTS_DIR / name for name in exact_names)
    for pattern in (
        f"{sid}*.md",
        f"{sid}*.json",
        f"{sid}*.jsonl",
        f"{sid}*.html",
        f"{sid}*.htm",
        f"{sid}*.pdf",
    ):
        try:
            candidates.extend(sorted(SPRINTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True))
        except OSError:
            continue
    for root in (SPRINTS_DIR / sid, SPRINTS_DIR / sid / ".research", SPRINTS_DIR / f"{sid}.research"):
        if not root.exists() or not root.is_dir():
            continue
        try:
            candidates.extend(p for p in root.rglob("*") if p.is_file())
        except OSError:
            continue

    rows: list[dict] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            if not path.exists() or not path.is_file():
                continue
            resolved = path.resolve()
            if not _is_within(resolved, SPRINTS_DIR):
                continue
            rel_path = _display_path(resolved)
            if rel_path in seen:
                continue
            seen.add(rel_path)
            stat = resolved.stat()
            kind = _artifact_kind(resolved)
            rows.append({
                "name": resolved.name,
                "kind": kind,
                "stage": _artifact_stage(kind),
                "rel_path": rel_path,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "reviewable": kind in {"prd", "design", "plan", "task_graph", "handoff", "eval", "report", "evidence", "coverage", "acceptance_verdict", "requirement_trace"},
                "view_url": _artifact_view_url(sid, rel_path, resolved.suffix),
            })
        except OSError:
            continue
    rows.sort(key=lambda item: (str(item.get("stage") or ""), -float(item.get("mtime") or 0), str(item.get("name") or "")))
    return rows


def _first_artifact(artifacts: list[dict], *kinds: str) -> dict:
    wanted = set(kinds)
    return next((item for item in artifacts if item.get("kind") in wanted), {})


def _artifact_ref(item: dict | None) -> dict:
    if not isinstance(item, dict) or not item:
        return {}
    return {
        "name": item.get("name") or "",
        "kind": item.get("kind") or "",
        "stage": item.get("stage") or "",
        "rel_path": item.get("rel_path") or "",
        "view_url": item.get("view_url") or "",
        "reviewable": bool(item.get("reviewable")),
    }


def _artifact_refs(artifacts: list[dict], *kinds: str) -> list[dict]:
    wanted = set(kinds)
    return [_artifact_ref(item) for item in artifacts if item.get("kind") in wanted]


def _artifact_rel_paths(artifacts: list[dict], *kinds: str) -> list[str]:
    return [str(item.get("rel_path") or item.get("name") or "") for item in _artifact_refs(artifacts, *kinds) if item]


def _artifact_by_name_part(artifacts: list[dict], *needles: str) -> dict:
    lowered = [needle.lower() for needle in needles if needle]
    for item in artifacts:
        hay = f"{item.get('name') or ''} {item.get('rel_path') or ''}".lower()
        if all(needle in hay for needle in lowered):
            return item
    return {}


def _artifact_abs_path(item: dict) -> Path | None:
    rel = str(item.get("rel_path") or "").strip()
    if not rel:
        return None
    path = (HARNESS_DIR / rel).resolve()
    if _is_within(path, SPRINTS_DIR):
        return path
    return None


def _read_artifact_json(item: dict) -> dict:
    path = _artifact_abs_path(item)
    if not path:
        return {}
    data, ok = _read_json(path)
    return data if ok and isinstance(data, dict) else {}


def _projection_requirements(sid: str, artifacts: list[dict]) -> dict:
    prd = _first_artifact(artifacts, "prd")
    contract = _first_artifact(artifacts, "contract")
    trace = _first_artifact(artifacts, "requirement_trace") or _artifact_by_name_part(artifacts, "requirement", "trace")
    coverage = _first_artifact(artifacts, "coverage") or _artifact_by_name_part(artifacts, "coverage")
    acceptance = _first_artifact(artifacts, "acceptance_verdict") or _artifact_by_name_part(artifacts, "acceptance", "verdict")
    coverage_json = _read_artifact_json(coverage)
    acceptance_json = _read_artifact_json(acceptance)
    return {
        "sprint_id": sid,
        "present": bool(prd or contract or trace or coverage or acceptance),
        "prd": _artifact_ref(prd),
        "contract": _artifact_ref(contract),
        "requirement_trace": _artifact_ref(trace),
        "coverage_report": _artifact_ref(coverage),
        "acceptance_verdict": _artifact_ref(acceptance),
        "coverage_summary": coverage_json.get("summary") or coverage_json.get("coverage_summary") or {},
        "verdict": acceptance_json.get("verdict") or "",
        "verdict_reasons": acceptance_json.get("reasons") or [],
    }


def _projection_plan(dashboard: dict, artifacts: list[dict]) -> dict:
    design = _first_artifact(artifacts, "design")
    plan = _first_artifact(artifacts, "plan")
    graph = _first_artifact(artifacts, "task_graph")
    present = bool(design or plan or graph)
    complete = bool(design and plan and graph)
    return {
        "present": present,
        "complete": complete,
        "status": "complete" if complete else "partial" if present else "waiting",
        "design": _artifact_ref(design),
        "plan": _artifact_ref(plan),
        "task_graph": _artifact_ref(graph),
        "graph_source": (dashboard.get("generated_from") or {}).get("task_graph_json") or "",
    }


def _projection_task_graph(dashboard: dict) -> dict:
    dag = dashboard.get("dag") if isinstance(dashboard.get("dag"), dict) else {}
    nodes = dag.get("nodes") if isinstance(dag.get("nodes"), list) else []
    edges = dag.get("edges") if isinstance(dag.get("edges"), list) else []
    return {
        "present": bool(nodes or edges or dag.get("required_gates")),
        "required_gates": dag.get("required_gates") or [],
        "nodes": nodes,
        "edges": edges,
        "source": (dashboard.get("generated_from") or {}).get("task_graph_json") or "",
    }


def _latest_verdict_from_events(kind: str, events: list[dict], status: dict) -> dict | None:
    event_tokens = ("plan_verdict",) if kind == "plan_review" else ("eval_passed", "eval_failed", "eval_verdict")
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or event.get("type") or "").lower()
        if not any(token in event_name for token in event_tokens):
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
        return {
            "verdict": payload.get("verdict") or "",
            "reason": payload.get("reason") or "",
            "ts": event.get("ts") or event.get("timestamp") or "",
            "source": "event",
        }
    history = status.get("history") if isinstance(status.get("history"), list) else []
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or item.get("phase") or "").lower()
        if kind == "plan_review" and "plan_reviewed" not in event_name:
            continue
        if kind == "eval_review" and "eval" not in event_name:
            continue
        return {
            "verdict": item.get("verdict") or "",
            "reason": item.get("reason") or "",
            "ts": item.get("ts") or item.get("timestamp") or "",
            "source": "status_history",
        }
    return None


def _plan_gate(status: dict, dashboard: dict, artifacts: list[dict], events: list[dict]) -> dict:
    sprint_status = str(status.get("status") or dashboard.get("sprint_status") or "").lower()
    phase = str(status.get("phase") or dashboard.get("phase") or "").lower()
    plan_artifacts = _artifact_rel_paths(artifacts, "design", "plan", "task_graph")
    has_plan = bool(_first_artifact(artifacts, "plan"))
    has_design = bool(_first_artifact(artifacts, "design"))
    has_graph = bool(_first_artifact(artifacts, "task_graph"))
    resolved_statuses = {"approved", "dispatched", "reviewing", "ready_for_review", "passed", "done", "completed", "failed_review"}
    resolved_phases = {"plan_reviewed", "building", "build_complete", "implementation_complete", "evaluating", "eval_completed", "eval_passed", "eval_failed"}
    if sprint_status in resolved_statuses or phase in resolved_phases:
        gate_status = "resolved"
    elif has_plan and has_design and has_graph and (phase in {"planning_complete", "planning"} or sprint_status in {"active", "planning"}):
        gate_status = "available"
    elif has_plan or has_design or has_graph:
        gate_status = "waiting"
    else:
        gate_status = "waiting"
    return {
        "kind": "plan_review",
        "status": gate_status,
        "allowed_actions": ["approve", "reject"] if gate_status == "available" else [],
        "source_artifacts": plan_artifacts,
        "last_verdict": _latest_verdict_from_events("plan_review", events, status),
        "reason": "",
        "missing_artifacts": [
            name for name, present in (("design", has_design), ("plan", has_plan), ("task_graph", has_graph)) if not present
        ],
    }


def _eval_gate(status: dict, dashboard: dict, artifacts: list[dict], events: list[dict]) -> dict:
    sprint_status = str(status.get("status") or dashboard.get("sprint_status") or "").lower()
    phase = str(status.get("phase") or dashboard.get("phase") or "").lower()
    source_artifacts = _artifact_rel_paths(artifacts, "handoff", "eval", "coverage", "acceptance_verdict", "requirement_trace")
    has_eval = bool(_first_artifact(artifacts, "eval"))
    has_handoff = bool(_first_artifact(artifacts, "handoff"))
    resolved_statuses = {"passed", "done", "completed", "failed_review", "failed", "cancelled"}
    resolved_phases = {"eval_completed", "eval_passed", "eval_failed"}
    if sprint_status in resolved_statuses or phase in resolved_phases:
        gate_status = "resolved"
    elif sprint_status in {"reviewing", "ready_for_review"} or phase in {"build_complete", "implementation_complete", "evaluating"}:
        gate_status = "available"
    elif has_eval or has_handoff:
        gate_status = "available"
    else:
        gate_status = "waiting"
    return {
        "kind": "eval_review",
        "status": gate_status,
        "allowed_actions": ["pass", "fail"] if gate_status == "available" else [],
        "source_artifacts": source_artifacts,
        "last_verdict": _latest_verdict_from_events("eval_review", events, status),
        "reason": "",
        "missing_artifacts": [name for name, present in (("handoff", has_handoff), ("eval", has_eval)) if not present],
    }


def _projection_human_gates(status: dict, dashboard: dict, artifacts: list[dict], events: list[dict]) -> list[dict]:
    return [
        _plan_gate(status, dashboard, artifacts, events),
        _eval_gate(status, dashboard, artifacts, events),
    ]


def _projection_evaluation(status: dict, artifacts: list[dict]) -> dict:
    eval_artifact = _first_artifact(artifacts, "eval")
    handoff = _first_artifact(artifacts, "handoff")
    coverage = _first_artifact(artifacts, "coverage") or _artifact_by_name_part(artifacts, "coverage")
    acceptance = _first_artifact(artifacts, "acceptance_verdict") or _artifact_by_name_part(artifacts, "acceptance", "verdict")
    coverage_json = _read_artifact_json(coverage)
    acceptance_json = _read_artifact_json(acceptance)
    return {
        "status": status.get("status") or "",
        "phase": status.get("phase") or "",
        "handoff": _artifact_ref(handoff),
        "eval": _artifact_ref(eval_artifact),
        "coverage_report": _artifact_ref(coverage),
        "acceptance_verdict": _artifact_ref(acceptance),
        "verdict": acceptance_json.get("verdict") or "",
        "requested_verdict": acceptance_json.get("requested_verdict") or "",
        "reasons": acceptance_json.get("reasons") or [],
        "coverage_summary": coverage_json.get("summary") or coverage_json.get("coverage_summary") or {},
    }


def _terminal_sprint_status(status: str) -> bool:
    return status.strip().lower() in {"passed", "done", "completed", "failed", "cancelled", "eval_pass"}


def _descendant_node_ids(node_id: str, nodes: list[dict]) -> list[str]:
    children: dict[str, list[str]] = {}
    status_by_id: dict[str, str] = {}
    for node in nodes:
        nid = str(node.get("id") or node.get("node_id") or "")
        if not nid:
            continue
        status_by_id[nid] = str(node.get("status") or "")
        for dep in node.get("depends_on") or []:
            if isinstance(dep, str):
                children.setdefault(dep, []).append(nid)
    out: list[str] = []
    stack = list(children.get(node_id, []))
    while stack:
        child = stack.pop(0)
        if child in out:
            continue
        if _normalize_status(status_by_id.get(child)) not in {"passed", "completed"}:
            out.append(child)
        stack.extend(children.get(child, []))
    return out


def _capability_mismatch_projection(dashboard: dict) -> dict:
    data_nodes = (dashboard.get("dag") or {}).get("nodes") or []
    nodes = [node for node in data_nodes if isinstance(node, dict)]
    supply_rows = ((dashboard.get("capabilities") or {}).get("pane_supply") or [])
    available = sorted({
        cap.removeprefix("inferred:")
        for row in supply_rows
        if isinstance(row, dict)
        for cap in (row.get("provided_capabilities") or [])
        if isinstance(cap, str)
    })
    mismatches: list[dict] = []
    for node in nodes:
        nid = str(node.get("id") or node.get("node_id") or "")
        required = [cap for cap in (node.get("required_capabilities") or []) if isinstance(cap, str)]
        required_skills = [skill for skill in (node.get("required_skills") or []) if isinstance(skill, str)]
        missing = [cap for cap in (node.get("missing_capabilities") or []) if isinstance(cap, str)]
        missing_skills = [skill for skill in (node.get("missing_skills") or []) if isinstance(skill, str)]
        route_decision = str(node.get("route_decision") or node.get("decision") or "")
        blocked_reason = str(node.get("blocked_reason") or "")
        normalized_status = _normalize_status(str(node.get("status") or ""))
        no_match = "no_matching_worker" in f"{route_decision} {blocked_reason}"
        status_blocked = normalized_status in {"blocked", "failed", "gate_blocked", "worker_blocked"}
        if not no_match and not status_blocked:
            continue
        if no_match and required and not missing:
            missing = [cap for cap in required if cap not in available]
        if not missing and not no_match:
            continue
        mismatches.append({
            "node_id": nid,
            "goal": node.get("goal") or node.get("title") or "",
            "requested_role": node.get("requested_role") or "",
            "required_skills": required_skills,
            "required_capabilities": required,
            "missing_skills": missing_skills,
            "missing_capabilities": missing or required,
            "logical_operator": node.get("logical_operator") or "",
            "preferred_model": node.get("preferred_model") or "",
            "selected_operator_id": node.get("suggested_operator_id") or node.get("selected_operator_id") or "",
            "capability_capsule_id": node.get("capability_capsule_id") or "",
            "candidate_workers_seen": bool(node.get("candidate_workers_seen")),
            "role_candidates_seen": bool(node.get("role_candidates_seen")),
            "route_decision": route_decision,
            "blocked_reason": blocked_reason,
            "waiting_nodes": _descendant_node_ids(nid, nodes),
        })
    if not mismatches:
        return {
            "present": False,
            "blocked_nodes": [],
            "available_capabilities": available,
        }
    primary = mismatches[0]
    return {
        "present": True,
        "blocked_node": primary.get("node_id", ""),
        "missing_capability": (primary.get("missing_capabilities") or [""])[0],
        "blocked_nodes": mismatches,
        "available_capabilities": available,
    }


def _human_action_required(status: dict, dashboard: dict, artifacts: list[dict], capability_mismatch: dict) -> dict:
    sprint_status = str(status.get("status") or dashboard.get("sprint_status") or "").lower()
    phase = str(status.get("phase") or dashboard.get("phase") or "").lower()
    stall = dashboard.get("stall") or {}
    plan_ready = bool(_first_artifact(artifacts, "design") and _first_artifact(artifacts, "plan") and _first_artifact(artifacts, "task_graph"))
    if capability_mismatch.get("present") and stall.get("is_stalled"):
        missing = capability_mismatch.get("missing_capability") or "required capability"
        return {
            "type": "capability_mismatch",
            "severity": "blocked",
            "title": "Capability mismatch",
            "detail": f"No worker advertises {missing}.",
            "primary_artifact": _first_artifact(artifacts, "task_graph"),
        }
    # plan_review is only a real decision while the runtime is actually waiting
    # on it: a contracted graph's gates come from the contract (no human plan
    # gate — contracted runs self-advance), and once any node has left
    # "pending" the runtime has already consumed the plan. Without these two
    # guards the artifact heuristic below kept the card up for entire
    # contracted runs (P4 finding: 39 sightings, zero plan verdicts).
    contracted = bool(dashboard.get("workflow_contract_id"))
    # G4 UI-rung run 6: the card resurfaced on the GENERIC path during "Plan
    # compiling…" (6 sightings, zero plan verdicts in the ledger) — the
    # pre-planner template carries no workflow_contract_id yet. The governed
    # generic path never waits on a human plan review: autopilot advances
    # pm->planner->builder and the CERTIFICATE is the plan gate.
    governance = dashboard.get("plan_governance") if isinstance(dashboard.get("plan_governance"), dict) else {}
    governed_generic = str(governance.get("state") or "") in {
        "compiling", "certified", "plan_compile_failed", "plan_certificate_invalid",
    }
    dag = dashboard.get("dag") if isinstance(dashboard.get("dag"), dict) else {}
    build_started = any(
        _normalize_status(str(node.get("status") or "")) != "pending"
        for node in (dag.get("nodes") or [])
        if isinstance(node, dict)
    )
    if plan_ready and not contracted and not governed_generic and not build_started and (sprint_status in {"active", "planning"} or phase in {"planning", "planning_complete"}):
        return {
            "type": "plan_review",
            "severity": "decision",
            "title": "Review the plan",
            "detail": "Approve the planner output or request changes before build work continues.",
            "primary_artifact": _first_artifact(artifacts, "plan", "design", "task_graph"),
        }
    if sprint_status in {"reviewing", "ready_for_review"}:
        return {
            "type": "eval_review",
            "severity": "decision",
            "title": "Review evaluator output",
            "detail": "Accept the result or send fixes back to Builder.",
            "primary_artifact": _first_artifact(artifacts, "eval", "handoff"),
        }
    if sprint_status == "approved" and _first_artifact(artifacts, "handoff"):
        return {
            "type": "handoff_submit",
            "severity": "decision",
            "title": "Submit handoff for review",
            "detail": "A Builder handoff exists and can move to evaluator review.",
            "primary_artifact": _first_artifact(artifacts, "handoff"),
        }
    if sprint_status == "failed_review":
        return {
            "type": "builder_fixes",
            "severity": "decision",
            "title": "Builder fixes required",
            "detail": "Evaluator rejected the handoff; route the sprint back to Builder with the eval notes.",
            "primary_artifact": _first_artifact(artifacts, "eval"),
        }
    if stall.get("is_stalled"):
        return {
            "type": "stall_review",
            "severity": "blocked",
            "title": stall.get("title") or "Sprint stalled",
            "detail": stall.get("detail") or "The harness needs operator review before it can advance.",
            "primary_artifact": _first_artifact(artifacts, "status", "task_graph"),
        }
    if _terminal_sprint_status(sprint_status):
        return {
            "type": "none",
            "severity": "ok",
            "title": "No decision required",
            "detail": "The sprint is in a terminal state.",
            "primary_artifact": _first_artifact(artifacts, "handoff", "eval", "report"),
        }
    return {
        "type": "monitor",
        "severity": "info",
        "title": "Monitor progress",
        "detail": "No human gate is currently visible from status artifacts.",
        "primary_artifact": _first_artifact(artifacts, "status", "task_graph"),
    }


def _action(
    action_id: str,
    label: str,
    *,
    availability: str,
    safe: bool,
    enabled: bool,
    effect: str,
    endpoint: str = "",
    method: str = "",
    cli_command: str = "",
    reason: str = "",
) -> dict:
    return {
        "id": action_id,
        "label": label,
        "availability": availability,
        "safe": safe,
        "enabled": enabled,
        "endpoint": endpoint,
        "method": method,
        "cli_command": cli_command,
        "effect": effect,
        "reason": reason,
    }


def _unsupported_actions(capability_mismatch: dict) -> list[dict]:
    retry_reason = (
        "Retrying the same dispatch would repeat the same worker match; it does not re-plan or repair the missing capability."
        if capability_mismatch.get("present")
        else "Dispatch retry needs a verified state transition before it can be exposed safely."
    )
    return [
        _action(
            "cancel",
            "Cancel sprint",
            availability="unsupported_deferred",
            safe=False,
            enabled=False,
            effect="Would stop or mark a sprint cancelled.",
            reason="No safe status-server endpoint or process/state cancellation contract has been verified.",
        ),
        _action(
            "retry_dispatch",
            "Retry dispatch",
            availability="unsafe_or_needs_engine_work",
            safe=False,
            enabled=False,
            effect="Would re-attempt worker matching for a blocked node.",
            reason=retry_reason,
        ),
        _action(
            "retry_node",
            "Retry node",
            availability="unsupported_deferred",
            safe=False,
            enabled=False,
            effect="Would re-run a failed node.",
            reason="Node retry semantics and evaluator/gate side effects are not verified safe.",
        ),
        _action(
            "skip_node",
            "Skip node",
            availability="unsafe_or_needs_engine_work",
            safe=False,
            enabled=False,
            effect="Would mark a node skipped.",
            reason="Skipping can break downstream DAG dependencies unless the engine proves it is safe.",
        ),
        _action(
            "mid_run_steering",
            "Send live guidance",
            availability="unsupported_deferred",
            safe=False,
            enabled=False,
            effect="Would steer a running agent.",
            reason="Raw Solar has no live mid-run steering channel.",
        ),
        _action(
            "capability_repair",
            "Repair capability mismatch",
            availability="unsafe_or_needs_engine_work",
            safe=False,
            enabled=False,
            effect="Would change planner/scheduler capability behavior.",
            reason="Capability repair crosses into engine behavior and needs owner approval.",
        ),
        _action(
            "wake",
            "Wake sprint",
            availability="unsupported_deferred",
            safe=False,
            enabled=False,
            effect="Would route the sprint through the wake state machine.",
            cli_command="solar harness wake <sprint-id>",
            reason="The raw command exists, but no safe dashboard endpoint is part of this backend sprint.",
        ),
    ]


def _available_actions(status: dict, human_action: dict, capability_mismatch: dict, sid: str = "") -> list[dict]:
    sprint_status = str(status.get("status") or "").lower()
    terminal = _terminal_sprint_status(sprint_status)
    actions: list[dict] = [
        _action(
            "view_artifacts",
            "View artifacts",
            availability="supported_now",
            safe=True,
            enabled=True,
            effect="Read-only artifact review.",
        )
    ]
    if human_action.get("type") == "plan_review":
        for verdict in ("approve", "reject"):
            actions.append(_action(
                f"plan_{verdict}",
                f"{verdict.title()} plan",
                availability="supported_now",
                safe=True,
                enabled=True,
                method="POST",
                endpoint=f"/api/sprints/{urllib.parse.quote(sid)}/plan-verdict" if sid else "/api/sprints/<sid>/plan-verdict",
                cli_command=f"solar harness plan-verdict <sprint-id> {verdict} <reason>",
                effect="Applies the existing atomic plan verdict state transition.",
            ))
    if human_action.get("type") == "handoff_submit":
        actions.append(_action(
            "handoff_submit",
            "Submit handoff",
            availability="supported_now",
            safe=True,
            enabled=True,
            method="POST",
            endpoint=f"/api/sprints/{urllib.parse.quote(sid)}/handoff-submit" if sid else "/api/sprints/<sid>/handoff-submit",
            cli_command="solar harness handoff-submit <sprint-id>",
            effect="Moves the sprint to evaluator review through the existing atomic command.",
        ))
    if human_action.get("type") == "eval_review":
        for verdict in ("pass", "fail"):
            actions.append(_action(
                f"eval_{verdict}",
                f"Eval {verdict}",
                availability="supported_now",
                safe=True,
                enabled=True,
                method="POST",
                endpoint=f"/api/sprints/{urllib.parse.quote(sid)}/eval-verdict" if sid else "/api/sprints/<sid>/eval-verdict",
                cli_command=f"solar harness eval-verdict <sprint-id> {verdict} <reason>",
                effect="Applies the existing atomic eval verdict state transition.",
            ))
    actions.append(_action(
        "edit_rerun",
        "Edit guidance and re-run",
        availability="supported_now",
        safe=True,
        enabled=not terminal,
        method="POST",
        endpoint="/intake",
        effect="Starts a new intake with revised guidance; does not steer the running agent.",
        reason="Disabled for terminal sprints." if terminal else "",
    ))
    actions.extend(_unsupported_actions(capability_mismatch))
    return actions


def _runtime_health_projection(dashboard: dict) -> list[dict]:
    rows: list[dict] = []
    for row in ((dashboard.get("capabilities") or {}).get("pane_supply") or []):
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or "").lower()
        if any(token in state for token in ("auth", "quota", "permission", "survey", "blocked", "error")):
            readiness = "blocked"
        elif any(token in state for token in ("running", "active", "dispatched", "busy", "in_progress")):
            readiness = "busy"
        elif any(token in state for token in ("idle", "ready", "waiting")):
            readiness = "ready"
        else:
            readiness = "unknown"
        rows.append({
            "pane_id": row.get("pane_id") or "",
            "role": row.get("role") or "",
            "state": row.get("state") or "",
            "model": row.get("model") or "",
            "readiness": readiness,
            "actor_id": row.get("actor_id") or "",
            "host_type": row.get("host_type") or "",
            "lease_state": row.get("lease_state") or "",
        })
    return rows


def _load_physical_operator_rows() -> list[dict]:
    data, ok = _read_json(HARNESS_DIR / "config" / "physical-operators.json")
    operators = data.get("operators", {}) if ok and isinstance(data, dict) else {}
    if not isinstance(operators, dict):
        return []
    rows: list[dict] = []
    for operator_id, cfg in operators.items():
        if not isinstance(cfg, dict):
            continue
        state_cfg = cfg.get("state") if isinstance(cfg.get("state"), dict) else {}
        auth_cfg = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
        quota_cfg = cfg.get("quota") if isinstance(cfg.get("quota"), dict) else {}
        surface_cfg = cfg.get("surface") if isinstance(cfg.get("surface"), dict) else {}
        model_binding = cfg.get("model_binding") if isinstance(cfg.get("model_binding"), dict) else {}
        runtime_state = str(
            cfg.get("runtime_state")
            or state_cfg.get("runtime_state")
            or ("disabled" if cfg.get("enabled") is False else "")
            or "idle"
        )
        quota_state = str(cfg.get("quota_guard_state") or quota_cfg.get("state") or "ok")
        auth_mode = str(cfg.get("auth_mode") or auth_cfg.get("mode") or "")
        key_ref = str(cfg.get("key_ref") or auth_cfg.get("secret_ref") or auth_cfg.get("key_env") or "")
        if runtime_state == "auth_expired" or quota_state == "auth_expired":
            auth_state = "auth_expired"
        elif auth_mode in {"api_key", "oauth", "subscription", "subscription_cli"} and not key_ref:
            auth_state = "key_ref_missing"
        elif auth_mode:
            auth_state = "configured"
        else:
            auth_state = "unknown"
        rows.append({
            "operator_id": str(operator_id),
            "display_name": str(cfg.get("display_name") or operator_id),
            "role": str(cfg.get("role") or cfg.get("persona") or ""),
            "roles": cfg.get("roles") if isinstance(cfg.get("roles"), list) else [],
            "backend": str(cfg.get("backend") or surface_cfg.get("tool") or ""),
            "model": str(cfg.get("model") or model_binding.get("model_id") or ""),
            "enabled": cfg.get("enabled") is not False,
            "available": cfg.get("available") is not False,
            "runtime_state": runtime_state,
            "quota_state": quota_state,
            "auth_mode": auth_mode,
            "auth_state": auth_state,
            "pane": str(cfg.get("pane") or ""),
            "capabilities": sorted(str(k) for k, v in (cfg.get("capability") or cfg.get("capability_profile") or {}).items() if isinstance(v, (int, float)) and v),
        })
    rows.sort(key=lambda item: (str(item.get("role") or ""), str(item.get("operator_id") or "")))
    return rows


def _operator_readiness_projection(dashboard: dict) -> list[dict]:
    pane_rows = _runtime_health_projection(dashboard)
    by_actor = {str(row.get("actor_id") or ""): row for row in pane_rows if str(row.get("actor_id") or "")}
    rows: list[dict] = []
    seen: set[str] = set()
    for op in _load_physical_operator_rows():
        actor_row = by_actor.get(str(op.get("operator_id") or "")) or {}
        runtime_state = str(actor_row.get("state") or op.get("runtime_state") or "unknown")
        if op.get("auth_state") == "auth_expired" or runtime_state == "auth_expired":
            readiness = "auth_blocked"
        elif str(op.get("quota_state") or "") in {"cooldown", "quota_exhausted"} or runtime_state in {"cooldown", "quota_exhausted"}:
            readiness = "quota_blocked"
        elif runtime_state in {"leased", "running", "draining"} or actor_row.get("readiness") == "busy":
            readiness = "busy"
        elif op.get("enabled") and op.get("available") and runtime_state in {"idle", "ready", "waiting", "unknown"}:
            readiness = "ready"
        elif not op.get("enabled") or runtime_state == "disabled":
            readiness = "disabled"
        else:
            readiness = "unknown"
        row = {
            **op,
            "pane_id": actor_row.get("pane_id") or op.get("pane") or "",
            "operator_runtime_state": runtime_state,
            "readiness": readiness,
        }
        rows.append(row)
        seen.add(str(op.get("operator_id") or ""))
    for pane in pane_rows:
        actor_id = str(pane.get("actor_id") or "")
        if actor_id and actor_id in seen:
            continue
        rows.append({
            "operator_id": actor_id or str(pane.get("pane_id") or ""),
            "display_name": actor_id or str(pane.get("pane_id") or ""),
            "role": pane.get("role") or "",
            "roles": [pane.get("role")] if pane.get("role") else [],
            "backend": "pane",
            "model": pane.get("model") or "",
            "enabled": True,
            "available": pane.get("readiness") != "blocked",
            "runtime_state": pane.get("state") or "",
            "operator_runtime_state": pane.get("state") or "",
            "quota_state": "unknown",
            "auth_mode": "",
            "auth_state": "unknown",
            "pane_id": pane.get("pane_id") or "",
            "readiness": pane.get("readiness") or "unknown",
            "capabilities": [],
        })
    return rows


def _projection_events(sid: str, limit: int = 80) -> list[dict]:
    paths = [
        SESSIONS_DIR / sid / "events.jsonl",
        SPRINTS_DIR / f"{sid}.events.jsonl",
        EVENTS_JSONL,
        HARNESS_DIR / "events" / "all.jsonl",
    ]
    for path in paths:
        if not path.exists():
            continue
        events: list[dict] = []
        scoped_path = path == SESSIONS_DIR / sid / "events.jsonl" or path == SPRINTS_DIR / f"{sid}.events.jsonl"
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if not isinstance(ev, dict):
                    continue
                event_sid = str(ev.get("sprint_id") or "").strip()
                if scoped_path:
                    if event_sid and event_sid != sid:
                        continue
                    next_ev = dict(ev)
                    next_ev["sprint_id"] = sid
                    next_ev["_event_scope"] = "requested"
                    next_ev["_event_source"] = "session_file" if path == SESSIONS_DIR / sid / "events.jsonl" else "sprint_file"
                    events.append(next_ev)
                elif event_sid == sid:
                    next_ev = dict(ev)
                    next_ev["_event_scope"] = "requested"
                    next_ev["_event_source"] = "global_file"
                    events.append(next_ev)
        except OSError:
            continue
        if events:
            return events[-limit:]
    return []


def _timeline_title(event_type: str, actor: str, payload: dict) -> str:
    decision = str(payload.get("decision") or "")
    node = str(payload.get("node_id") or payload.get("node") or "")
    if "intake" in event_type:
        return "Task intake recorded"
    if "plan_verdict" in event_type:
        return "Plan verdict recorded"
    if "eval_pass" in event_type or "eval_failed" in event_type:
        return "Evaluator verdict recorded"
    if "handoff" in event_type:
        return "Builder handoff recorded"
    if "dispatch" in event_type and "no_matching" in decision:
        return f"Dispatch blocked{f' for {node}' if node else ''}"
    if "dispatch" in event_type:
        return f"{actor} dispatch decision"
    if "model_session_started" in event_type:
        return f"{actor} started work"
    if "model_session_ended" in event_type:
        return f"{actor} finished work"
    return event_type.replace("_", " ").title()


def _timeline_from_events(events: list[dict], dashboard: dict, generated_at: str) -> list[dict]:
    rows: list[dict] = []
    for index, event in enumerate(events):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
        event_type = str(event.get("type") or event.get("event") or "event")
        actor = str(event.get("actor") or event.get("role") or payload.get("actor") or "Harness")
        decision = str(payload.get("decision") or event.get("decision") or "")
        reason = str(payload.get("reason") or payload.get("blocked_reason") or event.get("reason") or "")
        tone = "blocked" if "blocked" in event_type or "no_matching" in f"{decision} {reason}" else "complete"
        rows.append({
            "id": f"event-{index}",
            "source": "event",
            "ts": event.get("ts") or event.get("timestamp") or event.get("time") or "",
            "actor": actor,
            "title": _timeline_title(event_type, actor, payload),
            "summary": reason or str(payload.get("message") or event.get("message") or decision or ""),
            "tone": tone,
            "event_type": event_type,
        })
    if rows:
        return rows
    for index, node in enumerate((dashboard.get("dag") or {}).get("nodes") or []):
        if not isinstance(node, dict):
            continue
        status = str(node.get("status") or "pending")
        tone = "blocked" if _normalize_status(status) in {"blocked", "failed"} else "complete" if _normalize_status(status) == "passed" else "idle"
        nid = str(node.get("id") or node.get("node_id") or f"N{index + 1}")
        rows.append({
            "id": f"node-{nid}",
            "source": "dag",
            "ts": generated_at,
            "actor": "Planner",
            "title": f"{nid} is {status.replace('_', ' ')}",
            "summary": str(node.get("goal") or node.get("title") or ""),
            "tone": tone,
            "event_type": "dag_node",
        })
    return rows


# Machine-noise tokens that never belong in the human narrative.
_NARRATIVE_DROP = ("autopilot_", "kb_probe", "route_normalized", "doctor_", "ipv4_", "heartbeat")


def _event_token(event: dict, payload: dict) -> str:
    """The real coordinator action token. The runtime wraps events as 'log_message'
    with the actual token in payload.legacy_event; its command/activity sibling carries
    the same legacy_event — so reading this first lets us collapse the double-write."""
    legacy = payload.get("legacy_event")
    if isinstance(legacy, str) and legacy:
        return legacy
    return str(event.get("type") or event.get("event") or "event")


def _narrative_role(payload: dict, event: dict) -> str:
    raw = str(
        payload.get("role")
        or payload.get("target_role")
        or event.get("role")
        or payload.get("actor")
        or event.get("actor")
        or ""
    ).lower()
    if "plan" in raw:
        return "Planner"
    if "build" in raw or "impl" in raw:
        return "Builder"
    if "eval" in raw or "judge" in raw or "review" in raw:
        return "Evaluator"
    if raw == "pm" or "product" in raw or "manager" in raw:
        return "PM"
    if not raw or raw in {"coordinator", "harness", "autopilot", "solar-autopilot"}:
        return "Coordinator"
    return raw.title()


def _clean_to_state(to_status: str) -> str:
    """A state_changed `to` is often '<sid>:<status>:<phase>:<role>:<hash>' — surface just the
    status/phase so the narrative reads 'Moved to active / planning_complete', not a raw blob."""
    if ":" not in to_status:
        return to_status
    parts = [p for p in to_status.split(":") if p and p not in ("_", "None")]
    if parts and parts[0].startswith("sprint-"):
        parts = parts[1:]
    return " / ".join(parts[:2]) if parts else to_status


def _narrative_title(token: str, role: str, node: str, phase: str, decision: str, to_status: str) -> str:
    """Map an internal coordinator token to a plain human title."""
    t = token.lower()
    n = f" {node}" if node else ""
    who = role if role and role != "Coordinator" else ""
    if "intake" in t:
        return "Task scoped"
    if "plan_verdict" in t:
        return "Plan verdict recorded"
    if "eval_pass" in t:
        return "Result accepted"
    if "eval_fail" in t:
        return "Sent back for fixes"
    if "handoff" in t:
        return f"{who or 'Builder'} handed off{n}".strip()
    if "no_matching" in decision or ("dispatch" in t and "fail" in t):
        return f"Dispatch blocked{n}"
    if t in {"dispatched", "round_dispatched", "slice_dispatched", "mixture_dispatched", "graph_nodes_dispatched", "dispatch_queued"}:
        return f"Routed{n}{f' to {who}' if who else ''}"
    if "planner_notified" in t:
        return "Planner notified"
    if "model_session_started" in t:
        return f"{who or 'Agent'} started work{n}".strip()
    if "model_session_ended" in t:
        return f"{who or 'Agent'} finished work{n}".strip()
    if t in {"handle_passed_completed", "graph_parent_ready_passed"}:
        return f"{who or 'Agent'} completed{n}".strip()
    if t in {"parallel_integrated", "mixture_merged"}:
        return "Work integrated"
    if "state_chang" in t or "phase_transition" in t:
        dest = to_status or phase
        return f"Moved to {dest}".strip() if dest else "State changed"
    if "phase" in t:
        return f"Phase: {phase}".strip() if phase else "Phase advanced"
    return token.replace("_", " ").strip().capitalize() or "Event"


def _narrative_tone(token: str, decision: str, to_status: str) -> str:
    blob = f"{token} {decision} {to_status}".lower()
    if "fail" in blob or "blocked" in blob or "no_matching" in blob or "error" in blob:
        return "blocked"
    if any(word in blob for word in ("passed", "completed", "accepted", "ended", "integrated", "done", "ready")):
        return "complete"
    return "working"


def _narrative_from_events(events: list[dict], limit: int = 60) -> list[dict]:
    """A de-noised, de-duplicated human narrative from the raw coordinator event stream.
    Each real action is double-written (a log_message plus a command/activity event, both
    carrying payload.legacy_event); we collapse those to one step, map the internal token to
    a human title, and drop machine noise — so the UI shows a story, not a jargon wall."""
    rows: list[dict] = []
    seen: set = set()
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        token = _event_token(event, payload)
        tl = token.lower()
        actor_raw = str(event.get("actor") or payload.get("actor") or "").lower()
        if tl.startswith(_NARRATIVE_DROP) or actor_raw == "solar-autopilot":
            continue
        node = str(payload.get("node_id") or payload.get("node") or event.get("node_id") or "")
        role = _narrative_role(payload, event)
        phase = str(payload.get("phase") or event.get("phase") or "")
        decision = str(payload.get("decision") or event.get("decision") or "")
        to_status = _clean_to_state(str(payload.get("to") or payload.get("status") or ""))
        round_num = str(payload.get("round") or "")
        ts = str(event.get("ts") or event.get("timestamp") or event.get("time") or "")
        reason = str(payload.get("reason") or payload.get("blocked_reason") or event.get("reason") or "")
        message = str(
            payload.get("message") or payload.get("summary") or payload.get("text")
            or event.get("message") or payload.get("thought") or ""
        ).strip()
        # A bare log_message / event envelope with no action token and no message is internal
        # noise (its meaningful form is dual-written as a structured event). Dropping it keeps
        # the narrative a story instead of a wall of "Log message" — the dominant real-world shape.
        if token in {"log_message", "event"} and not message:
            continue
        # Collapse the dual-write: the same token+node+role+round is one human step.
        key = (token, node, role, round_num or ts[:19])
        if key in seen:
            continue
        seen.add(key)
        title = _narrative_title(token, role, node, phase, decision, to_status)
        summary = reason or decision.replace("_", " ")
        if token in {"log_message", "event"} and message:
            title = message[:100]
        elif message and not summary:
            summary = message
        rows.append({
            "id": f"{ts}-{token}-{node}",
            "ts": ts,
            "role": role,
            "actor": role,
            "node_id": node,
            "title": title,
            "summary": summary[:240],
            "tone": _narrative_tone(token, decision, to_status),
            "token": token,
            "phase": phase,
        })
    return rows[-limit:]


def _projection_lazy_slices(sid: str) -> dict:
    quoted = urllib.parse.quote(sid) if sid else ""
    return {
        "events": f"/events?sprint_id={quoted}&limit=140" if sid else "/events?limit=140",
        "deliverables": f"/sprints/{quoted}/deliverables" if sid else "",
        "usage": "/usage",
    }


def build_projection_payload(sprint_id: str | None = None, mode: str = "full") -> tuple[dict, list[str]]:
    projection_mode = "fast" if str(mode or "").strip().lower() in {"fast", "summary"} else "full"
    dashboard, degraded = build_dashboard_payload(sprint_id)
    sid = str(dashboard.get("focus_sprint_id") or sprint_id or "")
    status = _load_status_by_sprint(sid) if sid else {}
    if sid and not status:
        degraded.append(f"sprint_status:missing:{sid}")
    artifacts = _projection_artifacts(sid)
    capability_mismatch = _capability_mismatch_projection(dashboard)
    human_action = _human_action_required(status, dashboard, artifacts, capability_mismatch)
    generated_at = _now()
    events = [] if projection_mode == "fast" else _projection_events(sid)
    timeline = [] if projection_mode == "fast" else _timeline_from_events(events, dashboard, generated_at)
    # The de-noised narrative is compact, so it ships in BOTH modes (the client renders it
    # instead of reverse-engineering the raw /events wall). Read independently of `events`,
    # which stays empty in fast mode.
    narrative = _narrative_from_events(_projection_events(sid, limit=160)) if sid else []
    requirements = _projection_requirements(sid, artifacts)
    plan = _projection_plan(dashboard, artifacts)
    task_graph = _projection_task_graph(dashboard)
    human_gates = _projection_human_gates(status, dashboard, artifacts, events)
    operators = _operator_readiness_projection(dashboard)
    evaluation = _projection_evaluation(status, artifacts)
    return {
        "projection_schema": "solar.dashboard_projection.v1",
        "projection_mode": projection_mode,
        "sprint_id": sid,
        "title": _clean_sprint_title(sid, dashboard.get("title") or status.get("title") or ""),
        "status": status.get("status") or dashboard.get("sprint_status") or "",
        "phase": status.get("phase") or dashboard.get("phase") or "",
        "lazy_slices": _projection_lazy_slices(sid),
        "sprint": {
            "sprint_id": sid,
            "epic_id": dashboard.get("epic_id") or status.get("epic_id") or "",
            "title": _clean_sprint_title(sid, dashboard.get("title") or status.get("title") or ""),
            "status": status.get("status") or dashboard.get("sprint_status") or "",
            "phase": status.get("phase") or dashboard.get("phase") or "",
            "raw_status": status,
        },
        "plan_governance": dashboard.get("plan_governance") or {},
        "requirements": requirements,
        "plan": plan,
        "task_graph": task_graph,
        "nodes": task_graph.get("nodes") or [],
        "dependencies": task_graph.get("edges") or [],
        "dispatch": {
            "resources": dashboard.get("resources") or {},
            "blocker_diagnostics": dashboard.get("blocker_diagnostics") or [],
            "stall": dashboard.get("stall") or {},
            "capability_mismatch": capability_mismatch,
        },
        "operators": operators,
        "human_gates": human_gates,
        "evaluation": evaluation,
        "events": events,
        "narrative": narrative,
        "summary": {
            "progress": dashboard.get("progress") or {},
            "stall": dashboard.get("stall") or {},
            "active_node": next((node.get("id") for node in (dashboard.get("dag") or {}).get("nodes", []) if isinstance(node, dict) and _normalize_status(str(node.get("status") or "")) == "active"), ""),
        },
        "human_action_required": human_action,
        "available_actions": _available_actions(status, human_action, capability_mismatch, sid),
        "capability_mismatch": capability_mismatch,
        "artifacts": artifacts,
        "runtime_health": _runtime_health_projection(dashboard),
        "timeline": timeline,
        "sources": dashboard.get("generated_from") or {},
        "degraded_sources": list(degraded),
    }, degraded


def build_dashboard_payload(sprint_id: str | None = None) -> tuple[dict, list[str]]:
    degraded: list[str] = []
    active = _active_sprint_ids()
    sid = sprint_id or (active[0] if active else "")
    status = _load_status_by_sprint(sid) if sid else {}
    if not sid or not status:
        degraded.append("sprint_status:missing")

    tg, tg_ok = _load_task_graph(sid) if sid else ({}, False)
    if sid and not tg_ok:
        degraded.append(f"task_graph:missing:{sid}")
    nodes = tg.get("nodes") or []
    if not isinstance(nodes, list):
        nodes = []
        degraded.append(f"task_graph:nodes_invalid:{sid}")

    routing = _load_autopilot_routing(sid) if sid else []
    all_routing = _load_routing_decisions()
    panes = _load_pane_state()
    registry = _capability_registry()
    node_cards = _build_node_cards(sid, nodes, tg.get("runtime_state") or {}, routing)
    diagnostics = _build_blocker_diagnostics(sid, status, nodes, node_cards, tg_ok)
    plan_governance = _build_plan_governance(sid, status, tg)
    stall = _build_stall_summary(
        status,
        node_cards,
        diagnostics,
        tg_ok,
        events=_recent_sprint_events(sid),
        plan_governance=plan_governance,
    )

    status_counts: dict[str, int] = {}
    cost_by_status: dict[str, float] = {}
    total_cost = 0.0
    for card in node_cards:
        st = card["status"]
        cost = float(card.get("estimated_cost") or 0)
        status_counts[st] = status_counts.get(st, 0) + 1
        cost_by_status[st] = cost_by_status.get(st, 0.0) + cost
        total_cost += cost

    return {
        "focus_sprint_id": sid,
        "active_sprints": active,
        "epic_id": status.get("epic_id", ""),
        "title": status.get("title", ""),
        "sprint_status": status.get("status", ""),
        "phase": status.get("phase", ""),
        "workflow_contract_id": str(tg.get("workflow_contract_id") or ""),
        "plan_governance": plan_governance,
        "generated_from": {
            "status_json": _display_path(SPRINTS_DIR / f"{sid}.status.json") if sid else "",
            "task_graph_json": _display_path(_existing_task_graph_path(sid)) if sid else "",
            "autopilot_state": _display_path(STATE_DIR / "autopilot-state.json"),
            "pane_state": _display_path(STATE_DIR / "pane-state.json"),
        },
        "progress": {
            "total_nodes": len(node_cards),
            "status_counts": status_counts,
            "passed_nodes": status_counts.get("passed", 0),
            "blocked_nodes": status_counts.get("blocked", 0) + status_counts.get("gate_blocked", 0) + status_counts.get("failed", 0),
            "active_nodes": status_counts.get("active", 0),
        },
        "dag": {
            "required_gates": tg.get("required_gates") or [],
            "nodes": node_cards,
            "edges": [
                {"from": dep, "to": card["id"]}
                for card in node_cards
                for dep in card.get("depends_on", [])
            ],
        },
        "capabilities": {
            "demand": _capability_counts(nodes),
            "role_demand": _role_counts(nodes),
            "pane_supply": _build_pane_supply(panes, registry),
        },
        "resources": {
            "estimated_total_cost": total_cost,
            "cost_by_status": cost_by_status,
            "routing_records_for_sprint": len(routing),
            "routing_records_total": len(all_routing),
            "busy_panes": sorted({r.get("target_pane") for r in all_routing if r.get("decision") == "dispatched" and r.get("target_pane")}),
        },
        "blocker_diagnostics": diagnostics,
        "stall": stall,
    }, degraded


def _build_plan_governance(sid: str, status: dict, tg: dict) -> dict:
    """G4 spec §3: the generic path's governance facts, surfaced truthfully.

    Everything derives from files the runtime actually writes (status.json,
    task_graph.json, <sid>.plan-compile-errors.json) — never heuristics
    (failure class 14). States:
      certified                -> stamped pm.generic.v1 + certificate PASS
      compiling                -> intake-born graph, not yet stamped (NEUTRAL:
                                  planner in flight / bounce loop teaching)
      plan_compile_failed      -> truthful terminal (bounces exhausted)
      plan_certificate_invalid -> truthful terminal (post-PASS mutation)
      contracted               -> fixed workflow contract (its own gates)
      epic                     -> epic decomposition graph
      legacy                   -> unmarked uncontracted (grandfathered)
    """
    contract_id = str(tg.get("workflow_contract_id") or "").strip()
    cert = tg.get("plan_certificate") if isinstance(tg.get("plan_certificate"), dict) else {}
    # The requirement compiler owns this provenance.  Planner output may
    # replace task_graph.json wholesale, so status.json is the durable source;
    # the graph copy remains supported for older/in-flight records.
    birth_marker = bool(
        tg.get("plan_compile_required") or status.get("plan_compile_required")
    )
    schema = str(tg.get("schema_version") or "")
    sprint_status = str(status.get("status") or "").strip().lower()
    phase = str(status.get("phase") or "").strip().lower()
    try:
        bounces = int(status.get("plan_compile_bounces") or 0)
    except (TypeError, ValueError):
        bounces = 0
    error_codes: list[str] = []
    if sid:
        try:
            payload = json.loads(
                (SPRINTS_DIR / f"{sid}.plan-compile-errors.json").read_text(encoding="utf-8")
            )
            for error in payload.get("errors") or []:
                if isinstance(error, dict) and str(error.get("code") or "").strip():
                    error_codes.append(str(error["code"]))
        except (OSError, ValueError):
            pass
    certified = contract_id == "pm.generic.v1" and str(cert.get("verdict") or "").upper() == "PASS"
    if sprint_status == "failed" and phase == "plan_compile_failed":
        state = "plan_compile_failed"
    elif sprint_status == "failed" and phase == "plan_certificate_invalid":
        state = "plan_certificate_invalid"
    elif schema.startswith("solar.epic."):
        state = "epic"
    elif contract_id and contract_id != "pm.generic.v1":
        state = "contracted"
    elif certified:
        state = "certified"
    elif contract_id == "pm.generic.v1" or birth_marker:
        state = "compiling"
    else:
        state = "legacy"
    return {
        "state": state,
        "certified": certified,
        "certificate": {
            "present": bool(cert),
            "verdict": str(cert.get("verdict") or ""),
            "validated_at": str(cert.get("validated_at") or ""),
            "graph_hash": str(cert.get("graph_hash") or "")[:12],
        },
        "plan_compile_bounces": bounces,
        "compile_error_codes": error_codes[:6],
        "birth_marker": birth_marker,
        "workflow_contract_id": contract_id,
    }


def build_sprint_index_payload(limit: int = 80) -> tuple[dict, list[str]]:
    degraded: list[str] = []
    if not SPRINTS_DIR.exists():
        degraded.append("sprints_dir:missing")
    rows = _sprint_status_rows(limit=limit)
    return {
        "sprints": rows,
        "count": len(rows),
        "active_sprints": [row["sprint_id"] for row in rows if row.get("is_active")],
    }, degraded


def _build_pane_supply(panes: list[dict], registry: dict[str, list[str]]) -> list[dict]:
    supply: list[dict] = []
    for p in panes:
        pane_id = str(p.get("id") or "")
        provided = registry.get(pane_id, [])
        actorhost = _actorhost_for_pane(pane_id, provided)
        supply.append({
            "pane_id": pane_id,
            "role": p.get("role", ""),
            "state": p.get("state", ""),
            "model": p.get("model", ""),
            "provided_capabilities": provided,
            "pane_carrier": {
                "pane_id": pane_id,
                "role": p.get("role", ""),
                "state": p.get("state", ""),
                "model": p.get("model", ""),
            },
            "actorhost": actorhost,
            "actor_id": actorhost.get("actor_id", "N/A"),
            "host_id": actorhost.get("host_id", "N/A"),
            "host_type": actorhost.get("host_type", "unknown"),
            "lease_state": actorhost.get("lease_state", "unknown"),
            "capability_match": actorhost.get("capability_match") or {},
        })
    return supply


def _list_epics() -> list[dict]:
    """Return lightweight list of known epic IDs from sprints dir."""
    seen: set[str] = set()
    epics: list[dict] = []
    for sf in sorted(SPRINTS_DIR.glob("*.status.json")):
        try:
            s = json.loads(sf.read_text())
        except Exception:
            continue
        epic_id = s.get("epic_id", "")
        if epic_id and epic_id not in seen:
            seen.add(epic_id)
            epics.append({"epic_id": epic_id, "sprint_count": 0})
    # Count child sprints per epic
    counts: dict[str, int] = {}
    for e in epics:
        eid = e["epic_id"]
        counts[eid] = sum(
            1 for sf in SPRINTS_DIR.glob("*.status.json")
            if eid in sf.name
        )
        e["sprint_count"] = counts[eid]
    return epics


def _load_child_sprints(epic_id: str) -> list[dict]:
    children: list[dict] = []
    for sf in sorted(SPRINTS_DIR.glob("*.status.json")):
        try:
            s = json.loads(sf.read_text())
        except Exception:
            continue
        if s.get("epic_id", "") == epic_id:
            children.append({
                "sprint_id": s.get("sprint_id", sf.stem.replace(".status", "")),
                "title": s.get("title", ""),
                "status": s.get("status", ""),
                "phase": s.get("phase", ""),
                "priority": s.get("priority", ""),
                "blocked_by": _extract_blocked_by(s),
            })
    return children


def _extract_blocked_by(status: dict) -> list[str]:
    blocked: list[str] = []
    for h in status.get("history", []):
        if h.get("event", "").startswith("autopilot_epic_child_dependency_blocked"):
            for b in h.get("blocked_by", []):
                if b not in blocked:
                    blocked.append(b)
    return blocked


def _gate_summary(children: list[dict]) -> dict:
    passed = sum(1 for c in children if c["status"] in {"passed", "completed"})
    blocked = sum(1 for c in children if c["blocked_by"])
    active = sum(1 for c in children if c["status"] == "active")
    return {"total": len(children), "passed": passed, "active": active, "blocked": blocked}


def _load_autopilot_routing(sprint_id: str) -> list[dict]:
    ap_path = STATE_DIR / "autopilot-state.json"
    data, ok = _read_json(ap_path)
    if not ok or not data:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict) and d.get("sprint_id") == sprint_id]
    if not isinstance(data, dict):
        return []
    decisions = data.get("routing_decisions", [])
    return [d for d in decisions if isinstance(d, dict) and d.get("sprint_id") == sprint_id] if isinstance(decisions, list) else []


def _load_pane_state() -> list[dict]:
    ps, ok = _read_json(STATE_DIR / "pane-state.json")
    if not ok:
        return []
    if isinstance(ps, list):
        return [pane for pane in ps if isinstance(pane, dict)]
    if not isinstance(ps, dict):
        return []
    panes = ps.get("panes", [])
    if isinstance(panes, list):
        return [pane for pane in panes if isinstance(pane, dict)]
    if isinstance(panes, dict):
        return [{"id": k, **v} for k, v in panes.items() if isinstance(v, dict)]
    return []


def _capability_registry() -> dict[str, list[str]]:
    """Build pane_id -> capability list from role-based defaults."""
    import sys
    if str(HARNESS_DIR / "lib") not in sys.path:
        sys.path.insert(0, str(HARNESS_DIR / "lib"))
    try:
        from autopilot import _load_capability_registry
        return _load_capability_registry()
    except Exception:
        return {}


def _safe_sprint_id(sid: str) -> bool:
    return bool(SAFE_SPRINT_ID_RE.fullmatch(str(sid or "")))


def _solar_harness_command_prefix() -> list[str]:
    solar = shutil.which("solar")
    if solar:
        return [solar, "harness"]
    local_solar = Path.home() / ".solar" / "bin" / "solar"
    if local_solar.exists():
        return [str(local_solar), "harness"]
    harness = shutil.which("solar-harness")
    if harness:
        return [harness]
    local_harness = HARNESS_DIR / "solar-harness.sh"
    return [str(local_harness)]


def _command_exists(cmd0: str) -> bool:
    return Path(cmd0).exists() or shutil.which(cmd0) is not None


def _verdict_payload(kind: str, sid: str, data: dict) -> tuple[dict, int]:
    if not _safe_sprint_id(sid):
        return {"ok": False, "status": "error", "error": "invalid_sprint_id"}, 400
    if not isinstance(data, dict):
        return {"ok": False, "status": "error", "error": "invalid_json_body"}, 400
    verdict = str(data.get("verdict") or data.get("action") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()
    if len(reason) > 4000:
        return {"ok": False, "status": "error", "error": "reason_too_long", "max_chars": 4000}, 400

    if kind == "plan":
        allowed = {"approve", "reject"}
        command_name = "plan-verdict"
        reason_required = verdict == "reject"
    else:
        allowed = {"pass", "fail"}
        command_name = "eval-verdict"
        reason_required = verdict == "fail"

    if verdict not in allowed:
        return {
            "ok": False,
            "status": "error",
            "error": "invalid_verdict",
            "allowed": sorted(allowed),
        }, 400
    if reason_required and not reason:
        return {"ok": False, "status": "error", "error": "reason_required"}, 400

    prefix = _solar_harness_command_prefix()
    if not prefix or not _command_exists(prefix[0]):
        return {
            "ok": False,
            "status": "error",
            "error": "solar_harness_cli_not_found",
            "command": prefix[0] if prefix else "",
        }, 500

    cmd = [*prefix, command_name, sid, verdict]
    if reason:
        cmd.append(reason)
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=60,
            cwd=os.getcwd(),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        projection, degraded = build_projection_payload(sid)
        return {
            "ok": False,
            "status": "error",
            "error": "verdict_timeout",
            "sprint_id": sid,
            "kind": kind,
            "verdict": verdict,
            "command": f"solar harness {command_name} <sid> <verdict> <reason>",
            "stdout_tail": output[-4000:],
            "projection": projection,
            "degraded_sources": degraded,
        }, 504

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    projection, degraded = build_projection_payload(sid)
    ok = proc.returncode == 0
    return {
        "ok": ok,
        "status": "ok" if ok else "error",
        "error": "" if ok else "verdict_command_failed",
        "sprint_id": sid,
        "kind": kind,
        "verdict": verdict,
        "returncode": proc.returncode,
        "command": f"solar harness {command_name} <sid> <verdict> <reason>",
        "stdout_tail": output[-4000:],
        "projection": projection,
        "degraded_sources": degraded,
    }, 200 if ok else 500


def submit_plan_verdict_payload(sid: str, data: dict) -> tuple[dict, int]:
    return _verdict_payload("plan", sid, data)


def submit_eval_verdict_payload(sid: str, data: dict) -> tuple[dict, int]:
    return _verdict_payload("eval", sid, data)


def submit_handoff_payload(sid: str, data: dict | None = None) -> tuple[dict, int]:
    if not _safe_sprint_id(sid):
        return {"ok": False, "status": "error", "error": "invalid_sprint_id"}, 400
    status = _load_status_by_sprint(sid)
    if not status:
        return {"ok": False, "status": "error", "error": "sprint_not_found", "sprint_id": sid}, 404
    sprint_status = str(status.get("status") or "").strip().lower()
    if sprint_status != "approved":
        return {
            "ok": False,
            "status": "error",
            "error": "handoff_not_available",
            "sprint_id": sid,
            "current_status": sprint_status,
            "required_status": "approved",
        }, 409
    artifacts = _projection_artifacts(sid)
    if not _first_artifact(artifacts, "handoff"):
        return {"ok": False, "status": "error", "error": "handoff_missing", "sprint_id": sid}, 400

    prefix = _solar_harness_command_prefix()
    if not prefix or not _command_exists(prefix[0]):
        return {
            "ok": False,
            "status": "error",
            "error": "solar_harness_cli_not_found",
            "command": prefix[0] if prefix else "",
        }, 500

    cmd = [*prefix, "handoff-submit", sid]
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=60,
            cwd=os.getcwd(),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        projection, degraded = build_projection_payload(sid)
        return {
            "ok": False,
            "status": "error",
            "error": "handoff_timeout",
            "sprint_id": sid,
            "command": "solar harness handoff-submit <sid>",
            "stdout_tail": output[-4000:],
            "projection": projection,
            "degraded_sources": degraded,
        }, 504

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    projection, degraded = build_projection_payload(sid)
    ok = proc.returncode == 0
    return {
        "ok": ok,
        "status": "ok" if ok else "error",
        "error": "" if ok else "handoff_command_failed",
        "sprint_id": sid,
        "returncode": proc.returncode,
        "command": "solar harness handoff-submit <sid>",
        "stdout_tail": output[-4000:],
        "projection": projection,
        "degraded_sources": degraded,
    }, 200 if ok else 500


def _request_json_body() -> dict:
    try:
        body = request.get_json(silent=True)  # type: ignore[attr-defined]
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Route: GET /orchestration/epics
# ---------------------------------------------------------------------------

@orchestration_bp.route("/epics", methods=["GET"])
def list_epics():
    degraded: list[str] = []
    epics = _list_epics()
    return jsonify(_envelope({"epics": epics}, degraded))


def _template_path(name: str) -> Path | None:
    for root in (HARNESS_DIR / "status-server" / "templates", SCRIPT_HARNESS_DIR / "status-server" / "templates"):
        path = root / name
        if path.exists() and path.is_file():
            return path
    return None


@orchestration_bp.route("", methods=["GET"])
@orchestration_bp.route("/", methods=["GET"])
def dashboard_page():
    template_path = _template_path("orchestration_panel.html")
    if template_path is None:
        return jsonify({"ok": False, "error": "orchestration template missing"}), 500
    try:
        return Response(template_path.read_text(encoding="utf-8"), mimetype="text/html")
    except OSError:
        return jsonify({"ok": False, "error": "orchestration template missing"}), 500


@orchestration_bp.route("/dashboard", methods=["GET"])
def dashboard_data():
    data, degraded = build_dashboard_payload(request.args.get("sprint_id") or None)
    return jsonify(_envelope(data, degraded))


@orchestration_bp.route("/projection", methods=["GET"])
def projection_data():
    data, degraded = build_projection_payload(request.args.get("sprint_id") or None)
    return jsonify(_envelope(data, degraded))


# ---------------------------------------------------------------------------
# Route: GET /orchestration/epics/<epic_id>
# ---------------------------------------------------------------------------

@orchestration_bp.route("/epics/<path:epic_id>", methods=["GET"])
def get_epic(epic_id: str):
    degraded: list[str] = []

    children = _load_child_sprints(epic_id)
    gate_summary = _gate_summary(children)

    # Load epic task_graph if available
    tg_path = SPRINTS_DIR / f"{epic_id}.task_graph.json"
    tg, tg_ok = _read_json(tg_path)
    if not tg_ok:
        degraded.append(f"task_graph:missing:{epic_id}")
        tg = {}

    return jsonify(_envelope({
        "epic_id": epic_id,
        "child_sprints": children,
        "gate_status_summary": gate_summary,
        "task_graph_nodes": (tg.get("nodes") or []) if tg else [],
        "blocked_by": [b for c in children for b in c.get("blocked_by", [])],
    }, degraded))


# ---------------------------------------------------------------------------
# Route: GET /orchestration/sprints/<sid>
# ---------------------------------------------------------------------------

@orchestration_bp.route("/sprints/<path:sid>", methods=["GET"])
def get_sprint(sid: str):
    degraded: list[str] = []

    status, status_ok = _read_json(SPRINTS_DIR / f"{sid}.status.json")
    if not status_ok:
        return jsonify({"ok": False, "error": f"sprint not found: {sid}"}), 404

    tg, tg_ok = _read_json(SPRINTS_DIR / f"{sid}.task_graph.json")
    if not tg_ok:
        degraded.append(f"task_graph:missing:{sid}")
        tg = {}

    # Routing decisions from autopilot-state
    routing = _load_autopilot_routing(sid)

    # Sidecar/verifier refs from dispatch runtime-context files
    sidecar_refs: list[str] = []
    verifier_refs: list[str] = []
    for rc_file in SPRINTS_DIR.glob(f"{sid}*.runtime-context.json"):
        sidecar_refs.append(str(rc_file.relative_to(HARNESS_DIR)))
    for eval_file in SPRINTS_DIR.glob(f"{sid}*.context-usage.json"):
        verifier_refs.append(str(eval_file.relative_to(HARNESS_DIR)))

    if not sidecar_refs:
        degraded.append("sidecar_ref:missing")
    if not verifier_refs:
        degraded.append("verifier_ref:not_run")

    nodes = (tg.get("nodes") or []) if tg else []
    node_capability_hits = []
    registry = _capability_registry()
    panes = _load_pane_state()
    pane_role_map = {p["id"]: p.get("role", "") for p in panes}

    for node in nodes:
        nid = node.get("id", "")
        req = node.get("required_capabilities", [])
        # Find matching routing decision
        rd = next((r for r in routing if r.get("node_id") == nid), None)
        provided = rd.get("provided_capabilities", []) if rd else []
        provided_names = {
            c.removeprefix("inferred:") if isinstance(c, str) and c.startswith("inferred:") else c
            for c in provided
        }
        missing = [c for c in req if c not in provided_names]
        node_capability_hits.append({
            "node_id": nid,
            "required": req,
            "provided": provided,
            "missing": missing,
            "decision": rd.get("decision", "unknown") if rd else "no_routing_record",
            "target_pane": rd.get("target_pane", "") if rd else "",
            "sidecar_ref": rd.get("sidecar_ref") if rd else None,
            "verifier_ref": rd.get("verifier_ref") if rd else None,
        })

    return jsonify(_envelope({
        "sprint_id": sid,
        "status": status.get("status", ""),
        "phase": status.get("phase", ""),
        "node_capability_hits": node_capability_hits,
        "sidecar_refs": sidecar_refs,
        "verifier_refs": verifier_refs,
        "routing_decisions": routing,
    }, degraded))


@orchestration_bp.route("/sprints/<path:sid>/projection", methods=["GET"])
def get_sprint_projection(sid: str):
    data, degraded = build_projection_payload(sid)
    if not data.get("sprint_id"):
        return jsonify({"ok": False, "error": f"sprint not found: {sid}"}), 404
    return jsonify(_envelope(data, degraded))


@orchestration_bp.route("/sprints/<path:sid>/plan-verdict", methods=["POST"])
def post_sprint_plan_verdict(sid: str):
    payload, status_code = submit_plan_verdict_payload(sid, _request_json_body())
    return jsonify(payload), status_code


@orchestration_bp.route("/sprints/<path:sid>/eval-verdict", methods=["POST"])
def post_sprint_eval_verdict(sid: str):
    payload, status_code = submit_eval_verdict_payload(sid, _request_json_body())
    return jsonify(payload), status_code


@orchestration_bp.route("/sprints/<path:sid>/handoff-submit", methods=["POST"])
def post_sprint_handoff_submit(sid: str):
    payload, status_code = submit_handoff_payload(sid, _request_json_body())
    return jsonify(payload), status_code


# ---------------------------------------------------------------------------
# Route: GET /orchestration/panes
# ---------------------------------------------------------------------------

@orchestration_bp.route("/panes", methods=["GET"])
def get_panes():
    degraded: list[str] = []
    panes = _load_pane_state()
    registry = _capability_registry()

    # Determine in_use_by from autopilot-state
    ap_data, ap_ok = _read_json(STATE_DIR / "autopilot-state.json")
    in_use: dict[str, str] = {}
    if ap_ok and ap_data:
        for rd in reversed(ap_data.get("routing_decisions", [])):
            pane_id = rd.get("target_pane", "")
            if pane_id and pane_id not in in_use and rd.get("decision") == "dispatched":
                in_use[pane_id] = rd.get("sprint_id", "")

    pane_info: list[dict] = []
    for p in panes:
        pid = p["id"]
        caps = registry.get(pid, [])
        pane_info.append({
            "pane_id": pid,
            "role": p.get("role", ""),
            "state": p.get("state", ""),
            "provided_capabilities": caps,
            "in_use_by": in_use.get(pid),
        })

    return jsonify(_envelope({"panes": pane_info}, degraded))


# ---------------------------------------------------------------------------
# Route: GET /orchestration/events (SSE + poll fallback)
# ---------------------------------------------------------------------------

@orchestration_bp.route("/events", methods=["GET"])
def stream_events():
    since = request.args.get("since", "")
    accept = request.headers.get("Accept", "")

    if "text/event-stream" in accept:
        return Response(
            stream_with_context(_sse_events(since)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Poll fallback
    events = _read_events_since(since, limit=50)
    return jsonify(_envelope({"events": events}))


def _read_events_since(since: str, limit: int = 50) -> list[dict]:
    if not EVENTS_JSONL.exists():
        return []
    results: list[dict] = []
    try:
        lines = EVENTS_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-200:]):
            try:
                ev = json.loads(line)
            except Exception:
                continue
            ts = ev.get("ts", "")
            if since and ts <= since:
                continue
            event_type = ev.get("event", "")
            if event_type.startswith(("autopilot_capability", "handoff_evidence")):
                results.append(ev)
            if len(results) >= limit:
                break
    except Exception:
        pass
    return list(reversed(results))


def _sse_events(since: str) -> Generator[str, None, None]:
    """Generate SSE stream of capability/evidence events."""
    last_ts = since
    try:
        while True:
            events = _read_events_since(last_ts, limit=10)
            for ev in events:
                last_ts = ev.get("ts", last_ts)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            time.sleep(2)
            yield ": heartbeat\n\n"
    except GeneratorExit:
        pass
