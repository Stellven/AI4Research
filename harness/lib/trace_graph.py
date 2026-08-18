"""Unified, read-only trace query across session events and DAG state."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "solar.trace_graph_query.v1"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _safe_id(value: str) -> str:
    value = value.strip()
    if not value or value in {".", ".."} or any(ch in value for ch in "/\\\0"):
        raise ValueError("sprint_id must be a non-empty path-safe identifier")
    return value


def _timestamp(record: dict[str, Any]) -> str:
    return str(record.get("ts") or record.get("timestamp") or record.get("updated_at") or "")


def _since_ok(record: dict[str, Any], since: str | None) -> bool:
    if not since:
        return True
    stamp = _timestamp(record)
    if not stamp:
        return False
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")) >= datetime.fromisoformat(
            since.replace("Z", "+00:00")
        )
    except ValueError:
        return False


def query_trace_graph(
    *,
    harness_dir: Path,
    sprints_dir: Path,
    sprint_id: str,
    actor: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    """Return events, graph state, closure, and correlation in one record."""
    sid = _safe_id(sprint_id)
    bounded_limit = max(1, min(int(limit), 1000))
    event_sources = [
        ("session_log", harness_dir / "sessions" / sid / "events.jsonl"),
        ("sprint_event", sprints_dir / f"{sid}.events.jsonl"),
    ]
    events: list[dict[str, Any]] = []
    for source, path in event_sources:
        for raw in _read_jsonl(path):
            record_sid = str(raw.get("sprint_id") or raw.get("sid") or raw.get("session_id") or "")
            if record_sid != sid:
                continue
            if actor and str(raw.get("actor") or "") != actor:
                continue
            record_type = str(raw.get("type") or raw.get("event_type") or "")
            if event_type and record_type != event_type:
                continue
            if not _since_ok(raw, since):
                continue
            events.append({"source": source, **raw})
    events.sort(key=lambda item: (_timestamp(item), int(item.get("seq") or 0), str(item.get("event_id") or "")))
    total = len(events)
    events = events[:bounded_limit]

    graph_path = sprints_dir / f"{sid}.task_graph.json"
    state_path = sprints_dir / f"{sid}.task_dag.state.json"
    closure_path = sprints_dir / f"{sid}.closure.json"
    graph = _read_json(graph_path)
    state = _read_json(state_path)
    closure = _read_json(closure_path)
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    node_results = state.get("node_results") if isinstance(state.get("node_results"), dict) else {}
    gate_results = state.get("gate_results") if isinstance(state.get("gate_results"), dict) else {}
    event_node_ids = sorted({str(e.get("node_id") or e.get("activity_id") or "") for e in events} - {""})
    graph_node_ids = {str(n.get("id") or "") for n in nodes if isinstance(n, dict)}
    return {
        "schema_version": SCHEMA_VERSION,
        "sprint_id": sid,
        "query": {"actor": actor, "event_type": event_type, "since": since, "limit": bounded_limit},
        "events": events,
        "event_count": len(events),
        "total_matching_events": total,
        "has_more": total > len(events),
        "graph": {
            "present": bool(graph),
            "node_count": len(nodes),
            "node_results": node_results,
            "gate_results": gate_results,
            "closure": closure,
        },
        "correlation": {
            "event_node_ids": event_node_ids,
            "known_event_node_ids": sorted(set(event_node_ids) & graph_node_ids),
            "unknown_event_node_ids": sorted(set(event_node_ids) - graph_node_ids),
        },
        "sources": [
            {"kind": kind, "path": str(path), "present": path.is_file()}
            for kind, path in event_sources
        ]
        + [
            {"kind": "task_graph", "path": str(graph_path), "present": bool(graph)},
            {"kind": "task_state", "path": str(state_path), "present": bool(state)},
            {"kind": "closure", "path": str(closure_path), "present": bool(closure)},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?")
    parser.add_argument("--harness-dir", type=Path, required=True)
    parser.add_argument("--sprints-dir", type=Path, required=True)
    parser.add_argument("--sprint-id", required=True)
    parser.add_argument("--actor")
    parser.add_argument("--event-type")
    parser.add_argument("--since")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    try:
        result = query_trace_graph(
            harness_dir=args.harness_dir,
            sprints_dir=args.sprints_dir,
            sprint_id=args.sprint_id,
            actor=args.actor,
            event_type=args.event_type,
            since=args.since,
            limit=args.limit,
        )
    except (ValueError, OSError) as exc:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
