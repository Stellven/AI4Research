"""Dispatch visibility view builder for Solar-Harness live-work visibility.

Pure function: build_visibility_view(epic_id, *, sprints_dir, events_dir, now)
reads task_graph.json and events.jsonl files from disk, returns a structured
visibility dict. All I/O paths are explicit parameters — no hidden clock,
no network calls.

Returns:
  {
    "epic_id": str,
    "child_sprints": list[dict],
    "ready_nodes": list[dict],
    "blocked_nodes": list[dict],
    "capability_use": dict,
    "last_event_ts": str | None,
    "source": str,
  }

Spec: sprint-20260514-p0-…-s02-architecture.data-model.md §N3
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_events_last_ts(events_path: Path) -> str | None:
    if not events_path.exists():
        return None
    try:
        last_line = None
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
        if not last_line:
            return None
        event = json.loads(last_line)
        return event.get("timestamp")
    except Exception:
        return None


def _collect_capability_use(nodes: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        for cap in node.get("required_capabilities", []):
            cap = str(cap)
            counts[cap] = counts.get(cap, 0) + 1
    return counts


def _classify_nodes(
    graph: dict[str, Any],
    results: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    ready: list[dict] = []
    blocked: list[dict] = []
    passed_ids: set[str] = set()

    nodes = graph.get("nodes", [])
    for node in nodes:
        nid = node.get("id", "")
        status = "pending"
        if nid in results and isinstance(results[nid], dict):
            status = results[nid].get("status", "pending")
        if status in ("passed", "failed", "skipped"):
            passed_ids.add(nid)

    for node in nodes:
        nid = node.get("id", "")
        status = "pending"
        if nid in results and isinstance(results[nid], dict):
            status = results[nid].get("status", "pending")

        if status in ("passed", "failed", "skipped"):
            continue

        deps = node.get("depends_on", []) or []
        unmet = [d for d in deps if d not in passed_ids]

        entry = {
            "id": nid,
            "status": status,
            "goal": node.get("goal", ""),
            "depends_on": deps,
        }

        if unmet:
            entry["blocked_by"] = unmet
            blocked.append(entry)
        else:
            ready.append(entry)

    return ready, blocked


def build_visibility_view(
    epic_id: str,
    *,
    sprints_dir: str | Path,
    events_dir: str | Path | None = None,
    now: str = "",
) -> dict[str, Any]:
    """Build a visibility view for an epic from sprint directories and events.

    Pure function: all I/O paths and timestamps are explicit parameters.

    Args:
        epic_id: The epic identifier to scan for child sprints.
        sprints_dir: Path to the sprints directory containing task_graph.json files.
        events_dir: Optional path to directory containing events.jsonl files.
                    Defaults to sprints_dir if not provided.
        now: ISO 8601 UTC timestamp, explicitly injected.

    Returns:
        Dict with epic_id, child_sprints, ready_nodes, blocked_nodes,
        capability_use, last_event_ts, source.
    """
    sprints_root = Path(sprints_dir)
    events_root = Path(events_dir) if events_dir else sprints_root

    child_sprints: list[dict[str, Any]] = []
    all_ready: list[dict[str, Any]] = []
    all_blocked: list[dict[str, Any]] = []
    all_capabilities: dict[str, int] = {}
    latest_ts: str | None = None

    for graph_path in sorted(sprints_root.glob(f"{epic_id}*.task_graph.json")):
        graph = _load_json_safe(graph_path)
        if graph is None:
            child_sprints.append({
                "sprint_id": graph_path.stem.replace(".task_graph", ""),
                "status": "graph_unreadable",
                "ready_nodes": [],
                "blocked_nodes": [],
            })
            continue

        sid = graph.get("sprint_id", graph_path.stem.replace(".task_graph", ""))
        results = graph.get("node_results") or graph.get("results") or {}

        ready, blocked = _classify_nodes(graph, results)
        cap_use = _collect_capability_use(graph.get("nodes", []))

        for cap, count in cap_use.items():
            all_capabilities[cap] = all_capabilities.get(cap, 0) + count

        all_ready.extend(ready)
        all_blocked.extend(blocked)

        status_file = sprints_root / f"{sid}.status.json"
        status_data = _load_json_safe(status_file)
        sprint_status = "unknown"
        if status_data:
            sprint_status = status_data.get("status", "unknown")

        child_sprints.append({
            "sprint_id": sid,
            "status": sprint_status,
            "ready_nodes": [{"id": n["id"], "goal": n["goal"]} for n in ready],
            "blocked_nodes": [{"id": n["id"], "blocked_by": n.get("blocked_by", [])} for n in blocked],
        })

        # Check events for this sprint
        events_path = events_root / f"{sid}.events.jsonl"
        ts = _load_events_last_ts(events_path)
        if ts:
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

    return {
        "epic_id": epic_id,
        "child_sprints": child_sprints,
        "ready_nodes": all_ready,
        "blocked_nodes": all_blocked,
        "capability_use": all_capabilities,
        "last_event_ts": latest_ts,
        "source": "dispatch_visibility",
        "now": now,
    }
