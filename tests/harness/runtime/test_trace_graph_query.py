from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness" / "lib"))

from session_log import SessionLog  # noqa: E402
from trace_graph import query_trace_graph  # noqa: E402


def test_windows_safe_concurrent_append_and_unified_query(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    sid = "sprint-trace-one"
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps({"sprint_id": sid, "nodes": [{"id": "S1"}, {"id": "S2"}]}), encoding="utf-8"
    )
    (sprints / f"{sid}.task_dag.state.json").write_text(
        json.dumps({"sprint_id": sid, "node_results": {"S1": {"status": "passed"}}, "gate_results": {}}),
        encoding="utf-8",
    )
    (sprints / f"{sid}.closure.json").write_text(json.dumps({"all_nodes_passed": False}), encoding="utf-8")

    def append(index: int) -> None:
        SessionLog.for_sprint(sid, harness_dir=str(harness)).append(
            "activity_succeeded",
            actor="worker",
            sprint_id=sid,
            activity_id="S1" if index % 2 == 0 else "S2",
            idempotency_key=f"trace:{index}",
            payload={"index": index},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(40)))

    raw = (harness / "sessions" / sid / "events.jsonl").read_bytes()
    assert not raw.startswith(b"\0")
    assert len([json.loads(line) for line in raw.decode().splitlines()]) == 40
    result = query_trace_graph(harness_dir=harness, sprints_dir=sprints, sprint_id=sid, actor="worker")
    assert result["schema_version"] == "solar.trace_graph_query.v1"
    assert result["event_count"] == 40
    assert result["graph"]["node_count"] == 2
    assert result["graph"]["node_results"]["S1"]["status"] == "passed"
    assert result["correlation"]["known_event_node_ids"] == ["S1", "S2"]
    assert result["correlation"]["unknown_event_node_ids"] == []


def test_query_is_scoped_bounded_and_rejects_path_escape(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    sprints.mkdir(parents=True)
    for sid in ("wanted", "other"):
        SessionLog.for_sprint(sid, harness_dir=str(harness)).append(
            "log_message", actor="worker", sprint_id=sid, idempotency_key=sid
        )
    result = query_trace_graph(harness_dir=harness, sprints_dir=sprints, sprint_id="wanted", limit=1)
    assert result["event_count"] == 1
    assert all(event["sprint_id"] == "wanted" for event in result["events"])
    try:
        query_trace_graph(harness_dir=harness, sprints_dir=sprints, sprint_id="../other")
    except ValueError:
        pass
    else:
        raise AssertionError("path escape was accepted")
