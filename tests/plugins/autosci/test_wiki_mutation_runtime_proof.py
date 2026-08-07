from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "wiki_mutation_runtime_proof.py"
ROUTE_CONFIG = REPO / "harness" / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"


def run_tool(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def write_novelty_writeback(tmp_path: Path, *, applied: bool = True) -> Path:
    root = tmp_path / "artifacts/runtime/novelty"
    wiki = tmp_path / "artifacts/autosci/workspace/wiki"
    idea = wiki / "ideas/skillgen.md"
    log = wiki / "log.md"
    edge = wiki / "graph/edges.jsonl"
    index = wiki / "index.md"
    context = wiki / "graph/context_brief.md"
    for path in (idea, log, edge, index, context):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{path.name}\n", encoding="utf-8")
    root.mkdir(parents=True)
    sidecar = root / "novelty-writeback.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema": "novelty_writeback.v1",
                "status": "completed" if applied else "inconclusive",
                "outputs": {
                    "write": {
                        "requested": True,
                        "applied": applied,
                        "idea_path": "artifacts/autosci/workspace/wiki/ideas/skillgen.md",
                        "log_path": "artifacts/autosci/workspace/wiki/log.md",
                        "edge_path": "artifacts/autosci/workspace/wiki/graph/edges.jsonl",
                        "rebuilt_paths": [
                            "artifacts/autosci/workspace/wiki/index.md",
                            "artifacts/autosci/workspace/wiki/graph/context_brief.md",
                        ],
                    }
                },
                "artifacts": [
                    {"type": "wiki_idea", "path": "artifacts/autosci/workspace/wiki/ideas/skillgen.md"},
                    {"type": "wiki_log", "path": "artifacts/autosci/workspace/wiki/log.md"},
                    {"type": "wiki_graph_edges", "path": "artifacts/autosci/workspace/wiki/graph/edges.jsonl"},
                    {"type": "wiki_rebuild", "path": "artifacts/autosci/workspace/wiki/index.md"},
                    {"type": "wiki_rebuild", "path": "artifacts/autosci/workspace/wiki/graph/context_brief.md"},
                ],
                "provenance": {"timestamp": "2026-06-29T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    return sidecar


def test_completed_wiki_writeback_writes_runtime_proof_manifest(tmp_path: Path) -> None:
    sidecar = write_novelty_writeback(tmp_path)
    proof = tmp_path / "artifacts/runtime/novelty/wiki-mutation.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-writeback",
            str(sidecar),
            "--native-skill",
            "novelty",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "completed"
    assert result["runtime_proof_manifest_status"] == "written"
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    proof_entry = manifest["proofs"][0]
    assert proof_entry["native_skill"] == "novelty"
    assert proof_entry["categories"] == ["wiki_mutation_evidence"]
    assert proof_entry["collection_mode"] == "approved_side_effect"
    assert proof_entry["production_ready"] is True
    assert proof_entry["provenance"]["source"] == "wiki_writeback_sidecar"
    assert proof_entry["provenance"]["artifact_kind"] == "novelty_writeback.v1"
    assert proof_entry["evidence_refs"] == [
        "artifacts/runtime/novelty/novelty-writeback.json",
        "artifacts/autosci/workspace/wiki/ideas/skillgen.md",
        "artifacts/autosci/workspace/wiki/log.md",
        "artifacts/autosci/workspace/wiki/graph/edges.jsonl",
        "artifacts/autosci/workspace/wiki/index.md",
        "artifacts/autosci/workspace/wiki/graph/context_brief.md",
    ]


def test_incomplete_wiki_writeback_does_not_write_runtime_proof(tmp_path: Path) -> None:
    sidecar = write_novelty_writeback(tmp_path, applied=False)
    proof = tmp_path / "artifacts/runtime/novelty/wiki-mutation.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-writeback",
            str(sidecar),
            "--native-skill",
            "novelty",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "inconclusive"
    assert result["runtime_proof_manifest_status"] == "not_written"
    assert any("completed" in error or "applied" in error for error in result["errors"])
    assert not proof.exists()


def test_wiki_mutation_runtime_proof_tool_is_exposed_for_wiki_mutation_routes() -> None:
    config = json.loads(ROUTE_CONFIG.read_text(encoding="utf-8"))
    routes = {item["native_skill"]: item for item in config["routes"]}
    expected = {
        "daily-arxiv",
        "edit",
        "exp-eval",
        "exp-pilot-eval",
        "exp-run",
        "ingest",
        "init",
        "novelty",
        "paper-draft",
    }
    for skill in expected:
        assert "tools/wiki_mutation_runtime_proof.py from-writeback" in routes[skill]["primary_tools"]

    exp_pilot_run = routes["exp-pilot-run"]
    assert "does not mutate wiki pages" in " ".join(exp_pilot_run["limitations"])
    assert "tools/wiki_mutation_runtime_proof.py from-writeback" not in exp_pilot_run["primary_tools"]
