#!/usr/bin/env python3
"""task_graph_io.py — Three-face IO for Solar Harness task graphs.

Splits task_graph.json into three concerns:
  spec   → task_graph.spec.json   (static topology: nodes, deps, gates)
  state  → task_dag.state.json    (runtime: node_results, gate_results, leases)
  closure→ closure.json           (closeout evidence: tests, evals, risks)

Legacy task_graph.json is kept as a compiled mirror (MirrorCompiler).
All load functions fail-open (return {} on missing/corrupt files).
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    _utc = getattr(datetime, "UTC", datetime.timezone.utc)
    return datetime.datetime.now(_utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sprint_path(sid: str, suffix: str) -> Path:
    return SPRINTS_DIR / f"{sid}.{suffix}"


def _read_json_safe(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ── spec face ─────────────────────────────────────────────────────────────────

def spec_path(sid: str) -> Path:
    return _sprint_path(sid, "task_graph.spec.json")


def load_spec(sid: str) -> dict[str, Any]:
    """Load task_graph.spec.json; returns {} on missing/corrupt."""
    return _read_json_safe(spec_path(sid))


def save_spec(sid: str, data: dict[str, Any]) -> None:
    data.setdefault("sprint_id", sid)
    _write_json_atomic(spec_path(sid), data)


def spec_valid(sid: str) -> tuple[bool, str]:
    """Validate spec file. Returns (ok, reason)."""
    path = spec_path(sid)
    if not path.is_file() or path.stat().st_size == 0:
        return False, "missing"
    spec = _read_json_safe(path)
    if not spec:
        return False, "parse_error"
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False, "nodes_missing"
    seen: set[str] = set()
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            return False, f"node_{idx}_not_object"
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            return False, f"node_{idx}_missing_id"
        if node_id in seen:
            return False, f"duplicate_node:{node_id}"
        seen.add(node_id)
        if not str(node.get("goal") or "").strip():
            return False, f"node_{node_id}_missing_goal"
        dep = node.get("depends_on", [])
        if dep is not None and not isinstance(dep, list):
            return False, f"node_{node_id}_invalid_depends_on"
    return True, "ok"


# ── state face ────────────────────────────────────────────────────────────────

def state_path(sid: str) -> Path:
    return _sprint_path(sid, "task_dag.state.json")


def load_state(sid: str) -> dict[str, Any]:
    """Load task_dag.state.json; returns {} on missing/corrupt."""
    return _read_json_safe(state_path(sid))


def save_state(sid: str, data: dict[str, Any]) -> None:
    data.setdefault("sprint_id", sid)
    data["updated_at"] = _now()
    _write_json_atomic(state_path(sid), data)


def patch_state(sid: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Load state, apply patch dict, save, return new state."""
    current = load_state(sid)
    current.update(patch)
    save_state(sid, current)
    return current


def set_node_result_in_state(sid: str, node_id: str, result: dict[str, Any]) -> None:
    """Write a node result into task_dag.state.json without touching spec."""
    state = load_state(sid)
    results = state.setdefault("node_results", {})
    results[node_id] = {**result, "updated_at": _now()}
    save_state(sid, state)


def set_gate_result_in_state(sid: str, gate: str, result: dict[str, Any]) -> None:
    state = load_state(sid)
    gate_results = state.setdefault("gate_results", {})
    gate_results[gate] = {**result, "updated_at": _now()}
    save_state(sid, state)


# ── closure face ──────────────────────────────────────────────────────────────

def closure_path(sid: str) -> Path:
    return _sprint_path(sid, "closure.json")


def load_closure(sid: str) -> dict[str, Any]:
    """Load closure.json; returns {} on missing/corrupt."""
    return _read_json_safe(closure_path(sid))


def save_closure(sid: str, data: dict[str, Any]) -> None:
    data.setdefault("sprint_id", sid)
    data.setdefault("closed_at", _now())
    _write_json_atomic(closure_path(sid), data)


def closure_complete(sid: str) -> bool:
    """Return True if closure.json shows all nodes and gates passed."""
    c = load_closure(sid)
    return bool(c.get("all_nodes_passed") and c.get("all_required_gates_passed"))


# ── legacy backfill ───────────────────────────────────────────────────────────

def backfill_state_from_legacy(sid: str, graph: dict[str, Any]) -> dict[str, Any]:
    """Create task_dag.state.json skeleton from legacy task_graph.json.

    Does NOT overwrite existing state; only writes if state is missing.
    Does NOT write runtime state back to spec.
    """
    sp = state_path(sid)
    if sp.is_file() and sp.stat().st_size > 0:
        return _read_json_safe(sp)  # already exists, don't overwrite

    node_results: dict[str, Any] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        node_results[node_id] = {
            "status": str(node.get("status") or "pending"),
            "updated_at": str(node.get("updated_at") or _now()),
            "source": "backfill_from_legacy",
        }

    gate_results: dict[str, Any] = {}
    legacy_gate = graph.get("gate_results")
    if isinstance(legacy_gate, dict):
        gate_results = legacy_gate

    state: dict[str, Any] = {
        "sprint_id": sid,
        "node_results": node_results,
        "gate_results": gate_results,
        "active_leases": {},
        "dispatch_ids": {},
        "event_cursor": 0,
        "updated_at": _now(),
        "backfilled_from_legacy": True,
    }
    _write_json_atomic(sp, state)
    return state


def backfill_spec_from_legacy(sid: str, graph: dict[str, Any]) -> dict[str, Any]:
    """Create task_graph.spec.json from legacy task_graph.json.

    Strips runtime-only fields (node_results, gate_results, active_leases, etc.)
    Does NOT overwrite existing spec.
    """
    sp = spec_path(sid)
    if sp.is_file() and sp.stat().st_size > 0:
        return _read_json_safe(sp)

    RUNTIME_KEYS = {"node_results", "gate_results", "active_leases", "dispatch_ids",
                    "event_cursor", "updated_at", "backfilled_from_legacy",
                    "graph_status_cache", "task_graph_status"}
    spec: dict[str, Any] = {k: v for k, v in graph.items() if k not in RUNTIME_KEYS}
    # Strip runtime fields from nodes too
    spec_nodes = []
    for node in spec.get("nodes", []):
        if not isinstance(node, dict):
            continue
        spec_nodes.append({k: v for k, v in node.items()
                           if k not in {"status", "updated_at", "result", "dispatch_id", "lease_id"}})
    spec["nodes"] = spec_nodes
    spec.setdefault("sprint_id", sid)
    _write_json_atomic(sp, spec)
    return spec


# ── mirror compiler ───────────────────────────────────────────────────────────

def compile_mirror(sid: str) -> dict[str, Any]:
    """Generate task_graph.json (compat mirror) from spec + state.

    This is the only place that should write task_graph.json going forward.
    """
    spec = load_spec(sid)
    state = load_state(sid)

    if not spec:
        return {}

    mirror = dict(spec)
    node_results = state.get("node_results") or {}
    gate_results = state.get("gate_results") or {}

    # Merge state into nodes (for compat consumers)
    merged_nodes = []
    for node in spec.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        merged = dict(node)
        if node_id in node_results and isinstance(node_results[node_id], dict):
            merged["status"] = str(node_results[node_id].get("status") or "pending")
            merged["updated_at"] = str(node_results[node_id].get("updated_at") or "")
        else:
            merged.setdefault("status", "pending")
        merged_nodes.append(merged)

    mirror["nodes"] = merged_nodes
    mirror["node_results"] = node_results
    mirror["gate_results"] = gate_results
    mirror["_mirror_compiled_at"] = _now()
    mirror["_mirror_source"] = "spec+state"
    return mirror


def write_mirror(sid: str) -> Path:
    """Compile and atomically write task_graph.json; return path."""
    mirror = compile_mirror(sid)
    out = _sprint_path(sid, "task_graph.json")
    if mirror:
        _write_json_atomic(out, mirror)
    return out


# ── merged view (for callers that need a unified graph) ───────────────────────

def load_merged(sid: str) -> dict[str, Any]:
    """Load spec+state merged into a single graph dict (like old task_graph.json).

    Priority: spec for topology, state for runtime. Falls back to legacy
    task_graph.json if spec is missing (fail-open).
    """
    ok, _ = spec_valid(sid)
    if ok:
        return compile_mirror(sid)
    # Fallback: legacy single-file
    legacy_path = _sprint_path(sid, "task_graph.json")
    if legacy_path.is_file():
        return _read_json_safe(legacy_path)
    return {}


# ── parent ready check via triface ───────────────────────────────────────────

def triface_parent_ready(sid: str) -> dict[str, Any]:
    """Check parent readiness using spec+state+closure.

    Returns dict with 'ready', 'reason', 'open_nodes', 'missing_gates'.
    """
    closure = load_closure(sid)
    if closure.get("all_nodes_passed") and closure.get("all_required_gates_passed"):
        return {
            "ready": True,
            "reason": "closure_complete",
            "open_nodes": [],
            "missing_gates": [],
            "source": "closure",
        }

    spec = load_spec(sid)
    state = load_state(sid)

    if not spec:
        return {"ready": False, "reason": "no_spec", "open_nodes": [], "missing_gates": []}

    node_results = state.get("node_results") or {}
    gate_results = state.get("gate_results") or {}
    required_gates = spec.get("required_gates") or []

    PASS = {"passed"}
    CLOSED = {"skipped", "cancelled", "skipped_parent_passed"}

    open_nodes = []
    failed_nodes = []
    for node in spec.get("nodes", []):
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or "")
        nr = node_results.get(nid) or {}
        st = str(nr.get("status") or "pending").lower()
        if st == "failed":
            failed_nodes.append(nid)
        elif st not in (PASS | CLOSED):
            open_nodes.append(nid)

    missing_gates = []
    for gate in required_gates:
        gr = gate_results.get(str(gate)) or {}
        if str(gr.get("status") or "") != "passed":
            missing_gates.append(gate)

    ready = not open_nodes and not failed_nodes and not missing_gates and bool(spec.get("nodes"))
    return {
        "ready": ready,
        "reason": "closure_incomplete" if not ready else "all_passed",
        "open_nodes": open_nodes,
        "failed_nodes": failed_nodes,
        "missing_gates": missing_gates,
        "source": "spec+state",
    }
