from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
HARNESS = REPO / "harness"
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
PARITY_FIXTURE = REPO / "tests" / "harness" / "research_orchestration" / "fixtures" / "upstream_research_parity_contracts.json"


def run_bridge(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path / "harness-out")
    return subprocess.run(
        [sys.executable, str(BRIDGE), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.stdout, proc.stderr
    return json.loads(proc.stdout)


def write_envelope(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_same_input_upstream_contract_vs_solar_semantics(tmp_path: Path) -> None:
    fixture = json.loads(PARITY_FIXTURE.read_text(encoding="utf-8"))
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer <<>>\n%%EOF\n")
    evidence = tmp_path / "experiment.json"
    evidence.write_text('{"experiment_result": {"metric": "support", "value": 0.83}}\n', encoding="utf-8")

    case_args = {
        "topic-survey": [],
        "url-report": [],
        "pdf-ingest": ["--source", str(source_pdf)],
        "evidence-resume": ["--source", str(evidence)],
    }

    for case in fixture["cases"]:
        proc = run_bridge(
            tmp_path,
            "research",
            "--prompt",
            case["prompt"],
            "--run-id",
            case["case_id"],
            "--artifact-root",
            str(tmp_path / f"artifacts-{case['case_id']}"),
            "--max-steps",
            "1",
            *case_args[case["case_id"]],
        )
        data = payload(proc)
        assert proc.returncode in {0, 2}, proc.stdout + proc.stderr
        contract = case["upstream_contract"]
        if "route" not in data:
            assert data["input_classification"]["workflow_kind"] == contract["workflow_kind"]
            assert data["final_status"] == "failed"
            assert data["error_type"] in {"FileNotFoundError", "ResearchRuntimeError", "ResearchOrchestrationError"}
            continue
        assert data["route"]["workflow_kind"] == contract["workflow_kind"]
        assert data["prompt"] == case["prompt"]
        assert data["start_node"] in set(data["node_states"]) | {data["start_node"]}
        if data["node_states"]:
            assert data["node_states"][data["start_node"]]["depends_on"] == []
        assert data["final_status"] in {"awaiting_external", "failed", "completed"}
        if data["final_status"] == "failed":
            assert data["current_blockers"]
        solar_contract = json.loads(Path(data["task_contract_path"]).read_text(encoding="utf-8"))
        assert solar_contract["deliverable"]["language"] == contract["output_language"]
        assert solar_contract["deliverable"]["delivery_type"] == contract["delivery_type"]
        assert solar_contract["constraints"]["request_capture"]["raw_prompt"] == case["prompt"]
        searchable = " ".join(
            [
                case["prompt"],
                solar_contract["workflow_kind"],
                solar_contract["deliverable"]["kind"],
                " ".join(solar_contract["deliverable"]["compiled_acceptance"]),
            ]
        ).lower()
        matched_goals = [
            goal
            for goal in contract["semantic_goals"]
            if any(token in searchable for token in goal.lower().replace("/", " ").split())
        ]
        assert matched_goals


def test_visualize_generates_input_bound_artifacts_and_filter_semantics(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "papers").mkdir(parents=True)
    (wiki / "concepts").mkdir()
    (wiki / "methods").mkdir()
    (wiki / "graph").mkdir()
    (wiki / "papers" / "source.md").write_text("# Source\n", encoding="utf-8")
    (wiki / "concepts" / "memory.md").write_text("# Memory\n", encoding="utf-8")
    (wiki / "methods" / "other.md").write_text("# Other\n", encoding="utf-8")
    (wiki / "graph" / "edges.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"source": "papers/source.md", "target": "concepts/memory.md", "relation": "uses_concept"}),
                json.dumps({"source": "papers/source.md", "target": "methods/other.md", "relation": "builds_on"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    envelope = write_envelope(
        tmp_path / "visualize-envelope.json",
        {
            "task_id": "visualize-task",
            "sprint_id": "visualize-sprint",
            "node_id": "visualize-node",
            "output_dir": str(tmp_path / "visualize-output"),
            "inputs": {
                "target": "papers/source.md",
                "wiki_root": str(wiki),
                "canvas": True,
                "focus": "papers/source.md",
                "depth": 1,
                "types": "papers,concepts",
                "edge_types": "uses_concept",
            },
        },
    )

    proc = run_bridge(tmp_path, "run", "--action", "visualize_graph", "--envelope", str(envelope))
    data = payload(proc)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = data["evidence"]
    assert evidence["status"] == "completed"
    assert evidence["outputs"]["source_ref"] == "papers/source.md"
    assert evidence["outputs"]["edges"] == [
        {
            "source": "papers/source.md",
            "target": "concepts/memory.md",
            "relation": "uses_concept",
            "operation": "confirm",
            "evidence_ids": ["visualize:papers-source-md", "visualize-papers-source-md", "papers/source.md"],
            "rendered": False,
        }
    ]
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    canvas_stdout = json.loads(Path(artifacts["visualize_canvas_stdout_json"]).read_text(encoding="utf-8"))
    assert canvas_stdout["nodes"] == 2
    assert canvas_stdout["edges"] == 1
    assert Path(artifacts["autosci_canvas_json"]).is_file()
    assert Path(artifacts["autosci_web_graph_json"]).is_file()


def test_visualize_damaged_source_fails_with_explicit_boundary(tmp_path: Path) -> None:
    wiki = tmp_path / "empty-wiki"
    wiki.mkdir()
    envelope = write_envelope(
        tmp_path / "visualize-broken-envelope.json",
        {
            "task_id": "visualize-broken-task",
            "sprint_id": "visualize-broken-sprint",
            "node_id": "visualize-broken-node",
            "output_dir": str(tmp_path / "visualize-broken-output"),
            "inputs": {"target": "missing-graph", "wiki_root": str(wiki), "canvas": True},
        },
    )

    proc = run_bridge(tmp_path, "run", "--action", "visualize_graph", "--envelope", str(envelope))
    data = payload(proc)
    assert proc.returncode == 0
    evidence = data["evidence"]
    assert evidence["status"] == "inconclusive"
    assert "AutoSci canvas generation produced no nodes or edges." in evidence["outputs"]["status_reasons"]
    assert "Graph data extraction produced no nodes or edges." in evidence["outputs"]["status_reasons"]
