#!/usr/bin/env python3
"""task_graph_state_io.py — spec/state/closure three-way split I/O for Solar Harness.

This module provides the default load/save paths for the task_graph three-face
split:

  spec  (task_graph.json)       — immutable topology: nodes, goals, gates, deps
  state (task_dag.state.json)   — mutable runtime: node_results, gate_results,
                                  leases, dispatch_ids, events
  closure (task_dag.closure.json) — terminal closeout evidence

Design principles:
  - spec is never written with runtime state
  - state is the single source of truth for runtime data
  - closure is the single source of truth for closeout evidence
  - legacy graphs without state/closure get backfilled on first access
  - all writes are atomic (temp file + os.replace)
"""
from __future__ import annotations

import datetime
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

HOME = Path.home()
HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or HOME / ".solar" / "harness"
)
SPRINTS_DIR = Path(os.environ.get("HARNESS_SPRINTS_DIR", HARNESS_DIR / "sprints"))

SCHEMA_VERSION_STATE = "solar.task_graph_state.v1"
SCHEMA_VERSION_CLOSURE = "solar.task_graph_closure.v1"

TERMINAL_STATUSES = {"passed", "failed", "skipped", "cancelled", "skipped_parent_passed"}


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def state_path_for_sprint(sprint_id: str, sprints_dir: Path | None = None) -> Path:
    """Return the canonical path for a sprint's state file."""
    base = sprints_dir or SPRINTS_DIR
    return base / f"{sprint_id}.task_dag.state.json"


def closure_path_for_sprint(sprint_id: str, sprints_dir: Path | None = None) -> Path:
    """Return the canonical path for a sprint's closure file."""
    base = sprints_dir or SPRINTS_DIR
    return base / f"{sprint_id}.task_dag.closure.json"


def spec_path_for_sprint(sprint_id: str, sprints_dir: Path | None = None) -> Path:
    """Return the canonical path for a sprint's spec (task_graph.json)."""
    base = sprints_dir or SPRINTS_DIR
    return base / f"{sprint_id}.task_graph.json"


def _sprint_id_from_graph(graph: dict[str, Any], graph_path: str | Path | None = None) -> str:
    sid = str(graph.get("sprint_id") or graph.get("id") or "").strip()
    if sid:
        return sid
    if graph_path:
        return Path(graph_path).name.removesuffix(".task_graph.json")
    return ""


# ---------------------------------------------------------------------------
# Empty skeletons
# ---------------------------------------------------------------------------

def make_empty_state(sprint_id: str, graph_ref: str = "") -> dict[str, Any]:
    """Create a blank runtime state skeleton."""
    return {
        "schema_version": SCHEMA_VERSION_STATE,
        "sprint_id": sprint_id,
        "graph_ref": graph_ref or f"{sprint_id}.task_graph.json",
        "node_results": {},
        "gate_results": {},
        "leases": {},
        "dispatch_ids": {},
        "events": [
            {
                "ts": _now(),
                "event": "state_initialized",
                "by": "task_graph_state_io",
                "note": "Empty state skeleton created.",
            }
        ],
        "updated_at": _now(),
        "event_cursor": 0,
    }


def make_empty_closure(sprint_id: str) -> dict[str, Any]:
    """Create a blank closure skeleton (not yet closed)."""
    return {
        "schema_version": SCHEMA_VERSION_CLOSURE,
        "sprint_id": sprint_id,
        "all_nodes_passed": False,
        "all_required_gates_passed": False,
        "acceptance_traceability_coverage": None,
        "tests": [],
        "evals": [],
        "changed_files": [],
        "residual_risks": [],
        "closed_at": None,
        "created_at": _now(),
    }


# ---------------------------------------------------------------------------
# State I/O
# ---------------------------------------------------------------------------

def load_state(sprint_id: str, sprints_dir: Path | None = None) -> dict[str, Any] | None:
    """Load state from disk. Returns None if file does not exist."""
    path = state_path_for_sprint(sprint_id, sprints_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(sprint_id: str, state: dict[str, Any], sprints_dir: Path | None = None) -> Path:
    """Save state atomically. Returns the written path."""
    state["updated_at"] = _now()
    path = state_path_for_sprint(sprint_id, sprints_dir)
    _atomic_write(path, state)
    return path


# ---------------------------------------------------------------------------
# Closure I/O
# ---------------------------------------------------------------------------

def load_closure(sprint_id: str, sprints_dir: Path | None = None) -> dict[str, Any] | None:
    """Load closure from disk. Returns None if file does not exist."""
    path = closure_path_for_sprint(sprint_id, sprints_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_closure(sprint_id: str, closure: dict[str, Any], sprints_dir: Path | None = None) -> Path:
    """Save closure atomically. Returns the written path."""
    path = closure_path_for_sprint(sprint_id, sprints_dir)
    _atomic_write(path, closure)
    return path


# ---------------------------------------------------------------------------
# Legacy backfill
# ---------------------------------------------------------------------------

def backfill_state_from_legacy(
    graph: dict[str, Any],
    graph_path: str | Path | None = None,
    sprints_dir: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Create a state skeleton from a monolithic task_graph.json.

    Extracts runtime fields (node_results, gate_results, node.status,
    node.assigned_to, node.dispatch_id) from the legacy graph and writes
    them to the canonical state file.

    If state already exists and force=False, returns the existing state.
    """
    sid = _sprint_id_from_graph(graph, graph_path)
    if not sid:
        raise ValueError("Cannot backfill state: sprint_id missing from graph")

    existing = load_state(sid, sprints_dir)
    if existing is not None and not force:
        return existing

    graph_ref = Path(graph_path).name if graph_path else f"{sid}.task_graph.json"
    state = make_empty_state(sid, graph_ref)

    # Extract node_results from legacy locations
    legacy_results = graph.get("node_results") or graph.get("results") or {}
    if isinstance(legacy_results, dict):
        state["node_results"] = deepcopy(legacy_results)

    # Also extract inline node status for nodes not in node_results
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        if node_id not in state["node_results"]:
            inline_status = str(node.get("status") or "").strip()
            if inline_status and inline_status != "pending":
                state["node_results"][node_id] = {
                    "status": inline_status,
                    "updated_at": str(node.get("updated_at") or _now()),
                }
        # Extract dispatch metadata
        if node_id in state["node_results"]:
            if node.get("assigned_to"):
                state["node_results"][node_id]["assigned_to"] = node["assigned_to"]
            if node.get("dispatch_id"):
                state["dispatch_ids"][node_id] = node["dispatch_id"]

    # Extract gate_results
    legacy_gates = graph.get("gate_results") or {}
    if isinstance(legacy_gates, dict):
        state["gate_results"] = deepcopy(legacy_gates)

    # Record backfill event
    state["events"].append({
        "ts": _now(),
        "event": "legacy_backfill",
        "by": "task_graph_state_io",
        "note": f"Backfilled from {graph_ref}; {len(state['node_results'])} node_results, {len(state['gate_results'])} gate_results extracted.",
    })
    state["event_cursor"] = len(state["events"])

    save_state(sid, state, sprints_dir)
    return state


def backfill_closure_from_legacy(
    graph: dict[str, Any],
    graph_path: str | Path | None = None,
    sprints_dir: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Create a closure skeleton from a monolithic task_graph.json.

    Checks if all nodes/gates passed and fills in what it can from the graph.
    Only creates real closure if the graph is actually closed.
    """
    sid = _sprint_id_from_graph(graph, graph_path)
    if not sid:
        raise ValueError("Cannot backfill closure: sprint_id missing from graph")

    existing = load_closure(sid, sprints_dir)
    if existing is not None and not force:
        return existing

    closure = make_empty_closure(sid)

    # Check node pass status
    nodes = graph.get("nodes") or []
    node_results = graph.get("node_results") or {}
    all_passed = True
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        # Check both inline and node_results
        inline_status = str(node.get("status") or "pending").lower()
        result_status = ""
        if isinstance(node_results.get(node_id), dict):
            result_status = str(node_results[node_id].get("status") or "").lower()
        effective = result_status or inline_status
        if effective != "passed" and effective not in {"skipped", "cancelled", "skipped_parent_passed"}:
            all_passed = False
            break

    closure["all_nodes_passed"] = all_passed

    # Check gates
    required_gates = graph.get("required_gates") or []
    gate_results = graph.get("gate_results") or {}
    all_gates_passed = True
    for gate in required_gates:
        gate_result = gate_results.get(gate)
        if not isinstance(gate_result, dict) or gate_result.get("status") != "passed":
            all_gates_passed = False
            break
    closure["all_required_gates_passed"] = all_gates_passed

    if all_passed and all_gates_passed:
        closure["closed_at"] = _now()

    save_closure(sid, closure, sprints_dir)
    return closure


# ---------------------------------------------------------------------------
# Unified loader (spec + state + closure)
# ---------------------------------------------------------------------------

def load_three_face(
    sprint_id: str,
    sprints_dir: Path | None = None,
    *,
    auto_backfill: bool = True,
) -> dict[str, Any]:
    """Load all three faces for a sprint.

    Returns a dict with keys: spec, state, closure, sprint_id, degraded.
    If state/closure are missing and auto_backfill is True, attempts to
    backfill from the legacy task_graph.json.
    """
    base = sprints_dir or SPRINTS_DIR
    spec_p = spec_path_for_sprint(sprint_id, base)
    degraded: list[str] = []

    # Load spec
    spec: dict[str, Any] | None = None
    if spec_p.exists():
        spec = json.loads(spec_p.read_text(encoding="utf-8"))
    else:
        degraded.append("spec_missing")

    # Load state
    state = load_state(sprint_id, base)
    if state is None and auto_backfill and spec is not None:
        state = backfill_state_from_legacy(spec, spec_p, base)
        degraded.append("state_backfilled_from_legacy")
    elif state is None:
        degraded.append("state_missing")

    # Load closure
    closure = load_closure(sprint_id, base)
    if closure is None and auto_backfill and spec is not None:
        closure = backfill_closure_from_legacy(spec, spec_p, base)
        degraded.append("closure_backfilled_from_legacy")
    elif closure is None:
        degraded.append("closure_missing")

    return {
        "sprint_id": sprint_id,
        "spec": spec,
        "state": state,
        "closure": closure,
        "degraded": degraded,
    }


# ---------------------------------------------------------------------------
# State mutation helpers (for R2+ consumers)
# ---------------------------------------------------------------------------

def record_event(state: dict[str, Any], event: str, by: str, note: str = "") -> None:
    """Append an event to the state's event log."""
    events = state.setdefault("events", [])
    events.append({
        "ts": _now(),
        "event": event,
        "by": by,
        "note": note,
    })
    state["event_cursor"] = len(events)
    state["updated_at"] = _now()


def set_node_result(
    state: dict[str, Any],
    node_id: str,
    status: str,
    *,
    note: str = "",
    assigned_to: str = "",
    dispatch_id: str = "",
) -> None:
    """Set a node result in the state (not in spec)."""
    results = state.setdefault("node_results", {})
    entry: dict[str, Any] = {
        "status": status,
        "updated_at": _now(),
    }
    if note:
        entry["note"] = note
    if assigned_to:
        entry["assigned_to"] = assigned_to
    if dispatch_id:
        entry["dispatch_id"] = dispatch_id
        state.setdefault("dispatch_ids", {})[node_id] = dispatch_id
    results[node_id] = entry
    state["updated_at"] = _now()


def set_gate_result(state: dict[str, Any], gate: str, status: str, node_id: str = "") -> None:
    """Set a gate result in the state."""
    gates = state.setdefault("gate_results", {})
    gates[gate] = {
        "status": status,
        "node": node_id,
        "updated_at": _now(),
    }
    state["updated_at"] = _now()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Minimal CLI for state/closure operations."""
    import argparse

    parser = argparse.ArgumentParser(description="task_graph spec/state/closure I/O")
    sub = parser.add_subparsers(dest="command")

    # backfill
    bf = sub.add_parser("backfill", help="Backfill state+closure from legacy task_graph.json")
    bf.add_argument("--graph", required=True, help="Path to task_graph.json")
    bf.add_argument("--force", action="store_true", help="Overwrite existing state/closure")

    # load
    ld = sub.add_parser("load", help="Load three-face for a sprint")
    ld.add_argument("--sprint-id", required=True)
    ld.add_argument("--no-backfill", action="store_true")

    # show-state
    ss = sub.add_parser("show-state", help="Show state for a sprint")
    ss.add_argument("--sprint-id", required=True)

    # show-closure
    sc = sub.add_parser("show-closure", help="Show closure for a sprint")
    sc.add_argument("--sprint-id", required=True)

    args = parser.parse_args()

    if args.command == "backfill":
        graph_p = Path(args.graph).expanduser()
        graph = json.loads(graph_p.read_text(encoding="utf-8"))
        sid = _sprint_id_from_graph(graph, graph_p)
        sd = graph_p.parent
        state = backfill_state_from_legacy(graph, graph_p, sd, force=args.force)
        closure = backfill_closure_from_legacy(graph, graph_p, sd, force=args.force)
        result = {
            "ok": True,
            "sprint_id": sid,
            "state_path": str(state_path_for_sprint(sid, sd)),
            "closure_path": str(closure_path_for_sprint(sid, sd)),
            "node_results_count": len(state.get("node_results", {})),
            "gate_results_count": len(state.get("gate_results", {})),
            "all_nodes_passed": closure.get("all_nodes_passed"),
            "all_required_gates_passed": closure.get("all_required_gates_passed"),
        }
        print(json.dumps(result, indent=2))

    elif args.command == "load":
        result = load_three_face(args.sprint_id, auto_backfill=not args.no_backfill)
        # Summarize for CLI output
        summary = {
            "sprint_id": result["sprint_id"],
            "spec_loaded": result["spec"] is not None,
            "state_loaded": result["state"] is not None,
            "closure_loaded": result["closure"] is not None,
            "degraded": result["degraded"],
        }
        if result["state"]:
            summary["node_results_count"] = len(result["state"].get("node_results", {}))
        if result["closure"]:
            summary["all_nodes_passed"] = result["closure"].get("all_nodes_passed")
        print(json.dumps(summary, indent=2))

    elif args.command == "show-state":
        state = load_state(args.sprint_id)
        if state:
            print(json.dumps(state, indent=2))
        else:
            print(json.dumps({"ok": False, "reason": "state_not_found"}))

    elif args.command == "show-closure":
        closure = load_closure(args.sprint_id)
        if closure:
            print(json.dumps(closure, indent=2))
        else:
            print(json.dumps({"ok": False, "reason": "closure_not_found"}))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
