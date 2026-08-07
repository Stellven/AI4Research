from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
BRIDGE = REPO / "harness" / "plugins" / "autosci" / "bin" / "autosci_bridge.py"


def run_tool(tool: str, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / tool), *args],
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


def test_prepare_paper_source_cli_prepares_local_markdown(tmp_path: Path) -> None:
    paper = tmp_path / "SkillGen.md"
    paper.write_text("# SkillGen\n\n## Abstract\n\nGenerated skill agents.\n", encoding="utf-8")
    result = payload(
        run_tool(
            "prepare_paper_source.py",
            str(paper),
            "--workspace-root",
            str(tmp_path),
            "--raw-root",
            str(tmp_path / "raw"),
            "--no-network-fetch",
        )
    )
    assert result["schema"] == "autosci_prepare_paper_source_cli.v1"
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["canonical_ingest_path"].endswith("SkillGen.md")


def test_discover_cli_reports_inconclusive_when_network_disabled(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "papers").mkdir(parents=True)
    (wiki / "papers/skillgen.md").write_text(
        "# SkillGen\n\narXiv: 2601.00001\n\nGenerated skill agents.\n",
        encoding="utf-8",
    )
    result = payload(
        run_tool(
            "discover.py",
            "from-wiki",
            "--wiki-root",
            str(wiki),
            "--workspace-root",
            str(tmp_path),
            "--no-network-fetch",
        )
    )
    assert result["schema"] == "autosci_discover_cli.v1"
    assert result["ok"] is False
    assert result["status"] == "inconclusive"
    assert result["anchors"] == ["2601.00001"]
    assert result["candidates"] == []
    assert "Network discovery disabled" in result["limitations"][0]


def test_source_fetch_helpers_do_not_synthesize_when_network_disabled() -> None:
    s2 = payload(run_tool("fetch_s2.py", "search", "skill generation", "--no-network-fetch"))
    assert s2["schema"] == "autosci_fetch_s2_cli.v1"
    assert s2["status"] == "inconclusive"
    assert s2["items"] == []

    deepxiv = payload(run_tool("fetch_deepxiv.py", "search", "skill generation", "--no-network-fetch"))
    assert deepxiv["schema"] == "autosci_fetch_deepxiv_cli.v1"
    assert deepxiv["status"] == "inconclusive"
    assert deepxiv["items"] == []

    paper_copilot = payload(run_tool("fetch_paper_copilot.py", "venue", "iclr", "2026", "--no-network-fetch"))
    assert paper_copilot["schema"] == "autosci_fetch_paper_copilot_cli.v1"
    assert paper_copilot["status"] == "inconclusive"
    assert paper_copilot["items"] == []


def test_source_fetch_helper_does_not_write_runtime_proof_when_inconclusive(tmp_path: Path) -> None:
    proof = tmp_path / "artifacts/runtime/discover/s2-proof.json"
    s2 = payload(
        run_tool(
            "fetch_s2.py",
            "search",
            "skill generation",
            "--no-network-fetch",
            "--runtime-proof-out",
            str(proof),
            "--native-skill",
            "discover",
            extra_env={"HARNESS_DIR": str(tmp_path)},
        )
    )
    assert s2["status"] == "inconclusive"
    assert s2["runtime_proof_manifest_status"] == "not_written"
    assert not proof.exists()


def test_paper_copilot_cli_reads_file_provider_evidence(tmp_path: Path) -> None:
    provider = tmp_path / "iclr2026.json"
    provider.write_text(
        json.dumps(
            [
                {
                    "id": "paper-copilot-001",
                    "title": "SkillGen Agents with Verified Tool Use",
                    "abstract": "A provider-backed paper list entry.",
                    "url": "https://example.org/skillgen",
                }
            ]
        ),
        encoding="utf-8",
    )
    result = payload(
        run_tool(
            "fetch_paper_copilot.py",
            "venue",
            "iclr",
            "2026",
            "--url",
            provider.as_uri(),
            "--limit",
            "5",
            "--no-network-fetch",
        )
    )
    assert result["schema"] == "autosci_fetch_paper_copilot_cli.v1"
    assert result["status"] == "completed"
    assert result["ok"] is True
    assert result["provider_status"]["provider"] == "paper_copilot"
    assert result["items"][0]["provider"] == "paper_copilot"
    assert result["items"][0]["title"] == "SkillGen Agents with Verified Tool Use"


def test_paper_copilot_cli_writes_provider_runtime_proof_manifest(tmp_path: Path) -> None:
    provider = tmp_path / "iclr2026.json"
    provider.write_text(
        json.dumps(
            [
                {
                    "id": "paper-copilot-001",
                    "title": "SkillGen Agents with Verified Tool Use",
                    "abstract": "A provider-backed paper list entry.",
                    "url": "https://example.org/skillgen",
                }
            ]
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "artifacts/runtime/discover/paper-copilot.evidence.json"
    proof = tmp_path / "artifacts/runtime/discover/paper-copilot.proof.json"
    result = payload(
        run_tool(
            "fetch_paper_copilot.py",
            "venue",
            "iclr",
            "2026",
            "--url",
            provider.as_uri(),
            "--limit",
            "5",
            "--no-network-fetch",
            "--evidence-out",
            str(evidence),
            "--runtime-proof-out",
            str(proof),
            "--native-skill",
            "discover",
            "--proof-collection-mode",
            "native_autosci_replay",
            extra_env={"HARNESS_DIR": str(tmp_path)},
        )
    )
    assert result["status"] == "completed"
    assert result["runtime_proof_manifest_status"] == "written"
    assert evidence.exists()
    assert proof.exists()
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    proof_entry = manifest["proofs"][0]
    assert proof_entry["native_skill"] == "discover"
    assert proof_entry["categories"] == ["provider_source_evidence"]
    assert proof_entry["collection_mode"] == "native_autosci_replay"
    assert proof_entry["production_ready"] is True
    assert proof_entry["provenance"]["source"] == "paper_copilot"
    assert proof_entry["provenance"]["artifact_kind"] == "venue_response"
    assert proof_entry["evidence_refs"] == ["artifacts/runtime/discover/paper-copilot.evidence.json"]


def test_paper_copilot_file_provider_does_not_default_to_external_runtime(tmp_path: Path) -> None:
    provider = tmp_path / "iclr2026.json"
    provider.write_text(
        json.dumps(
            [
                {
                    "id": "paper-copilot-001",
                    "title": "SkillGen Agents with Verified Tool Use",
                    "url": "https://example.org/skillgen",
                }
            ]
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "artifacts/runtime/discover/paper-copilot.proof.json"
    result = payload(
        run_tool(
            "fetch_paper_copilot.py",
            "venue",
            "iclr",
            "2026",
            "--url",
            provider.as_uri(),
            "--limit",
            "5",
            "--no-network-fetch",
            "--runtime-proof-out",
            str(proof),
            "--native-skill",
            "discover",
            extra_env={"HARNESS_DIR": str(tmp_path)},
        )
    )
    assert result["runtime_proof_manifest_status"] == "written"
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    assert manifest["proofs"][0]["categories"] == ["provider_source_evidence"]


def test_visualize_graph_data_reads_real_wiki_graph_and_rejects_unknown_flags(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "papers").mkdir(parents=True)
    (wiki / "ideas").mkdir()
    (wiki / "graph").mkdir()
    (wiki / "papers/source.md").write_text("# Source Paper\n\nGrounded source text.\n", encoding="utf-8")
    (wiki / "ideas/idea.md").write_text("# Idea\n\nGrounded idea text.\n", encoding="utf-8")
    (wiki / "graph/edges.jsonl").write_text(
        json.dumps({"source": "papers/source", "target": "ideas/idea", "relation": "inspires"}) + "\n",
        encoding="utf-8",
    )
    graph_out = tmp_path / "graph.json"

    result = payload(run_tool("visualize.py", "graph-data", "--wiki-root", str(wiki), "--out", str(graph_out)))
    assert result["ok"] is True
    assert graph_out.exists()
    assert {node["id"] for node in result["nodes"]} >= {"papers/source.md", "ideas/idea.md", "papers/source", "ideas/idea"}
    assert result["edges"][0]["relation"] == "inspires"

    rejected = run_tool("visualize.py", "graph-data", "--wiki-root", str(wiki), "--unknown-flag")
    assert rejected.returncode == 2
    error = json.loads(rejected.stderr)
    assert error["error_type"] == "unsupported_cli_flag"
    assert error["unsupported_args"] == ["--unknown-flag"]


def test_ask_wiki_retrieval_paths_are_cross_platform_canonical(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "papers").mkdir(parents=True)
    (wiki / "graph").mkdir()
    (wiki / "papers/skillgen.md").write_text(
        "# SkillGen\n\nSkillGen evidence links generated skills to verifier traces.\n",
        encoding="utf-8",
    )
    (wiki / "graph/context_brief.md").write_text("# Context\n\nSkillGen evidence context.\n", encoding="utf-8")
    (wiki / "graph/open_questions.md").write_text("# Open Questions\n\nHow robust is SkillGen evidence?\n", encoding="utf-8")
    (wiki / "index.md").write_text("# Index\n\nSkillGen evidence index.\n", encoding="utf-8")
    envelope = tmp_path / "ask-envelope.json"
    envelope.write_text(
        json.dumps(
            {
                "task_id": "task-ask-paths",
                "sprint_id": "run-ask-paths",
                "node_id": "node-ask-paths",
                "output_dir": "artifacts/autosci/ask-paths",
                "inputs": {"wiki_root": str(wiki), "query": "SkillGen evidence", "limit": 3},
                "outputs": {"evidence_payload_path": "artifacts/autosci/ask-paths/ask.evidence.json"},
            }
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(BRIDGE), "run", "--action", "ask_wiki", "--envelope", str(envelope)],
        cwd=REPO / "harness",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    evidence = json.loads((tmp_path / summary["evidence_path"]).read_text(encoding="utf-8"))
    retrieval_path = next(item["path"] for item in evidence["artifacts"] if item["type"] == "ask_retrieval_json")
    retrieval = json.loads((tmp_path / retrieval_path).read_text(encoding="utf-8"))
    paths = [
        *(str(hit["path"]) for hit in retrieval["hits"]),
        *(str(source["path"]) for source in retrieval["wiki_context"]["sources"].values()),
    ]
    assert paths
    assert all("\\" not in path for path in paths)
    assert "wiki/papers/skillgen.md" in paths
