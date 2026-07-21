#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "backfill_task_graph_gates",
        ROOT / "tools" / "backfill_task_graph_gates.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_standard_graph_backfills_default_gates_and_gate_results(tmp_path: Path):
    mod = _load_tool()
    graph = {
        "sprint_id": "standard-backfill",
        "dag_variant": "standard",
        "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
        "nodes": [
            {"id": "S1", "status": "passed"},
            {"id": "S2", "status": "passed"},
            {"id": "S3", "status": "passed"},
            {"id": "S4", "status": "passed"},
            {"id": "S5", "status": "passed"},
        ],
        "node_results": {},
        "gate_results": {},
    }
    path = tmp_path / "graph.task_graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = mod.backfill_graph(path)
    repaired = json.loads(path.read_text(encoding="utf-8"))
    by_id = {node["id"]: node for node in repaired["nodes"]}

    assert result["changed"] is True
    assert result["missing_after"] == []
    assert by_id["S1"]["gate"] == "G_PLAN"
    assert by_id["S2"]["gate"] == "G_IMPL"
    assert by_id["S3"]["gate"] == "G_VERIFY"
    assert by_id["S4"]["gate"] == "G_REVIEW"
    assert by_id["S5"]["gate"] == "G_REVIEW"
    assert repaired["gate_results"]["G_REVIEW"]["status"] == "passed"


def test_custom_required_gates_fill_in_order_for_unassigned_nodes(tmp_path: Path):
    mod = _load_tool()
    graph = {
        "sprint_id": "custom-gates",
        "dag_variant": "standard",
        "required_gates": ["G_PREFLIGHT", "G_INSTALL", "G_ANALYZE", "G_VERIFY", "G_REPORT"],
        "nodes": [
            {"id": "U1", "status": "passed"},
            {"id": "U2", "status": "passed"},
            {"id": "U3", "status": "reviewing"},
            {"id": "U4", "status": "pending"},
            {"id": "U5", "status": "pending"},
        ],
        "node_results": {},
        "gate_results": {},
    }
    path = tmp_path / "graph.task_graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = mod.backfill_graph(path)
    repaired = json.loads(path.read_text(encoding="utf-8"))

    assert result["changed"] is True
    assert result["missing_after"] == []
    assert [node.get("gate") for node in repaired["nodes"]] == [
        "G_PREFLIGHT",
        "G_INSTALL",
        "G_ANALYZE",
        "G_VERIFY",
        "G_REPORT",
    ]
    assert repaired["gate_results"]["G_ANALYZE"]["status"] == "blocked"
    assert repaired["gate_results"]["G_VERIFY"]["status"] == "blocked"


def test_existing_required_gate_owners_are_not_overassigned(tmp_path: Path):
    mod = _load_tool()
    graph = {
        "sprint_id": "partial-owners",
        "required_gates": ["G1", "G2", "G3", "G4"],
        "nodes": [
            {"id": "N1", "status": "passed"},
            {"id": "N2", "status": "passed", "gate": "G1"},
            {"id": "N3", "status": "passed"},
            {"id": "N4", "status": "passed", "gate": "G2"},
            {"id": "N5", "status": "passed"},
            {"id": "N6", "status": "passed", "gate": "G3"},
            {"id": "N7", "status": "passed"},
            {"id": "N8", "status": "passed", "gate": "G4"},
        ],
        "node_results": {},
        "gate_results": {},
    }
    path = tmp_path / "graph.task_graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = mod.backfill_graph(path)
    repaired = json.loads(path.read_text(encoding="utf-8"))
    by_id = {node["id"]: node for node in repaired["nodes"]}

    assert result["missing_after"] == []
    assert by_id["N1"].get("gate") is None
    assert by_id["N3"].get("gate") is None
    assert by_id["N5"].get("gate") is None
    assert by_id["N7"].get("gate") is None
    assert repaired["gate_results"]["G4"]["status"] == "passed"
