"""DeepResearch human-search DAG integration tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIB = _ROOT / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from graph_node_dispatcher import dispatch_queue_item  # noqa: E402
from graph_scheduler import load_graph, node_status, ready_nodes  # noqa: E402
from research.cli import main as research_main  # noqa: E402


def test_research_source_node_generates_human_search_handoff(tmp_path):
    sid = "sprint-test-human-search"
    db_path = tmp_path / "research.sqlite"
    handoff_md = tmp_path / "handoff.md"
    results_md = tmp_path / "results.md"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    node = {
        "id": "R2_external_search",
        "goal": "Search for space data center evidence",
        "depends_on": [],
        "write_scope": [str(tmp_path / "sources.jsonl")],
        "required_capabilities": ["research.source.web"],
        "human_search": {
            "db_path": str(db_path),
            "handoff_md": str(handoff_md),
            "results_md": str(results_md),
        },
    }
    graph_path.write_text(json.dumps({"sprint_id": sid, "nodes": [node]}, ensure_ascii=False), encoding="utf-8")

    result = dispatch_queue_item({
        "sprint_id": sid,
        "intent": "graph_node|node_id=R2_external_search",
        "payload": {
            "sprint_id": sid,
            "graph": str(graph_path),
            "node": node,
            "assignment": {"pane": "missing-pane-ok-for-human-search"},
        },
    })

    assert result["ok"] is True
    assert result["reason"] == "waiting_human_search"
    assert handoff_md.exists()
    graph = load_graph(graph_path)
    assert node_status(graph, "R2_external_search") == "waiting_human_search"
    assert graph["nodes"][0]["human_search"]["run_id"]


def test_import_search_marks_waiting_graph_node_passed(tmp_path):
    sid = "sprint-test-human-search-import"
    db_path = tmp_path / "research.sqlite"
    handoff_md = tmp_path / "handoff.md"
    results_md = tmp_path / "results.md"
    out_dir = tmp_path / "out"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    node = {
        "id": "R2_external_search",
        "goal": "Search for orbital data center evidence",
        "depends_on": [],
        "write_scope": [str(tmp_path / "sources.jsonl")],
        "required_capabilities": ["research.source.web"],
        "human_search": {
            "db_path": str(db_path),
            "handoff_md": str(handoff_md),
            "results_md": str(results_md),
        },
    }
    graph_path.write_text(json.dumps({"sprint_id": sid, "nodes": [node]}, ensure_ascii=False), encoding="utf-8")
    first = dispatch_queue_item({
        "sprint_id": sid,
        "intent": "graph_node|node_id=R2_external_search",
        "payload": {
            "sprint_id": sid,
            "graph": str(graph_path),
            "node": node,
            "assignment": {"pane": "missing-pane-ok-for-human-search"},
        },
    })
    run_id = first["run_id"]
    results_md.write_text(
        """# External Search Results: orbital data centers

## Source 1: Orbital Compute Note
URL: https://example.com/orbital-compute
Publisher: Example
Published: 2026-01-01
Source Type: official

Summary:
- Orbital data centers need launch economics, radiation tolerance, and downlink capacity.

Key Claims:
- Orbital compute can reduce terrestrial cooling pressure.

Relevant Quotes:
> Orbital compute depends on downlink capacity.
""",
        encoding="utf-8",
    )

    assert research_main([
        "import-search", str(db_path),
        "--run-id", run_id,
        "--input-md", str(results_md),
        "--continue",
        "--output-dir", str(out_dir),
        "--output-md", str(out_dir / "final.md"),
        "--graph", str(graph_path),
        "--node", "R2_external_search",
    ]) == 0

    graph = load_graph(graph_path)
    assert node_status(graph, "R2_external_search") == "passed"
    assert (out_dir / "final.md").exists()


def test_import_search_resumes_downstream_ready_node(tmp_path, capsys):
    sid = "sprint-test-human-search-resume"
    db_path = tmp_path / "research.sqlite"
    handoff_md = tmp_path / "handoff.md"
    results_md = tmp_path / "results.md"
    graph_path = tmp_path / f"{sid}.task_graph.json"
    nodes = [
        {
            "id": "R2_external_search",
            "goal": "Search for orbital data center evidence",
            "depends_on": [],
            "write_scope": [str(tmp_path / "sources.jsonl")],
            "required_capabilities": ["research.source.web"],
            "human_search": {
                "db_path": str(db_path),
                "handoff_md": str(handoff_md),
                "results_md": str(results_md),
            },
        },
        {
            "id": "R3_claim_mining",
            "goal": "Mine claims from imported evidence",
            "depends_on": ["R2_external_search"],
            "write_scope": [str(tmp_path / "claims.jsonl")],
            "required_capabilities": ["research.claim.mine"],
        },
    ]
    graph_path.write_text(json.dumps({"sprint_id": sid, "nodes": nodes}, ensure_ascii=False), encoding="utf-8")
    first = dispatch_queue_item({
        "sprint_id": sid,
        "intent": "graph_node|node_id=R2_external_search",
        "payload": {
            "sprint_id": sid,
            "graph": str(graph_path),
            "node": nodes[0],
            "assignment": {"pane": "missing-pane-ok-for-human-search"},
        },
    })
    results_md.write_text(
        """# External Search Results: orbital data centers

## Source 1: Orbital Compute Note
URL: https://example.com/orbital-compute
Publisher: Example
Published: 2026-01-01
Source Type: official

Summary:
- Orbital data centers need launch economics, radiation tolerance, and downlink capacity.

Key Claims:
- Orbital compute can reduce terrestrial cooling pressure.

Relevant Quotes:
> Orbital compute depends on downlink capacity.
""",
        encoding="utf-8",
    )

    assert research_main([
        "import-search", str(db_path),
        "--run-id", first["run_id"],
        "--input-md", str(results_md),
        "--graph", str(graph_path),
        "--node", "R2_external_search",
        "--dry-run-dispatch",
        "--json",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    graph = load_graph(graph_path)
    assert node_status(graph, "R2_external_search") == "passed"
    assert [node["id"] for node in ready_nodes(graph)] == ["R3_claim_mining"]
    downstream = payload["graph_update"]["downstream"]
    assert downstream["ok"] is True
    assert downstream["enqueue"]["enqueued"][0]["node"] == "R3_claim_mining"
    assert downstream["drain"]["results"][0]["node"] == "R3_claim_mining"
