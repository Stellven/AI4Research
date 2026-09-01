from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
REPO = HARNESS.parent
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"
GATE = HARNESS / "evaluators" / "scientific" / "autosci_skill_run_gate.py"
PAPER = REPO / "tests" / "plugins" / "autosci" / "fixtures" / "skillgen_operator_smoke_paper.md"
FULL_LIFECYCLE_NODES = [
    "literature_discover",
    "paper_ingest",
    "paper_analyze",
    "memory_update_initial",
    "graph_update",
    "claim_extract",
    "method_extract",
    "code_evidence_map",
    "idea_generate",
    "idea_evaluate",
    "experiment_design",
    "experiment_run",
    "experiment_monitor",
    "claim_verify",
    "report_draft",
    "artifact_review",
    "memory_update_final",
    "workflow_evolve",
    "report_plan",
    "publication_produce",
]
DEMO_SCHEDULER_NODES = [
    "paper_ingest",
    "paper_analyze",
    "claim_extract",
    "method_extract",
]

MINIMAL_STRUCTURAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 1\n0000000000 65535 f \n"
    b"trailer\n<<>>\nstartxref\n9\n%%EOF\n"
)


def run_shim(tmp_path: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_gate(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), str(path)],
        cwd=HARNESS,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def assert_gate_inconclusive_without_reasons(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.returncode == 3, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "inconclusive"
    assert result["reasons"] == []
    return result


def write_pdf(path: Path, text: str) -> None:
    fitz = pytest.importorskip("fitz")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def write_structural_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MINIMAL_STRUCTURAL_PDF)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def write_weak_lifecycle_summary(tmp_path: Path, path: Path) -> None:
    _write_json(
        path,
        {
            "schema": "scientific_lifecycle.v1",
            "workflow_id": "scientific_research_lifecycle_full_v1",
            "job_id": "job-scheduler-lifecycle-weak",
            "sprint_id": "job-scheduler-lifecycle-weak",
            "lifecycle_status": "passed",
            "required_nodes": FULL_LIFECYCLE_NODES,
            "node_results": {
                node_id: {
                    "node_id": node_id,
                    "status": "passed",
                }
                for node_id in FULL_LIFECYCLE_NODES
            },
            "gate_results": {
                node_id: {
                    "node_id": node_id,
                    "status": "passed",
                    "ok": True,
                }
                for node_id in FULL_LIFECYCLE_NODES
            },
            "blocked_nodes": {},
            "lifecycle_gate_result": {"ok": True, "status": "passed"},
        },
    )


def write_strict_lifecycle_summary(tmp_path: Path, path: Path) -> None:
    job_id = "job-scheduler-lifecycle-strict"
    node_results: dict[str, Any] = {}
    gate_results: dict[str, Any] = {}
    for node_id in FULL_LIFECYCLE_NODES:
        node_dir = tmp_path / "artifacts/scientific/lifecycle-handoff" / node_id
        artifact_path = node_dir / "workflow_evolution.json"
        bridge_result_path = node_dir / "bridge_result.json"
        operator_result_path = node_dir / "operator_result.json"
        artifact = {
            "schema": "workflow_evolution.v1",
            "task_id": f"task-{node_id}",
            "sprint_id": job_id,
            "node_id": node_id,
            "status": "completed",
            "inputs": {"handoff_test": True},
            "outputs": {
                "evolution": {
                    "proposal_id": f"proposal-{node_id}",
                    "scope": "scheduler lifecycle handoff",
                    "change_type": "other",
                    "rationale": f"Strict handoff fixture for {node_id}.",
                    "expected_effect": "Proves lifecycle summary handoff has runtime sidecars.",
                    "approval_state": "approved",
                    "evidence_ids": [f"evidence:{node_id}"],
                    "review": {
                        "human_accept_reject_required": False,
                        "protected_core_edits_applied": False,
                        "application_state": "not_applied",
                    },
                }
            },
            "artifacts": [],
            "provenance": {
                "operator_id": f"operator-{node_id}",
                "implementation_package": "harness.plugins.autosci.tests",
                "timestamp": "2026-06-26T00:00:00Z",
            },
            "limitations": ["Synthetic strict lifecycle handoff fixture."],
        }
        _write_json(artifact_path, artifact)
        artifact_hash = _sha256(artifact_path)
        _write_json(bridge_result_path, {"node_id": node_id, "status": "completed", "artifact_sha256": artifact_hash})
        _write_json(operator_result_path, {"node_id": node_id, "status": "completed", "bridge_result_path": _rel(bridge_result_path, tmp_path)})
        node_results[node_id] = {
            "job_id": job_id,
            "node_id": node_id,
            "logical_operator": f"Logical{node_id}",
            "operator_id": f"operator-{node_id}",
            "action": f"action_{node_id}",
            "status": "passed",
            "artifact_path": _rel(artifact_path, tmp_path),
            "artifact_sha256": artifact_hash,
            "bridge_result_path": _rel(bridge_result_path, tmp_path),
            "expected_schema": "workflow_evolution.v1",
            "gate": f"G_{node_id.upper()}",
            "operator_result_path": _rel(operator_result_path, tmp_path),
        }
        gate_results[node_id] = {
            "job_id": job_id,
            "node_id": node_id,
            "gate": f"G_{node_id.upper()}",
            "status": "passed",
            "ok": True,
            "reasons": [],
            "warnings": [],
        }
    _write_json(
        path,
        {
            "schema": "scientific_lifecycle.v1",
            "workflow_id": "scientific_research_lifecycle_full_v1",
            "job_id": job_id,
            "sprint_id": job_id,
            "execution_owner": "solar.operator_runtime.scheduler_lifecycle_handoff_test",
            "lifecycle_status": "passed",
            "required_nodes": FULL_LIFECYCLE_NODES,
            "node_results": node_results,
            "gate_results": gate_results,
            "blocked_nodes": {},
            "workflow_config_alignment": {
                "ok": True,
                "status": "aligned",
                "issues": [],
            },
            "lifecycle_gate_result": {"ok": True, "status": "passed"},
        },
    )


def test_autosci_skill_shim_lists_configured_skills(tmp_path: Path) -> None:
    proc = run_shim(tmp_path, "skills", "list")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 28
    skills = {item["skill"]: item for item in payload["skills"]}
    assert skills["ingest"]["solar_backend_action"] == "ingest_paper"
    assert skills["research"]["side_effect_policy"] == "approval_required"


def test_autosci_skill_shim_lists_skills_with_dollar_alias(tmp_path: Path) -> None:
    proc = run_shim(tmp_path, "$skills")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 28
    assert {item["skill"] for item in payload["skills"]} >= {"ingest", "research", "poster"}


def test_autosci_skill_shim_runs_ingest_and_gate(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "skill",
        "ingest",
        "--paper",
        str(PAPER),
        "--smoke",
        "--run-id",
        "shim-ingest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["status"] == "inconclusive"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2
    assert summary["workspace_updated_count"] > 0

    evidence_path = Path(summary["evidence_path"])
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == "inconclusive"
    actions = payload["outputs"]["skill_run"]["actions"]
    assert [action["action"] for action in actions] == ["ingest_paper", "analyze_paper"]
    assert Path(actions[0]["evidence_path"]).exists()
    workspace = payload["outputs"]["skill_run"]["workspace"]
    assert Path(workspace["wiki_root"]).exists()
    assert (
        tmp_path
        / "artifacts/autosci/workspace/wiki/papers/paper-skillgen-operator-smoke-paper.md"
    ).exists()
    assert (tmp_path / "artifacts/autosci/workspace/wiki/index.md").exists()

    gate = run_gate(evidence_path)
    assert_gate_inconclusive_without_reasons(gate)


def test_autosci_skill_shim_runs_ingest_with_dollar_skill_alias(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$skill",
        "ingest",
        "--paper",
        str(PAPER),
        "--smoke",
        "--run-id",
        "shim-dollar-skill-ingest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2


def test_autosci_skill_shim_runs_direct_dollar_skill(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$ingest",
        "--paper",
        str(PAPER),
        "--smoke",
        "--run-id",
        "shim-dollar-ingest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2


def test_autosci_skill_shim_runs_single_token_dollar_command_with_flags(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$survey --format latex --topic test --smoke --run-id shim-single-token-dollar-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "survey"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] > 0


def test_autosci_skill_shim_runs_text_dollar_command(tmp_path: Path) -> None:
    command = " ".join(
        [
            "$ingest",
            "--paper",
            shlex.quote(str(PAPER)),
            "--smoke",
            "--run-id",
            "shim-text-dollar-ingest",
        ]
    )
    proc = run_shim(tmp_path, "text", command)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2


def test_autosci_skill_shim_maps_positional_ingest_source(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$ingest",
        str(PAPER),
        "--run-id",
        "shim-positional-ingest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["paper_path"] == str(PAPER)
    action = payload["outputs"]["skill_run"]["actions"][0]
    paper = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert "Fixture abstract" not in json.dumps(paper)
    assert "SKILLGEN" in paper["outputs"]["paper"]["title"]
    preparation = paper["outputs"]["paper"]["preparation"]
    assert preparation["native_prepare_paper_source"]["schema"] == "autosci_prepare_paper_source_cli.v1"
    assert preparation["native_prepare_paper_source"]["status"] == "completed"
    artifact_types = {artifact["type"] for artifact in paper["artifacts"]}
    assert "prepare_paper_source_native_payload_json" in artifact_types
    assert "prepare_paper_source_native_stdout_json" in artifact_types
    artifact_paths = [artifact["path"] for artifact in paper["artifacts"]]
    assert not any("/OpenSolar/harness/artifacts/autosci/workspace/raw" in path for path in artifact_paths)


def test_autosci_skill_shim_ingests_pdf_with_extracted_text_and_no_fixture_leakage(tmp_path: Path) -> None:
    pdf_path = tmp_path / "raw" / "papers" / "SkillGen.pdf"
    write_pdf(
        pdf_path,
        "SKILLGEN: Verified Inference-Time Agent Skill Synthesis\n"
        "arXiv: 2601.00001\n"
        "Abstract\n"
        "This PDF describes inference-time skill synthesis with verifier gates and measurable gains.\n"
        "1. Introduction\n"
        "The pipeline trains reusable agent skills and evaluates repairs, regressions, and net gain.",
    )
    proc = run_shim(
        tmp_path,
        "$ingest",
        str(pdf_path),
        "--run-id",
        "shim-pdf-ingest-source-grounded",
        extra_env={"AUTOSCI_DISABLE_NETWORK_FETCH": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    paper = evidence["outputs"]["paper"]
    preparation = paper["preparation"]
    assert evidence["status"] == "completed"
    assert preparation["original_format"] == "pdf"
    assert preparation["extracted_text_path"]
    assert preparation["source_fetch_status"] == "skipped_network_disabled"
    assert preparation["native_prepare_paper_source"]["schema"] == "autosci_prepare_paper_source_cli.v1"
    assert preparation["native_prepare_paper_source"]["status"] == "completed"
    assert paper["parse_status"] == "parsed"
    assert "SKILLGEN" in paper["title"]
    assert "Fixture abstract" not in json.dumps(evidence)
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {
        "extracted_pdf_text",
        "ingest_final_source_registration_boundary_json",
        "research_graph_update_json",
        "research_memory_update_json",
        "provider_source_runtime_proof_manifest_json",
        "prepare_paper_source_native_payload_json",
        "prepare_paper_source_native_stdout_json",
        "synthetic_latex",
    } <= artifact_types
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "ingest"
    assert source_proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert any(ref.endswith("raw/papers/SkillGen.pdf") for ref in source_proof_entry["evidence_refs"])
    assert any(ref.endswith(".txt") for ref in source_proof_entry["evidence_refs"])
    boundary = paper["final_source_registration_boundary"]
    assert boundary["schema"] == "autosci_ingest_final_source_registration_boundary.v1"
    assert boundary["status"] == "ingest_source_registration_ready"
    assert boundary["source_preparation_verified"] is True
    assert boundary["parse_quality_ready"] is True
    assert boundary["raw_artifact_provenance_ready"] is True
    assert boundary["downstream_handoff_ready"] is True
    assert boundary["wiki_registration_ready"] is True
    assert boundary["missing"] == []
    prepared_paths = [
        artifact["path"]
        for artifact in evidence["artifacts"]
        if artifact["type"] in {"extracted_pdf_text", "synthetic_latex"}
    ]
    assert all(path.startswith("artifacts/autosci/workspace/raw/tmp/papers/") for path in prepared_paths)


def test_autosci_skill_shim_ingest_final_source_registration_boundary_ready_with_wiki_state(tmp_path: Path) -> None:
    source_path = tmp_path / "raw" / "papers" / "registered_source.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "\n".join(
            [
                "# Registered SkillGen Source",
                "",
                "## Abstract",
                "This paper source is already registered in the AutoSci wiki graph.",
                "",
                "## Method",
                "It records source preparation, graph handoff, and wiki registration evidence.",
            ]
        ),
        encoding="utf-8",
    )
    wiki_root = tmp_path / "custom-wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    paper_id = "paper-registered-source"
    paper_page = wiki_root / "papers" / f"{paper_id}.md"
    paper_page.write_text(
        f"# Registered SkillGen Source\n\nPaper id: `{paper_id}`\n",
        encoding="utf-8",
    )
    (wiki_root / "log.md").write_text(f"## Ingest\n\nRegistered `{paper_id}`.\n", encoding="utf-8")
    (wiki_root / "graph" / "edges.jsonl").write_text(
        json.dumps(
            {
                "source": "ingest",
                "edge_type": "source_candidate_ingested",
                "target": paper_id,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (wiki_root / "index.md").write_text(f"# Wiki\n\n## Papers\n\n- [{paper_id}](papers/{paper_page.name})\n", encoding="utf-8")
    (wiki_root / "graph" / "context_brief.md").write_text("# Context\n\nRegistered source context.\n", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$ingest",
        str(source_path),
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-ingest-final-source-registration",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["execution_status"] == "partial"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["inputs"]["wiki_root"] == str(wiki_root)
    boundary = evidence["outputs"]["final_source_registration_boundary"]
    assert boundary["status"] == "ingest_source_registration_ready"
    assert boundary["final_registration_ready"] is True
    assert boundary["source_preparation_verified"] is True
    assert boundary["parse_quality_ready"] is True
    assert boundary["raw_artifact_provenance_ready"] is True
    assert boundary["downstream_handoff_ready"] is True
    assert boundary["wiki_registration_ready"] is True
    assert boundary["missing"] == []
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {
        "ingest_final_source_registration_boundary_json",
        "research_graph_update_json",
        "research_memory_update_json",
        "provider_source_runtime_proof_manifest_json",
        "wiki_mutation_runtime_proof_manifest_json",
    } <= artifact_types
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "ingest"
    assert source_proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert any(ref.endswith("raw/papers/registered_source.md") for ref in source_proof_entry["evidence_refs"])
    wiki_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    wiki_proof_entry = wiki_proof["proofs"][0]
    assert wiki_proof_entry["native_skill"] == "ingest"
    assert wiki_proof_entry["categories"] == ["wiki_mutation_evidence"]
    assert any(ref.endswith(f"papers/{paper_page.name}") for ref in wiki_proof_entry["evidence_refs"])
    assert any(ref.endswith("graph/edges.jsonl") for ref in wiki_proof_entry["evidence_refs"])


def test_autosci_skill_shim_accepts_original_ingest_followup_flags(tmp_path: Path) -> None:
    command = " ".join(
        [
            "$ingest",
            shlex.quote(str(PAPER)),
            "--discover",
            "--visualize",
            "--run-id",
            "shim-ingest-followup-flags",
        ]
    )
    proc = run_shim(tmp_path, "text", command)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ingest"
    assert summary["action_count"] == 2

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    options = payload["inputs"]["native_options"]
    assert options["discover"] is True
    assert options["visualize"] is True


def test_autosci_skill_shim_accepts_discover_from_wiki_limit(tmp_path: Path) -> None:
    wiki_papers = tmp_path / "artifacts/autosci/workspace/wiki/papers"
    wiki_papers.mkdir(parents=True)
    wiki_papers.joinpath("seed.md").write_text(
        "---\ntitle: SkillGen Seed\narxiv: 2401.00001\n---\n# SkillGen Seed\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(tmp_path)
    env["AUTOSCI_DISABLE_NETWORK_FETCH"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            str(SHIM),
            "$discover",
            "--from-wiki",
            "--limit",
            "10",
            "--run-id",
            "shim-discover-from-wiki",
        ],
        cwd=HARNESS,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "discover"
    assert summary["execution_status"] == "partial"
    evidence_path = Path(summary["evidence_path"])
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    discovery = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert discovery["status"] == "inconclusive"
    assert discovery["outputs"]["mode"] == "wiki"
    assert discovery["outputs"]["limit"] == 10
    assert discovery["outputs"]["candidates"] == []
    boundary = discovery["outputs"]["source_provider_boundary"]["final_shortlist_boundary"]
    assert boundary["schema"] == "autosci_discover_final_shortlist_boundary.v1"
    assert boundary["final_shortlist_ready"] is False
    assert boundary["status"] == "discover_shortlist_incomplete"
    assert "discovery shortlist is empty" in boundary["blocking_reasons"]
    artifact_types = {artifact["type"] for artifact in discovery["artifacts"]}
    assert "discover_native_stdout_json" in artifact_types
    assert "discover_native_payload_json" in artifact_types
    assert "discover_final_shortlist_boundary_json" in artifact_types
    assert "local_fixture" not in json.dumps(discovery)


def test_autosci_skill_shim_discover_runtime_requires_provider_boundary(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-discover-runtime"
    external_dir.mkdir()
    allowlist = external_dir / "allowlist.json"
    before = external_dir / "before.json"
    after = external_dir / "after.json"
    runtime = external_dir / "source-runtime.json"
    allowlist.write_text('{"allowed": ["source-fetch"]}\n', encoding="utf-8")
    before.write_text('{"state": "before-source-fetch"}\n', encoding="utf-8")
    after.write_text('{"state": "after-source-fetch"}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-source-runtime-generic",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "discover_literature",
                        "status": "completed",
                        "exit_code": 0,
                        "candidates": [
                            {
                                "candidate_id": "generic-runtime-source",
                                "title": "Generic Runtime Source Without Provider Channel",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$discover",
        "skill generation",
        "--approval-ref",
        "approval-source-runtime-generic",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-discover-generic-runtime-boundary",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    discovery = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert discovery["status"] == "inconclusive"
    assert discovery["outputs"]["mode"] == "discover_literature_runtime_pending"
    boundary = discovery["outputs"]["source_provider_boundary"]
    assert boundary["status"] == "incomplete"
    assert boundary["completed"] is False
    assert boundary["generic_channels"] == ["approved_runtime"]
    assert "no non-fixture provider source channel was present" in boundary["invalid_reasons"]
    final_boundary = boundary["final_shortlist_boundary"]
    assert final_boundary["final_shortlist_ready"] is False
    assert final_boundary["status"] == "discover_shortlist_incomplete"
    assert "provider-backed source channel is missing" in final_boundary["blocking_reasons"]
    assert not any(
        artifact["type"] == "provider_source_runtime_proof_manifest_json"
        for artifact in discovery["artifacts"]
    )


def test_autosci_skill_shim_discover_runtime_attaches_provider_runtime_proof(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-discover-provider-runtime"
    external_dir.mkdir()
    allowlist = external_dir / "allowlist.json"
    before = external_dir / "before.json"
    after = external_dir / "after.json"
    runtime = external_dir / "source-runtime.json"
    allowlist.write_text('{"allowed": ["semantic_scholar"]}\n', encoding="utf-8")
    before.write_text('{"state": "before-source-fetch"}\n', encoding="utf-8")
    after.write_text('{"state": "after-source-fetch"}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-source-runtime-provider",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "discover_literature",
                        "status": "completed",
                        "exit_code": 0,
                        "command_run": "approved-semantic-scholar-fetch",
                        "candidates": [
                            {
                                "candidate_id": "runtime-source-001",
                                "title": "Runtime Verified Skill Generation Source",
                                "url": "https://arxiv.org/abs/2601.00005",
                                "source_channels": ["search_s2"],
                                "ranking_score": 0.93,
                                "ranking_rationale": "Approved source runtime returned this source.",
                                "dedup_status": "new",
                                "fetch_status": "fetched",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$discover",
        "skill generation",
        "--approval-ref",
        "approval-source-runtime-provider",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-discover-provider-runtime-proof",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert summary["status"] == "completed"
    assert summary["execution_status"] == "completed"
    assert summary["runtime_status_basis"] == "validated_discover_runtime"
    assert summary["route_coverage_status"] == "partial"
    assert Path(summary["managed_run_path"]) == tmp_path / "artifacts/autosci/runs/shim-discover-provider-runtime-proof"
    assert Path(summary["artifact_root"]) == tmp_path / "artifacts/autosci"
    assert Path(summary["harness_root"]) == tmp_path
    assert payload["outputs"]["skill_run"]["route"]["coverage_status"] == "partial"
    action = payload["outputs"]["skill_run"]["actions"][0]
    discovery = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert discovery["status"] == "completed"
    assert discovery["outputs"]["mode"] == "discover_literature_runtime_verified"
    boundary = discovery["outputs"]["source_provider_boundary"]
    assert boundary["status"] == "completed"
    assert boundary["provider_channels"] == ["search_s2"]

    proof_artifact = next(
        artifact
        for artifact in discovery["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "discover"
    assert proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "live_provider"
    assert any(ref.endswith("source-runtime.json") for ref in proof_entry["evidence_refs"])
    assert any(ref == "https://arxiv.org/abs/2601.00005" for ref in proof_entry["evidence_refs"])


def test_autosci_skill_shim_discover_wiki_runtime_proof_is_not_live_provider(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-discover-wiki-runtime"
    external_dir.mkdir()
    wiki_source = tmp_path / "workspace" / "wiki" / "papers" / "paper-runtime-wiki-source.md"
    wiki_source.parent.mkdir(parents=True)
    wiki_source.write_text(
        "# Runtime Wiki Source\n\narXiv:2601.00006\n",
        encoding="utf-8",
    )
    allowlist = external_dir / "allowlist.json"
    before = external_dir / "before.json"
    after = external_dir / "after.json"
    runtime = external_dir / "source-runtime.json"
    allowlist.write_text('{"allowed": ["workspace_wiki"]}\n', encoding="utf-8")
    before.write_text('{"state": "before-wiki-discovery"}\n', encoding="utf-8")
    after.write_text('{"state": "after-wiki-discovery"}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-source-runtime-wiki",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "discover_literature",
                        "status": "completed",
                        "exit_code": 0,
                        "command_run": "approved-local-wiki-discovery",
                        "candidates": [
                            {
                                "candidate_id": "runtime-wiki-source-001",
                                "title": "Runtime Verified Local Wiki Source",
                                "source_ref": str(wiki_source),
                                "source_channels": ["wiki"],
                                "ranking_score": 0.91,
                                "ranking_rationale": "Approved local wiki runtime produced this source.",
                                "dedup_status": "new",
                                "fetch_status": "fetched",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$discover",
        "--from-wiki",
        "--limit",
        "3",
        "--approval-ref",
        "approval-source-runtime-wiki",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-discover-wiki-runtime-proof",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    discovery = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert discovery["status"] == "completed"
    boundary = discovery["outputs"]["source_provider_boundary"]
    assert boundary["status"] == "completed"
    assert boundary["provider_channels"] == ["wiki"]
    final_boundary = boundary["final_shortlist_boundary"]
    assert final_boundary["status"] == "final_shortlist_ready"
    assert final_boundary["final_shortlist_ready"] is True

    proof_artifact = next(
        artifact
        for artifact in discovery["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "discover"
    assert proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "native_autosci_replay"
    assert "local wiki/source evidence" in proof_entry["description"]
    assert any(ref.endswith("source-runtime.json") for ref in proof_entry["evidence_refs"])
    assert "workspace/wiki/papers/paper-runtime-wiki-source.md" in proof_entry["evidence_refs"]


def test_autosci_skill_shim_discover_declared_scope_fails_without_covered_ranked_evidence(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-discover-declared-scope"
    external_dir.mkdir()
    allowlist = external_dir / "allowlist.json"
    before = external_dir / "before.json"
    after = external_dir / "after.json"
    runtime = external_dir / "source-runtime.json"
    allowlist.write_text('{"allowed": ["semantic_scholar"]}\n', encoding="utf-8")
    before.write_text('{"state": "before-source-fetch"}\n', encoding="utf-8")
    after.write_text('{"state": "after-source-fetch"}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-source-runtime-weak-discovery",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "discover_literature",
                        "status": "completed",
                        "exit_code": 0,
                        "command_run": "approved-semantic-scholar-fetch",
                        "candidates": [
                            {
                                "candidate_id": "weak-source-001",
                                "title": "High Temperature Superconductivity In Layered Materials",
                                "url": "https://example.test/superconductivity",
                                "source_channels": ["search_s2"],
                                "ranking_score": 1.0,
                            },
                            {
                                "candidate_id": "weak-source-002",
                                "title": "Selenium Battery Electrolyte Interfaces",
                                "url": "https://example.test/selenium",
                                "source_channels": ["search_s2"],
                                "ranking_score": 1.0,
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$discover",
        "--topic",
        (
            "Battery electrolyte discovery\n"
            "Required criteria: grid storage; lifetime; material availability; commercial readiness\n"
            "Framing questions: grid storage lifetime; material availability; commercial readiness"
        ),
        "--approval-ref",
        "approval-source-runtime-weak-discovery",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-discover-declared-scope-fails",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    action = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"][0]
    discovery = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert discovery["status"] == "inconclusive"
    boundary = discovery["outputs"]["source_provider_boundary"]["final_shortlist_boundary"]
    assert boundary["final_shortlist_ready"] is False
    assert "declared-scope discovery requires non-default ranking scores and rationales" in boundary["blocking_reasons"]
    assert "declared discovery criteria or framing questions are not covered by candidate evidence" in boundary["blocking_reasons"]
    assert boundary["ranking_audit"]["all_scores_default_one"] is True
    coverage = boundary["requested_coverage_audit"]
    assert coverage["declared_scope"] is True
    assert "grid storage" in coverage["missing_criteria"]
    assert "commercial readiness" in coverage["unresolved_framing_questions"]


def test_autosci_bridge_write_result_handles_long_windows_style_artifact_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.path.insert(0, str(SHIM.parent))
    bridge = __import__("autosci_bridge")
    monkeypatch.setattr(bridge, "HARNESS_DIR", tmp_path)
    long_dir = tmp_path / ("battery-grid-storage-electrolyte-material-availability-" * 2)[:96]
    long_dir = long_dir / ("commercial-readiness-lifetime-cycle-stability-" * 2)[:88]
    long_dir = long_dir / ("declared-framing-questions-and-provider-evidence-" * 2)[:92]
    evidence_path = long_dir / "discover_literature.evidence.json"
    result_path = long_dir / "result.json"
    ledger_path = long_dir / "evidence.jsonl"
    handoff_path = long_dir / "handoff.md"
    assert len(str(evidence_path)) > 260

    result = bridge._write_result(
        "discover_literature",
        {
            "outputs": {
                "evidence_payload_path": str(evidence_path),
                "result_path": str(result_path),
                "evidence_jsonl": str(ledger_path),
                "handoff_path": str(handoff_path),
            }
        },
        {
            "schema": "literature_discovery.v1",
            "status": "inconclusive",
            "inputs": {},
            "outputs": {"query": "grid storage battery electrolytes", "candidates": []},
            "artifacts": [],
            "limitations": ["shortlist incomplete"],
        },
    )

    assert result["status"] == "inconclusive"
    actual_evidence_path = bridge._resolve_harness_path(result["evidence_path"])
    assert os.path.isfile(bridge._windows_long_path(actual_evidence_path))
    assert os.path.isfile(bridge._windows_long_path(result_path))
    assert os.path.isfile(bridge._windows_long_path(ledger_path))
    assert os.path.isfile(bridge._windows_long_path(handoff_path))
    with open(bridge._windows_long_path(actual_evidence_path), encoding="utf-8") as fh:
        assert json.load(fh)["schema"] == "literature_discovery.v1"
    with open(bridge._windows_long_path(result_path), encoding="utf-8") as fh:
        saved_result = json.load(fh)
        assert saved_result["evidence_path"] == result["evidence_path"]
        assert "artifacts/autosci/short-paths/" in saved_result["evidence_path"].replace("\\", "/")
    with open(bridge._windows_long_path(ledger_path), encoding="utf-8") as fh:
        assert fh.read().strip()


def test_autosci_skill_shim_runs_research_pipeline(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "skill",
        "research",
        "--paper",
        str(PAPER),
        "--topic",
        "agent skill learning",
        "--smoke",
        "--run-id",
        "shim-research",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["status"] == "inconclusive"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 16
    assert summary["failed_count"] == 0

    evidence_path = Path(summary["evidence_path"])
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    actions = [item["action"] for item in payload["outputs"]["skill_run"]["actions"]]
    assert actions == [
        "ingest_paper",
        "analyze_paper",
        "update_memory",
        "update_graph",
        "discover_literature",
        "extract_claims",
        "extract_methods",
        "map_code_evidence",
        "generate_ideas",
        "evaluate_ideas",
        "design_experiment",
        "run_experiment",
        "monitor_experiment",
        "verify_claim",
        "write_report",
        "evolve_workflow",
    ]
    assert (tmp_path / "artifacts/autosci/runs/shim-research/report.md").exists()
    assert (tmp_path / "artifacts/autosci/runs/shim-research/publication_bundle.json").exists()
    progress_path = tmp_path / "artifacts/autosci/runs/shim-research/autosci_skill_run_progress.json"
    assert progress_path.exists()
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress["schema"] == "autosci_skill_run_progress.v1"
    assert progress["status"] == "inconclusive"
    assert progress["completed_count"] == 16
    assert (tmp_path / "artifacts/autosci/workspace/wiki/ideas/idea-001.md").exists()
    assert (tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-001.md").exists()
    assert (tmp_path / "artifacts/autosci/workspace/wiki/outputs/report-skillgen-operator-smoke.md").exists()
    assert any(artifact["type"] == "skill_run_progress_json" for artifact in payload["artifacts"])

    gate = run_gate(evidence_path)
    assert_gate_inconclusive_without_reasons(gate)


def test_research_preserves_full_natural_language_prompt_and_run_id(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "梳理网页",
        "https://example.org/seed",
        "并生成中文报告",
        "--run-id",
        "real-data-run-001",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    expected = "梳理网页 https://example.org/seed 并生成中文报告"
    assert payload["inputs"]["target"] == expected
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["sprint_id"] == "real-data-run-001"
    assert evidence["inputs"]["prompt"] == expected
    assert evidence["inputs"]["run_id"] == "real-data-run-001"


def test_autosci_skill_shim_research_start_from_writes_pipeline_artifacts(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen-main",
        "--venue",
        "ICLR",
        "--start-from",
        "stage3-collect",
        "--skip-paper",
        "--run-id",
        "shim-research-start-from",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 1
    assert summary["schema_only_count"] == 1

    progress = tmp_path / "artifacts/autosci/workspace/wiki/outputs/pipeline-progress.md"
    report = tmp_path / "artifacts/autosci/workspace/wiki/outputs/PIPELINE_REPORT.md"
    state_path = tmp_path / "artifacts/autosci/workspace/wiki/outputs/pipeline-state.json"
    assert progress.exists()
    assert report.exists()
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pipeline"]["target"] == "skillgen-main"
    assert state["pipeline"]["venue"] == "ICLR"
    assert state["pipeline"]["resume_from"] == "collect"
    assert state["pipeline"]["skip_paper"] is True

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["start_from"] == "stage3-collect"
    assert payload["inputs"]["native_options"]["skip_paper"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "run_research_lifecycle"
    assert action["schema"] == "workflow_evolution.v1"
    assert action["gate_status"] == "schema_only"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evidence["status"] == "inconclusive"
    assert evolution["current_stage"] == "collect"
    assert any(artifact["type"] == "pipeline_progress_markdown" for artifact in evidence["artifacts"])
    assert any(artifact["type"] == "pipeline_report_markdown" for artifact in evidence["artifacts"])
    assert any(artifact["type"] == "pipeline_state_json" for artifact in evidence["artifacts"])


def test_autosci_skill_shim_research_lifecycle_completes_from_verified_stage_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for folder in ("papers", "ideas", "experiments", "outputs"):
        (wiki_root / folder).mkdir(parents=True, exist_ok=True)
    (wiki_root / "papers/paper-skillgen.md").write_text("# SkillGen Paper\n", encoding="utf-8")
    (wiki_root / "ideas/idea-skillgen.md").write_text("# SkillGen Idea\n", encoding="utf-8")
    (wiki_root / "experiments/exp-skillgen.md").write_text("# SkillGen Experiment\nstatus: completed\n", encoding="utf-8")
    (wiki_root / "outputs/paper-plan.md").write_text("# Paper Plan\n", encoding="utf-8")
    paper = tmp_path / "source-paper.md"
    paper.write_text("# Source Paper\nEvidence-backed source.\n", encoding="utf-8")
    allowlist = tmp_path / "research-allowlist.json"
    before = tmp_path / "research-before.json"
    after = tmp_path / "research-after.json"
    pdf = tmp_path / "paper-main.pdf"
    allowlist.write_text(json.dumps({"approved": True, "scope": "research lifecycle"}), encoding="utf-8")
    before.write_text(json.dumps({"state": "before"}), encoding="utf-8")
    after.write_text(json.dumps({"state": "after"}), encoding="utf-8")
    write_structural_pdf(pdf)

    discovery = tmp_path / "discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "status": "completed",
                "outputs": {"candidates": [{"candidate_id": "paper:1", "title": "Prior Work"}]},
            }
        ),
        encoding="utf-8",
    )
    novelty = tmp_path / "novelty.json"
    novelty.write_text(
        json.dumps({"schema": "external_novelty.v1", "status": "completed", "outputs": {"sources": [{"id": "web:1"}, {"id": "web:2"}]}}),
        encoding="utf-8",
    )
    review = tmp_path / "review-llm.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "score": 0.74,
                        "recommendation": "revise",
                        "evidence_ids": ["review-llm:research"],
                        "review_llm": {"status": "completed"},
                    },
                    "final_acceptance_boundary": {"final_acceptance_ready": True},
                    "findings": [],
                },
            }
        ),
        encoding="utf-8",
    )
    exp_runtime = tmp_path / "exp-runtime.json"
    exp_runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "run_experiment",
                        "status": "completed",
                        "exit_code": 0,
                        "result_collected": True,
                        "outcome": "supports",
                        "metrics": [{"name": "accuracy", "value": 0.91}],
                        "evidence_ids": ["runtime:research-exp"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    compile_runtime = tmp_path / "compile-runtime.json"
    compile_runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "compile_paper",
                        "status": "completed",
                        "exit_code": 0,
                        "pdf_generated": True,
                        "pdf_path": str(pdf),
                        "evidence_ids": ["runtime:research-compile"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen-main",
        "--paper",
        str(paper),
        "--approval-ref",
        "approval-research",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(exp_runtime),
        "--runtime-evidence",
        str(compile_runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--after-artifact",
        str(pdf),
        "--discovery-evidence",
        str(discovery),
        "--novelty-evidence",
        str(novelty),
        "--review-llm-evidence",
        str(review),
        "--run-id",
        "shim-research-verified-lifecycle",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["action_count"] == 1
    assert summary["passed_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "run_research_lifecycle"
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evidence["status"] == "completed"
    assert evolution["pipeline"]["status"] == "completed"
    assert evolution["current_stage"] == "completed"
    assert {stage["state"] for stage in evolution["stage_plan"]} == {"completed"}
    state_path = tmp_path / "artifacts/autosci/workspace/wiki/outputs/pipeline-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pipeline"]["status"] == "completed"
    assert state["evidence_report"]["review_llm_completed"] is True
    assert state["evidence_report"]["experiment_runtime"]["verified"] is True
    assert state["evidence_report"]["compile_runtime"]["verified"] is True
    assert state["evidence_report"]["integrated_pdf"]["status"] == "completed"
    assert (tmp_path / "artifacts/autosci/workspace/paper/main.pdf").exists()
    artifact_map = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in artifact_map
    assert "review_model_runtime_proof_manifest_json" in artifact_map
    assert "approval_runtime_proof_manifest_json" in artifact_map
    provider_proof = json.loads((tmp_path / artifact_map["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    review_proof = json.loads((tmp_path / artifact_map["review_model_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifact_map["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert provider_proof["proofs"][0]["native_skill"] == "research"
    assert provider_proof["proofs"][0]["categories"] == ["provider_source_evidence"]
    assert review_proof["proofs"][0]["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]


def test_autosci_skill_shim_research_lifecycle_ignores_weak_scheduler_summary(tmp_path: Path) -> None:
    lifecycle_summary = tmp_path / "scientific-lifecycle-summary.json"
    write_weak_lifecycle_summary(tmp_path, lifecycle_summary)

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen-main",
        "--lifecycle-summary",
        str(lifecycle_summary),
        "--run-id",
        "shim-research-scheduler-summary",
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["passed_count"] == 0
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "run_research_lifecycle"
    assert action["gate_status"] == "schema_only"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evidence["status"] == "inconclusive"
    assert evolution["pipeline"]["status"] != "completed"
    assert any(stage["state"] != "completed" for stage in evolution["stage_plan"])
    state_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pipeline_state_json")
    state = json.loads((tmp_path / state_artifact["path"]).read_text(encoding="utf-8"))
    assert state["evidence_report"]["scheduler_lifecycle_completed"] is False


def test_autosci_skill_shim_research_lifecycle_completes_from_strict_scheduler_summary(tmp_path: Path) -> None:
    lifecycle_summary = tmp_path / "scientific-lifecycle-summary.json"
    write_strict_lifecycle_summary(tmp_path, lifecycle_summary)

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen-main",
        "--lifecycle-summary",
        str(lifecycle_summary),
        "--run-id",
        "shim-research-strict-scheduler-summary",
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["passed_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "run_research_lifecycle"
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evidence["status"] == "completed"
    assert evolution["pipeline"]["status"] == "completed"
    assert {stage["state"] for stage in evolution["stage_plan"]} == {"completed"}
    state_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pipeline_state_json")
    state = json.loads((tmp_path / state_artifact["path"]).read_text(encoding="utf-8"))
    scheduler_lifecycle = state["evidence_report"]["scheduler_lifecycle"]
    assert state["evidence_report"]["scheduler_lifecycle_completed"] is True
    assert scheduler_lifecycle["node_count"] == len(FULL_LIFECYCLE_NODES)
    assert scheduler_lifecycle["lifecycle_runtime_gate_status"] == "passed"
    assert scheduler_lifecycle["workflow_config_alignment_status"] == "aligned"
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" not in artifact_types
    assert "review_model_runtime_proof_manifest_json" not in artifact_types
    assert "approval_runtime_proof_manifest_json" not in artifact_types


def test_autosci_skill_shim_research_scheduler_run_attaches_blocked_summary(tmp_path: Path) -> None:
    paper = tmp_path / "scheduler-generic-paper.md"
    paper.write_text(
        "# Scheduler Generic Paper\n\n"
        "## Abstract\n"
        "This paper verifies generic workflow dispatch for the research scheduler path.\n",
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--paper",
        str(paper),
        "--scheduler-run",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-generic-scheduler-run",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["execution_status"] == "gated"
    assert summary["scheduler_lifecycle_status"] == "passed"
    assert summary["scheduler_lifecycle_node_count"] == 1
    assert summary["scheduler_lifecycle_blocked_node_count"] == 0
    assert summary["scheduler_dispatch_boundary_status"] == "generic_workflow_runner"
    assert summary["scheduler_dispatch_boundary_production_ready"] is True
    assert summary["scheduler_dispatch_boundary_blocking_reasons"] == []

    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert scheduler_summary["schema"] == "scientific_lifecycle.v1"
    assert scheduler_summary["execution_owner"] == "solar.operator_runtime.generic_scientific_workflow_runner"
    assert scheduler_summary["node_summaries"]["paper_ingest"]["runner_contract"] == "generic_workflow_runner"
    assert scheduler_summary["dispatch_boundary"]["status"] == "generic_workflow_runner"
    assert scheduler_summary["dispatch_input_profiles"]["paper_ingest"]["uses_fixture_or_smoke_input"] is False

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    skill_run = payload["outputs"]["skill_run"]
    assert skill_run["scheduler_lifecycle"]["runner_kind"] == "generic_workflow"
    assert skill_run["scheduler_lifecycle"]["summary_path"] == summary["scheduler_lifecycle_summary_path"]
    action = skill_run["actions"][0]
    assert action["action"] == "run_research_lifecycle"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    state_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pipeline_state_json")
    state = json.loads((tmp_path / state_artifact["path"]).read_text(encoding="utf-8"))
    assert state["evidence_report"]["scheduler_lifecycle_completed"] is False


def test_autosci_skill_shim_research_scheduler_blocked_gate_surfaces_authorization(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-include-blocked-external",
        "--scheduler-node-id",
        "literature_discover",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-generic-scheduler-authorization",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["scheduler_lifecycle_status"] == "blocked"
    assert summary["scheduler_authorization_required"] is True
    assert summary["scheduler_authorization_request_count"] == 1
    assert summary["authorization_required"] is True
    assert summary["authorization_request_count"] >= 1

    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert scheduler_summary["authorization_required"] is True
    request = scheduler_summary["authorization_requests"][0]
    assert request["schema"] == "scientific_workflow_gate_authorization_request.v1"
    assert request["node_id"] == "literature_discover"
    assert request["continuation"]["retriable"] is True

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    requests = payload["outputs"]["authorization_requests"]
    assert any(item.get("schema") == "autosci_route_gate_authorization_request.v1" for item in requests)
    assert any(item.get("schema") == "scientific_workflow_gate_authorization_request.v1" for item in requests)


def test_autosci_skill_shim_research_scheduler_demo_uses_multi_node_preset(tmp_path: Path) -> None:
    paper = tmp_path / "scheduler-demo-paper.md"
    paper.write_text(
        "# Scheduler Demo Paper\n\n"
        "## Abstract\n"
        "This paper verifies the explicit multi-node scheduler demo preset.\n",
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen demo",
        "--paper",
        str(paper),
        "--scheduler-run",
        "--scheduler-demo",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-demo-scheduler",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["scheduler_lifecycle_status"] == "passed"
    assert summary["scheduler_lifecycle_node_count"] == len(DEMO_SCHEDULER_NODES)
    assert summary["scheduler_dispatch_boundary_status"] == "generic_workflow_runner"

    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert scheduler_summary["required_nodes"] == DEMO_SCHEDULER_NODES
    assert set(scheduler_summary["node_results"]) == set(DEMO_SCHEDULER_NODES)
    assert scheduler_summary["dispatch_boundary"]["required_nodes"] == DEMO_SCHEDULER_NODES


def test_autosci_skill_shim_research_legacy_scheduler_run_attaches_blocked_summary(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--scheduler-include-blocked-external",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-scheduler-run",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "research"
    assert summary["execution_status"] == "gated"
    assert summary["scheduler_lifecycle_status"] == "blocked"
    assert summary["scheduler_lifecycle_node_count"] == 14
    assert summary["scheduler_lifecycle_blocked_node_count"] == 2
    assert summary["scheduler_authorization_required"] is True
    assert summary["scheduler_authorization_request_count"] == 2
    assert summary["authorization_required"] is True
    assert summary["authorization_request_count"] == 3
    assert summary["scheduler_workflow_config_alignment_status"] == "drift"
    assert summary["scheduler_workflow_config_alignment_ok"] is False
    assert "configured_nodes_not_required_by_run" in summary["scheduler_workflow_config_alignment_issues"]
    assert summary["scheduler_dispatch_boundary_status"] == "bounded_smoke"
    assert summary["scheduler_dispatch_boundary_production_ready"] is False
    assert "runner_contract=bounded_smoke_runner" in summary["scheduler_dispatch_boundary_blocking_reasons"]

    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert scheduler_summary["schema"] == "scientific_lifecycle.v1"
    assert scheduler_summary["execution_owner"] == "solar.operator_runtime.scheduler_lifecycle_smoke"
    assert scheduler_summary["lifecycle_status"] == "blocked"
    assert scheduler_summary["workflow_config_alignment"]["status"] == "drift"
    assert scheduler_summary["dispatch_boundary"]["status"] == "bounded_smoke"
    assert set(scheduler_summary["blocked_nodes"]) == {"report_plan", "publication_produce"}
    assert scheduler_summary["authorization_required"] is True
    assert len(scheduler_summary["authorization_requests"]) == 2
    assert {
        request["node_id"]
        for request in scheduler_summary["authorization_requests"]
    } == {"report_plan", "publication_produce"}
    assert all(
        request["schema"] == "scientific_workflow_gate_authorization_request.v1"
        and request["continuation"]["retriable"] is True
        for request in scheduler_summary["authorization_requests"]
    )
    assert len(scheduler_summary["node_results"]) == 14

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "inconclusive"
    assert payload["outputs"]["authorization_required"] is True
    assert len(payload["outputs"]["authorization_requests"]) == 3
    assert any("workflow-config drift" in item for item in payload["limitations"])
    skill_run = payload["outputs"]["skill_run"]
    assert skill_run["scheduler_lifecycle"]["summary_path"] == summary["scheduler_lifecycle_summary_path"]
    assert skill_run["scheduler_lifecycle"]["workflow_config_alignment_status"] == "drift"
    assert payload["inputs"]["lifecycle_summary"] == [summary["scheduler_lifecycle_summary_path"]]
    action = skill_run["actions"][0]
    assert action["action"] == "run_research_lifecycle"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    state_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pipeline_state_json")
    state = json.loads((tmp_path / state_artifact["path"]).read_text(encoding="utf-8"))
    assert state["evidence_report"]["scheduler_lifecycle_completed"] is False
    assert any(stage["state"] in {"pending", "pending_evidence"} for stage in evolution["stage_plan"])


def test_autosci_skill_shim_research_scheduler_strict_workflow_config_alignment_fails(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--scheduler-require-workflow-config-alignment",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-scheduler-strict-config",
    )

    assert proc.returncode == 2, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["status"] == "failed"
    assert summary["scheduler_lifecycle_status"] == "failed"
    assert summary["scheduler_workflow_config_alignment_status"] == "drift"
    assert "configured_nodes_not_required_by_run" in summary["scheduler_workflow_config_alignment_issues"]

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert any("workflow-config drift" in item for item in payload["limitations"])
    scheduler_lifecycle = payload["outputs"]["skill_run"]["scheduler_lifecycle"]
    assert scheduler_lifecycle["workflow_config_alignment_status"] == "drift"


def test_autosci_skill_shim_research_scheduler_strict_production_dispatch_fails(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--scheduler-require-production-dispatch",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-scheduler-production-boundary",
    )

    assert proc.returncode == 2, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["status"] == "failed"
    assert summary["scheduler_lifecycle_status"] == "failed"
    assert summary["scheduler_dispatch_boundary_status"] == "bounded_smoke"
    assert summary["scheduler_dispatch_boundary_production_ready"] is False
    assert "runner_contract=bounded_smoke_runner" in summary["scheduler_dispatch_boundary_blocking_reasons"]

    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert scheduler_summary["dispatch_boundary"]["production_ready"] is False
    assert any(
        item["check"] == "production_dispatch_boundary" and item["status"] == "error"
        for item in scheduler_summary["checks"]
    )
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    scheduler_lifecycle = payload["outputs"]["skill_run"]["scheduler_lifecycle"]
    assert scheduler_lifecycle["dispatch_boundary_status"] == "bounded_smoke"
    assert scheduler_lifecycle["dispatch_boundary_production_ready"] is False


def test_autosci_skill_shim_research_scheduler_run_records_human_gate(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--scheduler-include-human-gates",
        "--idea-approval-ref",
        "approval-shim-idea-gate",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-human-gate",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["scheduler_lifecycle_status"] == "blocked"
    assert summary["scheduler_authorization_required"] is True
    assert summary["scheduler_authorization_request_count"] == 1
    assert summary["authorization_required"] is True
    assert summary["authorization_request_count"] == 2
    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert "idea_acceptance_gate" in scheduler_summary["node_results"]
    assert scheduler_summary["node_results"]["idea_acceptance_gate"]["approval_ref"] == "approval-shim-idea-gate"
    assert "results_acceptance_gate" in scheduler_summary["blocked_nodes"]
    assert scheduler_summary["authorization_required"] is True
    request = scheduler_summary["authorization_requests"][0]
    assert request["schema"] == "scientific_workflow_gate_authorization_request.v1"
    assert request["node_id"] == "results_acceptance_gate"
    assert request["continuation"]["retriable"] is True
    assert "report_draft" not in scheduler_summary["required_nodes"]

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["outputs"]["authorization_required"] is True
    assert len(payload["outputs"]["authorization_requests"]) == 2
    scheduler_lifecycle = payload["outputs"]["skill_run"]["scheduler_lifecycle"]
    assert scheduler_lifecycle["status"] == "blocked"
    assert scheduler_lifecycle["blocked_node_count"] == 1


def test_autosci_skill_shim_research_scheduler_online_uses_source_runtime_evidence(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-source-runtime"
    external_dir.mkdir()
    allowlist = external_dir / "allowlist.json"
    before = external_dir / "before.json"
    after = external_dir / "after.json"
    runtime = external_dir / "source-runtime.json"
    source_manifest = external_dir / "source-manifest.json"
    allowlist.write_text('{"allowed": ["semantic_scholar", "arxiv"]}\n', encoding="utf-8")
    before.write_text('{"state": "before-source-fetch"}\n', encoding="utf-8")
    after.write_text('{"state": "after-source-fetch", "candidates": ["runtime-source-001"]}\n', encoding="utf-8")
    source_manifest.write_text('{"candidate_ids": ["runtime-source-001"]}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-source-runtime-shim",
                "sprint_id": "sprint-source-runtime-shim",
                "node_id": "source_runtime",
                "status": "completed",
                "exit_code": 0,
                "inputs": {"approval_ref": "approval-source-runtime-shim"},
                "outputs": {
                    "runtime": {
                        "action": "discover_literature",
                        "status": "completed",
                        "approval_ref": "approval-source-runtime-shim",
                        "command_run": "approved-semantic-scholar-fetch",
                        "exit_code": 0,
                        "evidence_ids": ["runtime:source-fetch:shim"],
                        "checks": [{"check": "source_fetch", "status": "ok", "detail": "one candidate"}],
                        "candidates": [
                            {
                                "candidate_id": "runtime-source-001",
                                "title": "Runtime Verified Skill Generation Source",
                                "url": "https://arxiv.org/abs/2601.00005",
                                "source_channels": ["search_s2"],
                                "ranking_score": 0.93,
                                "ranking_rationale": "Approved source runtime returned this source.",
                                "dedup_status": "new",
                                "fetch_status": "fetched",
                            }
                        ],
                    }
                },
                "artifacts": [{"type": "source_manifest", "path": str(source_manifest)}],
                "provenance": {
                    "operator_id": "external-source-runtime-shim",
                    "implementation_package": "harness.tests",
                    "timestamp": "2026-06-26T00:00:00Z",
                },
                "limitations": ["Runtime source evidence was supplied by the test harness."],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--online",
        "--topic",
        "skill generation",
        "--approval-ref",
        "approval-source-runtime-shim",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-online-source",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["scheduler_lifecycle_status"] == "blocked"
    assert summary["scheduler_lifecycle_node_count"] == 14
    assert summary["scheduler_lifecycle_blocked_node_count"] == 2
    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    literature_path = tmp_path / scheduler_summary["node_results"]["literature_discover"]["artifact_path"]
    literature = json.loads(literature_path.read_text(encoding="utf-8"))
    assert literature["outputs"]["mode"] == "discover_literature_runtime_verified"
    assert literature["outputs"]["candidates"][0]["source_channels"] == ["search_s2"]
    assert literature["outputs"]["source_provider_boundary"]["status"] == "completed"
    assert literature["outputs"]["source_provider_boundary"]["provider_channels"] == ["search_s2"]
    final_boundary = literature["outputs"]["source_provider_boundary"]["final_shortlist_boundary"]
    assert final_boundary["final_shortlist_ready"] is True
    assert final_boundary["status"] == "final_shortlist_ready"
    assert final_boundary["provider_channels"] == ["search_s2"]
    assert "fixture" not in literature["outputs"]["candidates"][0]["candidate_id"]


def test_autosci_skill_shim_research_scheduler_uses_experiment_runtime_evidence(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-experiment-runtime"
    external_dir.mkdir()
    allowlist = external_dir / "experiment-allowlist.json"
    before = external_dir / "experiment-before.json"
    after = external_dir / "experiment-after.json"
    runtime = external_dir / "experiment-runtime.json"
    allowlist.write_text('{"allowed": ["approved-local-experiment"]}\n', encoding="utf-8")
    before.write_text('{"state": "planned"}\n', encoding="utf-8")
    after.write_text('{"state": "completed", "metrics": ["accuracy"]}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-experiment-runtime-shim",
                "sprint_id": "sprint-experiment-runtime-shim",
                "node_id": "experiment_runtime",
                "status": "completed",
                "exit_code": 0,
                "inputs": {"approval_ref": "approval-experiment-runtime-shim"},
                "outputs": {
                    "runtime": {
                        "action": "run_experiment",
                        "status": "completed",
                        "approval_ref": "approval-experiment-runtime-shim",
                        "command_run": "approved-local-experiment",
                        "exit_code": 0,
                        "result_collected": True,
                        "outcome": "supports",
                        "metrics": [{"name": "accuracy", "value": 0.81}],
                        "evidence_ids": ["runtime:experiment:shim-scheduler"],
                        "logs": ["approved experiment runtime completed"],
                    }
                },
                "artifacts": [{"type": "experiment_after", "path": str(after)}],
                "provenance": {
                    "operator_id": "external-experiment-runtime-shim",
                    "implementation_package": "harness.tests",
                    "timestamp": "2026-06-26T00:00:00Z",
                },
                "limitations": ["Runtime experiment evidence was supplied by the test harness."],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--experiment-approval-ref",
        "approval-experiment-runtime-shim",
        "--experiment-allowlist-evidence",
        str(allowlist),
        "--experiment-runtime-evidence",
        str(runtime),
        "--experiment-before-artifact",
        str(before),
        "--experiment-after-artifact",
        str(after),
        "--scheduler-timeout",
        "45",
        "--run-id",
        "shim-research-experiment-runtime",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["scheduler_lifecycle_status"] == "blocked"
    assert summary["scheduler_lifecycle_node_count"] == 14
    assert summary["scheduler_lifecycle_blocked_node_count"] == 2
    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    run_path = tmp_path / scheduler_summary["node_results"]["experiment_run"]["artifact_path"]
    run_evidence = json.loads(run_path.read_text(encoding="utf-8"))
    result = run_evidence["outputs"]["result"]
    assert result["execution_mode"] == "human_approved"
    assert result["metrics"] == [{"name": "accuracy", "value": 0.81}]
    assert "runtime:experiment:shim-scheduler" in result["evidence_ids"]
    assert "fixture result collected" not in "\n".join(result["logs"]).lower()
    assert any(artifact["type"] == "experiment_runtime_evidence_json" for artifact in run_evidence["artifacts"])

    monitor_path = tmp_path / scheduler_summary["node_results"]["experiment_monitor"]["artifact_path"]
    monitor_evidence = json.loads(monitor_path.read_text(encoding="utf-8"))
    status_report = monitor_evidence["outputs"]["status_report"]
    assert status_report["state"] == "completed"
    assert "runtime:experiment:shim-scheduler" in status_report["evidence_ids"]


def test_autosci_skill_shim_research_scheduler_executes_approved_experiment_command(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-experiment-executor"
    external_dir.mkdir()
    runner = external_dir / "approved_experiment_runner.py"
    runner.write_text(
        "\n".join(
            [
                "import argparse",
                "import json",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--experiment-id', required=True)",
                "args = parser.parse_args()",
                "print(json.dumps({",
                "    'experiment_id': args.experiment_id,",
                "    'outcome': 'supports',",
                "    'metrics': [{'name': 'accuracy', 'value': 0.86}],",
                "    'evidence_ids': ['runtime:experiment:shim-executor'],",
                "    'logs': ['approved shim executor produced experiment result'],",
                "}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command_template = f"{sys.executable} {runner} --experiment-id {{experiment_id}}"
    allowlist = external_dir / "experiment-allowlist.json"
    before = external_dir / "experiment-before.json"
    after = external_dir / "experiment-after.json"
    allowlist.write_text(json.dumps({"commands": [command_template]}) + "\n", encoding="utf-8")
    before.write_text('{"state": "planned"}\n', encoding="utf-8")
    after.write_text('{"state": "completed"}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--experiment-approval-ref",
        "approval-experiment-executor-shim",
        "--experiment-allowlist-evidence",
        str(allowlist),
        "--experiment-before-artifact",
        str(before),
        "--experiment-after-artifact",
        str(after),
        "--experiment-execute-approved",
        "--experiment-executor-timeout-seconds",
        "20",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-experiment-executor",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["scheduler_lifecycle_status"] == "blocked"
    assert summary["scheduler_lifecycle_node_count"] == 14
    assert summary["scheduler_lifecycle_blocked_node_count"] == 2
    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    run_evidence = json.loads((tmp_path / scheduler_summary["node_results"]["experiment_run"]["artifact_path"]).read_text(encoding="utf-8"))
    result = run_evidence["outputs"]["result"]
    assert result["metrics"] == [{"name": "accuracy", "value": 0.86}]
    assert "runtime:experiment:shim-executor" in result["evidence_ids"]
    assert "approved shim executor produced experiment result" in "\n".join(result["logs"])
    artifact_types = {artifact["type"] for artifact in run_evidence["artifacts"]}
    assert {"experiment_runtime_evidence_json", "executor_stdout", "executor_stderr"}.issubset(artifact_types)
    assert "fixture result collected" not in "\n".join(result["logs"]).lower()


def test_autosci_skill_shim_research_scheduler_records_truthful_legacy_publication_compile_boundary(tmp_path: Path) -> None:
    external_dir = tmp_path / "external-publication-compile"
    external_dir.mkdir()
    review_llm_path = external_dir / "review_llm_artifact_review.json"
    review_llm_path.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "task-review-llm-publication-compile-shim",
                "sprint_id": "external-review-llm-publication-compile-shim",
                "node_id": "external_artifact_review",
                "status": "completed",
                "inputs": {"target": "scheduler-lifecycle-publication-compile-shim"},
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:scheduler-lifecycle-publication-compile-shim",
                        "target": "scheduler-lifecycle-publication-compile-shim",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "standard",
                        "focus": "completeness",
                        "score": 0.87,
                        "recommendation": "inconclusive",
                        "evidence_ids": ["review-llm:publication-compile-shim"],
                    },
                    "findings": [],
                    "artifact": {"artifact_id": "artifact:scheduler-lifecycle-publication-compile-shim"},
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "external-review-llm-publication-compile-shim",
                    "implementation_package": "harness.tests",
                    "timestamp": "2026-06-26T00:00:00Z",
                },
                "limitations": ["Test fixture supplied as explicit external Review LLM evidence."],
            }
        ),
        encoding="utf-8",
    )
    compile_target = external_dir / "compile_target"
    compile_target.mkdir()
    (compile_target / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nApproved shim scheduler publication compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    fake_bin = external_dir / "bin"
    fake_bin.mkdir()
    fake_latexmk = fake_bin / "latexmk"
    fake_latexmk.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path('main.pdf').write_bytes({MINIMAL_STRUCTURAL_PDF!r})\n"
        "print('fake shim scheduler latexmk completed')\n",
        encoding="utf-8",
    )
    fake_latexmk.chmod(0o755)
    allowlist = external_dir / "compile-allowlist.json"
    before = external_dir / "compile-before.json"
    allowlist.write_text(json.dumps({"executables": ["latexmk"]}) + "\n", encoding="utf-8")
    before.write_text(json.dumps({"paper_dir": str(compile_target), "pdf_exists": False}) + "\n", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$research",
        "skillgen lifecycle",
        "--scheduler-run",
        "--scheduler-legacy-smoke-runner",
        "--scheduler-dispatch-external-evidence",
        "--scheduler-require-workflow-config-alignment",
        "--review-llm-evidence",
        str(review_llm_path),
        "--compile-target",
        str(compile_target),
        "--compile-approval-ref",
        "approval-publication-compile-shim",
        "--compile-allowlist-evidence",
        str(allowlist),
        "--compile-before-artifact",
        str(before),
        "--compile-execute-approved",
        "--compile-executor-timeout-seconds",
        "20",
        "--scheduler-timeout",
        "20",
        "--run-id",
        "shim-research-publication-compile",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["status"] == "failed"
    assert summary["scheduler_lifecycle_status"] == "failed"
    assert summary["scheduler_lifecycle_node_count"] == 14
    assert summary["scheduler_workflow_config_alignment_status"] == "drift"
    assert summary["scheduler_workflow_config_alignment_ok"] is False
    assert "configured_nodes_not_required_by_run" in summary["scheduler_workflow_config_alignment_issues"]
    assert summary["scheduler_dispatch_boundary_status"] == "bounded_smoke"
    assert summary["scheduler_dispatch_boundary_production_ready"] is False
    scheduler_summary = json.loads(Path(summary["scheduler_lifecycle_summary_path"]).read_text(encoding="utf-8"))
    assert scheduler_summary["workflow_config_alignment"]["status"] == "drift"
    report_plan_summary = scheduler_summary["node_summaries"]["report_plan"]
    assert report_plan_summary["bridge_result"]["status"] == "inconclusive"
    assert report_plan_summary["gate_result"]["status"] == "inconclusive"
    report_plan_evidence = json.loads((tmp_path / report_plan_summary["evidence_path"]).read_text(encoding="utf-8"))
    plan_artifact = next(
        artifact
        for artifact in report_plan_evidence["artifacts"]
        if artifact["type"] == "paper_plan_json"
    )
    plan_payload = json.loads((tmp_path / plan_artifact["path"]).read_text(encoding="utf-8"))
    compile_handoff = plan_payload["compile_handoff"]
    assert compile_handoff["status"] == "completed"
    assert compile_handoff["semantic_runtime"]["verified"] is True
    assert compile_handoff["executor_result"]["executed"] is True
    assert any(path.endswith("main.pdf") for path in compile_handoff["pdf_paths"])
    boundary_artifact = next(
        artifact
        for artifact in report_plan_evidence["artifacts"]
        if artifact["type"] == "paper_plan_final_acceptance_boundary_json"
    )
    boundary = json.loads((tmp_path / boundary_artifact["path"]).read_text(encoding="utf-8"))
    assert boundary["final_plan_accepted"] is False
    assert "validated idea graph with succeeded experiment evidence is missing" in boundary["blocking_reasons"]


def test_autosci_skill_shim_accepts_exp_run_native_options_without_fixture_fallback(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-001",
        "--env",
        "local",
        "--collect",
        "--run-id",
        "shim-exp-run-native",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 1
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == "exp-001"
    assert payload["inputs"]["paper_path"] == ""
    assert payload["inputs"]["smoke"] is False
    assert payload["inputs"]["native_options"]["env"] == "local"
    assert payload["inputs"]["native_options"]["collect"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    assert action["schema"] == "experiment_status.v1"
    assert action["gate_status"] == "schema_only"
    status_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = status_evidence["outputs"]["status_report"]
    assert status_evidence["status"] == "inconclusive"
    assert report["experiment_id"] == "exp-001"
    assert report["state"] == "unknown"
    assert any("Collect mode was requested" in item for item in report["observations"])
    assert any("Approval-gated external effects" in item for item in payload["limitations"])


def test_autosci_skill_shim_exp_run_full_routes_deploy_and_collect_actions(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-skillgen",
        "--full",
        "--env",
        "local",
        "--run-id",
        "shim-exp-run-full-native",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 3

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    assert [action["action"] for action in actions] == [
        "design_experiment",
        "run_experiment",
        "monitor_experiment",
    ]
    assert payload["inputs"]["native_options"]["full"] is True
    result = json.loads(Path(actions[1]["evidence_path"]).read_text(encoding="utf-8"))
    assert result["status"] == "inconclusive"
    assert any("approval is required and absent" in item for item in result["limitations"])


def test_autosci_skill_shim_exp_status_pipeline_runs_monitor_action(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$exp-status",
        "--pipeline",
        "skillgen-main",
        "--run-id",
        "shim-exp-status-pipeline",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-status"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["pipeline"] == "skillgen-main"
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    status_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = status_evidence["outputs"]["status_report"]
    assert status_evidence["status"] == "inconclusive"
    assert report["experiment_id"] == "skillgen-main"


def test_autosci_skill_shim_exp_status_pipeline_reads_wiki_experiment_state(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    experiments = wiki_root / "experiments"
    logs = wiki_root / "logs"
    experiments.mkdir(parents=True)
    logs.mkdir(parents=True)
    (logs / "exp-skillgen.log").write_text("completed run\n", encoding="utf-8")
    (experiments / "exp-skillgen.md").write_text(
        "\n".join(
            [
                "---",
                "title: SkillGen Experiment",
                "experiment_id: exp-skillgen",
                "pipeline: skillgen-main",
                "status: completed",
                "outcome: supports",
                "run_log: ../logs/exp-skillgen.log",
                "evidence_ids:",
                "  - runtime:exp-skillgen",
                "---",
                "# SkillGen Experiment",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-status",
        "--pipeline",
        "skillgen-main",
        "--run-id",
        "shim-exp-status-wiki-state",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-status"
    assert summary["action_count"] == 1
    assert summary["passed_count"] == 1
    assert summary["schema_only_count"] == 0

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    assert action["gate_status"] == "passed"
    status_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = status_evidence["outputs"]["status_report"]
    assert status_evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-skillgen"
    assert report["state"] == "completed"
    assert "runtime:exp-skillgen" in report["evidence_ids"]
    artifact_types = {artifact["type"] for artifact in status_evidence["artifacts"]}
    assert {"wiki_state_resolver_json", "wiki_experiment_markdown", "wiki_experiment_run_log"} <= artifact_types


@pytest.mark.parametrize(
    ("wiki_status", "expected_state"),
    [
        ("collected", "completed"),
        ("collect-ready", "running"),
        ("ready", "running"),
    ],
)
def test_autosci_skill_shim_exp_status_normalizes_native_wiki_states(
    tmp_path: Path,
    wiki_status: str,
    expected_state: str,
) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    experiments = wiki_root / "experiments"
    experiments.mkdir(parents=True)
    (experiments / "exp-skillgen.md").write_text(
        "\n".join(
            [
                "---",
                "title: SkillGen Experiment",
                "experiment_id: exp-skillgen",
                "pipeline: skillgen-main",
                f"status: {wiki_status}",
                "evidence_ids:",
                "  - runtime:exp-skillgen",
                "---",
                "# SkillGen Experiment",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-status",
        "--pipeline",
        "skillgen-main",
        "--run-id",
        f"shim-exp-status-{wiki_status}",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["gate_status"] == "passed"
    status_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = status_evidence["outputs"]["status_report"]
    assert status_evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-skillgen"
    assert report["state"] == expected_state


def test_autosci_skill_shim_blocks_unapproved_exp_run_deploy_without_fixture_support(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-skillgen",
        "--review",
        "--env",
        "local",
        "--run-id",
        "shim-exp-run-deploy-native",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] > 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    plan_action = next(action for action in actions if action["action"] == "design_experiment")
    plan = json.loads(Path(plan_action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_plan = plan["outputs"]["experiment_plan"]
    assert experiment_plan["execution_mode"] == "human_approved"
    assert "approval-gated native experiment" in experiment_plan["objective"]
    assert "fixture" not in json.dumps(experiment_plan).lower()
    result_action = next(action for action in actions if action["action"] == "run_experiment")
    result = json.loads(Path(result_action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_result = result["outputs"]["result"]
    assert result["status"] == "inconclusive"
    assert experiment_result["outcome"] == "inconclusive"
    assert experiment_result["execution_mode"] == "human_approved"
    assert "fixture result collected" not in "\n".join(experiment_result["logs"])
    assert "evidence:autosci-fixture-result" not in json.dumps(experiment_result)
    assert any("approval is required and absent" in item for item in result["limitations"])


def test_autosci_skill_shim_exp_design_attaches_review_llm_validation(tmp_path: Path) -> None:
    review = tmp_path / "exp-design-review.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-exp-design",
                "status": "completed",
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:idea-skillgen-design",
                        "target": "idea-skillgen-design",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "hard",
                        "focus": "method",
                        "score": 0.84,
                        "recommendation": "pass_with_caveats",
                        "evidence_ids": ["review:exp-design"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-design",
        "idea-skillgen-design",
        "--review-llm-evidence",
        str(review),
        "--run-id",
        "shim-exp-design-review-llm",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-design"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "design_experiment"
    assert action["schema"] == "experiment_plan.v1"
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    plan = evidence["outputs"]["experiment_plan"]
    assert plan["experiment_id"] == "exp-idea-skillgen-design"
    assert plan["review_llm"]["status"] == "completed"
    assert plan["review_llm"]["recommendation"] == "pass_with_caveats"
    assert "review-exp-design" in plan["evidence_ids"]
    assert "review_llm_design_validation == completed" in plan["success_criteria"]
    boundary = plan["source_context"]["final_execution_boundary"]
    assert boundary["status"] == "execution_readiness_incomplete"
    assert boundary["review_llm_completed"] is True
    assert "before-state evidence must match the declared dataset exactly" in boundary["blocking_reasons"]
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert "experiment_design_review_llm_evidence_json" in artifact_types
    assert "experiment_design_final_execution_boundary_json" in artifact_types
    assert "review_model_runtime_proof_manifest_json" in artifact_types
    assert "wiki_mutation_runtime_proof_manifest_json" not in artifact_types
    payload_artifact_types = {artifact["type"] for artifact in payload["artifacts"]}
    assert "wiki_mutation_runtime_proof_manifest_json" not in payload_artifact_types
    proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "review_model_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-design"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    assert Path(action["evidence_path"]).relative_to(tmp_path).as_posix() in proof_entry["evidence_refs"]


def test_autosci_skill_shim_exp_design_marks_execution_ready_with_approval_preflight(tmp_path: Path) -> None:
    review = tmp_path / "exp-design-review-ready.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-exp-design-ready",
                "status": "completed",
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:idea-skillgen-ready",
                        "target": "idea-skillgen-ready",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "score": 0.9,
                        "recommendation": "accept",
                        "evidence_ids": ["review:exp-design-ready"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    allowlist = tmp_path / "exp-design-allowlist.json"
    workspace = tmp_path / "approved-workspace"
    workspace.mkdir()
    runner = workspace / "run.py"
    before = workspace / "samples.csv"
    expected = workspace / "result.json"
    runner.write_text("print('bounded')\n", encoding="utf-8")
    before.write_text("value\n1\n", encoding="utf-8")
    assert not expected.exists()
    command_argv = [sys.executable, str(runner), str(before), str(expected)]
    allowlist.write_text(
        json.dumps({"command_argvs": [command_argv]}),
        encoding="utf-8",
    )
    experiment_contract = tmp_path / "approved-contract.json"
    experiment_contract.write_text(
        json.dumps(
            {
                "verification_contract_version": "1",
                "readiness_profile": "human_approved_local",
                "execution_mode": "human_approved",
                "workspace_root": str(workspace),
                "runner": {"path": str(runner)},
                "dataset": {"path": str(before), "format": "csv", "role": "evaluation"},
                "variants": [
                    {"name": "baseline", "description": "baseline"},
                    {"name": "variant", "description": "candidate"},
                ],
                "thresholds": [{"metric": "score", "operator": ">=", "value": 0.5}],
                "random_seed": 7,
                "stopping_conditions": ["all rows processed"],
                "command_argv": command_argv,
                "command_allowlist": [" ".join(command_argv)],
                "expected_artifacts": [str(expected)],
                "network_access": "denied",
                "write_scope": [str(workspace)],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-design",
        "idea-skillgen-ready",
        "--review",
        "--review-llm-evidence",
        str(review),
        "--approval-ref",
        "approval-exp-design-ready",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--experiment-contract",
        str(experiment_contract),
        "--run-id",
        "shim-exp-design-execution-ready",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-design"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    plan = evidence["outputs"]["experiment_plan"]
    boundary = plan["source_context"]["final_execution_boundary"]
    assert boundary["status"] == "execution_ready"
    assert boundary["execution_ready"] is True
    assert boundary["approval_ready_for_execution"] is True
    assert boundary["review_llm_completed"] is True
    assert boundary["verification_contract_complete"] is True
    assert boundary["approval_preflight"]["command_authorized"] is True
    assert plan["execution_ready"] is True
    assert not expected.exists()
    assert plan["dataset"]["path"]
    assert len(plan["variants"]) == 2
    assert plan["thresholds"]
    assert isinstance(plan["random_seed"], int)
    assert plan["stopping_conditions"]
    assert plan["command_argv"]
    assert "final_execution_boundary == execution_ready" in plan["success_criteria"]
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "experiment_design_final_execution_boundary_json" in artifacts
    sidecar = json.loads((tmp_path / artifacts["experiment_design_final_execution_boundary_json"]).read_text(encoding="utf-8"))
    assert sidecar["status"] == "execution_ready"
    payload_artifacts = {artifact["type"]: artifact["path"] for artifact in payload["artifacts"]}
    assert "wiki_mutation_runtime_proof_manifest_json" in payload_artifacts
    mutation_proof = json.loads((tmp_path / payload_artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = mutation_proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-design"
    assert proof_entry["categories"] == ["wiki_mutation_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    assert any("workspace/wiki/experiments/exp-idea-skillgen-ready.md" in ref for ref in proof_entry["evidence_refs"])
    assert any("workspace/wiki/outputs/experiment.md" in ref for ref in proof_entry["evidence_refs"])


def test_autosci_skill_shim_exp_design_rejects_unrelated_command_allowlist(tmp_path: Path) -> None:
    review = tmp_path / "exp-design-review-unrelated.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-exp-design-unrelated",
                "status": "completed",
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:idea-unrelated",
                        "target": "idea-unrelated",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "recommendation": "accept",
                        "evidence_ids": ["review:unrelated"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    allowlist = tmp_path / "unrelated-allowlist.json"
    before = tmp_path / "before.json"
    allowlist.write_text(json.dumps({"commands": ["echo unrelated"]}), encoding="utf-8")
    before.write_text(json.dumps({"workspace": "prepared"}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-design",
        "idea-unrelated",
        "--review",
        "--review-llm-evidence",
        str(review),
        "--approval-ref",
        "approval-unrelated",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--run-id",
        "shim-exp-design-unrelated-allowlist",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(Path(json.loads(proc.stdout)["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    plan = evidence["outputs"]["experiment_plan"]
    boundary = plan["source_context"]["final_execution_boundary"]
    assert plan["execution_ready"] is False
    assert boundary["approval_preflight"]["command_authorized"] is False
    assert "planned runtime command is not authorized by the supplied allowlist evidence" in boundary["blocking_reasons"]


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("malicious_argv", "planned runtime command is not authorized by the supplied allowlist evidence"),
        ("executable_only", "planned runtime command is not authorized by the supplied allowlist evidence"),
        ("prefix_only", "planned runtime command is not authorized by the supplied allowlist evidence"),
        ("placeholder_template", "planned runtime command is not authorized by the supplied allowlist evidence"),
        ("unknown_mode", "approval exemption is limited to explicit deterministic fixture mode"),
        ("outside_workspace", "runner, dataset, and expected artifacts must remain inside workspace root"),
        ("dataset_before_mismatch", "before-state evidence must match the declared dataset exactly"),
        (
            "missing_output_parent",
            "expected artifact targets must have an existing writable parent and must not be directories",
        ),
    ],
)
def test_autosci_skill_shim_exp_design_readiness_fail_closed(
    tmp_path: Path,
    case: str,
    expected_reason: str,
) -> None:
    workspace = tmp_path / "fixture-workspace"
    workspace.mkdir()
    runner = workspace / "run.py"
    dataset = workspace / "samples.csv"
    expected = workspace / "result.json"
    runner.write_text("print('safe fixture')\n", encoding="utf-8")
    dataset.write_text("value\n1\n", encoding="utf-8")
    before = dataset
    execution_mode = "fixture"
    command_argv = [sys.executable, str(runner), str(dataset), str(expected)]
    allowlist_payload: dict[str, object] = {"command_argvs": [list(command_argv)]}

    if case == "malicious_argv":
        allowlist_payload = {"command_argvs": [[sys.executable, "malicious.py", "--delete-all"]]}
    elif case == "executable_only":
        allowlist_payload = {"executables": [sys.executable, Path(sys.executable).name]}
    elif case == "prefix_only":
        allowlist_payload = {"allowed_prefixes": [[sys.executable, str(runner)]]}
    elif case == "placeholder_template":
        allowlist_payload = {
            "command_argvs": [[sys.executable, str(runner), "{dataset}", "{expected_artifact}"]]
        }
    elif case == "unknown_mode":
        execution_mode = "unknown-mode"
    elif case == "outside_workspace":
        runner = tmp_path / "outside-runner.py"
        runner.write_text("print('outside')\n", encoding="utf-8")
        command_argv = [sys.executable, str(runner), str(dataset), str(expected)]
        allowlist_payload = {"command_argvs": [list(command_argv)]}
    elif case == "dataset_before_mismatch":
        before = workspace / "different.csv"
        before.write_text("value\n2\n", encoding="utf-8")
    elif case == "missing_output_parent":
        expected = workspace / "missing-output-dir" / "result.json"
        command_argv = [sys.executable, str(runner), str(dataset), str(expected)]
        allowlist_payload = {"command_argvs": [list(command_argv)]}

    allowlist = tmp_path / f"{case}-allowlist.json"
    allowlist.write_text(json.dumps(allowlist_payload), encoding="utf-8")
    contract_path = tmp_path / f"{case}-contract.json"
    contract_path.write_text(
        json.dumps(
            {
                "verification_contract_version": "1",
                "readiness_profile": "deterministic_local_fixture",
                "execution_mode": execution_mode,
                "workspace_root": str(workspace),
                "runner": {"path": str(runner)},
                "dataset": {"path": str(dataset), "format": "csv", "role": "evaluation"},
                "variants": [
                    {"name": "baseline", "description": "baseline"},
                    {"name": "variant", "description": "candidate"},
                ],
                "thresholds": [{"metric": "score", "operator": ">=", "value": 0.5}],
                "random_seed": 7,
                "stopping_conditions": ["all rows processed"],
                "command_argv": command_argv,
                "command_allowlist": [" ".join(command_argv)],
                "expected_artifacts": [str(expected)],
                "network_access": "denied",
                "write_scope": [str(workspace)],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-design",
        f"idea-{case}",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--experiment-contract",
        str(contract_path),
        "--run-id",
        f"shim-exp-design-{case}",
    )
    expected_exit = 2 if case == "unknown_mode" else 0
    assert proc.returncode == expected_exit, proc.stderr
    payload = json.loads(Path(json.loads(proc.stdout)["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    plan = evidence["outputs"]["experiment_plan"]
    boundary = plan["source_context"]["final_execution_boundary"]

    assert plan["execution_ready"] is False
    assert boundary["approval_preflight"]["status"] == "incomplete"
    assert expected_reason in boundary["blocking_reasons"]


def test_autosci_skill_shim_exp_run_uses_verified_runtime_evidence_and_mutates_wiki(tmp_path: Path) -> None:
    allowlist = tmp_path / "exp-allowlist.json"
    runtime = tmp_path / "exp-runtime.json"
    before = tmp_path / "exp-before.json"
    after = tmp_path / "exp-after.json"
    allowlist.write_text(json.dumps({"approved": True, "scope": "exp-approved"}), encoding="utf-8")
    before.write_text(json.dumps({"state": "planned"}), encoding="utf-8")
    after.write_text(json.dumps({"state": "completed"}), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-exp-approved-runtime",
                "sprint_id": "sprint-exp-approved-runtime",
                "node_id": "node-exp-approved-runtime",
                "status": "completed",
                "inputs": {"approval_ref": "approval-exp-approved"},
                "outputs": {
                    "runtime": {
                        "action": "run_experiment",
                        "status": "completed",
                        "approval_ref": "approval-exp-approved",
                        "exit_code": 0,
                        "command_run": "python run_exp.py --experiment exp-approved",
                        "outcome": "supports",
                        "result_collected": True,
                        "metrics": [{"name": "accuracy", "value": 0.91}],
                        "evidence_ids": ["runtime:exp-approved"],
                        "logs": ["approved experiment runtime completed"],
                    }
                },
                "artifacts": [{"type": "runtime_after", "path": str(after)}],
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-approved",
        "--review",
        "--env",
        "local",
        "--approval-ref",
        "approval-exp-approved",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-exp-run-runtime-verified",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    result_action = next(action for action in actions if action["action"] == "run_experiment")
    assert result_action["status"] == "passed"
    result = json.loads(Path(result_action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_result = result["outputs"]["result"]
    assert result["status"] == "completed"
    assert experiment_result["experiment_id"] == "exp-approved"
    assert experiment_result["outcome"] == "supports"
    assert experiment_result["metrics"] == [{"name": "accuracy", "value": 0.91}]
    assert experiment_result["command_run"] == "python run_exp.py --experiment exp-approved"
    assert "runtime:exp-approved" in experiment_result["evidence_ids"]
    assert "fixture result collected" not in "\n".join(experiment_result["logs"]).lower()
    artifact_types = {artifact["type"] for artifact in result["artifacts"]}
    assert {
        "approval_contract_json",
        "experiment_runtime_evidence_json",
        "wiki_experiment_state",
        "wiki_log",
        "wiki_graph_edges",
        "experiment_run_final_runtime_audit_boundary_json",
    }.issubset(artifact_types)
    boundary = experiment_result["final_runtime_audit_boundary"]
    assert boundary["schema"] == "autosci_experiment_run_final_runtime_audit_boundary.v1"
    assert boundary["stage"] == "run"
    assert boundary["status"] == "stage_runtime_audit_ready"
    assert boundary["stage_audit_ready"] is True
    assert boundary["final_runtime_audit_ready"] is False
    assert boundary["wiki_state_mutated"] is True

    state_path = tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-approved.md"
    assert state_path.exists()
    state_text = state_path.read_text(encoding="utf-8")
    assert "status: completed" in state_text
    assert "outcome: supports" in state_text
    assert "runtime:exp-approved" in state_text
    assert "produced_result" in (tmp_path / "artifacts/autosci/workspace/wiki/graph/edges.jsonl").read_text(encoding="utf-8")
    assert "completed `exp-approved`" in (tmp_path / "artifacts/autosci/workspace/wiki/log.md").read_text(encoding="utf-8")


def test_autosci_skill_shim_exp_run_executes_approved_native_command(tmp_path: Path) -> None:
    allowlist = tmp_path / "exp-native-allowlist.json"
    before = tmp_path / "exp-native-before.json"
    after = tmp_path / "exp-native-after.json"
    marker = tmp_path / "exp-native-marker.txt"
    marker_command_script = tmp_path / "exp_native_command.py"
    before.write_text(json.dumps({"state": "planned", "approved": True}), encoding="utf-8")
    after.write_text(json.dumps({"state": "completed", "approved": True}), encoding="utf-8")
    marker_command_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import argparse",
                "from pathlib import Path",
                "import json",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--experiment-id', required=True)",
                "parser.add_argument('--marker', required=True)",
                "args = parser.parse_args()",
                "Path(args.marker).write_text('executed', encoding='utf-8')",
                "payload = {",
                "    'schema': 'experiment_result.v1',",
                "    'task_id': 'task-exp-native-run',",
                "    'sprint_id': 'sprint-exp-native-run',",
                "    'node_id': 'node-exp-native-run',",
                "    'status': 'completed',",
                "    'inputs': {'experiment_id': args.experiment_id},",
                "    'outputs': {",
                "        'result': {",
                "            'experiment_id': args.experiment_id,",
                "            'outcome': 'supports',",
                "            'metrics': [",
                "                {'name': 'f1', 'value': 0.88},",
                "            ],",
                "            'evidence_ids': ['runtime:exp-native'],",
                "            'logs': ['native command executed'],",
                "        }",
                "    },",
                "    'artifacts': [",
                "        {'type': 'experiment_runtime_output_json', 'path': str(args.marker), 'label': 'marker'},",
                "    ],",
                "    'provenance': {",
                "        'operator_id': 'test-script',",
                "        'implementation_package': 'test',",
                "        'timestamp': '2026-06-24T00:00:00Z',",
                "    },",
                "    'limitations': [],",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )
    marker_command_script.chmod(0o755)
    allowlist.write_text(
        json.dumps(
            {
                "commands": [
                    " ".join(
                        [
                            str(sys.executable),
                            str(marker_command_script),
                            "--experiment-id",
                            "{experiment_id}",
                            "--marker",
                            str(marker),
                        ]
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-native-001",
        "--review",
        "--env",
        "local",
        "--approval-ref",
        "approval-exp-native-001",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-exp-run-native-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = next(action for action in payload["outputs"]["skill_run"]["actions"] if action["action"] == "run_experiment")
    assert action["status"] == "passed"
    assert action["gate_status"] == "passed"
    result = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_result = result["outputs"]["result"]
    assert result["status"] == "completed"
    assert experiment_result["experiment_id"] == "exp-native-001"
    assert experiment_result["outcome"] == "supports"
    assert "runtime:exp-native" in experiment_result["evidence_ids"]
    assert marker.exists()
    assert marker.read_text(encoding="utf-8") == "executed"
    assert "native command executed" in " ".join(experiment_result["logs"])
    assert "python" in experiment_result["command_run"]
    artifact_types = {artifact["type"] for artifact in result["artifacts"]}
    assert {
        "approval_contract_json",
        "experiment_runtime_evidence_json",
        "run_experiment_result_json",
        "executor_stdout",
        "executor_stderr",
        "experiment_deploy_report_json",
        "experiment_run_report_json",
    }.issubset(artifact_types)
    deploy_report_path = next(
        artifact["path"]
        for artifact in result["artifacts"]
        if artifact["type"] == "experiment_deploy_report_json"
    )
    deploy_report = json.loads((tmp_path / deploy_report_path).read_text(encoding="utf-8"))
    assert deploy_report["schema"] == "autosci_experiment_deploy_report.v1"
    assert deploy_report["deploy_mode"] == "local_command"
    assert deploy_report["ready_for_execution"] is True
    run_report_path = next(
        artifact["path"]
        for artifact in result["artifacts"]
        if artifact["type"] == "experiment_run_report_json"
    )
    run_report = json.loads((tmp_path / run_report_path).read_text(encoding="utf-8"))
    assert run_report["schema"] == "autosci_experiment_run_report.v1"
    assert run_report["stage"] == "run"
    assert run_report["result_collected"] is True

    state_path = tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-native-001.md"
    state_text = state_path.read_text(encoding="utf-8")
    assert "status: completed" in state_text
    assert "outcome: supports" in state_text
    assert "runtime:exp-native" in state_text


def test_autosci_skill_shim_exp_run_parity_demo_auto_executes_local_command(tmp_path: Path) -> None:
    allowlist = tmp_path / "exp-parity-allowlist.json"
    marker = tmp_path / "exp-parity-marker.txt"
    marker_command_script = tmp_path / "exp_parity_command.py"
    marker_command_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import argparse",
                "from pathlib import Path",
                "import json",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--experiment-id', required=True)",
                "parser.add_argument('--marker', required=True)",
                "args = parser.parse_args()",
                "Path(args.marker).write_text('parity executed', encoding='utf-8')",
                "payload = {",
                "    'schema': 'experiment_result.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'result': {",
                "            'experiment_id': args.experiment_id,",
                "            'outcome': 'supports',",
                "            'metrics': [{'name': 'f1', 'value': 0.92}],",
                "            'evidence_ids': ['runtime:exp-parity'],",
                "            'logs': ['parity local command executed'],",
                "        }",
                "    },",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )
    marker_command_script.chmod(0o755)
    allowlist.write_text(
        json.dumps(
            {
                "commands": [
                    " ".join(
                        [
                            str(sys.executable),
                            str(marker_command_script),
                            "--experiment-id",
                            "{experiment_id}",
                            "--marker",
                            str(marker),
                        ]
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-parity-001",
        "--review",
        "--env",
        "local",
        "--allowlist-evidence",
        str(allowlist),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-exp-run-parity-demo-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = next(action for action in payload["outputs"]["skill_run"]["actions"] if action["action"] == "run_experiment")
    assert action["status"] == "passed"
    result = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_result = result["outputs"]["result"]
    assert result["status"] == "completed"
    assert experiment_result["experiment_id"] == "exp-parity-001"
    assert experiment_result["outcome"] == "supports"
    assert marker.read_text(encoding="utf-8") == "parity executed"
    assert "runtime:exp-parity" in experiment_result["evidence_ids"]
    policy = result["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:run_experiment:")
    artifacts = {artifact["type"]: artifact["path"] for artifact in result["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "experiment_runtime_evidence_json" in artifacts
    assert "run_experiment_result_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:run_experiment:")


def test_autosci_skill_shim_exp_pilot_run_executes_approved_native_command_without_wiki_writeback(tmp_path: Path) -> None:
    allowlist = tmp_path / "pilot-native-allowlist.json"
    before = tmp_path / "pilot-native-before.json"
    marker = tmp_path / "pilot-native-marker.txt"
    marker_command_script = tmp_path / "pilot_native_command.py"
    before.write_text(json.dumps({"state": "approved_for_pilot"}), encoding="utf-8")
    marker_command_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import argparse",
                "from pathlib import Path",
                "import json",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--experiment-id', required=True)",
                "parser.add_argument('--marker', required=True)",
                "args = parser.parse_args()",
                "Path(args.marker).write_text('pilot executed', encoding='utf-8')",
                "payload = {",
                "    'schema': 'experiment_result.v1',",
                "    'task_id': 'task-pilot-native-run',",
                "    'sprint_id': 'sprint-pilot-native-run',",
                "    'node_id': 'node-pilot-native-run',",
                "    'status': 'completed',",
                "    'inputs': {'experiment_id': args.experiment_id},",
                "    'outputs': {",
                "        'result': {",
                "            'experiment_id': args.experiment_id,",
                "            'outcome': 'supports',",
                "            'metrics': [{'name': 'accuracy', 'value': 0.93}],",
                "            'evidence_ids': ['runtime:pilot-native'],",
                "            'logs': ['pilot native command executed'],",
                "        }",
                "    },",
                "    'provenance': {",
                "        'operator_id': 'pilot-test-script',",
                "        'implementation_package': 'test',",
                "        'timestamp': '2026-06-24T00:00:00Z',",
                "    },",
                "    'limitations': [],",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )
    marker_command_script.chmod(0o755)
    allowlist.write_text(
        json.dumps(
            {
                "commands": [
                    " ".join(
                        [
                            str(sys.executable),
                            str(marker_command_script),
                            "--experiment-id",
                            "{experiment_id}",
                            "--marker",
                            str(marker),
                        ]
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-pilot-run",
        "pilot-native-001",
        "--approval-ref",
        "approval-pilot-native-001",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-exp-pilot-run-native-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-pilot-run"
    assert summary["execution_status"] == "gated"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "run_pilot_experiment"
    assert action["status"] == "passed"
    result = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    pilot_result = result["outputs"]["result"]
    assert result["status"] == "completed"
    assert pilot_result["experiment_id"] == "pilot-native-001"
    assert pilot_result["outcome"] == "supports"
    assert pilot_result["metrics"] == [{"name": "accuracy", "value": 0.93}]
    assert "runtime:pilot-native" in pilot_result["evidence_ids"]
    assert "pilot native command executed" in " ".join(pilot_result["logs"])
    assert marker.exists()
    assert marker.read_text(encoding="utf-8") == "pilot executed"

    boundary = pilot_result["pilot_final_acceptance_boundary"]
    assert boundary["stage"] == "pilot_run"
    assert boundary["status"] == "pilot_runtime_ready"
    assert boundary["pilot_runtime_ready"] is True
    assert boundary["pilot_verdict_ready"] is False
    assert boundary["writeback_completed"] is False
    assert boundary["final_pilot_acceptance_ready"] is False
    assert "exp-pilot-eval" in boundary["limitations"][0]

    artifact_types = {artifact["type"] for artifact in result["artifacts"]}
    assert {
        "approval_contract_json",
        "pilot_runtime_evidence_json",
        "pilot_runtime_after_artifact",
        "pilot_run_result_json",
        "executor_stdout",
        "executor_stderr",
        "experiment_deploy_report_json",
        "experiment_run_report_json",
        "pilot_run_final_acceptance_boundary_json",
        "approval_runtime_proof_manifest_json",
        "side_effect_runtime_proof_manifest_json",
    }.issubset(artifact_types)
    assert "wiki_mutation_runtime_proof_manifest_json" not in artifact_types
    assert "wiki_experiment_state" not in artifact_types
    assert not (tmp_path / "artifacts/autosci/workspace/wiki/experiments/pilot-native-001.md").exists()

    contract_path = next(artifact["path"] for artifact in result["artifacts"] if artifact["type"] == "approval_contract_json")
    contract = json.loads((tmp_path / contract_path).read_text(encoding="utf-8"))
    assert contract["action"] == "run_pilot_experiment"
    assert contract["execution_verified"] is True
    run_report_path = next(artifact["path"] for artifact in result["artifacts"] if artifact["type"] == "experiment_run_report_json")
    run_report = json.loads((tmp_path / run_report_path).read_text(encoding="utf-8"))
    assert run_report["stage"] == "pilot_run"
    assert run_report["result_collected"] is True


def test_autosci_skill_shim_exp_pilot_run_parity_demo_auto_executes_local_command(tmp_path: Path) -> None:
    allowlist = tmp_path / "pilot-parity-allowlist.json"
    marker = tmp_path / "pilot-parity-marker.txt"
    marker_command_script = tmp_path / "pilot_parity_command.py"
    marker_command_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import argparse",
                "from pathlib import Path",
                "import json",
                "",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--experiment-id', required=True)",
                "parser.add_argument('--marker', required=True)",
                "args = parser.parse_args()",
                "Path(args.marker).write_text('pilot parity executed', encoding='utf-8')",
                "payload = {",
                "    'schema': 'experiment_result.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'result': {",
                "            'experiment_id': args.experiment_id,",
                "            'outcome': 'supports',",
                "            'metrics': [{'name': 'accuracy', 'value': 0.91}],",
                "            'evidence_ids': ['runtime:pilot-parity'],",
                "            'logs': ['pilot parity command executed'],",
                "        }",
                "    },",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )
    marker_command_script.chmod(0o755)
    allowlist.write_text(
        json.dumps(
            {
                "commands": [
                    " ".join(
                        [
                            str(sys.executable),
                            str(marker_command_script),
                            "--experiment-id",
                            "{experiment_id}",
                            "--marker",
                            str(marker),
                        ]
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-pilot-run",
        "pilot-parity-001",
        "--allowlist-evidence",
        str(allowlist),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-exp-pilot-run-parity-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    result = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    pilot_result = result["outputs"]["result"]
    assert result["status"] == "completed"
    assert pilot_result["experiment_id"] == "pilot-parity-001"
    assert pilot_result["outcome"] == "supports"
    assert marker.read_text(encoding="utf-8") == "pilot parity executed"
    policy = result["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:run_pilot_experiment:")
    artifacts = {artifact["type"]: artifact["path"] for artifact in result["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:run_pilot_experiment:")
    assert "wiki_experiment_state" not in {artifact["type"] for artifact in result["artifacts"]}


def test_autosci_skill_shim_exp_run_assimilates_remote_helper_runtime_evidence(tmp_path: Path) -> None:
    allowlist = tmp_path / "exp-remote-allowlist.json"
    remote_allowlist = tmp_path / "exp-remote-inner-allowlist.json"
    before = tmp_path / "exp-remote-before.json"
    after = tmp_path / "exp-remote-after.json"
    run_dir = tmp_path / "remote-run"
    runtime_out = tmp_path / "exp-remote-runtime.json"
    inner_script = tmp_path / "exp_remote_inner.py"
    before.write_text(json.dumps({"state": "planned", "approved": True}), encoding="utf-8")
    after.write_text(json.dumps({"state": "completed", "approved": True}), encoding="utf-8")
    inner_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "from pathlib import Path",
                "Path('results.json').write_text(json.dumps({",
                "    'outcome': 'supports',",
                "    'metrics': [{'name': 'accuracy', 'value': 0.92}],",
                "    'logs': ['remote helper collected result'],",
                "}), encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )
    inner_script.chmod(0o755)
    inner_command = " ".join([str(sys.executable), str(inner_script)])
    inner_command_arg = " ".join([shlex.quote(str(sys.executable)), shlex.quote(str(inner_script))])
    remote_allowlist.write_text(json.dumps({"commands": [inner_command]}), encoding="utf-8")
    outer_command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "launch",
            "--approval-ref",
            "approval-exp-remote",
            "--experiment",
            "{experiment_id}",
            "--allowlist-evidence",
            shlex.quote(str(remote_allowlist)),
            "--command",
            shlex.quote(inner_command_arg),
            "--run-dir",
            shlex.quote(str(run_dir)),
            "--runtime-evidence-out",
            shlex.quote(str(runtime_out)),
            "--timeout-seconds",
            "20",
            "--execute-approved",
        ]
    )
    allowlist.write_text(json.dumps({"commands": [outer_command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-remote",
        "--review",
        "--env",
        "local",
        "--approval-ref",
        "approval-exp-remote",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-exp-run-remote-helper",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["execution_status"] == "gated"
    assert runtime_out.exists()

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = next(action for action in payload["outputs"]["skill_run"]["actions"] if action["action"] == "run_experiment")
    assert action["status"] == "passed"
    result = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_result = result["outputs"]["result"]
    assert result["status"] == "completed"
    assert experiment_result["experiment_id"] == "exp-remote"
    assert experiment_result["outcome"] == "supports"
    assert experiment_result["metrics"] == [{"name": "accuracy", "value": 0.92}]
    assert "remote-runtime:exp-remote" in experiment_result["evidence_ids"]
    assert "remote helper collected result" in " ".join(experiment_result["logs"])
    runtime_artifacts = [
        artifact["path"]
        for artifact in result["artifacts"]
        if artifact["type"] == "experiment_runtime_evidence_json"
    ]
    assert any(path.endswith("exp-remote-runtime.json") for path in runtime_artifacts)

    remote_runtime = json.loads(runtime_out.read_text(encoding="utf-8"))
    assert remote_runtime["schema"] == "autosci_runtime_evidence.v1"
    assert remote_runtime["status"] == "completed"
    assert remote_runtime["outputs"]["runtime"]["run_dir"] == str(run_dir.resolve())
    assert remote_runtime["outputs"]["runtime"]["result_collected"] is True

    state_path = tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-remote.md"
    state_text = state_path.read_text(encoding="utf-8")
    assert "status: completed" in state_text
    assert "outcome: supports" in state_text
    assert "remote-runtime:exp-remote" in state_text


def test_autosci_skill_shim_exp_run_rejects_remote_helper_stdout_without_runtime_evidence(tmp_path: Path) -> None:
    allowlist = tmp_path / "exp-remote-missing-allowlist.json"
    before = tmp_path / "exp-remote-missing-before.json"
    after = tmp_path / "exp-remote-missing-after.json"
    missing_runtime = tmp_path / "missing-remote-runtime.json"
    fake_remote = tmp_path / "fake_remote_stdout.py"
    before.write_text(json.dumps({"state": "planned", "approved": True}), encoding="utf-8")
    after.write_text(json.dumps({"state": "completed", "approved": True}), encoding="utf-8")
    fake_remote.write_text(
        "\n".join(
            [
                "import json",
                f"print(json.dumps({{'schema': 'autosci_remote_cli.v1', 'status': 'completed', 'ok': True, 'runtime_evidence_path': {str(missing_runtime)!r}}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command = " ".join([shlex.quote(str(sys.executable)), shlex.quote(str(fake_remote))])
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-remote-missing",
        "--review",
        "--env",
        "local",
        "--approval-ref",
        "approval-exp-remote-missing",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-exp-run-remote-missing-runtime",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = next(action for action in payload["outputs"]["skill_run"]["actions"] if action["action"] == "run_experiment")
    assert action["status"] != "passed"
    result = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    experiment_result = result["outputs"]["result"]
    assert result["status"] == "inconclusive"
    assert {"name": "runtime_evidence_verified", "value": False} in experiment_result["metrics"]
    assert "remote-runtime:exp-remote-missing" not in experiment_result["evidence_ids"]
    local_runtime_path = next(
        artifact["path"]
        for artifact in result["artifacts"]
        if artifact["type"] == "experiment_runtime_evidence_json"
    )
    local_runtime = json.loads((tmp_path / local_runtime_path).read_text(encoding="utf-8"))
    runtime = local_runtime["outputs"]["runtime"]
    assert runtime["result_collected"] is False
    assert runtime["result_path"] == ""
    assert runtime["remote_runtime_evidence_path"] == ""


def test_autosci_skill_shim_exp_status_reads_persistent_session_registry(tmp_path: Path) -> None:
    allowlist = tmp_path / "exp-session-allowlist.json"
    before = tmp_path / "exp-session-before.json"
    run_dir = tmp_path / "session-run"
    fake_launch = tmp_path / "fake_launch.py"
    before.write_text(json.dumps({"state": "planned", "approved": True}), encoding="utf-8")
    fake_launch.write_text(
        "\n".join(
            [
                "import json",
                f"print(json.dumps({{'schema': 'autosci_remote_cli.v1', 'command': 'launch', 'status': 'inconclusive', 'ok': False, 'run_dir': {str(run_dir)!r}, 'result_collected': False, 'runtime_evidence_path': ''}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command = " ".join([shlex.quote(str(sys.executable)), shlex.quote(str(fake_launch))])
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    launched = run_shim(
        tmp_path,
        "$exp-run",
        "exp-session",
        "--review",
        "--env",
        "local",
        "--approval-ref",
        "approval-exp-session",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-exp-session-launch",
    )
    assert launched.returncode == 0, launched.stderr
    registry_path = tmp_path / "artifacts/autosci/workspace/wiki/experiments/session-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["schema"] == "autosci_experiment_session_registry.v1"
    assert registry["sessions"][0]["experiment_id"] == "exp-session"
    assert registry["sessions"][0]["state"] == "running"

    status = run_shim(
        tmp_path,
        "$exp-status",
        "exp-session",
        "--run-id",
        "shim-exp-session-status",
    )
    assert status.returncode == 0, status.stderr
    summary = json.loads(status.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-session"
    assert report["state"] == "running"
    assert any("Resolved experiment session" in item for item in report["observations"])
    assert any("Run approved collect" in item for item in report["next_actions"])
    assert any("no remote process was polled" in item for item in evidence["limitations"])
    assert any(artifact["type"] == "experiment_session_registry_json" for artifact in evidence["artifacts"])


def test_autosci_skill_shim_exp_status_executes_approved_remote_check(tmp_path: Path) -> None:
    run_dir = tmp_path / "remote-status-run"
    run_dir.mkdir()
    (run_dir / "status.json").write_text(
        json.dumps({"status": "running", "evidence_ids": ["remote-status:exp-remote-check"]}),
        encoding="utf-8",
    )
    before = tmp_path / "remote-status-before.json"
    before.write_text(json.dumps({"approved": True, "state": "before-check"}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools/remote.py")),
            "check",
            "--experiment",
            "exp-remote-check",
            "--run-dir",
            shlex.quote(str(run_dir)),
        ]
    )
    allowlist = tmp_path / "remote-status-allowlist.json"
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    status = run_shim(
        tmp_path,
        "$exp-status",
        "exp-remote-check",
        "--env",
        "remote",
        "--approval-ref",
        "approval-remote-status-check",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--remote-check-command",
        command,
        "--remote-run-dir",
        str(run_dir),
        "--execute-approved",
        "--run-id",
        "shim-exp-status-remote-check",
    )

    assert status.returncode == 0, status.stderr
    summary = json.loads(status.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-remote-check"
    assert report["state"] == "running"
    assert any("Approved remote status check" in item for item in report["observations"])
    assert any("remote_poll_boundary_status=local_run_dir_check" in item for item in report["observations"])
    assert any("no result collection" in item for item in evidence["limitations"])
    assert any("not a proven live SSH/provider poll" in item for item in evidence["limitations"])
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"approval_contract_json", "remote_status_runtime_evidence_json", "remote_status_file"} <= artifact_types
    assert "provider_source_runtime_proof_manifest_json" not in artifact_types
    runtime_path = next(
        artifact["path"]
        for artifact in evidence["artifacts"]
        if artifact["type"] == "remote_status_runtime_evidence_json"
    )
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_detail = runtime["outputs"]["runtime"]
    assert runtime["schema"] == "autosci_runtime_evidence.v1"
    assert runtime_detail["action"] == "monitor_experiment"
    assert runtime_detail["remote_cli_command"] == "check"
    assert runtime_detail["remote_status_state"] == "running"
    boundary = runtime_detail["remote_poll_boundary"]
    assert boundary["schema"] == "autosci_remote_poll_boundary.v1"
    assert boundary["status"] == "local_run_dir_check"
    assert boundary["live_remote_poll_verified"] is False
    assert boundary["local_artifact_check"] is True
    assert "status was derived from local run-dir artifacts" in boundary["invalid_reasons"]


def test_autosci_skill_shim_exp_status_parity_demo_remote_opt_in_executes_check(tmp_path: Path) -> None:
    run_dir = tmp_path / "remote-status-parity-run"
    run_dir.mkdir()
    (run_dir / "status.json").write_text(
        json.dumps({"status": "running", "evidence_ids": ["remote-status:exp-remote-parity"]}),
        encoding="utf-8",
    )
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools/remote.py")),
            "check",
            "--experiment",
            "exp-remote-parity",
            "--run-dir",
            shlex.quote(str(run_dir)),
        ]
    )
    allowlist = tmp_path / "remote-status-parity-allowlist.json"
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    status = run_shim(
        tmp_path,
        "$exp-status",
        "exp-remote-parity",
        "--env",
        "remote",
        "--allowlist-evidence",
        str(allowlist),
        "--remote-check-command",
        command,
        "--remote-run-dir",
        str(run_dir),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-exp-status-parity-remote-check",
        extra_env={"SOLAR_AUTOSCI_ALLOW_REMOTE": "1"},
    )

    assert status.returncode == 0, status.stderr
    summary = json.loads(status.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-remote-parity"
    assert report["state"] == "running"
    assert any("Approved remote status check" in item for item in report["observations"])
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:monitor_experiment:")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "remote_status_runtime_evidence_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:monitor_experiment:")


def test_autosci_skill_shim_exp_status_executes_approved_live_remote_check(tmp_path: Path) -> None:
    run_dir = tmp_path / "live-remote-status-run"
    run_dir.mkdir()
    before = tmp_path / "live-remote-status-before.json"
    before.write_text(json.dumps({"approved": True, "state": "before-live-check"}), encoding="utf-8")
    provider_script = tmp_path / "fake_live_status_provider.py"
    provider_script.write_text(
        "import json\n"
        "print(json.dumps({'remote_state': 'running', 'provider': 'ssh'}))\n",
        encoding="utf-8",
    )
    provider_command = shlex.join([str(sys.executable), str(provider_script)])
    provider_allowlist = tmp_path / "live-provider-allowlist.json"
    provider_allowlist.write_text(json.dumps({"commands": [provider_command]}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools/remote.py")),
            "check",
            "--experiment",
            "exp-live-remote-check",
            "--run-dir",
            shlex.quote(str(run_dir)),
            "--approval-ref",
            "approval-live-remote-status-provider",
            "--allowlist-evidence",
            shlex.quote(str(provider_allowlist)),
            "--status-command",
            shlex.quote(provider_command),
            "--transport",
            "ssh",
            "--session-id",
            "ssh-session-123",
            "--execute-approved",
        ]
    )
    allowlist = tmp_path / "live-remote-status-allowlist.json"
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    status = run_shim(
        tmp_path,
        "$exp-status",
        "exp-live-remote-check",
        "--env",
        "remote",
        "--approval-ref",
        "approval-live-remote-status-check",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--remote-check-command",
        command,
        "--remote-run-dir",
        str(run_dir),
        "--execute-approved",
        "--run-id",
        "shim-exp-status-live-remote-check",
    )

    assert status.returncode == 0, status.stderr
    summary = json.loads(status.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-live-remote-check"
    assert report["state"] == "running"
    assert any("remote_poll_boundary_status=live_remote_poll" in item for item in report["observations"])
    assert not any("not a proven live SSH/provider poll" in item for item in evidence["limitations"])
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    runtime_path = next(
        artifact["path"]
        for artifact in evidence["artifacts"]
        if artifact["type"] == "remote_status_runtime_evidence_json"
    )
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_detail = runtime["outputs"]["runtime"]
    assert runtime_detail["remote_status_state"] == "running"
    assert "Remote check payload reported `running`." in runtime_detail["logs"]
    boundary = runtime_detail["remote_poll_boundary"]
    assert boundary["schema"] == "autosci_remote_poll_boundary.v1"
    assert boundary["status"] == "live_remote_poll"
    assert boundary["live_remote_poll_verified"] is True
    assert boundary["local_artifact_check"] is True
    assert boundary["transport"] == "ssh"
    assert boundary["session_id"] == "ssh-session-123"
    proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-status"
    assert proof_entry["categories"] == ["external_runtime_evidence", "provider_source_evidence"]
    assert proof_entry["collection_mode"] == "live_provider"
    assert any(ref.endswith("remote_status_runtime_evidence.json") for ref in proof_entry["evidence_refs"])


def test_autosci_skill_shim_exp_collect_uses_verified_runtime_evidence(tmp_path: Path) -> None:
    allowlist = tmp_path / "collect-allowlist.json"
    runtime = tmp_path / "collect-runtime.json"
    before = tmp_path / "collect-before.json"
    after = tmp_path / "collect-after.json"
    allowlist.write_text(json.dumps({"approved": True, "scope": "exp-collect"}), encoding="utf-8")
    before.write_text(json.dumps({"state": "running"}), encoding="utf-8")
    after.write_text(json.dumps({"state": "completed"}), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "task-exp-collect-runtime",
                "sprint_id": "sprint-exp-collect-runtime",
                "node_id": "node-exp-collect-runtime",
                "status": "completed",
                "inputs": {"approval_ref": "approval-exp-collect"},
                "outputs": {
                    "runtime": {
                        "action": "run_experiment",
                        "status": "completed",
                        "approval_ref": "approval-exp-collect",
                        "exit_code": 0,
                        "command_run": "python collect_exp.py --experiment exp-collect",
                        "outcome": "partially_supports",
                        "result_collected": True,
                        "metrics": [{"name": "f1", "value": 0.77}],
                        "evidence_ids": ["runtime:exp-collect"],
                        "logs": ["approved collect completed"],
                    }
                },
                "artifacts": [{"type": "runtime_after", "path": str(after)}],
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-collect",
        "--collect",
        "--approval-ref",
        "approval-exp-collect",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-exp-collect-runtime-verified",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-run"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-collect"
    assert report["state"] == "completed"
    assert "runtime:exp-collect" in report["evidence_ids"]
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"approval_contract_json", "experiment_runtime_evidence_json", "wiki_experiment_state"}.issubset(artifact_types)
    state_text = (tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-collect.md").read_text(encoding="utf-8")
    assert "status: completed" in state_text
    assert "outcome: partially_supports" in state_text
    assert "runtime:exp-collect" in state_text


def test_autosci_skill_shim_exp_collect_executes_approved_remote_pull_results(tmp_path: Path) -> None:
    allowlist = tmp_path / "remote-collect-allowlist.json"
    before = tmp_path / "remote-collect-before.json"
    result_dir = tmp_path / "remote-results"
    result_dir.mkdir()
    (result_dir / "results.json").write_text(
        json.dumps(
            {
                "outcome": "partially_supports",
                "metrics": [{"name": "accuracy", "value": 0.94}],
                "evidence_ids": ["result:exp-remote-collect"],
                "logs": ["remote pull-results collected metrics"],
            }
        ),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"state": "running", "approved": True}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "pull-results",
            "--result-dir",
            shlex.quote(str(result_dir)),
        ]
    )
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-remote-collect",
        "--collect",
        "--approval-ref",
        "approval-exp-remote-collect",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-exp-remote-collect",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-remote-collect"
    assert report["state"] == "completed"
    assert "remote-collect:exp-remote-collect" in report["evidence_ids"]
    assert "result:exp-remote-collect" in report["evidence_ids"]
    assert any("collect_executor_result=True" in item for item in report["observations"])
    assert any("remote_collection_boundary_status=local_result_dir_collection" in item for item in report["observations"])
    assert any("not a proven live SSH/provider pull-results operation" in item for item in evidence["limitations"])
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"experiment_runtime_evidence_json", "executor_stdout", "executor_stderr", "remote_collected_file", "wiki_experiment_state"}.issubset(artifact_types)
    assert "experiment_run_final_runtime_audit_boundary_json" in artifact_types
    runtime_path = next(artifact["path"] for artifact in evidence["artifacts"] if artifact["type"] == "experiment_runtime_evidence_json")
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_payload = runtime["outputs"]["runtime"]
    assert runtime_payload["result_collected"] is True
    assert runtime_payload["metrics"] == [{"name": "accuracy", "value": 0.94}]
    assert runtime_payload["outcome"] == "partially_supports"
    assert runtime_payload["remote_cli_command"] == "pull-results"
    boundary = runtime_payload["remote_collection_boundary"]
    assert boundary["schema"] == "autosci_remote_collection_boundary.v1"
    assert boundary["status"] == "local_result_dir_collection"
    assert boundary["live_remote_collection_verified"] is False
    assert boundary["local_result_dir_collection"] is True
    runtime_audit = report["final_runtime_audit_boundary"]
    assert runtime_audit["stage"] == "collect"
    assert runtime_audit["status"] == "stage_runtime_audit_ready"
    assert runtime_audit["stage_audit_ready"] is True
    assert runtime_audit["final_runtime_audit_ready"] is False
    assert runtime_audit["collection_ledger_recorded"] is True
    assert runtime_audit["live_remote_collection_verified"] is False
    assert not any(
        artifact["type"] == "provider_source_runtime_proof_manifest_json"
        for artifact in evidence["artifacts"]
    )

    state_text = (tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-remote-collect.md").read_text(encoding="utf-8")
    assert "outcome: partially_supports" in state_text
    assert "- accuracy: 0.94" in state_text


def test_autosci_skill_shim_exp_collect_parity_demo_remote_opt_in_executes_pull_results(tmp_path: Path) -> None:
    allowlist = tmp_path / "remote-collect-parity-allowlist.json"
    result_dir = tmp_path / "remote-parity-results"
    result_dir.mkdir()
    (result_dir / "results.json").write_text(
        json.dumps(
            {
                "outcome": "supports",
                "metrics": [{"name": "accuracy", "value": 0.96}],
                "evidence_ids": ["result:exp-remote-parity-collect"],
                "logs": ["parity remote pull-results collected metrics"],
            }
        ),
        encoding="utf-8",
    )
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "pull-results",
            "--result-dir",
            shlex.quote(str(result_dir)),
        ]
    )
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-remote-parity-collect",
        "--collect",
        "--allowlist-evidence",
        str(allowlist),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-exp-remote-parity-collect",
        extra_env={"SOLAR_AUTOSCI_ALLOW_REMOTE": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-remote-parity-collect"
    assert report["state"] == "completed"
    assert "result:exp-remote-parity-collect" in report["evidence_ids"]
    assert any("collect_executor_result=True" in item for item in report["observations"])
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:monitor_experiment:")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "experiment_runtime_evidence_json" in artifacts
    assert "wiki_experiment_state" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    state_text = (tmp_path / "artifacts/autosci/workspace/wiki/experiments/exp-remote-parity-collect.md").read_text(encoding="utf-8")
    assert "status: completed" in state_text
    assert "outcome: supports" in state_text
    assert "- accuracy: 0.96" in state_text


def test_autosci_skill_shim_exp_collect_executes_approved_live_remote_pull_results(tmp_path: Path) -> None:
    allowlist = tmp_path / "live-remote-collect-allowlist.json"
    provider_allowlist = tmp_path / "live-remote-provider-allowlist.json"
    before = tmp_path / "live-remote-collect-before.json"
    result_dir = tmp_path / "live-remote-results"
    result_dir.mkdir()
    provider_script = tmp_path / "fake_live_pull_results_provider.py"
    provider_script.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "Path('results.json').write_text(json.dumps({\n"
        "    'outcome': 'supports',\n"
        "    'metrics': [{'name': 'accuracy', 'value': 0.97}],\n"
        "    'evidence_ids': ['result:exp-live-remote-collect'],\n"
        "    'logs': ['live provider pull-results collected metrics'],\n"
        "}))\n",
        encoding="utf-8",
    )
    provider_command = shlex.join([str(sys.executable), str(provider_script)])
    provider_allowlist.write_text(json.dumps({"commands": [provider_command]}), encoding="utf-8")
    before.write_text(json.dumps({"state": "running", "approved": True}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "pull-results",
            "--result-dir",
            shlex.quote(str(result_dir)),
            "--approval-ref",
            "approval-live-remote-pull-provider",
            "--allowlist-evidence",
            shlex.quote(str(provider_allowlist)),
            "--pull-command",
            shlex.quote(provider_command),
            "--transport",
            "ssh",
            "--session-id",
            "ssh-session-collect-123",
            "--execute-approved",
        ]
    )
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-live-remote-collect",
        "--collect",
        "--approval-ref",
        "approval-exp-live-remote-collect",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-exp-live-remote-collect",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "completed"
    assert report["experiment_id"] == "exp-live-remote-collect"
    assert report["state"] == "completed"
    assert "result:exp-live-remote-collect" in report["evidence_ids"]
    assert any("remote_collection_boundary_status=live_remote_collection" in item for item in report["observations"])
    assert not any("not a proven live SSH/provider pull-results operation" in item for item in evidence["limitations"])
    runtime_path = next(artifact["path"] for artifact in evidence["artifacts"] if artifact["type"] == "experiment_runtime_evidence_json")
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_payload = runtime["outputs"]["runtime"]
    assert runtime_payload["result_collected"] is True
    assert runtime_payload["metrics"] == [{"name": "accuracy", "value": 0.97}]
    assert runtime_payload["outcome"] == "supports"
    boundary = runtime_payload["remote_collection_boundary"]
    assert boundary["schema"] == "autosci_remote_collection_boundary.v1"
    assert boundary["status"] == "live_remote_collection"
    assert boundary["live_remote_collection_verified"] is True
    assert boundary["transport"] == "ssh"
    assert boundary["session_id"] == "ssh-session-collect-123"
    runtime_audit = report["final_runtime_audit_boundary"]
    assert runtime_audit["stage"] == "collect"
    assert runtime_audit["status"] == "final_runtime_audit_ready"
    assert runtime_audit["stage_audit_ready"] is True
    assert runtime_audit["final_runtime_audit_ready"] is True
    assert runtime_audit["collection_ledger_recorded"] is True
    assert runtime_audit["live_remote_collection_verified"] is True
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-run"
    assert proof_entry["categories"] == [
        "external_runtime_evidence",
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "provider_source_evidence",
        "wiki_mutation_evidence",
    ]
    assert proof_entry["collection_mode"] == "live_provider"


def test_autosci_skill_shim_exp_collect_rejects_empty_remote_pull_results(tmp_path: Path) -> None:
    allowlist = tmp_path / "remote-empty-allowlist.json"
    before = tmp_path / "remote-empty-before.json"
    result_dir = tmp_path / "remote-empty-results"
    result_dir.mkdir()
    before.write_text(json.dumps({"state": "running", "approved": True}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "pull-results",
            "--result-dir",
            shlex.quote(str(result_dir)),
        ]
    )
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-remote-empty",
        "--collect",
        "--approval-ref",
        "approval-exp-remote-empty",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-exp-remote-empty",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "monitor_experiment"
    assert action["status"] != "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert evidence["status"] == "inconclusive"
    assert report["state"] == "unknown"
    assert any("runtime_semantic_status=incomplete" in item for item in report["observations"])
    runtime_path = next(artifact["path"] for artifact in evidence["artifacts"] if artifact["type"] == "experiment_runtime_evidence_json")
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_payload = runtime["outputs"]["runtime"]
    assert runtime_payload["result_collected"] is False
    assert runtime_payload["metrics"] == []
    assert any(check["check"] == "collected_files_present" and check["status"] == "error" for check in runtime_payload["checks"])


def test_autosci_skill_shim_exp_collect_writes_multiseed_metric_aggregate_report(tmp_path: Path) -> None:
    allowlist = tmp_path / "remote-multiseed-allowlist.json"
    before = tmp_path / "remote-multiseed-before.json"
    result_dir = tmp_path / "remote-multiseed-results"
    result_dir.mkdir()
    (result_dir / "seed-1.json").write_text(
        json.dumps(
            {
                "outcome": "supports",
                "metrics": [{"name": "accuracy", "value": 0.8, "seed": 1}],
                "evidence_ids": ["result:exp-multiseed:seed-1"],
                "logs": ["seed 1 complete"],
            }
        ),
        encoding="utf-8",
    )
    (result_dir / "seed-2.json").write_text(
        json.dumps(
            {
                "outcome": "supports",
                "metrics": [{"name": "accuracy", "value": 0.9, "seed": 2}],
                "evidence_ids": ["result:exp-multiseed:seed-2"],
                "logs": ["seed 2 complete"],
            }
        ),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"state": "running", "approved": True}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "pull-results",
            "--result-dir",
            shlex.quote(str(result_dir)),
        ]
    )
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-run",
        "exp-multiseed",
        "--collect",
        "--approval-ref",
        "approval-exp-multiseed",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-exp-multiseed-collect",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"experiment_metric_aggregate_report_json", "experiment_run_report_json"}.issubset(artifact_types)
    aggregate_path = next(
        artifact["path"]
        for artifact in evidence["artifacts"]
        if artifact["type"] == "experiment_metric_aggregate_report_json"
    )
    aggregate_report = json.loads((tmp_path / aggregate_path).read_text(encoding="utf-8"))
    assert aggregate_report["schema"] == "autosci_experiment_metric_aggregate_report.v1"
    assert aggregate_report["status"] == "completed"
    accuracy = aggregate_report["aggregates"][0]
    assert accuracy["name"] == "accuracy"
    assert accuracy["sample_count"] == 2
    assert accuracy["seed_count"] == 2
    assert accuracy["mean"] == pytest.approx(0.85)
    assert accuracy["std"] == pytest.approx(0.070710678, rel=1e-6)

    runtime_path = next(
        artifact["path"]
        for artifact in evidence["artifacts"]
        if artifact["type"] == "experiment_runtime_evidence_json"
    )
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_payload = runtime["outputs"]["runtime"]
    assert runtime_payload["metric_aggregates"][0]["mean"] == pytest.approx(0.85)
    assert len(runtime_payload["result_paths"]) == 2


def test_autosci_skill_shim_exp_collect_reuses_exactly_once_collection_ledger(tmp_path: Path) -> None:
    allowlist = tmp_path / "remote-once-allowlist.json"
    before = tmp_path / "remote-once-before.json"
    result_dir = tmp_path / "remote-once-results"
    result_dir.mkdir()
    (result_dir / "results.json").write_text(
        json.dumps(
            {
                "outcome": "supports",
                "metrics": [{"name": "accuracy", "value": 0.96}],
                "evidence_ids": ["result:exp-once"],
                "logs": ["first collection payload"],
            }
        ),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"state": "running", "approved": True}), encoding="utf-8")
    command = " ".join(
        [
            shlex.quote(str(sys.executable)),
            shlex.quote(str(REPO / "tools" / "remote.py")),
            "pull-results",
            "--result-dir",
            shlex.quote(str(result_dir)),
        ]
    )
    allowlist.write_text(json.dumps({"commands": [command]}), encoding="utf-8")

    common_args = [
        "$exp-run",
        "exp-once",
        "--collect",
        "--approval-ref",
        "approval-exp-once",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
    ]
    first = run_shim(tmp_path, *common_args, "--run-id", "shim-exp-once-first")
    assert first.returncode == 0, first.stderr
    second = run_shim(tmp_path, *common_args, "--run-id", "shim-exp-once-second")
    assert second.returncode == 0, second.stderr

    summary = json.loads(second.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["status_report"]
    assert report["state"] == "completed"
    assert any("collection_duplicate=True" in item for item in report["observations"])

    ledger_path = tmp_path / "artifacts/autosci/workspace/wiki/collections/collection-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["schema"] == "autosci_collection_ledger.v1"
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["experiment_id"] == "exp-once"
    assert ledger["entries"][0]["evidence_ids"] == [
        "remote-collect:exp-once",
        "remote-once-results/results.json",
        "result:exp-once",
    ]

    runtime_path = next(artifact["path"] for artifact in evidence["artifacts"] if artifact["type"] == "experiment_runtime_evidence_json")
    runtime = json.loads((tmp_path / runtime_path).read_text(encoding="utf-8"))
    runtime_payload = runtime["outputs"]["runtime"]
    assert runtime_payload["collection_duplicate"] is True
    assert runtime_payload["collection_identity"] == ledger["entries"][0]["collection_identity"]
    log_text = (tmp_path / "artifacts/autosci/workspace/wiki/log.md").read_text(encoding="utf-8")
    assert log_text.count("completed `exp-once`") == 1


def test_autosci_skill_shim_accepts_paper_plan_title_without_topic_fallback(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$paper-plan",
        "idea-001",
        "--venue",
        "ICLR",
        "--title",
        "Skill Generation for Inference-Time Agents",
        "--run-id",
        "shim-paper-plan-native",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-plan"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == "idea-001"
    assert payload["inputs"]["venue"] == "ICLR"
    assert payload["inputs"]["native_options"]["title"] == "Skill Generation for Inference-Time Agents"
    assert payload["inputs"]["topic"] == ""
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "plan_report"
    assert action["schema"] == "scientific_report_plan.v1"
    report_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = report_evidence["outputs"]["report_plan"]
    assert report_evidence["status"] == "inconclusive"
    assert report["title"] == "Skill Generation for Inference-Time Agents"
    assert any(section["section_id"] == "review-gates" for section in report["sections"])
    assert (tmp_path / "artifacts/autosci/runs/shim-paper-plan-native/paper_plan.md").exists()


def test_autosci_skill_shim_paper_plan_blocks_final_acceptance_without_compile(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "lit-skillgen",
                "status": "completed",
                "outputs": {
                    "query": "skill generation",
                    "candidates": [
                        {
                            "candidate_id": "arxiv:2601.00001",
                            "title": "SkillGen: Generating Skills for Agents",
                            "arxiv_id": "2601.00001",
                            "source_ref": "https://arxiv.org/abs/2601.00001",
                            "source_channels": ["search_s2"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review-llm.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-paper-plan",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_available": True,
                        "review_mode": "review_llm",
                        "score": 0.82,
                        "recommendation": "accept",
                        "evidence_ids": ["review:paper-plan"],
                        "findings": [],
                        "review_llm": {"status": "completed"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$paper-plan",
        "idea-skillgen",
        "--title",
        "SkillGen Plan",
        "--discovery-evidence",
        str(discovery),
        "--review-llm-evidence",
        str(review),
        "--run-id",
        "shim-paper-plan-citation-review",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-plan"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    report = evidence["outputs"]["report_plan"]
    figure_plan = next(section for section in report["sections"] if section["section_id"] == "figure-citation-plan")
    assert "SkillGen: Generating Skills for Agents" in figure_plan["purpose"]
    assert any(section["section_id"] == "final-plan-acceptance-boundary" for section in report["sections"])
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    citation_map = json.loads((tmp_path / artifacts["citation_map_json"]).read_text(encoding="utf-8"))
    assert citation_map["status"] == "completed"
    assert citation_map["citation_count"] == 1
    assert "paper_plan_final_acceptance_boundary_json" in artifacts
    assert "review_model_runtime_proof_manifest_json" in artifacts
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    plan_json = json.loads((tmp_path / artifacts["paper_plan_json"]).read_text(encoding="utf-8"))
    assert plan_json["review_llm_completed"] is True
    assert plan_json["review_boundary"]["status"] == "completed"
    assert plan_json["review_boundary"]["invocation_mode"] == "evidence"
    assert plan_json["review_boundary"]["evidence_ids"] == ["review:paper-plan"]
    assert plan_json["final_acceptance_boundary"]["status"] == "paper_plan_final_acceptance_incomplete"
    assert plan_json["final_acceptance_boundary"]["final_plan_accepted"] is False
    assert "verified downstream compile/PDF handoff is missing" in plan_json["final_acceptance_boundary"]["blocking_reasons"]
    proof = json.loads((tmp_path / artifacts["review_model_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "paper-plan"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    expected_ref = Path(action["evidence_path"]).relative_to(tmp_path).as_posix()
    assert expected_ref in [str(ref).replace("\\", "/") for ref in proof_entry["evidence_refs"]]
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "paper-plan"
    assert source_proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert any(ref.endswith("discovery.json") for ref in source_proof_entry["evidence_refs"])
    assert "https://arxiv.org/abs/2601.00001" in source_proof_entry["evidence_refs"]


def test_autosci_skill_shim_paper_plan_rejects_weak_review_llm_boundary(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "lit-weak-review-boundary",
                "status": "completed",
                "outputs": {
                    "query": "skill generation",
                    "candidates": [
                        {
                            "candidate_id": "arxiv:2601.00002",
                            "title": "Skill Learning for Agents",
                            "arxiv_id": "2601.00002",
                            "source_ref": "https://arxiv.org/abs/2601.00002",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    weak_review = tmp_path / "weak-review-llm.json"
    weak_review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "weak-review-paper-plan",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "score": 0.91,
                        "recommendation": "accept",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$paper-plan",
        "idea-skillgen",
        "--title",
        "SkillGen Weak Review Plan",
        "--discovery-evidence",
        str(discovery),
        "--review-llm-evidence",
        str(weak_review),
        "--run-id",
        "shim-paper-plan-weak-review-boundary",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(Path(json.loads(proc.stdout)["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    plan_json = json.loads((tmp_path / artifacts["paper_plan_json"]).read_text(encoding="utf-8"))
    assert plan_json["review_llm_completed"] is False
    assert plan_json["review_boundary"]["status"] == "invalid"
    assert plan_json["review_boundary"]["completed"] is False
    assert any("review_available is not true" in reason for reason in plan_json["review_boundary"]["invalid_reasons"])
    assert plan_json["final_acceptance_boundary"]["status"] == "paper_plan_final_acceptance_incomplete"
    assert "completed Review LLM boundary evidence is missing" in plan_json["final_acceptance_boundary"]["blocking_reasons"]


def test_autosci_skill_shim_paper_plan_attaches_verified_compile_handoff(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    for name in ("ideas", "experiments", "methods", "concepts", "topics", "papers", "graph", "outputs"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "ideas/skillgen.md").write_text(
        "---\nstatus: validated\nnovelty_score: 4\nlinked_experiments: [exp-skillgen]\n---\n"
        "# SkillGen\n\n## Approach sketch\n\nUse [[verifier-gated-skill-selection]] to validate generated skills.\n",
        encoding="utf-8",
    )
    (wiki_root / "experiments/exp-skillgen.md").write_text(
        "---\nstatus: succeeded\nkey_result: validated generated skill claims\n---\n"
        "# SkillGen Experiment\n\nThe experiment succeeded with validated evidence.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/verifier-gated-skill-selection.md").write_text(
        "# Verifier-Gated Skill Selection\n\nA method page for the paper plan evidence map.\n",
        encoding="utf-8",
    )
    discovery = tmp_path / "discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "lit-skillgen-plan-compile",
                "status": "completed",
                "outputs": {
                    "query": "skill generation",
                    "candidates": [
                        {
                            "candidate_id": "arxiv:2601.00001",
                            "title": "SkillGen: Generating Skills for Agents",
                            "arxiv_id": "2601.00001",
                            "source_ref": "https://arxiv.org/abs/2601.00001",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review-llm.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-paper-plan-compile",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_available": True,
                        "review_mode": "review_llm",
                        "recommendation": "accept",
                        "evidence_ids": ["review:paper-plan-compile"],
                        "review_llm": {"status": "completed"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    compiled_dir = tmp_path / "compiled-plan"
    compiled_dir.mkdir()
    pdf = compiled_dir / "main.pdf"
    write_structural_pdf(pdf)
    before = tmp_path / "paper-plan-before.json"
    allowlist = tmp_path / "paper-plan-allowlist.json"
    runtime = tmp_path / "paper-plan-compile-runtime.json"
    before.write_text(json.dumps({"plan": "before"}), encoding="utf-8")
    allowlist.write_text(json.dumps({"approved": True, "scope": "paper-plan-compile-handoff"}), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "paper-plan-compile-runtime",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "compile_paper",
                        "status": "completed",
                        "approval_ref": "approval-paper-plan-compile",
                        "exit_code": 0,
                        "pdf_generated": True,
                        "pdf_path": str(pdf),
                        "evidence_ids": ["runtime:paper-plan-compile"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$paper-plan",
        "skillgen",
        "--title",
        "SkillGen Plan",
        "--wiki-root",
        str(wiki_root),
        "--discovery-evidence",
        str(discovery),
        "--review-llm-evidence",
        str(review),
        "--approval-ref",
        "approval-paper-plan-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--runtime-evidence",
        str(runtime),
        "--after-artifact",
        str(pdf),
        "--run-id",
        "shim-paper-plan-compile-handoff",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-plan"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    report = evidence["outputs"]["report_plan"]
    assert any(section["section_id"] == "compile-audit" for section in report["sections"])
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert {
        "paper_draft_compile_handoff_json",
        "paper_compile_runtime_evidence_json",
        "compiled_pdf",
        "paper_plan_final_acceptance_boundary_json",
    } <= set(artifacts)
    plan_json = json.loads((tmp_path / artifacts["paper_plan_json"]).read_text(encoding="utf-8"))
    assert plan_json["compile_handoff"]["status"] == "completed"
    assert plan_json["compile_handoff"]["verified"] is True
    assert plan_json["idea_graph_map"]["idea_graph_ready"] is True
    assert "runtime:paper-plan-compile" in plan_json["compile_handoff"]["evidence_ids"]
    assert plan_json["final_acceptance_boundary"]["status"] == "final_plan_accepted"
    assert plan_json["final_acceptance_boundary"]["final_plan_accepted"] is True
    assert plan_json["final_acceptance_boundary"]["draft_compile_ready"] is True
    boundary = json.loads((tmp_path / artifacts["paper_plan_final_acceptance_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "final_plan_accepted"


def test_autosci_skill_shim_paper_draft_writes_latex_source(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$paper-draft",
        "idea-001",
        "--venue",
        "ICLR",
        "--title",
        "Skill Generation for Inference-Time Agents",
        "--run-id",
        "shim-paper-draft-native",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-draft"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1
    assert summary["passed_count"] == 0
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == "idea-001"
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "write_report"
    assert action["schema"] == "scientific_report.v1"
    assert action["gate_status"] == "schema_only"
    report_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert report_evidence["status"] == "inconclusive"
    assert report_evidence["outputs"]["report"]["title"] == "Skill Generation for Inference-Time Agents"
    artifacts = {artifact["type"]: artifact["path"] for artifact in report_evidence["artifacts"]}
    assert {
        "latex_source",
        "paper_math_commands_tex",
        "paper_sections_directory",
        "paper_figures_directory",
        "paper_tables_directory",
        "markdown_report",
        "report_plan_json",
        "citation_map_json",
        "paper_draft_section_evidence_map_json",
        "paper_draft_final_manuscript_boundary_json",
    }.issubset(artifacts)
    boundary = json.loads((tmp_path / artifacts["paper_draft_final_manuscript_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "paper_draft_final_manuscript_incomplete"
    assert boundary["final_manuscript_ready"] is False
    assert boundary["publication_ready_claim_allowed"] is False
    assert "completed Review LLM boundary evidence is missing" in boundary["blocking_reasons"]
    assert "verified compile/PDF handoff is missing" in boundary["blocking_reasons"]

    paper_dir = tmp_path / "artifacts/autosci/runs/shim-paper-draft-native/paper"
    main_tex = paper_dir / "main.tex"
    assert main_tex.exists()
    main_text = main_tex.read_text(encoding="utf-8")
    assert "\\documentclass{article}" in main_text
    assert "\\input{math_commands}" in main_text
    assert (paper_dir / "math_commands.tex").exists()
    assert (paper_dir / "sections").is_dir()
    assert (paper_dir / "sections/introduction.tex").exists()
    assert (paper_dir / "sections/related-work.tex").exists()
    assert (paper_dir / "sections/method.tex").exists()
    assert (paper_dir / "sections/experiments.tex").exists()
    assert (paper_dir / "sections/conclusion.tex").exists()
    assert (paper_dir / "figures").is_dir()
    assert (paper_dir / "tables").is_dir()
    section_map = json.loads((tmp_path / artifacts["paper_draft_section_evidence_map_json"]).read_text(encoding="utf-8"))
    assert section_map["schema"] == "autosci_paper_draft_section_evidence_map.v1"
    assert section_map["standard_section_count"] == 5
    assert {row["section_id"] for row in section_map["standard_sections"]} == {
        "introduction",
        "related_work",
        "method",
        "experiments",
        "conclusion",
    }
    bundle = json.loads((tmp_path / "artifacts/autosci/runs/shim-paper-draft-native/publication_bundle.json").read_text(encoding="utf-8"))
    bundle_file_types = {item["type"] for item in bundle["outputs"]["bundle"]["files"]}
    assert "latex_source" in bundle_file_types
    assert "paper_math_commands_tex" in bundle_file_types
    assert "paper_figures_directory" in bundle_file_types
    assert "paper_tables_directory" in bundle_file_types
    assert "paper_draft_section_evidence_map_json" in bundle_file_types
    assert "paper_draft_final_manuscript_boundary_json" in bundle_file_types


def test_autosci_skill_shim_paper_draft_includes_verified_compile_pdf_handoff(tmp_path: Path) -> None:
    discovery = tmp_path / "paper-draft-discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "lit-paper-draft",
                "status": "completed",
                "outputs": {
                    "query": "skill generation",
                    "candidates": [
                        {
                            "candidate_id": "arxiv:2601.00003",
                            "title": "SkillGen Draft Evidence",
                            "arxiv_id": "2601.00003",
                            "source_ref": "https://arxiv.org/abs/2601.00003",
                            "source_channels": ["search_s2"],
                            "bibtex": "@article{skillgen2026, title={SkillGen Draft Evidence}, year={2026}}",
                            "bibtex_verified": True,
                            "bibtex_provenance": "semantic_scholar:arxiv:2601.00003",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "paper-draft-review-llm.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-paper-draft",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_available": True,
                        "review_mode": "review_llm",
                        "recommendation": "accept",
                        "evidence_ids": ["review:paper-draft"],
                        "review_llm": {"status": "completed"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    pdf = compiled_dir / "main.pdf"
    write_structural_pdf(pdf)
    before = tmp_path / "paper-draft-before.json"
    allowlist = tmp_path / "paper-draft-allowlist.json"
    runtime = tmp_path / "paper-draft-compile-runtime.json"
    before.write_text(json.dumps({"draft": "before"}), encoding="utf-8")
    allowlist.write_text(json.dumps({"approved": True, "scope": "paper-draft-compile-handoff"}), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "paper-draft-compile-runtime",
                "status": "completed",
                "outputs": {
                    "runtime": {
                        "action": "compile_paper",
                        "status": "completed",
                        "approval_ref": "approval-paper-draft-compile",
                        "exit_code": 0,
                        "command_run": "pdflatex main.tex",
                        "pdf_generated": True,
                        "pdf_path": str(pdf),
                        "evidence_ids": ["runtime:paper-draft-compile"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$paper-draft",
        "idea-001",
        "--title",
        "Skill Generation for Inference-Time Agents",
        "--discovery-evidence",
        str(discovery),
        "--review-llm-evidence",
        str(review),
        "--approval-ref",
        "approval-paper-draft-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--runtime-evidence",
        str(runtime),
        "--after-artifact",
        str(pdf),
        "--run-id",
        "shim-paper-draft-compile-handoff",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-draft"
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    projection_proof_artifact = next(
        artifact
        for artifact in payload["artifacts"]
        if artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
    )
    projection_proof = json.loads((tmp_path / projection_proof_artifact["path"]).read_text(encoding="utf-8"))
    projection_proof_entry = projection_proof["proofs"][0]
    assert projection_proof_entry["native_skill"] == "paper-draft"
    assert projection_proof_entry["categories"] == ["wiki_mutation_evidence"]
    assert projection_proof_entry["collection_mode"] == "manual_review"
    assert any("artifacts/autosci/workspace/wiki/outputs/" in ref for ref in projection_proof_entry["evidence_refs"])
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "write_report"
    assert action["gate_status"] == "passed"

    report_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert report_evidence["status"] == "completed"
    report = report_evidence["outputs"]["report"]
    assert report["compile_handoff"]["status"] == "completed"
    assert report["compile_handoff"]["verified"] is True
    assert "runtime:paper-draft-compile" in report["compile_handoff"]["evidence_ids"]
    assert any(section["section_id"] == "compiled-paper" for section in report["sections"])
    assert any(section["section_id"] == "final-manuscript-boundary" for section in report["sections"])
    artifacts = {artifact["type"]: artifact["path"] for artifact in report_evidence["artifacts"]}
    assert {
        "paper_draft_compile_handoff_json",
        "paper_compile_runtime_evidence_json",
        "compiled_pdf",
        "citation_map_json",
        "paper_draft_final_manuscript_boundary_json",
        "review_model_runtime_proof_manifest_json",
        "provider_source_runtime_proof_manifest_json",
        "paper_references_bib",
        "paper_draft_bibtex_coverage_json",
        "paper_draft_section_evidence_map_json",
    } <= set(artifacts)
    references_bib = (tmp_path / artifacts["paper_references_bib"]).read_text(encoding="utf-8")
    assert "[UNCONFIRMED]" not in references_bib
    bibtex_coverage = json.loads((tmp_path / artifacts["paper_draft_bibtex_coverage_json"]).read_text(encoding="utf-8"))
    assert bibtex_coverage["entry_count"] == 1
    assert bibtex_coverage["verified_count"] == 1
    assert bibtex_coverage["unconfirmed_count"] == 0
    assert bibtex_coverage["references_bib_path"] == artifacts["paper_references_bib"]
    section_map = json.loads((tmp_path / artifacts["paper_draft_section_evidence_map_json"]).read_text(encoding="utf-8"))
    assert section_map["citation_count"] == 1
    assert section_map["standard_section_count"] == 5
    assert "arxiv:2601.00003" in section_map["citation_ids"]
    boundary = json.loads((tmp_path / artifacts["paper_draft_final_manuscript_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "final_manuscript_ready"
    assert boundary["final_manuscript_ready"] is True
    assert boundary["publication_ready_claim_allowed"] is True
    assert boundary["citation_count"] == 1
    assert boundary["verified_bibtex_count"] == 1
    assert boundary["unconfirmed_bibtex_count"] == 0
    assert boundary["review_llm_completed"] is True
    assert boundary["compile_handoff_verified"] is True
    proof = json.loads((tmp_path / artifacts["review_model_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "paper-draft"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    expected_ref = Path(action["evidence_path"]).relative_to(tmp_path).as_posix()
    assert expected_ref in [str(ref).replace("\\", "/") for ref in proof_entry["evidence_refs"]]
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "paper-draft"
    assert source_proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert any(ref.endswith("paper-draft-discovery.json") for ref in source_proof_entry["evidence_refs"])
    assert "https://arxiv.org/abs/2601.00003" in source_proof_entry["evidence_refs"]

    bundle = json.loads(
        (tmp_path / "artifacts/autosci/runs/shim-paper-draft-compile-handoff/publication_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    bundle_file_types = {item["type"] for item in bundle["outputs"]["bundle"]["files"]}
    assert {"compiled_pdf", "paper_draft_compile_handoff_json", "paper_compile_runtime_evidence_json"} <= bundle_file_types
    assert {
        "citation_map_json",
        "paper_draft_final_manuscript_boundary_json",
        "paper_references_bib",
        "paper_draft_section_evidence_map_json",
    } <= bundle_file_types


def test_paper_draft_final_boundary_rejects_unverified_bibtex() -> None:
    sys.path.insert(0, str(SHIM.parent))
    bridge = __import__("autosci_bridge")
    boundary = bridge._paper_draft_final_manuscript_boundary(
        {
            "citations": [
                {
                    "citation_id": "arxiv:2601.00003",
                    "title": "Unverified Reference",
                    "bibtex": "@article{unverified, title={Unverified Reference}}",
                    "bibtex_verified": False,
                }
            ]
        },
        {"completed": True, "status": "completed", "evidence_ids": ["review:paper"]},
        {"verified": True, "status": "completed", "pdf_paths": ["paper.pdf"]},
        has_source_evidence=True,
    )
    assert boundary["status"] == "paper_draft_final_manuscript_incomplete"
    assert boundary["publication_ready_claim_allowed"] is False
    assert boundary["verified_bibtex_count"] == 0
    assert "one or more citations lack explicitly verified BibTeX evidence" in boundary["blocking_reasons"]


def test_autosci_skill_shim_runs_paper_compile_fix_diagnostics(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    paper_dir.joinpath("main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nSkillGen draft.\n\\end{document}\n",
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--fix",
        "--run-id",
        "shim-paper-compile-fix",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-compile"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == str(paper_dir)
    assert payload["inputs"]["native_options"]["fix"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "compile_paper"
    bundle = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert bundle["schema"] == "publication_bundle.v1"
    assert bundle["status"] == "inconclusive"
    assert any(artifact["type"] == "paper_compile_checklist_json" for artifact in bundle["artifacts"])
    assert any(artifact["type"] == "paper_compile_diagnostics_markdown" for artifact in bundle["artifacts"])


def test_autosci_skill_shim_paper_compile_fix_applies_approved_after_artifact(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    tex = paper_dir / "main.tex"
    tex.write_text(
        "\\documentclass{article}\n\\begin{document}\nBroken draft\n\\end{document}\n",
        encoding="utf-8",
    )
    fixed = tmp_path / "main-fixed.tex"
    fixed.write_text(
        "\\documentclass{article}\n\\begin{document}\nApproved fixed draft.\n\\end{document}\n",
        encoding="utf-8",
    )
    before = tmp_path / "main-before.tex"
    before.write_text(tex.read_text(encoding="utf-8"), encoding="utf-8")
    allowlist = tmp_path / "compile-allowlist.json"
    allowlist.write_text('{"allowed": ["source_auto_fix"]}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--fix",
        "--approval-ref",
        "approval-compile-fix",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(fixed),
        "--execute-approved",
        "--run-id",
        "shim-paper-compile-approved-fix",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    bundle = evidence["outputs"]["bundle"]
    assert tex.read_text(encoding="utf-8") == fixed.read_text(encoding="utf-8")
    assert any(artifact["type"] == "paper_compile_fix_writeback_json" for artifact in bundle["files"])
    fix_artifact = next(artifact for artifact in bundle["files"] if artifact["type"] == "paper_compile_fix_writeback_json")
    fix_evidence = json.loads((tmp_path / fix_artifact["path"]).read_text(encoding="utf-8"))
    assert fix_evidence["status"] == "completed"
    checklist_artifact = next(artifact for artifact in bundle["files"] if artifact["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["fix_writeback"]["applied"] is True


def test_autosci_skill_shim_runs_survey_rebuttal_and_poster_native_sidecars(tmp_path: Path) -> None:
    cases = [
        ("$survey", "topic:skillgen", "write_survey", "scientific_report.v1", "partial"),
        ("$rebuttal", "review-comments", "draft_rebuttal", "publication_bundle.v1", "partial"),
        ("$poster", "report-001", "build_poster", "publication_bundle.v1", "gated"),
    ]
    for command, target, expected_action, expected_schema, expected_status in cases:
        run_id = f"shim-{expected_action}"
        proc = run_shim(
            tmp_path,
            command,
            target,
            "--title",
            f"SkillGen {expected_action}",
            "--run-id",
            run_id,
        )
        assert proc.returncode == 0, proc.stderr
        summary = json.loads(proc.stdout)
        assert summary["execution_status"] == expected_status
        assert summary["action_count"] == 1
        assert summary["schema_only_count"] == 1
        payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
        action = payload["outputs"]["skill_run"]["actions"][0]
        assert action["action"] == expected_action
        assert action["schema"] == expected_schema
        evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
        assert evidence["status"] == "inconclusive"
        if expected_schema == "scientific_report.v1":
            assert evidence["outputs"]["report"]["title"] == f"SkillGen {expected_action}"
            assert any(artifact["type"] == "survey_markdown" for artifact in evidence["artifacts"])
            artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
            boundary = json.loads((tmp_path / artifacts["survey_final_coverage_boundary_json"]).read_text(encoding="utf-8"))
            assert boundary["schema"] == "autosci_survey_final_coverage_boundary.v1"
            assert boundary["final_coverage_ready"] is False
            assert boundary["status"] == "survey_coverage_incomplete"
        else:
            files = evidence["outputs"]["bundle"]["files"]
            assert files
            assert all((tmp_path / item["path"]).exists() for item in files)
            if expected_action == "build_poster":
                assert not any(item["type"] == "poster_html" for item in files)
                validation = json.loads(
                    (
                        tmp_path
                        / next(item for item in files if item["type"] == "poster_validation_json")["path"]
                    ).read_text(encoding="utf-8")
                )
                assert validation["content_pipeline_status"] == "paper_source_missing"


def test_autosci_skill_shim_survey_completes_with_citation_evidence(tmp_path: Path) -> None:
    discovery = tmp_path / "survey-discovery.json"
    discovery.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "lit-survey-skillgen",
                "status": "completed",
                "outputs": {
                    "query": "skill generation",
                    "candidates": [
                        {
                            "candidate_id": "arxiv:2601.00002",
                            "title": "Survey Evidence for Skill Generation",
                            "arxiv_id": "2601.00002",
                            "source_ref": "https://arxiv.org/abs/2601.00002",
                            "source_channels": ["references"],
                        },
                        {
                            "candidate_id": "arxiv:2601.00003",
                            "title": "Extra Survey Evidence",
                            "arxiv_id": "2601.00003",
                            "source_ref": "https://arxiv.org/abs/2601.00003",
                            "source_channels": ["references"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$survey",
        "topic:skillgen",
        "--title",
        "SkillGen Survey",
        "--discovery-evidence",
        str(discovery),
        "--format",
        "latex",
        "--max-papers",
        "1",
        "--run-id",
        "shim-survey-citation-map",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "survey"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    report = evidence["outputs"]["report"]
    prior_work = next(section for section in report["sections"] if section["section_id"] == "prior-work-map")
    assert "Survey Evidence for Skill Generation" in prior_work["body"]
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    citation_map = json.loads((tmp_path / artifacts["citation_map_json"]).read_text(encoding="utf-8"))
    assert citation_map["citation_count"] == 1
    assert citation_map["citations"][0]["title"] == "Survey Evidence for Skill Generation"
    boundary = json.loads((tmp_path / artifacts["survey_final_coverage_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["final_coverage_ready"] is True
    assert boundary["status"] == "final_coverage_ready"
    assert boundary["coverage_scope"] == "bounded_source_backed"
    assert boundary["exhaustive_coverage_verified"] is False
    plan = json.loads((tmp_path / artifacts["survey_plan_json"]).read_text(encoding="utf-8"))
    assert plan["final_coverage_boundary"] == boundary
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "survey"
    assert source_proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert source_proof_entry["collection_mode"] == "manual_review"
    assert any(ref.endswith("survey-discovery.json") for ref in source_proof_entry["evidence_refs"])
    assert "https://arxiv.org/abs/2601.00002" in source_proof_entry["evidence_refs"]
    bibtex = json.loads((tmp_path / artifacts["survey_bibtex_coverage_json"]).read_text(encoding="utf-8"))
    assert bibtex["entry_count"] == 1
    assert bibtex["unconfirmed_count"] == 1
    assert "[UNCONFIRMED]" in bibtex["entries"][0]["bibtex"]
    writeback = json.loads((tmp_path / artifacts["survey_archive_writeback_json"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "completed"
    assert writeback["outputs"]["write"]["applied"] is True
    assert writeback["outputs"]["write"]["edge_count"] == 1
    mutation_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert mutation_proof["proofs"][0]["categories"] == ["wiki_mutation_evidence"]
    archive_text = (tmp_path / writeback["outputs"]["write"]["target_path"]).read_text(encoding="utf-8")
    assert "Related Work: SkillGen Survey" in archive_text


def test_autosci_skill_shim_rebuttal_maps_review_llm_findings(tmp_path: Path) -> None:
    review = tmp_path / "rebuttal-review.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-rebuttal",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_available": True,
                        "review_mode": "review_llm",
                        "score": 0.64,
                        "recommendation": "revise",
                        "evidence_ids": ["review:rebuttal"],
                        "findings": [
                            {
                                "criterion": "evidence",
                                "issue": "Clarify which experiment supports the generated-skill claim.",
                                "suggestion": "Cite the runtime evidence and ablation table.",
                            }
                        ],
                        "review_llm": {"status": "completed"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$rebuttal",
        "review-comments",
        "--title",
        "SkillGen Rebuttal",
        "--review-llm-evidence",
        str(review),
        "--run-id",
        "shim-rebuttal-review-map",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "rebuttal"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    files = evidence["outputs"]["bundle"]["files"]
    map_file = next(item for item in files if item["type"] == "rebuttal_response_map_json")
    response_map = json.loads((tmp_path / map_file["path"]).read_text(encoding="utf-8"))
    assert response_map["mapped_concerns"]
    assert response_map["unmapped_concerns"] == []
    assert "generated-skill claim" in response_map["mapped_concerns"][0]["concern"]
    proof_file = next(item for item in files if item["type"] == "review_model_runtime_proof_manifest_json")
    proof = json.loads((tmp_path / proof_file["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "rebuttal"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert Path(action["evidence_path"]).relative_to(tmp_path).as_posix() in proof_entry["evidence_refs"]


def test_autosci_skill_shim_rebuttal_ingests_reviewer_thread_and_submission_audit(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for name in ("ideas", "experiments", "methods", "graph", "outputs"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "ideas/skillgen.md").write_text(
        "---\nstatus: validated\nlinked_experiments: [exp-skillgen]\n---\n"
        "# SkillGen Idea\n\nGenerated skill claims are validated by baseline ablation evidence.\n",
        encoding="utf-8",
    )
    (wiki_root / "experiments/exp-skillgen.md").write_text(
        "# SkillGen Experiment\n\nstatus: succeeded\nThe completed baseline ablation supports generated skill claims.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/verifier-gated-skill-selection.md").write_text(
        "# Verifier-Gated Skill Selection\n\n## Procedure\n\nThe verifier-gated skill selection method description is recorded here.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/edges.jsonl").write_text("", encoding="utf-8")

    reviewer_thread = tmp_path / "reviewer-thread.json"
    reviewer_thread.write_text(
        json.dumps(
            {
                "schema": "autosci_reviewer_thread.v1",
                "task_id": "review-thread-skillgen",
                "status": "completed",
                "outputs": {
                    "reviewer_thread": {
                        "reviewers": [
                            {
                                "reviewer": "Reviewer 1",
                                "concerns": [
                                    {
                                        "concern": "The generated skill claim needs baseline ablation evidence.",
                                        "type": "evidence",
                                        "severity": "major",
                                        "evidence_ids": ["review-comment:rv1-c1"],
                                    }
                                ],
                            },
                            {
                                "reviewer": "Reviewer 2",
                                "questions": [
                                    {
                                        "question": "The verifier-gated skill selection method description is unclear.",
                                        "type": "clarity",
                                        "severity": "minor",
                                        "evidence_ids": ["review-comment:rv2-c1"],
                                    }
                                ],
                            },
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    review_llm = tmp_path / "rebuttal-review-llm.json"
    review_llm.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-llm-rebuttal",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_available": True,
                        "review_mode": "review_llm",
                        "score": 0.84,
                        "recommendation": "accept_with_revisions",
                        "evidence_ids": ["review-llm:rebuttal-thread"],
                        "findings": [],
                        "review_llm": {
                            "status": "completed",
                            "invocation_mode": "command",
                            "evidence_ids": ["review-llm:rebuttal-thread"],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    submission_audit = tmp_path / "rebuttal-submission-audit.json"
    submission_audit.write_text(
        json.dumps(
            {
                "schema": "autosci_publication_submission_audit.v1",
                "status": "completed",
                "evidence_ids": ["submission-audit:rebuttal"],
                "outputs": {
                    "audit": {
                        "status": "completed",
                        "submission_ready": True,
                        "portal_submission_completed": False,
                        "checks": [
                            {"check": "coverage", "status": "ok"},
                            {"check": "word_limit", "status": "ok"},
                            {"check": "no_unconfirmed_claims", "status": "ok"},
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$rebuttal",
        "--title",
        "SkillGen Rebuttal",
        "--paper-slug",
        "skillgen",
        "--venue",
        "ICLR",
        "--format",
        "formal",
        "--wiki-root",
        str(wiki_root),
        "--reviewer-thread-evidence",
        str(reviewer_thread),
        "--review-llm-evidence",
        str(review_llm),
        "--submission-audit",
        str(submission_audit),
        "--stress-test",
        "--run-id",
        "shim-rebuttal-thread-audit",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "rebuttal"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["reviewer_thread_evidence"] == [str(reviewer_thread)]
    assert payload["inputs"]["native_options"]["paper_slug"] == "skillgen"
    assert payload["inputs"]["native_options"]["submission_audit"] == str(submission_audit)
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    assert evidence["inputs"]["reviewer_thread_evidence"] == [str(reviewer_thread)]
    assert evidence["inputs"]["paper_slug"] == "skillgen"
    assert evidence["inputs"]["submission_audit"] == str(submission_audit)
    files = evidence["outputs"]["bundle"]["files"]
    map_file = next(item for item in files if item["type"] == "rebuttal_response_map_json")
    formal_file = next(item for item in files if item["type"] == "rebuttal_formal_text")
    stress_file = next(item for item in files if item["type"] == "rebuttal_stress_test_boundary_json")
    submission_file = next(item for item in files if item["type"] == "rebuttal_submission_audit_boundary_json")

    response_map = json.loads((tmp_path / map_file["path"]).read_text(encoding="utf-8"))
    assert response_map["schema"] == "autosci_rebuttal_response_map.v1"
    assert response_map["reviewer_thread"]["status"] == "completed"
    assert response_map["reviewer_thread"]["concern_count"] == 2
    assert [item["concern_id"] for item in response_map["mapped_concerns"]] == ["Rv1-C1", "Rv2-C1"]
    assert response_map["coverage"]["wiki_mapped_count"] == 2
    assert response_map["stress_test_boundary"]["stress_test_ready"] is True
    assert response_map["submission_boundary"]["submission_audit_ready"] is True

    formal_text = (tmp_path / formal_file["path"]).read_text(encoding="utf-8")
    assert "[Rv1-C1]" in formal_text
    assert "Reviewer 2:" in formal_text
    stress = json.loads((tmp_path / stress_file["path"]).read_text(encoding="utf-8"))
    assert stress["status"] == "completed"
    assert stress["review_llm_completed"] is True
    submission = json.loads((tmp_path / submission_file["path"]).read_text(encoding="utf-8"))
    assert submission["status"] == "submission_audit_ready"
    assert submission["portal_submission_completed"] is False


def test_autosci_skill_shim_rebuttal_atomizes_comma_separated_review_files(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for name in ("ideas", "methods", "experiments", "graph", "outputs"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "ideas/skillgen.md").write_text(
        "---\nstatus: validated\nlinked_experiments: [exp-skillgen]\n---\n"
        "# SkillGen Idea\n\nGenerated skill claims have baseline ablation evidence.\n",
        encoding="utf-8",
    )
    (wiki_root / "experiments/exp-skillgen.md").write_text(
        "# SkillGen Experiment\n\nstatus: succeeded\nThe baseline ablation completed successfully.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/verifier-gated-skill-selection.md").write_text(
        "# Verifier-Gated Skill Selection\n\n## Procedure\n\nThe method procedure is explicit and source-backed.\n",
        encoding="utf-8",
    )
    review_1 = tmp_path / "reviewer-1.txt"
    review_2 = tmp_path / "reviewer-2.txt"
    review_1.write_text(
        "Reviewer 1:\n- The generated skill claim needs baseline ablation evidence.\n",
        encoding="utf-8",
    )
    review_2.write_text(
        "Reviewer 2:\n- The verifier-gated method procedure is unclear.\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$rebuttal",
        f"{review_1},{review_2}",
        "--title",
        "SkillGen Raw Rebuttal",
        "--wiki-root",
        str(wiki_root),
        "--no-stress-test",
        "--run-id",
        "shim-rebuttal-comma-review-files",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "rebuttal"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == f"{review_1},{review_2}"
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    files = evidence["outputs"]["bundle"]["files"]
    file_map = {item["type"]: item["path"] for item in files}
    response_map = json.loads((tmp_path / file_map["rebuttal_response_map_json"]).read_text(encoding="utf-8"))
    assert response_map["reviewer_thread"]["status"] == "completed"
    assert response_map["reviewer_thread"]["atomization_completed"] is True
    assert response_map["reviewer_thread"]["concern_count"] == 2
    assert response_map["reviewer_thread"]["raw_parser_used"] is True
    assert set(response_map["reviewer_thread"]["source_paths"]) == {
        str(review_1.relative_to(tmp_path)),
        str(review_2.relative_to(tmp_path)),
    }
    assert [item["concern_id"] for item in response_map["mapped_concerns"]] == ["Rv1-C1", "Rv2-C1"]
    assert response_map["coverage"]["wiki_mapped_count"] == 2
    formal_text = (tmp_path / file_map["rebuttal_formal_text"]).read_text(encoding="utf-8")
    assert "[Rv1-C1]" in formal_text
    assert "[Rv2-C1]" in formal_text


def test_autosci_skill_shim_accepts_survey_format_latex(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$survey",
        "topic:skillgen",
        "--format",
        "latex",
        "--run-id",
        "shim-survey-format-latex",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "survey"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["format"] == "latex"
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "write_survey"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    assert evidence["inputs"]["format"] == "latex"
    latex_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "survey_latex_source")
    assert latex_artifact["path"].endswith(".tex")
    latex_source = (tmp_path / latex_artifact["path"]).read_text(encoding="utf-8")
    assert "\\documentclass{article}" in latex_source
    assert "\\section{Prior Work Map}" in latex_source


def test_autosci_skill_shim_runs_wiki_and_control_proposal_actions(tmp_path: Path) -> None:
    cases = [
        ("$prefill", "foundation:skillgen", "prefill_foundations", "research_memory_update.v1", "gated"),
        ("$edit", "wiki/ideas/skillgen.md", "edit_wiki_plan", "research_memory_update.v1", "gated"),
        ("$setup", "autosci", "setup_status", "workflow_evolution.v1", "gated"),
        ("$reset", "autosci", "reset_plan", "workflow_evolution.v1", "gated"),
    ]
    for command, target, expected_action, expected_schema, expected_status in cases:
        run_id = f"shim-{expected_action}"
        proc = run_shim(
            tmp_path,
            command,
            target,
            "--run-id",
            run_id,
        )
        assert proc.returncode == 0, proc.stderr
        summary = json.loads(proc.stdout)
        assert summary["execution_status"] == expected_status
        assert summary["action_count"] == 1
        payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
        action = payload["outputs"]["skill_run"]["actions"][0]
        assert action["action"] == expected_action
        assert action["schema"] == expected_schema
        assert action["status"] == "passed"
        evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
        assert evidence["status"] == "completed"
        if expected_schema == "research_memory_update.v1":
            change = evidence["outputs"]["changes"][0]
            assert change["operation"] == "propose"
            assert change["evidence_ids"]
        else:
            evolution = evidence["outputs"]["evolution"]
            assert evolution["approval_state"] == "proposed"
            assert evolution["review"]["protected_core_edits_applied"] is False
            assert (tmp_path / evolution["recommended_changes_path"]).exists()
            assert (tmp_path / evolution["patch_candidates_path"]).is_dir()


def test_autosci_skill_shim_prefill_applies_approved_wiki_mutation(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "foundations").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    page = wiki_root / "foundations/foundation-skillgen.md"
    before = tmp_path / "prefill-before.md"
    before.write_text("# Before\n\nNo foundation page exists yet.\n", encoding="utf-8")
    runtime = tmp_path / "prefill-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:prefill-skillgen"]}\n', encoding="utf-8")
    allowlist = tmp_path / "prefill-allowlist.json"
    allowlist.write_text('{"allowed": ["prefill_foundations"]}\n', encoding="utf-8")
    proc = run_shim(
        tmp_path,
        "$prefill",
        "foundation:skillgen",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-prefill-skillgen",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(page),
        "--execute-approved",
        "--run-id",
        "shim-prefill-approved",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "prefill"
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    change = evidence["outputs"]["changes"][0]
    assert change["operation"] == "create"
    assert change["before_sha256"] != change["after_sha256"]
    assert page.exists()
    page_text = page.read_text(encoding="utf-8")
    assert "approval-prefill-skillgen" in page_text
    assert 'entity_type: "foundation"' in page_text
    assert 'source_url: ""' in page_text
    assert "key_papers" not in page_text
    assert "related_concepts" not in page_text
    assert (wiki_root / "log.md").exists()
    assert (wiki_root / "index.md").exists()
    assert (wiki_root / "graph/context_brief.md").exists()
    assert "foundation-skillgen" in (wiki_root / "index.md").read_text(encoding="utf-8")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "prefill_plan_json" in artifacts
    assert "approval_contract_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "provider_source_runtime_proof_manifest_json" not in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    plan = json.loads((tmp_path / artifacts["prefill_plan_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    side_effect_proof = json.loads((tmp_path / artifacts["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    wiki_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert contract["execution_verified"] is True
    assert plan["mode"] == "add"
    assert plan["selected_count"] == 1
    assert plan["dedup"][0]["exists"] is False
    assert approval_proof["proofs"][0]["native_skill"] == "prefill"
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]
    assert wiki_proof["proofs"][0]["categories"] == ["wiki_mutation_evidence"]


def test_autosci_skill_shim_prefill_parity_demo_auto_applies_local_writeback(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "foundations").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    page = wiki_root / "foundations/foundation-lora.md"

    proc = run_shim(
        tmp_path,
        "$prefill",
        "--add",
        "LoRA",
        "--wiki-root",
        str(wiki_root),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-prefill-policy-auto",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert page.exists()
    assert evidence["outputs"]["changes"][0]["operation"] == "create"
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:prefill_foundations:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "prefill_foundations_local_mutation_runtime_evidence_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:prefill_foundations:")


def test_autosci_skill_shim_prefill_add_mode_records_catalog_plan_without_mutation(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "foundations").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    proc = run_shim(
        tmp_path,
        "$prefill",
        "--add",
        "LoRA",
        "--topic",
        "NLP",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-prefill-add-plan",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    envelope = json.loads((tmp_path / "artifacts/autosci/runs/shim-prefill-add-plan/envelopes/prefill_foundations.json").read_text(encoding="utf-8"))
    assert envelope["inputs"]["add"] == "LoRA"
    assert envelope["inputs"]["domain"] == "NLP"
    assert envelope["inputs"]["prefill_mode"] == "add"

    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    change = evidence["outputs"]["changes"][0]
    assert change["operation"] == "propose"
    assert change["entity_id"] == "foundation-lora"
    assert not (wiki_root / "foundations/foundation-lora.md").exists()
    plan_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "prefill_plan_json")
    plan = json.loads((tmp_path / plan_artifact["path"]).read_text(encoding="utf-8"))
    assert plan["mode"] == "add"
    assert plan["domain"] == "NLP"
    assert plan["selected_count"] == 1
    assert plan["selected_seeds"][0]["foundation_id"] == "foundation-lora"
    assert plan["catalog"]["status"] == "completed"


def test_autosci_skill_shim_prefill_renders_supplied_source_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "foundations").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    page = wiki_root / "foundations/foundation-lora.md"
    before = tmp_path / "prefill-before.md"
    before.write_text("# Before\n\nNo LoRA foundation exists.\n", encoding="utf-8")
    runtime = tmp_path / "prefill-runtime.json"
    runtime.write_text('{"schema": "autosci_runtime_evidence.v1", "status": "completed"}\n', encoding="utf-8")
    allowlist = tmp_path / "prefill-allowlist.json"
    allowlist.write_text('{"allowed": ["prefill_foundations", "wiki_foundation_write"]}\n', encoding="utf-8")
    source = tmp_path / "lora-source.json"
    source.write_text(
        json.dumps(
            {
                "schema": "autosci_prefill_source_evidence.v1",
                "status": "completed",
                "outputs": {
                    "title": "LoRA",
                    "source_url": "https://en.wikipedia.org/wiki/Low-rank_adaptation",
                    "summary": "LoRA is a parameter-efficient adaptation method using low-rank update matrices.",
                    "sections": [
                        {"title": "Architecture", "content": "- Low-rank adapters are inserted into model layers."},
                        {"title": "Limitations", "content": "- Rank selection changes quality and memory tradeoffs."},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$prefill",
        "--add",
        "LoRA",
        "--topic",
        "NLP",
        "--wiki-root",
        str(wiki_root),
        "--source-evidence",
        str(source),
        "--approval-ref",
        "approval-prefill-lora-source",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(page),
        "--execute-approved",
        "--run-id",
        "shim-prefill-source-backed",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    plan = json.loads((tmp_path / artifacts["prefill_plan_json"]).read_text(encoding="utf-8"))
    page_text = page.read_text(encoding="utf-8")
    assert plan["source_evidence_count"] == 1
    assert plan["selected_seeds"][0]["source_status"] == "completed"
    assert 'source_url: "https://en.wikipedia.org/wiki/Low-rank_adaptation"' in page_text
    assert 'source_status: "source_backed"' in page_text
    assert "LoRA is a parameter-efficient adaptation method" in page_text
    assert "LoRA is a parameter-efficient adaptation method using low-rank update matrices. (LLM analysis)" not in page_text
    assert "- Low-rank adapters are inserted into model layers." in page_text
    assert "provider_source_runtime_proof_manifest_json" in artifacts


def test_autosci_skill_shim_prefill_online_fetch_disabled_records_fallback_boundary(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "foundations").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    proc = run_shim(
        tmp_path,
        "$prefill",
        "--add",
        "LoRA Disabled Fetch",
        "--topic",
        "NLP",
        "--wiki-root",
        str(wiki_root),
        "--online",
        "--run-id",
        "shim-prefill-online-disabled",
        extra_env={"AUTOSCI_WIKIPEDIA_FETCH_DISABLED": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    envelope = json.loads((tmp_path / "artifacts/autosci/runs/shim-prefill-online-disabled/envelopes/prefill_foundations.json").read_text(encoding="utf-8"))
    assert envelope["inputs"]["online"] is True

    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    plan = json.loads((tmp_path / artifacts["prefill_plan_json"]).read_text(encoding="utf-8"))
    assert plan["source_evidence_count"] == 0
    assert plan["fetch_attempts"][0]["title"] == "LoRA Disabled Fetch"
    assert plan["fetch_attempts"][0]["status"] == "fetch_disabled"
    assert plan["selected_seeds"][0]["source_status"] == "fallback_llm_analysis"
    assert plan["selected_seeds"][0]["source_evidence_path"] == ""
    sidecar = tmp_path / plan["fetch_attempts"][0]["path"]
    assert json.loads(sidecar.read_text(encoding="utf-8"))["status"] == "fetch_disabled"


@pytest.mark.parametrize(
    ("command", "expected_action", "native_skill"),
    [
        ("$setup", "setup_status", "setup"),
        ("$reset", "reset_plan", "reset"),
    ],
)
def test_autosci_skill_shim_control_routes_emit_approved_external_runtime_proofs(
    tmp_path: Path,
    command: str,
    expected_action: str,
    native_skill: str,
) -> None:
    allowlist = tmp_path / f"{native_skill}-allowlist.json"
    runtime = tmp_path / f"{native_skill}-runtime.json"
    before = tmp_path / f"{native_skill}-before.json"
    after = tmp_path / f"{native_skill}-after.json"
    allowlist.write_text(json.dumps({"allowed": [expected_action]}), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "status": "completed",
                "exit_code": 0,
                "evidence_ids": [f"runtime:{native_skill}:external-control"],
                "command": f"approved-{native_skill}-external-runtime",
            }
        ),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"state": "before"}), encoding="utf-8")
    after.write_text(json.dumps({"state": "after"}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        command,
        "autosci",
        "--approval-ref",
        f"approval-{native_skill}-external-runtime",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        f"shim-{native_skill}-external-runtime",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == native_skill
    assert summary["passed_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == expected_action
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evolution["approval_state"] == "proposed"
    assert evolution["review"]["external_control_runtime_verified"] is True
    assert evolution["review"]["protected_core_edits_applied"] is False
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "provider_source_runtime_proof_manifest_json" not in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" not in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    side_effect_proof = json.loads((tmp_path / artifacts["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert contract["execution_verified"] is True
    assert contract["semantic_runtime"]["verified"] is True
    assert approval_proof["proofs"][0]["native_skill"] == native_skill
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]


def test_autosci_skill_shim_reset_accepts_native_scope_and_keeps_dry_run_non_destructive(tmp_path: Path) -> None:
    wiki_root = tmp_path / "reset-project/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers/old.md").write_text("# Old Paper\n", encoding="utf-8")
    (wiki_root / "log.md").write_text("# Existing Log\n", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$reset",
        "autosci",
        "--scope",
        "wiki",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-reset-scope-dry-run",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["scope"] == "wiki"
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evolution["review"]["reset_scope"] == "wiki"
    assert evolution["review"]["reset_dry_run"]["status"] == "dry_run"
    assert evolution["review"]["protected_core_edits_applied"] is False
    assert (wiki_root / "papers/old.md").exists()
    assert (wiki_root / "log.md").read_text(encoding="utf-8") == "# Existing Log\n"
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "reset_plan_json" in artifacts
    plan = json.loads((tmp_path / artifacts["reset_plan_json"]).read_text(encoding="utf-8"))
    assert "papers/old.md" in "\n".join(plan["delete_files"])


def test_autosci_skill_shim_reset_executes_approved_local_scope_with_runtime_proofs(tmp_path: Path) -> None:
    project_root = tmp_path / "reset-project"
    wiki_root = project_root / "wiki"
    raw_root = project_root / "raw/papers"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    raw_root.mkdir(parents=True)
    (wiki_root / "papers/old.md").write_text("# Old Paper\n", encoding="utf-8")
    (wiki_root / "ideas/old.md").write_text("# Old Idea\n", encoding="utf-8")
    (wiki_root / "graph/context_brief.md").write_text("# Old Context\n", encoding="utf-8")
    (wiki_root / "log.md").write_text("# Old Log\n", encoding="utf-8")
    (raw_root / "source.txt").write_text("raw source remains for wiki-only reset\n", encoding="utf-8")
    allowlist = tmp_path / "reset-allowlist.json"
    before = tmp_path / "reset-before.json"
    allowlist.write_text(json.dumps({"allowed": ["reset_plan"], "scope": "wiki"}), encoding="utf-8")
    before.write_text(json.dumps({"wiki_root": str(wiki_root), "papers": 1, "ideas": 1}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$reset",
        "autosci",
        "--scope",
        "wiki",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-reset-local",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-reset-approved-local",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["passed_count"] == 1
    assert not (wiki_root / "papers/old.md").exists()
    assert not (wiki_root / "ideas/old.md").exists()
    assert not (wiki_root / "graph/context_brief.md").exists()
    assert (wiki_root / "papers/.gitkeep").exists()
    assert (raw_root / "source.txt").exists()
    assert "Applied approved reset scope" in (wiki_root / "log.md").read_text(encoding="utf-8")

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evolution["approval_state"] == "proposed"
    assert evolution["review"]["protected_core_edits_applied"] is False
    assert evolution["review"]["approval_contract_verified"] is True
    assert evolution["review"]["local_reset_execution"]["executed"] is True
    assert evolution["review"]["local_reset_execution"]["tool_status"] == "completed"
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "reset_runtime_evidence_json" in artifacts
    assert "reset_after_snapshot_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    runtime = json.loads((tmp_path / artifacts["reset_runtime_evidence_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    wiki_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert contract["execution_verified"] is True
    assert runtime["status"] == "completed"
    assert runtime["outputs"]["runtime"]["scopes"] == ["wiki"]
    assert approval_proof["proofs"][0]["native_skill"] == "reset"
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert wiki_proof["proofs"][0]["categories"] == ["wiki_mutation_evidence"]


def test_autosci_skill_shim_reset_autosci_native_auto_executes_scoped_reset(tmp_path: Path) -> None:
    project_root = tmp_path / "reset-native-project"
    wiki_root = project_root / "wiki"
    raw_root = project_root / "raw/papers"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    raw_root.mkdir(parents=True)
    (wiki_root / "papers/old.md").write_text("# Old Paper\n", encoding="utf-8")
    (wiki_root / "graph/context_brief.md").write_text("# Old Context\n", encoding="utf-8")
    (wiki_root / "log.md").write_text("# Old Log\n", encoding="utf-8")
    (raw_root / "source.txt").write_text("raw source remains for wiki-only reset\n", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$reset",
        "autosci",
        "--scope",
        "wiki",
        "--wiki-root",
        str(wiki_root),
        "--gate-mode",
        "autosci_native",
        "--run-id",
        "shim-reset-autosci-native-policy",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["passed_count"] == 1
    assert not (wiki_root / "papers/old.md").exists()
    assert not (wiki_root / "graph/context_brief.md").exists()
    assert (wiki_root / "papers/.gitkeep").exists()
    assert (raw_root / "source.txt").exists()
    assert "Applied approved reset scope" in (wiki_root / "log.md").read_text(encoding="utf-8")

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evolution["review"]["local_reset_execution"]["executed"] is True
    assert evolution["review"]["approval_contract_verified"] is True
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "autosci_native"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:autosci_native:reset_plan:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "reset_before_snapshot_json" in artifacts
    assert "reset_runtime_evidence_json" in artifacts
    assert "reset_after_snapshot_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:autosci_native:reset_plan:")
    before_refs = [
        str(item.get("artifact_path") or item.get("path") or "")
        for item in contract["before_artifacts"]
        if isinstance(item, dict)
    ]
    assert any(ref.endswith("reset_before_snapshot.json") for ref in before_refs)
    before_snapshot = json.loads((tmp_path / artifacts["reset_before_snapshot_json"]).read_text(encoding="utf-8"))
    assert before_snapshot["schema"] == "autosci_reset_before_snapshot.v1"
    assert before_snapshot["wiki_directories"]["papers"]["markdown_count"] == 1


def test_autosci_skill_shim_edit_applies_approved_after_artifact(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    target = wiki_root / "ideas/skillgen.md"
    target.write_text("# SkillGen\n\nOld content.\n", encoding="utf-8")
    after = tmp_path / "skillgen-after.md"
    after.write_text("# SkillGen\n\nApproved edited content.\n", encoding="utf-8")
    before = tmp_path / "skillgen-before.md"
    before.write_text("# SkillGen\n\nOld content.\n", encoding="utf-8")
    runtime = tmp_path / "edit-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:edit-skillgen"]}\n', encoding="utf-8")
    allowlist = tmp_path / "edit-allowlist.json"
    allowlist.write_text('{"allowed": ["edit_wiki_plan"]}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$edit",
        "wiki/ideas/skillgen.md",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-edit-skillgen",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-edit-approved",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "edit"
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    change = evidence["outputs"]["changes"][0]
    assert change["operation"] == "update"
    assert change["before_sha256"] != change["after_sha256"]
    assert target.read_text(encoding="utf-8") == after.read_text(encoding="utf-8")
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"wiki_page", "wiki_log", "wiki_rebuild"}.issubset(artifact_types)
    assert {
        "provider_source_runtime_proof_manifest_json",
        "approval_runtime_proof_manifest_json",
        "side_effect_runtime_proof_manifest_json",
        "wiki_mutation_runtime_proof_manifest_json",
    }.issubset(artifact_types)
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    side_effect_proof = json.loads((tmp_path / artifacts["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    wiki_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert source_proof["proofs"][0]["categories"] == ["provider_source_evidence"]
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]
    assert wiki_proof["proofs"][0]["categories"] == ["wiki_mutation_evidence"]


def test_autosci_skill_shim_edit_parity_demo_auto_applies_after_artifact(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    target = wiki_root / "ideas/skillgen.md"
    target.write_text("# SkillGen\n\nOld content.\n", encoding="utf-8")
    after = tmp_path / "skillgen-after.md"
    after.write_text("# SkillGen\n\nPolicy-approved edited content.\n", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$edit",
        "wiki/ideas/skillgen.md",
        "--wiki-root",
        str(wiki_root),
        "--after-artifact",
        str(after),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-edit-policy-auto",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert target.read_text(encoding="utf-8") == after.read_text(encoding="utf-8")
    assert evidence["outputs"]["changes"][0]["operation"] == "update"
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:edit_wiki_plan:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "edit_wiki_plan_local_mutation_runtime_evidence_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True


def test_autosci_skill_shim_edit_applies_approved_raw_add(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    raw_root = tmp_path / "artifacts/autosci/workspace/raw"
    (wiki_root / "graph").mkdir(parents=True)
    before = tmp_path / "raw-before.md"
    before.write_text("# Before\n\nraw/papers/new-source.md does not exist yet.\n", encoding="utf-8")
    after = tmp_path / "raw-after.md"
    after.write_text("# New Raw Source\n\nApproved raw content.\n", encoding="utf-8")
    runtime = tmp_path / "edit-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:edit-raw-add"]}\n', encoding="utf-8")
    allowlist = tmp_path / "edit-allowlist.json"
    allowlist.write_text('{"allowed": ["edit_wiki_plan"]}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$edit",
        "raw/papers/new-source.md",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-edit-raw-add",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-edit-raw-add",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    raw_target = raw_root / "papers/new-source.md"
    assert raw_target.read_text(encoding="utf-8") == after.read_text(encoding="utf-8")
    change = evidence["outputs"]["changes"][0]
    assert change["entity_type"] == "raw_source"
    assert change["operation"] == "create"
    assert change["path"] == "raw/papers/new-source.md"
    assert change["before_sha256"] != change["after_sha256"]
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "raw_source" in artifacts
    assert "wiki_log" in artifacts
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert source_proof["proofs"][0]["categories"] == ["provider_source_evidence"]


def test_autosci_skill_shim_edit_blocks_existing_raw_add(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    raw_target = tmp_path / "artifacts/autosci/workspace/raw/papers/existing-source.md"
    raw_target.parent.mkdir(parents=True)
    raw_target.write_text("old raw content\n", encoding="utf-8")
    (wiki_root / "graph").mkdir(parents=True)
    after = tmp_path / "raw-after.md"
    after.write_text("new raw content\n", encoding="utf-8")
    runtime = tmp_path / "edit-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:edit-raw-block"]}\n', encoding="utf-8")
    allowlist = tmp_path / "edit-allowlist.json"
    allowlist.write_text('{"allowed": ["edit_wiki_plan"]}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$edit",
        "raw/papers/existing-source.md",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-edit-raw-block",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-edit-raw-block",
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert raw_target.read_text(encoding="utf-8") == "old raw content\n"
    change = evidence["outputs"]["changes"][0]
    assert change["operation"] == "blocked"
    assert "read-only" in change["summary"]


def test_autosci_skill_shim_edit_applies_approved_raw_delete(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    raw_target = tmp_path / "artifacts/autosci/workspace/raw/papers/delete-source.md"
    raw_target.parent.mkdir(parents=True)
    raw_target.write_text("delete raw content\n", encoding="utf-8")
    (wiki_root / "graph").mkdir(parents=True)
    before = tmp_path / "raw-before.md"
    before.write_text("delete raw content\n", encoding="utf-8")
    after = tmp_path / "raw-after.md"
    after.write_text("# After\n\nraw/papers/delete-source.md deleted by approved edit.\n", encoding="utf-8")
    runtime = tmp_path / "edit-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:edit-raw-delete"]}\n', encoding="utf-8")
    allowlist = tmp_path / "edit-allowlist.json"
    allowlist.write_text('{"allowed": ["edit_wiki_plan"]}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$edit",
        "raw/papers/delete-source.md",
        "--delete",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-edit-raw-delete",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-edit-raw-delete",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    envelope = json.loads((tmp_path / "artifacts/autosci/runs/shim-edit-raw-delete/envelopes/edit_wiki_plan.json").read_text(encoding="utf-8"))
    assert envelope["inputs"]["delete"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert not raw_target.exists()
    change = evidence["outputs"]["changes"][0]
    assert change["entity_type"] == "raw_source"
    assert change["operation"] == "delete"
    assert change["path"] == "raw/papers/delete-source.md"
    assert change["before_sha256"] != change["after_sha256"]
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts


def test_autosci_skill_shim_runs_ask_check_and_init_diagnostics(tmp_path: Path) -> None:
    cases = [
        ("$ask", "What supports SkillGen?", "ask_wiki", "research_memory_update.v1", "partial", "schema_only"),
        ("$check", "autosci wiki", "check_wiki_health", "workflow_evolution.v1", "partial", "passed"),
        ("$init", "agent skill learning", "init_sources", "literature_discovery.v1", "gated", "schema_only"),
    ]
    for command, target, expected_action, expected_schema, expected_status, expected_action_status in cases:
        run_id = f"shim-{expected_action}"
        proc = run_shim(
            tmp_path,
            command,
            target,
            "--run-id",
            run_id,
        )
        assert proc.returncode == 0, proc.stderr
        summary = json.loads(proc.stdout)
        assert summary["execution_status"] == expected_status
        assert summary["action_count"] == 1
        payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
        action = payload["outputs"]["skill_run"]["actions"][0]
        assert action["action"] == expected_action
        assert action["schema"] == expected_schema
        assert action["status"] == expected_action_status
        evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
        if expected_action == "ask_wiki":
            assert evidence["status"] == "inconclusive"
            assert evidence["outputs"]["changes"][0]["operation"] == "no_op"
            assert any(artifact["type"] == "ask_answer_markdown" for artifact in evidence["artifacts"])
        elif expected_action == "check_wiki_health":
            assert evidence["outputs"]["evolution"]["approval_state"] == "proposed"
            assert (tmp_path / evidence["outputs"]["evolution"]["recommended_changes_path"]).exists()
        elif expected_action == "init_sources":
            assert evidence["status"] == "inconclusive"
            assert evidence["outputs"]["mode"] == "init_native_local_plan"
            assert evidence["outputs"]["candidates"] == []
            artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
            assert "init_discovery_prepare_manifest_json" in artifact_types
            assert "init_discovery_plan_json" in artifact_types


def test_autosci_skill_shim_init_uses_verified_runtime_source_manifest(tmp_path: Path) -> None:
    allowlist = tmp_path / "allowlist.json"
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    runtime = tmp_path / "init-runtime.json"
    allowlist.write_text('{"allowed": ["discover"]}\n', encoding="utf-8")
    before.write_text('{"state": "before"}\n', encoding="utf-8")
    after.write_text('{"state": "after"}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "init-runtime-skillgen",
                "status": "completed",
                "exit_code": 0,
                "candidates": [
                        {
                            "title": "SkillGen Source Candidate",
                        "url": "https://arxiv.org/abs/2601.00003",
                            "abstract": "Runtime-discovered source candidate.",
                        },
                        {
                            "title": "SkillGen Source Candidate Two",
                            "url": "https://arxiv.org/abs/2601.00005",
                            "abstract": "Second runtime-discovered source candidate.",
                        },
                ],
                "evidence_ids": ["runtime:init-skillgen"],
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$init",
        "skill generation",
        "--approval-ref",
        "approval-init-runtime",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--runtime-evidence",
        str(runtime),
        "--run-id",
        "shim-init-runtime-manifest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "init"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    assert evidence["outputs"]["mode"] == "init_runtime_verified"
    assert evidence["outputs"]["candidates"][0]["title"] == "SkillGen Source Candidate"
    boundary = evidence["outputs"]["final_fan_in_boundary"]
    assert boundary["schema"] == "autosci_init_sources_final_fan_in_boundary.v1"
    assert boundary["status"] == "init_sources_provider_ready"
    assert boundary["stage_provider_ready"] is True
    assert boundary["final_fan_in_ready"] is False
    assert boundary["provider_boundary_completed"] is True
    assert boundary["fan_in_completed"] is False
    assert any(artifact["type"] == "init_sources_final_fan_in_boundary_json" for artifact in evidence["artifacts"])
    proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "init"
    assert proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "live_provider"
    assert any(ref.endswith("init-runtime.json") for ref in proof_entry["evidence_refs"])
    assert "https://arxiv.org/abs/2601.00003" in proof_entry["evidence_refs"]
    approval_proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "approval_runtime_proof_manifest_json"
    )
    approval_proof = json.loads((tmp_path / approval_proof_artifact["path"]).read_text(encoding="utf-8"))
    approval_entry = approval_proof["proofs"][0]
    assert approval_entry["native_skill"] == "init"
    assert approval_entry["categories"] == ["approval_boundary_evidence"]
    assert "side_effect_execution_evidence" not in approval_entry["categories"]
    contract_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "approval_contract_json")
    contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
    assert contract["semantic_runtime"]["verified"] is True


def test_autosci_skill_shim_init_write_fans_runtime_sources_into_wiki(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    allowlist = tmp_path / "allowlist.json"
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    runtime = tmp_path / "init-runtime.json"
    allowlist.write_text('{"allowed": ["discover", "wiki_fan_in"]}\n', encoding="utf-8")
    before.write_text('{"papers": []}\n', encoding="utf-8")
    after.write_text('{"papers": ["skillgen-source"]}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "init-runtime-skillgen",
                "status": "completed",
                "exit_code": 0,
                "candidates": [
                        {
                            "candidate_id": "skillgen-source",
                        "title": "SkillGen Source Candidate",
                        "url": "https://arxiv.org/abs/2601.00003",
                            "abstract": "Runtime-discovered source candidate.",
                        },
                        {
                            "candidate_id": "skillgen-source-two",
                            "title": "SkillGen Source Candidate Two",
                            "url": "https://arxiv.org/abs/2601.00005",
                            "abstract": "Second runtime-discovered source candidate.",
                        },
                ],
                "evidence_ids": ["runtime:init-skillgen"],
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$init",
        "skill generation",
        "--approval-ref",
        "approval-init-runtime",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--runtime-evidence",
        str(runtime),
        "--wiki-root",
        str(wiki_root),
        "--write",
        "--run-id",
        "shim-init-runtime-fan-in",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))

    fan_in = evidence["outputs"]["source_fan_in"]
    assert fan_in["status"] == "completed"
    assert fan_in["applied"] is True
    assert fan_in["written_count"] == 2
    fan_in_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "source_fan_in_writeback_json")
    fan_in_evidence = json.loads((tmp_path / fan_in_artifact["path"]).read_text(encoding="utf-8"))
    assert fan_in_evidence["status"] == "completed"
    wiki_proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
    )
    wiki_proof = json.loads((tmp_path / wiki_proof_artifact["path"]).read_text(encoding="utf-8"))
    wiki_proof_entry = wiki_proof["proofs"][0]
    assert wiki_proof_entry["native_skill"] == "init"
    assert wiki_proof_entry["categories"] == ["wiki_mutation_evidence"]
    assert any(ref.endswith("source_fan_in_writeback.json") for ref in wiki_proof_entry["evidence_refs"])
    assert any(ref.endswith("wiki/graph/edges.jsonl") for ref in wiki_proof_entry["evidence_refs"])
    boundary = evidence["outputs"]["final_fan_in_boundary"]
    assert boundary["status"] == "init_sources_final_fan_in_ready"
    assert boundary["stage_provider_ready"] is True
    assert boundary["final_fan_in_ready"] is True
    assert boundary["fan_in_completed"] is True
    assert boundary["graph_log_rebuild_ready"] is True
    assert boundary["written_count"] == 2
    assert any(
        artifact["type"] == "provider_source_runtime_proof_manifest_json"
        for artifact in evidence["artifacts"]
    )
    page = wiki_root / "papers/skillgen-source.md"
    assert page.exists()
    assert "SkillGen Source Candidate" in page.read_text(encoding="utf-8")
    assert "Source Candidate Fan-In" in (wiki_root / "log.md").read_text(encoding="utf-8")
    assert "source_candidate_ingested" in (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    assert (wiki_root / "index.md").exists()
    assert (wiki_root / "graph/context_brief.md").exists()


def test_autosci_skill_shim_init_parity_demo_auto_fans_runtime_sources_into_wiki(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    runtime = tmp_path / "init-parity-runtime.json"
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "init-parity-runtime-skillgen",
                "status": "completed",
                "exit_code": 0,
                "candidates": [
                        {
                            "candidate_id": "skillgen-parity-source",
                        "title": "SkillGen Parity Source Candidate",
                        "url": "https://arxiv.org/abs/2601.00004",
                            "abstract": "Runtime-discovered source candidate for parity fan-in.",
                        },
                        {
                            "candidate_id": "skillgen-parity-source-two",
                            "title": "SkillGen Parity Source Candidate Two",
                            "url": "https://arxiv.org/abs/2601.00005",
                            "abstract": "Second runtime-discovered source candidate for parity fan-in.",
                        },
                ],
                "evidence_ids": ["runtime:init-parity-skillgen"],
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$init",
        "skill generation",
        "--runtime-evidence",
        str(runtime),
        "--wiki-root",
        str(wiki_root),
        "--write",
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-init-parity-demo-source-fan-in",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))

    assert evidence["status"] == "completed"
    fan_in = evidence["outputs"]["source_fan_in"]
    assert fan_in["status"] == "completed"
    assert fan_in["applied"] is True
    assert fan_in["policy_auto_fan_in"] is True
    assert fan_in["source_runtime_verified_for_policy"] is True
    assert fan_in["written_count"] == 2
    boundary = evidence["outputs"]["final_fan_in_boundary"]
    assert boundary["status"] == "init_sources_final_fan_in_ready"
    assert boundary["final_fan_in_ready"] is True
    assert boundary["approval_contract_verified"] is True
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:init_sources:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "source_fan_in_writeback_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["semantic_runtime"]["verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:init_sources:")
    after_refs = [
        str(item.get("artifact_path") or item.get("path") or "")
        for item in contract["after_artifacts"]
        if isinstance(item, dict)
    ]
    assert any(ref.endswith("source_fan_in_writeback.json") for ref in after_refs)
    assert any(ref.endswith("wiki/graph/edges.jsonl") for ref in after_refs)

    fan_in_evidence = json.loads((tmp_path / artifacts["source_fan_in_writeback_json"]).read_text(encoding="utf-8"))
    assert fan_in_evidence["status"] == "completed"
    assert fan_in_evidence["outputs"]["write"]["policy_auto_fan_in"] is True
    page = wiki_root / "papers/skillgen-parity-source.md"
    assert page.exists()
    assert "SkillGen Parity Source Candidate" in page.read_text(encoding="utf-8")
    assert "Source Candidate Fan-In" in (wiki_root / "log.md").read_text(encoding="utf-8")
    assert "source_candidate_ingested" in (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    assert (wiki_root / "index.md").exists()
    assert (wiki_root / "graph/context_brief.md").exists()


def test_autosci_skill_shim_daily_arxiv_uses_verified_runtime_digest(tmp_path: Path) -> None:
    allowlist = tmp_path / "daily-allowlist.json"
    before = tmp_path / "daily-before.json"
    after = tmp_path / "daily-after.json"
    runtime = tmp_path / "daily-runtime.json"
    allowlist.write_text('{"allowed": ["daily-arxiv"]}\n', encoding="utf-8")
    before.write_text('{"digest": "before"}\n', encoding="utf-8")
    after.write_text('{"digest": "after"}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "daily-runtime-skillgen",
                "status": "completed",
                "exit_code": 0,
                "candidates": [
                        {
                            "title": "Daily SkillGen Paper",
                        "url": "https://arxiv.org/abs/2601.00004",
                            "abstract": "Daily arXiv source candidate.",
                        },
                        {
                            "title": "Daily SkillGen Paper Two",
                            "url": "https://arxiv.org/abs/2601.00005",
                            "abstract": "Second daily arXiv source candidate.",
                        },
                ],
                "evidence_ids": ["runtime:daily-skillgen"],
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$daily-arxiv",
        "skill generation",
        "--approval-ref",
        "approval-daily-runtime",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--runtime-evidence",
        str(runtime),
        "--mode",
        "inform",
        "--hours",
        "48",
        "--categories",
        "cs.AI",
        "cs.CL",
        "--max-recommendations",
        "7",
        "--max-auto-ingest",
        "2",
        "--send-email",
        "false",
        "--run-id",
        "shim-daily-runtime-digest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "daily-arxiv"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 1
    envelope = json.loads(
        (tmp_path / "artifacts/autosci/runs/shim-daily-runtime-digest/envelopes/daily_arxiv_prepare_finalize.json").read_text(
            encoding="utf-8"
        )
    )
    assert envelope["inputs"]["mode"] == "inform"
    assert envelope["inputs"]["hours"] == 48
    assert envelope["inputs"]["categories"] == ["cs.AI", "cs.CL"]
    assert envelope["inputs"]["max_recommendations"] == 7
    assert envelope["inputs"]["limit"] == 7
    assert envelope["inputs"]["max_auto_ingest"] == 2
    assert envelope["inputs"]["send_email"] == "false"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    native_options = payload["inputs"]["native_options"]
    assert native_options["daily_mode"] == "inform"
    assert native_options["daily_hours"] == 48
    assert native_options["daily_categories"] == ["cs.AI", "cs.CL"]
    assert native_options["daily_max_recommendations"] == 7
    assert native_options["daily_max_auto_ingest"] == 2
    assert native_options["daily_send_email"] == "false"
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    assert evidence["outputs"]["mode"] == "daily_arxiv_runtime_verified"
    assert evidence["outputs"]["candidates"][0]["title"] == "Daily SkillGen Paper"
    assert evidence["outputs"]["review_llm"]["status"] == "unavailable"
    assert evidence["outputs"]["review_llm_completed"] is False
    boundary = evidence["outputs"]["final_provider_delivery_boundary"]
    assert boundary["schema"] == "autosci_daily_arxiv_final_provider_delivery_boundary.v1"
    assert boundary["status"] == "daily_provider_ready"
    assert boundary["stage_provider_ready"] is True
    assert boundary["final_delivery_ready"] is False
    assert boundary["provider_boundary_completed"] is True
    assert boundary["ranking_ready"] is True
    assert boundary["fan_in_completed"] is False
    assert any(artifact["type"] == "daily_arxiv_final_provider_delivery_boundary_json" for artifact in evidence["artifacts"])
    assert not any(
        artifact["type"] == "side_effect_runtime_proof_manifest_json"
        for artifact in evidence["artifacts"]
    )
    assert not any(
        artifact["type"] == "review_model_runtime_proof_manifest_json"
        for artifact in evidence["artifacts"]
    )
    proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "daily-arxiv"
    assert proof_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "live_provider"
    assert any(ref.endswith("daily-runtime.json") for ref in proof_entry["evidence_refs"])
    assert "https://arxiv.org/abs/2601.00004" in proof_entry["evidence_refs"]
    approval_proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "approval_runtime_proof_manifest_json"
    )
    approval_proof = json.loads((tmp_path / approval_proof_artifact["path"]).read_text(encoding="utf-8"))
    approval_entry = approval_proof["proofs"][0]
    assert approval_entry["native_skill"] == "daily-arxiv"
    assert approval_entry["categories"] == ["approval_boundary_evidence"]
    assert "side_effect_execution_evidence" not in approval_entry["categories"]
    contract_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "approval_contract_json")
    contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
    assert contract["semantic_runtime"]["verified"] is True


def test_autosci_skill_shim_daily_arxiv_runs_native_local_feed_pipeline(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    (wiki_root / "papers").mkdir(parents=True)
    feed = tmp_path / "daily-feed.json"
    decisions = tmp_path / "daily-decisions.json"
    feed.write_text(
        json.dumps(
            [
                {
                    "arxiv_id": "2607.00001",
                    "title": "Native Local Daily AutoSci",
                    "abstract": "A local-feed paper for daily arXiv parity.",
                    "category": "cs.AI",
                    "published": "2026-07-03T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    decisions.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "arxiv_id": "2607.00001",
                        "decision": "strong_recommend",
                        "confidence": "high",
                        "score": 0.94,
                        "rationale": "Matches the local AutoSci parity test topic.",
                        "wiki_connections": ["autosci parity"],
                        "signals_used": ["arxiv", "local_decision"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$daily-arxiv",
        "autosci parity",
        "--feed",
        str(feed),
        "--decisions",
        str(decisions),
        "--wiki-root",
        str(wiki_root),
        "--no-external",
        "--run-id",
        "shim-daily-native-local",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    native_options = payload["inputs"]["native_options"]
    assert native_options["daily_feed"] == str(feed)
    assert native_options["daily_decisions"] == str(decisions)
    assert native_options["daily_no_external"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    assert evidence["outputs"]["mode"] == "daily_arxiv_native_local_finalized"
    assert evidence["outputs"]["candidates"][0]["title"] == "Native Local Daily AutoSci"
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "daily_arxiv_recommendation_context_json" in artifacts
    assert "daily_arxiv_digest_json" in artifacts
    assert "daily_arxiv_digest_markdown" in artifacts
    context = json.loads((tmp_path / artifacts["daily_arxiv_recommendation_context_json"]).read_text(encoding="utf-8"))
    digest = json.loads((tmp_path / artifacts["daily_arxiv_digest_json"]).read_text(encoding="utf-8"))
    assert context["counts"]["feed_total"] == 1
    assert context["notes"][-1] == "External enrichment skipped by command-line option."
    assert digest["llm_decision_available"] is True


def test_autosci_skill_shim_daily_arxiv_write_creates_ingest_handoff(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    allowlist = tmp_path / "daily-allowlist.json"
    before = tmp_path / "daily-before.json"
    after = tmp_path / "daily-after.json"
    runtime = tmp_path / "daily-runtime.json"
    review_llm = tmp_path / "daily-review-llm.json"
    allowlist.write_text('{"allowed": ["daily-arxiv", "auto_ingest"]}\n', encoding="utf-8")
    before.write_text('{"digest": "before"}\n', encoding="utf-8")
    after.write_text('{"digest": "after", "papers": ["daily-skillgen"]}\n', encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "daily-runtime-skillgen",
                "status": "completed",
                "exit_code": 0,
                "candidates": [
                        {
                            "candidate_id": "daily-skillgen",
                        "title": "Daily SkillGen Paper",
                        "url": "https://arxiv.org/abs/2601.00004",
                            "abstract": "Daily arXiv source candidate.",
                        },
                        {
                            "candidate_id": "daily-skillgen-two",
                            "title": "Daily SkillGen Paper Two",
                            "url": "https://arxiv.org/abs/2601.00005",
                            "abstract": "Second daily arXiv source candidate.",
                        },
                ],
                "evidence_ids": ["runtime:daily-skillgen"],
            }
        ),
        encoding="utf-8",
    )
    review_llm.write_text(
        json.dumps(
            {
                "schema": "autosci_artifact_review.v1",
                "task_id": "daily-review-skillgen",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "recommendation": "pass_with_caveats",
                        "score": 0.86,
                        "evidence_ids": ["review:daily-skillgen"],
                        "review_llm": {
                            "status": "completed",
                            "provider": "codex",
                            "model": "gpt-4.1-mini",
                            "evidence_ids": ["review:daily-skillgen"],
                        },
                    },
                    "findings": [{"severity": "minor", "summary": "Digest candidate is relevant."}],
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$daily-arxiv",
        "skill generation",
        "--approval-ref",
        "approval-daily-runtime",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--runtime-evidence",
        str(runtime),
        "--review-llm-evidence",
        str(review_llm),
        "--wiki-root",
        str(wiki_root),
        "--write",
        "--run-id",
        "shim-daily-runtime-auto-ingest",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))

    fan_in = evidence["outputs"]["source_fan_in"]
    assert fan_in["status"] == "ingest_handoff_ready"
    assert fan_in["handoff_ready"] is True
    assert fan_in["ingest_completed"] is False
    assert fan_in["applied"] is False
    assert fan_in["written_count"] == 0
    assert fan_in["ingest_commands"][0]["command"] == "/ingest https://arxiv.org/abs/2601.00004"
    assert any(artifact["type"] == "daily_arxiv_ingest_handoff_json" for artifact in evidence["artifacts"])
    assert not any(
        artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
        for artifact in evidence["artifacts"]
    )
    boundary = evidence["outputs"]["final_provider_delivery_boundary"]
    assert boundary["status"] == "daily_provider_ready"
    assert boundary["stage_provider_ready"] is True
    assert boundary["final_delivery_ready"] is False
    assert boundary["fan_in_completed"] is False
    assert boundary["provider_boundary_completed"] is True
    assert "arxiv" in boundary["source_channels"]
    assert evidence["outputs"]["review_llm"]["status"] == "completed"
    assert evidence["outputs"]["review_llm_completed"] is True
    assert evidence["outputs"]["review_evidence_ids"] == ["daily-review-skillgen", "review:daily-skillgen"]
    review_proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "review_model_runtime_proof_manifest_json"
    )
    review_proof = json.loads((tmp_path / review_proof_artifact["path"]).read_text(encoding="utf-8"))
    review_entry = review_proof["proofs"][0]
    assert review_entry["native_skill"] == "daily-arxiv"
    assert review_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert review_entry["collection_mode"] == "manual_review"
    assert any(ref.endswith("daily-review-llm.json") for ref in review_entry["evidence_refs"])
    assert not any(
        artifact["type"] == "side_effect_runtime_proof_manifest_json"
        for artifact in evidence["artifacts"]
    )
    page = wiki_root / "papers/daily-skillgen.md"
    assert not page.exists()
    assert not (wiki_root / "graph/edges.jsonl").exists()


@pytest.mark.parametrize(
    ("command", "expected_status", "protected"),
    [
        ("setup", "inconclusive", True),
        ("status", "completed", False),
        ("disable", "inconclusive", True),
    ],
)
def test_autosci_skill_shim_daily_arxiv_routes_management_subcommands(
    tmp_path: Path,
    command: str,
    expected_status: str,
    protected: bool,
) -> None:
    proc = run_shim(
        tmp_path,
        "$daily-arxiv",
        command,
        "--run-id",
        f"shim-daily-{command}",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "daily-arxiv"
    assert summary["execution_status"] == "gated"
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "daily_arxiv_prepare_finalize"
    assert action["schema"] == "workflow_evolution.v1"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == expected_status
    evolution = evidence["outputs"]["evolution"]
    assert evolution["scope"] == f"daily arXiv {command}"
    assert evolution["review"]["daily_command"] == command
    assert evolution["review"]["protected_core_edits_required"] is protected
    assert evolution["review"]["protected_core_edits_applied"] is False
    assert any("not as recommendation query text" in item for item in evidence["limitations"])


def test_autosci_skill_shim_ask_and_check_read_workspace_wiki(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen\nslug: skillgen\ntags: [skillgen]\nimportance: 3\n---\n"
        "# SkillGen\n\nSkillGen validates generated skills with evidence-linked regression tests.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/edges.jsonl").write_text(
        json.dumps(
            {
                "from": "paper:skillgen",
                "to": "concept:generated-skills",
                "type": "supports",
                "operation": "confirm",
                "evidence_ids": ["paper:skillgen"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    ask = run_shim(
        tmp_path,
        "$ask",
        "What evidence validates SkillGen skills?",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-ask-wiki-retrieval",
    )
    assert ask.returncode == 0, ask.stderr
    ask_summary = json.loads(ask.stdout)
    ask_payload = json.loads(Path(ask_summary["evidence_path"]).read_text(encoding="utf-8"))
    ask_action = ask_payload["outputs"]["skill_run"]["actions"][0]
    assert ask_action["status"] == "passed"
    ask_evidence = json.loads(Path(ask_action["evidence_path"]).read_text(encoding="utf-8"))
    assert ask_evidence["status"] == "completed"
    assert ask_evidence["outputs"]["changes"][0]["confidence"] == 0.75
    assert "Source-grounded extractive answer" in ask_evidence["outputs"]["changes"][0]["summary"]
    retrieval_artifact = next(item for item in ask_evidence["artifacts"] if item["type"] == "ask_retrieval_json")
    retrieval = json.loads((tmp_path / retrieval_artifact["path"]).read_text(encoding="utf-8"))
    assert retrieval["status"] == "completed"
    assert retrieval["answer_status"] == "completed"
    assert retrieval["hits"]
    boundary = retrieval["final_answer_boundary"]
    assert boundary["schema"] == "autosci_ask_final_answer_boundary.v1"
    assert boundary["final_answer_ready"] is False
    assert boundary["status"] == "ask_final_answer_incomplete"
    assert boundary["retrieval_source_count"] == 1
    assert boundary["model_status"] == "unavailable"
    assert retrieval["hits"][0]["path"].endswith("papers/skillgen.md")
    assert any(artifact["type"] == "ask_final_answer_boundary_json" for artifact in ask_evidence["artifacts"])
    source_proof_artifact = next(
        artifact
        for artifact in ask_evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    source_proof = json.loads((tmp_path / source_proof_artifact["path"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "ask"
    assert source_proof_entry["categories"] == ["provider_source_evidence"]
    assert source_proof_entry["collection_mode"] == "manual_review"
    assert any(ref.endswith("papers/skillgen.md") for ref in source_proof_entry["evidence_refs"])
    answer_artifact = next(item for item in ask_evidence["artifacts"] if item["type"] == "ask_answer_markdown")
    answer_text = (tmp_path / answer_artifact["path"]).read_text(encoding="utf-8")
    assert "SkillGen validates generated skills" in answer_text
    assert "papers/skillgen.md" in answer_text

    check = run_shim(
        tmp_path,
        "$check",
        "autosci wiki",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-check-wiki-health",
    )
    assert check.returncode == 0, check.stderr
    check_summary = json.loads(check.stdout)
    check_payload = json.loads(Path(check_summary["evidence_path"]).read_text(encoding="utf-8"))
    check_action = check_payload["outputs"]["skill_run"]["actions"][0]
    check_evidence = json.loads(Path(check_action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = check_evidence["outputs"]["evolution"]
    boundary = evolution["review"]["final_quality_boundary"]
    assert boundary["schema"] == "autosci_check_final_quality_boundary.v1"
    assert boundary["final_quality_ready"] is False
    assert boundary["local_structure_ready"] is True
    assert boundary["model_status"] == "unavailable"
    assert any(artifact["type"] == "check_final_quality_boundary_json" for artifact in check_evidence["artifacts"])
    markdown = (tmp_path / evolution["recommended_changes_path"]).read_text(encoding="utf-8")
    assert re.search(r"Markdown pages: `[1-9][0-9]*`", markdown)
    assert "Edge errors: `0`" in markdown


def test_autosci_skill_shim_ask_respects_native_format_modes(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen\nslug: skillgen\ntags: [skillgen]\nimportance: 3\n---\n"
        "# SkillGen\n\n"
        "SkillGen validates generated skills with evidence-linked regression tests in 2026.\n",
        encoding="utf-8",
    )

    table = run_shim(
        tmp_path,
        "$ask",
        "What evidence validates SkillGen skills?",
        "--wiki-root",
        str(wiki_root),
        "--format",
        "table",
        "--run-id",
        "shim-ask-format-table",
    )
    assert table.returncode == 0, table.stderr
    table_summary = json.loads(table.stdout)
    table_payload = json.loads(Path(table_summary["evidence_path"]).read_text(encoding="utf-8"))
    table_envelope = json.loads((tmp_path / "artifacts/autosci/runs/shim-ask-format-table/envelopes/ask_wiki.json").read_text(encoding="utf-8"))
    assert table_envelope["inputs"]["format"] == "table"
    assert table_envelope["inputs"]["native_options"]["format"] == "table"
    table_action = table_payload["outputs"]["skill_run"]["actions"][0]
    table_evidence = json.loads(Path(table_action["evidence_path"]).read_text(encoding="utf-8"))
    table_retrieval_artifact = next(item for item in table_evidence["artifacts"] if item["type"] == "ask_retrieval_json")
    table_retrieval = json.loads((tmp_path / table_retrieval_artifact["path"]).read_text(encoding="utf-8"))
    assert table_retrieval["requested_format"] == "table"
    table_answer_artifact = next(item for item in table_evidence["artifacts"] if item["type"] == "ask_answer_markdown")
    table_answer = (tmp_path / table_answer_artifact["path"]).read_text(encoding="utf-8")
    assert "## Answer Table" in table_answer
    assert "| # | Evidence | Source | Score |" in table_answer

    timeline = run_shim(
        tmp_path,
        "$ask",
        "What evidence validates SkillGen skills?",
        "--wiki-root",
        str(wiki_root),
        "--format",
        "timeline",
        "--run-id",
        "shim-ask-format-timeline",
    )
    assert timeline.returncode == 0, timeline.stderr
    timeline_summary = json.loads(timeline.stdout)
    timeline_payload = json.loads(Path(timeline_summary["evidence_path"]).read_text(encoding="utf-8"))
    timeline_action = timeline_payload["outputs"]["skill_run"]["actions"][0]
    timeline_evidence = json.loads(Path(timeline_action["evidence_path"]).read_text(encoding="utf-8"))
    timeline_retrieval_artifact = next(item for item in timeline_evidence["artifacts"] if item["type"] == "ask_retrieval_json")
    timeline_retrieval = json.loads((tmp_path / timeline_retrieval_artifact["path"]).read_text(encoding="utf-8"))
    assert timeline_retrieval["requested_format"] == "timeline"
    timeline_answer_artifact = next(item for item in timeline_evidence["artifacts"] if item["type"] == "ask_answer_markdown")
    timeline_answer = (tmp_path / timeline_answer_artifact["path"]).read_text(encoding="utf-8")
    assert "## Timeline" in timeline_answer
    assert "papers/skillgen.md" in timeline_answer


def test_autosci_skill_shim_ask_uses_model_command_with_retrieved_sources(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen\n---\n"
        "# SkillGen\n\n"
        "SkillGen is supported by verifier-gated generated skills and runtime evidence.\n",
        encoding="utf-8",
    )
    model_command = tmp_path / "ask_model_command.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "",
                "request = json.loads(sys.stdin.read())",
                "assert request['schema'] == 'autosci_model_request.v1'",
                "assert request['action'] == 'ask_wiki'",
                "assert request['context']['retrieval_hits']",
                "print(json.dumps({",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'SkillGen is supported by verifier-gated generated skills in the retrieved wiki evidence.',",
                "        'confidence': 0.82,",
                "        'evidence_ids': ['artifacts/autosci/workspace/wiki/papers/skillgen.md'],",
                "        'model': 'test-model',",
                "        'provider': 'command',",
                "    },",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ask",
        "What supports SkillGen?",
        "--wiki-root",
        str(wiki_root),
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--run-id",
        "shim-ask-model-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ask"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "ask_wiki"
    assert action["schema"] == "research_memory_update.v1"
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    change = evidence["outputs"]["changes"][0]
    assert "artifacts/autosci/workspace/wiki/papers/skillgen.md" in change["evidence_ids"]
    assert change["confidence"] == 0.82
    assert "explicit model evidence" in change["summary"]

    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {
        "ask_answer_markdown",
        "ask_retrieval_json",
        "ask_final_answer_boundary_json",
        "model_command_request_json",
        "model_command_stdout_json",
        "model_command_stderr",
        "model_runtime_proof_manifest_json",
        "provider_source_runtime_proof_manifest_json",
    } <= artifact_types
    request_artifact = next(item for item in evidence["artifacts"] if item["type"] == "model_command_request_json")
    assert re.fullmatch(r"[a-f0-9]{64}", request_artifact["sha256"])
    request_payload = json.loads((tmp_path / request_artifact["path"]).read_text(encoding="utf-8"))
    assert request_payload["schema"] == "autosci_model_request.v1"
    assert request_payload["action"] == "ask_wiki"
    retrieval_artifact = next(item for item in evidence["artifacts"] if item["type"] == "ask_retrieval_json")
    retrieval = json.loads((tmp_path / retrieval_artifact["path"]).read_text(encoding="utf-8"))
    assert retrieval["model_output"]["status"] == "completed"
    assert retrieval["model_output"]["evidence_ids"] == ["artifacts/autosci/workspace/wiki/papers/skillgen.md"]
    assert re.fullmatch(r"[a-f0-9]{64}", retrieval["model_output"]["request_sha256"])
    assert re.fullmatch(r"[a-f0-9]{64}", retrieval["model_output"]["response_sha256"])
    boundary = retrieval["final_answer_boundary"]
    assert boundary["final_answer_ready"] is True
    assert boundary["status"] == "final_answer_ready"
    assert boundary["retrieval_source_count"] == 1
    assert boundary["model_status"] == "completed"
    assert boundary["model_evidence_ids"] == ["artifacts/autosci/workspace/wiki/papers/skillgen.md"]
    assert boundary["cited_retrieval_source_ids"] == ["artifacts/autosci/workspace/wiki/papers/skillgen.md"]
    assert re.fullmatch(r"[a-f0-9]{64}", boundary["request_sha256"])
    assert re.fullmatch(r"[a-f0-9]{64}", boundary["response_sha256"])
    proof_artifact = next(item for item in evidence["artifacts"] if item["type"] == "model_runtime_proof_manifest_json")
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "ask"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    assert proof_entry["production_ready"] is True
    assert Path(action["evidence_path"]).relative_to(tmp_path).as_posix() in proof_entry["evidence_refs"]
    source_proof_artifact = next(
        item for item in evidence["artifacts"] if item["type"] == "provider_source_runtime_proof_manifest_json"
    )
    source_proof = json.loads((tmp_path / source_proof_artifact["path"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "ask"
    assert source_proof_entry["categories"] == ["provider_source_evidence"]
    assert source_proof_entry["collection_mode"] == "manual_review"
    assert not any(category == "external_runtime_evidence" for category in source_proof_entry["categories"])
    answer_artifact = next(item for item in evidence["artifacts"] if item["type"] == "ask_answer_markdown")
    answer_text = (tmp_path / answer_artifact["path"]).read_text(encoding="utf-8")
    assert "## Model Synthesis" in answer_text
    assert "verifier-gated generated skills" in answer_text


def test_autosci_skill_shim_ask_crystallize_writes_approved_output(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for name in ("papers", "outputs", "graph"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen\nslug: skillgen\n---\n"
        "# SkillGen\n\n"
        "SkillGen is supported by verifier-gated generated skills and runtime evidence.\n",
        encoding="utf-8",
    )
    allowlist = tmp_path / "allowlist.json"
    before = tmp_path / "before.json"
    runtime = tmp_path / "runtime.json"
    after = tmp_path / "after.json"
    allowlist.write_text('{"allowed": ["ask_crystallize", "wiki_output_write"]}\n', encoding="utf-8")
    before.write_text('{"outputs": []}\n', encoding="utf-8")
    runtime.write_text('{"schema": "autosci_runtime_evidence.v1", "status": "completed"}\n', encoding="utf-8")
    after.write_text('{"outputs": ["what-supports-skillgen"]}\n', encoding="utf-8")
    model_command = tmp_path / "ask_model_command.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "",
                "request = json.loads(sys.stdin.read())",
                "assert request['action'] == 'ask_wiki'",
                "assert request['context']['retrieval_hits']",
                "print(json.dumps({",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'SkillGen is supported by verifier-gated generated skills in the retrieved wiki source.',",
                "        'confidence': 0.88,",
                "        'evidence_ids': ['model:skillgen-crystallize'],",
                "        'model': 'test-model',",
                "        'provider': 'command',",
                "    },",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ask",
        "What supports SkillGen?",
        "--wiki-root",
        str(wiki_root),
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--crystallize",
        "--approval-ref",
        "approval-ask-crystallize",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--runtime-evidence",
        str(runtime),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-ask-crystallize",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    envelope = json.loads((tmp_path / "artifacts/autosci/runs/shim-ask-crystallize/envelopes/ask_wiki.json").read_text(encoding="utf-8"))
    assert envelope["inputs"]["native_options"]["crystallize"] is True
    assert envelope["inputs"]["crystallize"] is True

    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    change = evidence["outputs"]["changes"][0]
    assert change["entity_type"] == "ask_output"
    assert change["operation"] == "create"
    assert change["path"].endswith("wiki/outputs/what-supports-skillgen.md")
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {
        "ask_crystallize_writeback_json",
        "wiki_output",
        "wiki_log",
        "wiki_graph_edges",
        "wiki_rebuild",
        "approval_runtime_proof_manifest_json",
        "side_effect_runtime_proof_manifest_json",
        "wiki_mutation_runtime_proof_manifest_json",
    } <= artifact_types

    writeback_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "ask_crystallize_writeback_json")
    writeback = json.loads((tmp_path / writeback_artifact["path"]).read_text(encoding="utf-8"))
    write = writeback["outputs"]["write"]
    assert write["applied"] is True
    assert write["status"] == "completed"
    assert write["final_answer_boundary_status"] == "final_answer_ready"
    page_text = (tmp_path / write["path"]).read_text(encoding="utf-8")
    assert "[[skillgen]]" in page_text
    assert "verifier-gated generated skills" in page_text
    assert "Final answer boundary: `final_answer_ready`" in page_text
    edge_text = (tmp_path / write["edge_paths"][0]).read_text(encoding="utf-8")
    assert '"edge_type": "derived_from"' in edge_text
    assert '"target_type": "ask_output"' in edge_text
    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "[what-supports-skillgen](outputs/what-supports-skillgen.md)" in index_text

    wiki_proof_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
    )
    wiki_proof = json.loads((tmp_path / wiki_proof_artifact["path"]).read_text(encoding="utf-8"))
    wiki_entry = wiki_proof["proofs"][0]
    assert wiki_entry["native_skill"] == "ask"
    assert wiki_entry["categories"] == ["wiki_mutation_evidence"]
    assert any(ref.endswith("outputs/what-supports-skillgen.md") for ref in wiki_entry["evidence_refs"])


def test_autosci_skill_shim_ask_crystallize_parity_demo_auto_writes_output(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for name in ("papers", "outputs", "graph"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen\nslug: skillgen\n---\n"
        "# SkillGen\n\n"
        "SkillGen is supported by verifier-gated generated skills and runtime evidence.\n",
        encoding="utf-8",
    )
    model_command = tmp_path / "ask_model_command.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "request = json.loads(sys.stdin.read())",
                "assert request['context']['retrieval_hits']",
                "print(json.dumps({",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'SkillGen is supported by verifier-gated generated skills in the retrieved wiki source.',",
                "        'confidence': 0.88,",
                "        'evidence_ids': ['model:skillgen-policy-crystallize'],",
                "        'model': 'test-model',",
                "        'provider': 'command',",
                "    },",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ask",
        "What supports SkillGen?",
        "--wiki-root",
        str(wiki_root),
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--crystallize",
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-ask-crystallize-policy-auto",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    change = evidence["outputs"]["changes"][0]
    assert change["operation"] == "create"
    assert change["path"].endswith("wiki/outputs/what-supports-skillgen.md")
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:ask_wiki:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "ask_wiki_local_mutation_runtime_evidence_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert (wiki_root / "outputs/what-supports-skillgen.md").exists()


def test_autosci_skill_shim_ask_crystallize_writes_typed_target(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for name in ("papers", "concepts", "outputs", "graph"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen\nslug: skillgen\ntags: [skillgen]\nimportance: 3\n---\n"
        "# SkillGen\n\n"
        "SkillGen is supported by verifier-gated generated skills and runtime evidence.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/context_brief.md").write_text(
        "# Context Brief\n\nSkillGen connects generated skills, verifier checks, and runtime evidence.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/open_questions.md").write_text(
        "# Open Questions\n\n- How much evidence supports SkillGen beyond a single paper?\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/edges.jsonl").write_text(
        '{"source": "skillgen", "target": "runtime-evidence", "type": "supported_by"}\n',
        encoding="utf-8",
    )
    (wiki_root / "index.md").write_text(
        "# Index\n\n- [skillgen](papers/skillgen.md)\n",
        encoding="utf-8",
    )
    allowlist = tmp_path / "allowlist.json"
    before = tmp_path / "before.json"
    runtime = tmp_path / "runtime.json"
    after = tmp_path / "after.json"
    allowlist.write_text('{"allowed": ["ask_crystallize", "wiki_concept_write"]}\n', encoding="utf-8")
    before.write_text('{"concepts": []}\n', encoding="utf-8")
    runtime.write_text('{"schema": "autosci_runtime_evidence.v1", "status": "completed"}\n', encoding="utf-8")
    after.write_text('{"concepts": ["skillgen-support"]}\n', encoding="utf-8")
    model_command = tmp_path / "ask_model_command.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "request = json.loads(sys.stdin.read())",
                "assert request['action'] == 'ask_wiki'",
                "assert request['prompt'] != 'concept:skillgen-support'",
                "assert request['context']['wiki_context']['sources']['context_brief']['status'] == 'present'",
                "assert request['context']['wiki_context']['sources']['open_questions']['status'] == 'present'",
                "assert request['context']['gap_annotations']['status'] == 'matched_open_questions'",
                "print(json.dumps({",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'SkillGen support is grounded in verifier-gated generated skills from the retrieved source.',",
                "        'confidence': 0.87,",
                "        'evidence_ids': ['model:skillgen-concept'],",
                "        'model': 'test-model',",
                "        'provider': 'command',",
                "    },",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ask",
        "What supports SkillGen?",
        "--target",
        "concept:skillgen-support",
        "--wiki-root",
        str(wiki_root),
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--crystallize",
        "--approval-ref",
        "approval-ask-concept",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--runtime-evidence",
        str(runtime),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-ask-crystallize-concept",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    envelope = json.loads((tmp_path / "artifacts/autosci/runs/shim-ask-crystallize-concept/envelopes/ask_wiki.json").read_text(encoding="utf-8"))
    assert envelope["inputs"]["target"] == "concept:skillgen-support"
    assert envelope["inputs"]["crystallize_target"] == "concept:skillgen-support"
    assert envelope["inputs"]["query"] != "concept:skillgen-support"

    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    change = evidence["outputs"]["changes"][0]
    assert change["entity_type"] == "concept"
    assert change["entity_id"] == "concept-skillgen-support"
    assert change["operation"] == "create"
    assert change["path"].endswith("wiki/concepts/skillgen-support.md")
    page_text = (tmp_path / change["path"]).read_text(encoding="utf-8")
    assert 'entity_type: "concept"' in page_text
    assert 'entity_id: "concept-skillgen-support"' in page_text
    assert "SkillGen support is grounded" in page_text
    assert "## Knowledge Gaps" in page_text
    assert "## Crystallize Recommendation" in page_text
    writeback_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "ask_crystallize_writeback_json")
    writeback = json.loads((tmp_path / writeback_artifact["path"]).read_text(encoding="utf-8"))
    write = writeback["outputs"]["write"]
    assert write["crystallize_target"] == "concept:skillgen-support"
    assert write["target_entity_type"] == "concept"
    retrieval_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "ask_retrieval_json")
    retrieval = json.loads((tmp_path / retrieval_artifact["path"]).read_text(encoding="utf-8"))
    assert retrieval["wiki_context"]["sources"]["context_brief"]["status"] == "present"
    assert retrieval["wiki_context"]["sources"]["open_questions"]["status"] == "present"
    assert retrieval["wiki_context"]["sources"]["index"]["status"] == "present"
    assert retrieval["wiki_context"]["sources"]["edges"]["matched_edge_count"] == 1
    assert retrieval["gap_annotations"]["status"] == "matched_open_questions"
    assert retrieval["crystallize_recommendation"]["recommendation"] == "worthwhile"
    answer_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "ask_answer_markdown")
    answer_text = (tmp_path / answer_artifact["path"]).read_text(encoding="utf-8")
    assert "## Wiki Context" in answer_text
    assert "## Knowledge Gaps" in answer_text
    assert "Crystallize recommendation:" in answer_text


def test_autosci_skill_shim_check_uses_model_command_for_quality_review(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    for name in ("papers", "methods", "ideas", "experiments", "outputs", "graph"):
        (wiki_root / name).mkdir(parents=True, exist_ok=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "\n".join(
            [
                "---",
                "title: SkillGen",
                "slug: skillgen",
                "tags: [skillgen]",
                "importance: 3",
                "---",
                "",
                "# SkillGen",
                "",
                "SkillGen wiki evidence links claims, methods, ideas, experiments, and outputs.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (wiki_root / "graph/edges.jsonl").write_text("", encoding="utf-8")
    model_command = tmp_path / "check_model_command.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "",
                "request = json.loads(sys.stdin.read())",
                "assert request['schema'] == 'autosci_model_request.v1'",
                "assert request['action'] == 'check_wiki_health'",
                "assert request['context']['findings']['markdown_page_count'] == 1",
                "assert request['context']['findings']['lint_report']['issue_counts']['error'] == 0",
                "print(json.dumps({",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'The wiki has the required structural blocks and a valid source-linked graph edge.',",
                "        'confidence': 0.91,",
                "        'evidence_ids': ['model:wiki-health-review'],",
                "        'findings': [{'criterion': 'source graph', 'verdict': 'pass'}],",
                "        'model': 'test-model',",
                "        'provider': 'command',",
                "    },",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$check",
        "autosci wiki",
        "--wiki-root",
        str(wiki_root),
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--run-id",
        "shim-check-model-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "check"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "check_wiki_health"
    assert action["schema"] == "workflow_evolution.v1"
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert "model:wiki-health-review" in evolution["evidence_ids"]
    assert evolution["collected"]["runtime_errors"] == []
    assert evolution["collected"]["ambiguous_manuals_or_prompts"] == []
    assert evolution["collected"]["gate_rejection_reasons"][0]["status"] == "passed"
    assert "Model/reviewer evidence completed" in evolution["collected"]["gate_rejection_reasons"][0]["reasons"][0]
    boundary = evolution["review"]["final_quality_boundary"]
    assert boundary["final_quality_ready"] is True
    assert boundary["status"] == "final_quality_ready"
    assert boundary["local_structure_ready"] is True
    assert boundary["local_blocking_reasons"] == []
    assert boundary["model_status"] == "completed"
    assert boundary["model_evidence_ids"] == ["model:wiki-health-review"]
    assert re.fullmatch(r"[a-f0-9]{64}", boundary["request_sha256"])
    assert re.fullmatch(r"[a-f0-9]{64}", boundary["response_sha256"])

    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {
        "recommended_changes_markdown",
        "patch_candidates_directory",
        "check_final_quality_boundary_json",
        "wiki_lint_report_json",
        "model_command_request_json",
        "model_command_stdout_json",
        "model_command_stderr",
        "model_runtime_proof_manifest_json",
    } <= artifact_types
    request_artifact = next(item for item in evidence["artifacts"] if item["type"] == "model_command_request_json")
    assert re.fullmatch(r"[a-f0-9]{64}", request_artifact["sha256"])
    request_payload = json.loads((tmp_path / request_artifact["path"]).read_text(encoding="utf-8"))
    assert request_payload["action"] == "check_wiki_health"
    lint_artifact = next(item for item in evidence["artifacts"] if item["type"] == "wiki_lint_report_json")
    lint_report = json.loads((tmp_path / lint_artifact["path"]).read_text(encoding="utf-8"))
    assert lint_report["schema"] == "autosci_wiki_lint_cli.v1"
    assert lint_report["issue_counts"]["error"] == 0
    proof_artifact = next(item for item in evidence["artifacts"] if item["type"] == "model_runtime_proof_manifest_json")
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "check"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    assert proof_entry["production_ready"] is True
    assert Path(action["evidence_path"]).relative_to(tmp_path).as_posix() in proof_entry["evidence_refs"]
    markdown = (tmp_path / evolution["recommended_changes_path"]).read_text(encoding="utf-8")
    assert "## Model Evidence" in markdown
    assert "Native lint errors: `0`" in markdown
    assert "valid source-linked graph edge" in markdown


def test_autosci_skill_shim_runs_remaining_gated_backend_actions(tmp_path: Path) -> None:
    cases = [
        ("$daily-arxiv", "agents", "daily_arxiv_prepare_finalize", "literature_discovery.v1", "gated", "schema_only"),
        ("$exp-pilot-eval", "pilot-claim-001", "evaluate_pilot_result", "claim_verdict.v1", "gated", "schema_only"),
        ("$exp-pilot-run", "pilot-001", "run_pilot_experiment", "experiment_result.v1", "gated", "schema_only"),
        ("$refine", "report-001", "refine_artifact", "workflow_evolution.v1", "gated", "passed"),
        ("$research", "skillgen lifecycle", "run_research_lifecycle", "workflow_evolution.v1", "gated", "schema_only"),
        ("$visualize", "autosci graph", "visualize_graph", "research_graph_update.v1", "gated", "passed"),
    ]
    for command, target, expected_action, expected_schema, expected_status, expected_action_status in cases:
        run_id = f"shim-{expected_action}"
        proc = run_shim(
            tmp_path,
            command,
            target,
            "--run-id",
            run_id,
        )
        assert proc.returncode == 0, proc.stderr
        summary = json.loads(proc.stdout)
        assert summary["execution_status"] == expected_status
        assert summary["action_count"] == 1
        payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
        action = payload["outputs"]["skill_run"]["actions"][0]
        assert action["action"] == expected_action
        assert action["schema"] == expected_schema
        assert action["status"] == expected_action_status
        evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
        if expected_action in {"daily_arxiv_prepare_finalize", "evaluate_pilot_result", "run_pilot_experiment"}:
            assert evidence["status"] == "inconclusive"
        if expected_action in {"daily_arxiv_prepare_finalize", "run_pilot_experiment", "visualize_graph"}:
            contract_artifact = next(
                artifact for artifact in evidence["artifacts"] if artifact["type"] == "approval_contract_json"
            )
            contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
            assert contract["approved"] is False
            assert "approval_ref" in contract["missing"]
        if expected_action in {"refine_artifact", "run_research_lifecycle"}:
            assert evidence["outputs"]["evolution"]["review"]["protected_core_edits_applied"] is False
            contract_artifact = next(
                artifact for artifact in evidence["artifacts"] if artifact["type"] == "approval_contract_json"
            )
            contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
            assert contract["approved"] is False
        if expected_action == "visualize_graph":
            assert evidence["outputs"]["edges"][0]["operation"] == "propose"


def test_autosci_strict_gate_emits_side_effect_access_requests_for_native_parity_commands(tmp_path: Path) -> None:
    cases = [
        (
            "$daily-arxiv",
            "agents",
            ["--gate-mode", "strict_hitl"],
            "daily_arxiv_prepare_finalize",
            "daily-arxiv",
            {"network_fetch"},
        ),
        (
            "$research",
            "skillgen lifecycle",
            ["--gate-mode", "strict_hitl"],
            "run_research_lifecycle",
            "research",
            {"network_fetch", "local_command", "wiki_mutation", "remote_execution", "tex_compile"},
        ),
        (
            "$ideate",
            "skillgen ideas",
            ["--gate-mode", "strict_hitl", "--skip-validation"],
            "generate_ideas",
            "ideate",
            {"network_fetch", "local_command", "wiki_mutation"},
        ),
        (
            "$exp-run",
            "exp-001",
            ["--env", "local", "--gate-mode", "strict_hitl"],
            "run_experiment",
            "exp-run",
            {"local_command", "wiki_mutation"},
        ),
    ]
    for command, target, extra_args, expected_action, native_skill, material_effects in cases:
        proc = run_shim(
            tmp_path,
            command,
            target,
            "--run-id",
            f"shim-side-effect-access-{expected_action}",
            *extra_args,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        summary = json.loads(proc.stdout)
        assert summary["status"] == "inconclusive"

        payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
        actions = payload["outputs"]["skill_run"]["actions"]
        action = next(item for item in actions if item["action"] == expected_action)
        assert action["status"] == "schema_only"
        evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
        assert evidence["status"] == "inconclusive"
        outputs = evidence["outputs"]
        assert outputs["side_effect_access_required"] is True
        assert outputs["side_effect_access_status"] == "blocked_side_effect_access_required"
        request = outputs["side_effect_access_request"]
        assert request["schema"] == "autosci_side_effect_access_request.v1"
        assert request["status"] == "blocked_side_effect_access_required"
        assert request["native_skill"] == native_skill
        assert request["gate_policy"]["mode"] == "strict_hitl"
        assert request["gate_policy"]["execute_side_effects"] is False
        assert material_effects.issubset(set(request["requested_side_effects"]))
        continuation = request["continuation"]
        assert continuation["schema"] == "autosci_side_effect_continuation.v1"
        assert continuation["status"] == "awaiting_side_effect_access"
        assert continuation["retriable"] is True
        assert continuation["same_envelope_supported"] is True
        assert continuation["resume_strategy"] == "rerun_same_action_with_access_patch"
        assert continuation["non_error_contract"]["blocked_runs_exit_successfully"] is True
        assert continuation["non_error_contract"]["evidence_status"] == "inconclusive"
        option_names = {option["name"] for option in continuation["access_patch_options"]}
        assert {"bounded_policy_mode", "native_policy_mode", "hitl_approval"}.issubset(option_names)
        assert any(
            artifact["type"] == "side_effect_access_request_json"
            for artifact in evidence["artifacts"]
        )


def test_autosci_skill_shim_visualize_projects_action_graph_update_into_workspace_graph(tmp_path: Path) -> None:
    run_id = "shim-visualize-projects-action-graph"
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers" / "source.md").write_text("---\ntitle: Source Paper\n---\n# Source Paper\n", encoding="utf-8")
    (wiki_root / "ideas" / "skillgen.md").write_text("---\ntitle: SkillGen Idea\n---\n# SkillGen Idea\n", encoding="utf-8")
    source_edge = {"source": "papers/source.md", "target": "ideas/skillgen.md", "relation": "inspires"}
    edges_path = wiki_root / "graph" / "edges.jsonl"
    edges_path.write_text(json.dumps(source_edge, sort_keys=True) + "\n", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$visualize",
        "autosci graph",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        run_id,
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "visualize"
    assert summary["workspace_updated_count"] > 0

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "visualize_graph"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["schema"] == "research_graph_update.v1"
    assert evidence["outputs"]["edges"]

    projected_edges = [
        json.loads(line)
        for line in edges_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        edge.get("run_id") == run_id
        and str(edge.get("source_evidence") or "").endswith("research_graph_update.visualize.json")
        for edge in projected_edges
    )

    manifest_path = wiki_root / "graph" / "projection_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "autosci_workspace_graph_projection.v1"
    assert manifest["status"] == "projected"
    assert manifest["projected_edge_count"] >= 1
    assert any(path.endswith("research_graph_update.visualize.json") for path in manifest["source_evidence"])


def test_autosci_skill_shim_accepts_visualize_serve_flag_without_server_execution(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$visualize",
        "autosci graph",
        "--serve",
        "--run-id",
        "shim-visualize-serve-flag",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "visualize"
    assert summary["execution_status"] == "gated"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["serve"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "visualize_graph"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["inputs"]["serve_requested"] is True
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert "autosci_web_graph_json" in artifact_types
    assert "autosci_canvas_json" in artifact_types
    assert "visualize_web_health_json" not in artifact_types
    contract_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "approval_contract_json"
    )
    contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
    assert contract["approved"] is False
    assert "approval_ref" in contract["missing"]
    authorization = contract["authorization_request"]
    assert authorization["schema"] == "autosci_gate_authorization_request.v1"
    assert authorization["status"] == "awaiting_authorization"
    assert authorization["continuation"]["schema"] == "autosci_gate_continuation.v1"
    assert authorization["continuation"]["retriable"] is True
    assert authorization["continuation"]["resume_strategy"] == "rerun_same_action_with_approval_patch"


def test_autosci_skill_shim_visualize_parity_demo_auto_runs_server_probe(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir()
    (wiki_root / "ideas" / "skillgen.md").write_text(
        "---\n"
        "title: SkillGen\n"
        "slug: skillgen\n"
        "status: proposed\n"
        "tags: []\n"
        "---\n"
        "# SkillGen\n",
        encoding="utf-8",
    )
    (wiki_root / "graph" / "edges.jsonl").write_text("", encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$visualize",
        "autosci graph",
        "--serve",
        "--wiki-root",
        str(wiki_root),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-visualize-parity-demo-serve",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "visualize"
    assert summary["passed_count"] == 1
    assert "authorization_required" not in summary

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert "authorization_required" not in payload["outputs"]
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["allowed"] is True
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:visualize_graph:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "visualize_web_health_json" in artifacts
    assert "approval_contract_json" in artifacts
    serve_probe = json.loads((tmp_path / artifacts["visualize_web_health_json"]).read_text(encoding="utf-8"))
    assert serve_probe["server_started"] is True
    assert serve_probe["server_stopped"] is True
    assert serve_probe["health"]["ok"] is True

    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:visualize_graph:")
    assert contract["execution_verified"] is True


def test_autosci_skill_shim_visualize_serve_emits_approved_runtime_proofs(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "topics").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    before = tmp_path / "visualize-before.json"
    before.write_text('{"graph_state": "before"}\n', encoding="utf-8")
    allowlist = tmp_path / "visualize-allowlist.json"
    allowlist.write_text('{"allowed": ["visualize_graph", "serve.py --health-check"]}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$visualize",
        "autosci graph",
        "--serve",
        "--wiki-root",
        str(wiki_root),
        "--approval-ref",
        "approval-visualize-serve",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-visualize-approved-serve",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "visualize"
    assert summary["passed_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "visualize_graph"
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "visualize_web_health_json" in artifacts
    assert "approval_contract_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    assert "provider_source_runtime_proof_manifest_json" not in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" not in artifacts

    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    side_effect_proof = json.loads((tmp_path / artifacts["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert contract["execution_verified"] is True
    assert approval_proof["proofs"][0]["native_skill"] == "visualize"
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]


def test_autosci_skill_shim_visualize_accepts_native_focus_and_filters(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "concepts").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers" / "source.md").write_text("---\ntitle: Source Paper\n---\n# Source Paper\n", encoding="utf-8")
    (wiki_root / "concepts" / "skill.md").write_text("---\ntitle: Skill Concept\n---\n# Skill Concept\n", encoding="utf-8")
    (wiki_root / "methods" / "filtered.md").write_text("---\ntitle: Filtered Method\n---\n# Filtered Method\n", encoding="utf-8")
    (wiki_root / "graph" / "edges.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"source": "papers/source.md", "target": "concepts/skill.md", "relation": "uses_concept"}),
                json.dumps({"source": "papers/source.md", "target": "methods/filtered.md", "relation": "builds_on"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$visualize",
        "autosci graph",
        "--canvas",
        "--focus",
        "papers/source.md",
        "--depth",
        "1",
        "--types",
        "papers,concepts",
        "--edge-types",
        "uses_concept",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-visualize-focus-filter",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "visualize"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    edges = evidence["outputs"]["edges"]
    assert len(edges) == 1
    assert edges[0]["relation"] == "uses_concept"
    assert edges[0]["source"] == "papers/source.md"
    assert edges[0]["target"] == "concepts/skill.md"
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "autosci_canvas_json" in artifacts
    assert "obsidian_graph_config_json" not in artifacts
    assert artifacts["autosci_canvas_json"].endswith("canvases/focus-papers-source.md.canvas")
    canvas_payload = json.loads((tmp_path / artifacts["visualize_canvas_stdout_json"]).read_text(encoding="utf-8"))
    assert canvas_payload["nodes"] == 2
    assert canvas_payload["edges"] == 1


def test_autosci_skill_shim_refine_applies_approved_after_artifact(tmp_path: Path) -> None:
    target = tmp_path / "artifacts/autosci/workspace/wiki/outputs/report-001.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Report\n\nOld draft.\n", encoding="utf-8")
    after = tmp_path / "report-001-after.md"
    after.write_text("# Report\n\nApproved refined draft.\n", encoding="utf-8")
    before = tmp_path / "report-001-before.md"
    before.write_text("# Report\n\nOld draft.\n", encoding="utf-8")
    runtime = tmp_path / "refine-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:refine-report"]}\n', encoding="utf-8")
    allowlist = tmp_path / "refine-allowlist.json"
    allowlist.write_text('{"allowed": ["refine_artifact"]}\n', encoding="utf-8")
    review_evidence = tmp_path / "refine-review.json"
    review_evidence.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "score": 6.0,
                        "verdict": "needs-work",
                        "actionable_items": [
                            {"issue": "Clarify contribution statement.", "severity": "major"}
                        ],
                        "weaknesses": [
                            {"issue": "Contribution statement is vague.", "severity": "major"}
                        ],
                        "review_llm": {
                            "status": "completed",
                            "provider": "openai",
                            "model": "gpt-4.1-mini",
                            "evidence_ids": ["review:refine-report"],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$refine",
        str(target),
        "--difficulty",
        "hard",
        "--focus",
        "writing",
        "--max-rounds",
        "2",
        "--target-score",
        "8",
        "--review-llm-evidence",
        str(review_evidence),
        "--approval-ref",
        "approval-refine-report",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-refine-approved-apply",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "refine"
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evolution["approval_state"] == "applied"
    assert evolution["review"]["protected_core_edits_applied"] is True
    assert evolution["review"]["refine_apply"]["applied"] is True
    assert evolution["review"]["refine_loop_report"]["score_history"] == [6.0]
    assert evolution["review"]["refine_loop_report"]["termination_reason"] == "approved_after_artifact_applied"
    assert evolution["review"]["refine_loop_report"]["difficulty"] == "hard"
    assert evolution["review"]["refine_loop_report"]["focus"] == "writing"
    assert target.read_text(encoding="utf-8") == after.read_text(encoding="utf-8")
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"refine_apply_writeback_json", "refined_artifact", "refine_loop_report_json"}.issubset(artifact_types)
    assert {
        "provider_source_runtime_proof_manifest_json",
        "approval_runtime_proof_manifest_json",
        "side_effect_runtime_proof_manifest_json",
        "review_model_runtime_proof_manifest_json",
    }.issubset(artifact_types)
    apply_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "refine_apply_writeback_json")
    apply_evidence = json.loads((tmp_path / apply_artifact["path"]).read_text(encoding="utf-8"))
    assert apply_evidence["status"] == "completed"
    loop_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "refine_loop_report_json")
    loop_report = json.loads((tmp_path / loop_artifact["path"]).read_text(encoding="utf-8"))
    assert loop_report["review_evidence_completed"] is True
    assert loop_report["fixed_issues"][0]["issue"] == "Clarify contribution statement."
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    side_effect_proof = json.loads((tmp_path / artifacts["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    review_proof = json.loads((tmp_path / artifacts["review_model_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert source_proof["proofs"][0]["categories"] == ["provider_source_evidence"]
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]
    assert review_proof["proofs"][0]["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert any(str(ref).endswith("refine-review.json") for ref in review_proof["proofs"][0]["evidence_refs"])


def test_autosci_skill_shim_refine_parity_demo_auto_applies_after_artifact(tmp_path: Path) -> None:
    target = tmp_path / "artifacts/autosci/workspace/wiki/outputs/report-policy.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Report\n\nOld draft.\n", encoding="utf-8")
    after = tmp_path / "report-policy-after.md"
    after.write_text("# Report\n\nPolicy-approved refined draft.\n", encoding="utf-8")
    review_evidence = tmp_path / "refine-review.json"
    review_evidence.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "score": 6.0,
                        "verdict": "needs-work",
                        "actionable_items": [{"issue": "Clarify contribution statement.", "severity": "major"}],
                        "review_llm": {
                            "status": "completed",
                            "provider": "openai",
                            "model": "gpt-4.1-mini",
                            "evidence_ids": ["review:refine-policy"],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$refine",
        str(target),
        "--review-llm-evidence",
        str(review_evidence),
        "--after-artifact",
        str(after),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-refine-policy-auto",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evolution = evidence["outputs"]["evolution"]
    assert evolution["approval_state"] == "applied"
    assert evolution["review"]["protected_core_edits_applied"] is True
    assert evolution["review"]["refine_apply"]["applied"] is True
    assert target.read_text(encoding="utf-8") == after.read_text(encoding="utf-8")
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:refine_artifact:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "refine_artifact_local_mutation_runtime_evidence_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True


def test_autosci_skill_shim_refine_runs_review_command_quality_gate(tmp_path: Path) -> None:
    target = tmp_path / "artifacts/autosci/workspace/wiki/outputs/report-review-loop.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Report\n\nOld draft with vague contribution.\n", encoding="utf-8")
    after = tmp_path / "report-review-loop-after.md"
    after.write_text(
        "# Report\n\n## Contribution\n\nApproved refined draft with a clear contribution, evidence trail, and next-step decision.\n",
        encoding="utf-8",
    )
    before = tmp_path / "report-review-loop-before.md"
    before.write_text("# Report\n\nOld draft with vague contribution.\n", encoding="utf-8")
    runtime = tmp_path / "refine-runtime.json"
    runtime.write_text('{"status": "completed", "exit_code": 0, "evidence_ids": ["runtime:refine-loop"]}\n', encoding="utf-8")
    allowlist = tmp_path / "refine-allowlist.json"
    allowlist.write_text('{"allowed": ["refine_artifact"]}\n', encoding="utf-8")
    command_path = tmp_path / "review_llm_command.py"
    command_path.write_text(
        """
import json
import sys

request = json.loads(sys.stdin.read())
target = request["inputs"].get("target", "N/A")
print(json.dumps({
    "schema": "artifact_review.v1",
    "status": "completed",
    "outputs": {
        "review": {
            "artifact_id": "artifact:" + target,
            "target": target,
            "review_mode": "review_llm",
            "review_available": True,
            "difficulty": request.get("difficulty", "standard"),
            "focus": request.get("focus", "writing"),
            "score": 0.92,
            "recommendation": "pass_with_review_required",
            "evidence_ids": ["review-llm:refine-command"]
        },
        "findings": []
    }
}))
""".lstrip(),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$refine",
        str(target),
        "--difficulty",
        "hard",
        "--focus",
        "writing",
        "--max-rounds",
        "2",
        "--target-score",
        "0.5",
        "--review-llm-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(command_path))}",
        "--approval-ref",
        "approval-refine-command",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-refine-review-command",
    )
    assert proc.returncode == 2, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    report = evidence["outputs"]["evolution"]["review"]["refine_loop_report"]
    assert report["review_evidence_completed"] is True
    assert report["termination_reason"] == "quality_target_not_reached"
    assert report["status"] == "incomplete"
    assert report["score_history"][-1] < 0.5
    assert report["unresolved_issues"]
    assert report["auto_review_rounds"][0]["path"].endswith("refine_review_round_01.json")
    artifact_types = {artifact["type"] for artifact in evidence["artifacts"]}
    assert {"refine_review_round_json", "review_model_runtime_proof_manifest_json"}.issubset(artifact_types)
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    review_round = json.loads((tmp_path / artifacts["refine_review_round_json"]).read_text(encoding="utf-8"))
    assert review_round["outputs"]["review"]["review_llm"]["invocation_mode"] == "command"
    proof = json.loads((tmp_path / artifacts["review_model_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert any(str(ref).endswith("refine_review_round_01.json") for ref in proof["proofs"][0]["evidence_refs"])


def test_autosci_skill_shim_pilot_eval_uses_runtime_evidence(tmp_path: Path) -> None:
    runtime = tmp_path / "pilot-runtime.json"
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "pilot-runtime-skillgen",
                "status": "completed",
                "exit_code": 0,
                "outcome": "supports",
                "metrics": [{"name": "pilot_accuracy", "value": 0.73}],
                "evidence_ids": ["runtime:pilot-skillgen"],
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$exp-pilot-eval",
        "pilot-claim-001",
        "--runtime-evidence",
        str(runtime),
        "--run-id",
        "shim-pilot-eval-runtime",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-pilot-eval"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    verdict = evidence["outputs"]["verdicts"][0]
    assert verdict["claim_id"] == "pilot-claim-001"
    assert verdict["verdict"] == "supported"
    assert verdict["evidence_outcome"] == "supports"
    assert "runtime:pilot-skillgen" in verdict["evidence_ids"]
    assert any(artifact["type"] == "pilot_runtime_evidence_json" for artifact in evidence["artifacts"])
    assert any(artifact["type"] == "pilot_eval_final_acceptance_boundary_json" for artifact in evidence["artifacts"])
    boundary = verdict["pilot_final_acceptance_boundary"]
    assert boundary["status"] == "pilot_acceptance_incomplete"
    assert boundary["pilot_runtime_ready"] is True
    assert boundary["pilot_verdict_ready"] is True
    assert boundary["writeback_status"]["status"] == "not_requested"
    assert boundary["final_pilot_acceptance_ready"] is False


def test_autosci_skill_shim_pilot_eval_write_updates_wiki_with_approval(tmp_path: Path) -> None:
    claim_id = "pilot-claim-write"
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    idea_path = wiki_root / "ideas" / f"{claim_id}.md"
    idea_path.write_text(
        "---\ntitle: Pilot Claim Write\nstatus: pilot\n---\n# Pilot Claim Write\n",
        encoding="utf-8",
    )
    runtime = tmp_path / "pilot-runtime-write.json"
    allowlist = tmp_path / "pilot-eval-allowlist.json"
    before = tmp_path / "pilot-eval-before.md"
    allowlist.write_text(json.dumps({"allowed": ["evaluate_pilot_result"]}), encoding="utf-8")
    before.write_text(idea_path.read_text(encoding="utf-8"), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "pilot-runtime-write",
                "status": "completed",
                "exit_code": 0,
                "outcome": "supports",
                "metrics": [{"name": "pilot_accuracy", "value": 0.77}],
                "evidence_ids": ["runtime:pilot-write"],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-pilot-eval",
        claim_id,
        "--runtime-evidence",
        str(runtime),
        "--wiki-root",
        str(wiki_root),
        "--write",
        "--approval-ref",
        "approval-pilot-write",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(idea_path),
        "--execute-approved",
        "--run-id",
        "shim-pilot-eval-writeback",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    writeback_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pilot_verdict_writeback_json")
    writeback = json.loads((tmp_path / writeback_artifact["path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "completed"
    assert writeback["outputs"]["write"]["applied"] is True
    assert "claim_verdict: supported" in idea_path.read_text(encoding="utf-8")
    assert "claim_verdict_written" in (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" not in artifacts
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    wiki_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert approval_proof["proofs"][0]["native_skill"] == "exp-pilot-eval"
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert wiki_proof["proofs"][0]["categories"] == ["wiki_mutation_evidence"]
    boundary_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pilot_eval_final_acceptance_boundary_json")
    boundary = json.loads((tmp_path / boundary_artifact["path"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "final_pilot_acceptance_ready"
    assert boundary["pilot_runtime_ready"] is True
    assert boundary["pilot_verdict_ready"] is True
    assert boundary["writeback_completed"] is True
    assert boundary["final_pilot_acceptance_ready"] is True
    verdict = evidence["outputs"]["verdicts"][0]
    assert verdict["final_pilot_acceptance_ready"] is True


def test_autosci_skill_shim_pilot_eval_parity_demo_auto_writes_wiki(tmp_path: Path) -> None:
    claim_id = "pilot-claim-parity-write"
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    idea_path = wiki_root / "ideas" / f"{claim_id}.md"
    idea_path.write_text(
        "---\ntitle: Pilot Claim Parity Write\nstatus: pilot\n---\n# Pilot Claim Parity Write\n",
        encoding="utf-8",
    )
    runtime = tmp_path / "pilot-runtime-parity-write.json"
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "pilot-runtime-parity-write",
                "status": "completed",
                "exit_code": 0,
                "outcome": "supports",
                "metrics": [{"name": "pilot_accuracy", "value": 0.81}],
                "evidence_ids": ["runtime:pilot-parity-write"],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-pilot-eval",
        claim_id,
        "--runtime-evidence",
        str(runtime),
        "--wiki-root",
        str(wiki_root),
        "--write",
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-pilot-eval-parity-writeback",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    writeback_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "pilot_verdict_writeback_json")
    writeback = json.loads((tmp_path / writeback_artifact["path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "completed"
    assert writeback["outputs"]["write"]["applied"] is True
    policy = writeback["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:evaluate_pilot_result:")
    assert "claim_verdict: supported" in idea_path.read_text(encoding="utf-8")
    assert "claim_verdict_written" in (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:evaluate_pilot_result:")


def test_autosci_skill_shim_exp_eval_merges_experiment_code_and_review_llm_evidence(tmp_path: Path) -> None:
    claim_id = "claim-skillgen-001"
    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps(
            {
                "schema": "research_claims.v1",
                "task_id": "claims-skillgen",
                "status": "completed",
                "outputs": {
                    "claims": [
                        {
                            "claim_id": claim_id,
                            "text": "SkillGen improves generated-skill reliability on held-out repair tasks.",
                            "evidence_ids": ["claim:skillgen"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    result = tmp_path / "experiment-result.json"
    result.write_text(
        json.dumps(
            {
                "schema": "experiment_result.v1",
                "task_id": "result-skillgen",
                "status": "completed",
                "outputs": {
                    "result": {
                        "experiment_id": "exp-skillgen",
                        "outcome": "supports",
                        "evidence_ids": ["experiment:skillgen"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    code = tmp_path / "code-evidence.json"
    code.write_text(
        json.dumps(
            {
                "schema": "code_evidence_map.v1",
                "task_id": "code-skillgen",
                "status": "completed",
                "outputs": {
                    "mappings": [
                        {
                            "mapping_id": "code-map-skillgen",
                            "claim_id": claim_id,
                            "evidence_ids": ["code:skillgen-eval"],
                            "files": ["experiments/skillgen_eval.py"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review-llm-exp-eval.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-exp-eval",
                "status": "completed",
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:exp-skillgen",
                        "target": claim_id,
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "hard",
                        "focus": "evidence",
                        "score": 0.81,
                        "recommendation": "pass_with_caveats",
                        "evidence_ids": ["review:exp-eval"],
                    },
                    "findings": [
                        {
                            "finding_id": "review.exp-eval.evidence-linked",
                            "severity": "low",
                            "category": "evidence",
                            "evidence": "Experiment and code evidence are linked to the claim.",
                            "suggestion": "Keep the linkage in the paper evidence table.",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-eval",
        claim_id,
        "--claims-evidence",
        str(claims),
        "--experiment-result-evidence",
        str(result),
        "--code-evidence",
        str(code),
        "--review-llm-evidence",
        str(review),
        "--run-id",
        "shim-exp-eval-review-llm",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "exp-eval"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "verify_claim"
    assert action["schema"] == "claim_verdict.v1"
    assert action["gate_status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    verdict = evidence["outputs"]["verdicts"][0]
    assert verdict["claim_id"] == claim_id
    assert verdict["verdict"] == "supported"
    assert verdict["experiment_id"] == "exp-skillgen"
    assert verdict["review_llm"]["status"] == "completed"
    assert verdict["review_llm"]["recommendation"] == "pass_with_caveats"
    assert "review-exp-eval" in verdict["evidence_ids"]
    assert "review:exp-eval" in verdict["evidence_ids"]
    assert "code-map-skillgen" in verdict["code_evidence_ids"]
    assert "Review LLM evidence" in verdict["basis"]
    assert any(artifact["type"] == "claim_review_llm_evidence_json" for artifact in evidence["artifacts"])
    assert any(artifact["type"] == "review_model_runtime_proof_manifest_json" for artifact in evidence["artifacts"])
    assert any(artifact["type"] == "experiment_evaluation_final_verdict_boundary_json" for artifact in evidence["artifacts"])
    proof_artifact = next(
        artifact
        for artifact in evidence["artifacts"]
        if artifact["type"] == "review_model_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "exp-eval"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    expected_ref = Path(action["evidence_path"]).relative_to(tmp_path).as_posix()
    assert expected_ref in [str(ref).replace("\\", "/") for ref in proof_entry["evidence_refs"]]
    boundary = verdict["final_verdict_boundary"]
    assert boundary["status"] == "final_verdict_incomplete"
    assert boundary["experiment_result_ready"] is True
    assert boundary["claim_evidence_linked"] is True
    assert boundary["code_evidence_linked"] is True
    assert boundary["review_llm_completed"] is True
    assert boundary["writeback_status"]["status"] == "not_requested"
    assert boundary["final_verdict_ready"] is False


def test_autosci_skill_shim_exp_eval_write_updates_wiki_with_approval(tmp_path: Path) -> None:
    claim_id = "claim-skillgen-write"
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "topics").mkdir(parents=True)
    idea_path = wiki_root / "ideas" / f"{claim_id}.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Writeback Idea\nstatus: candidate\n---\n# SkillGen Writeback Idea\n",
        encoding="utf-8",
    )
    (wiki_root / "topics/skillgen.md").write_text(
        "# SkillGen\n\n## Open problems\n- Need cross-domain validation before publication.\n",
        encoding="utf-8",
    )
    before = tmp_path / "before-claim-writeback.md"
    before.write_text(idea_path.read_text(encoding="utf-8"), encoding="utf-8")
    allowlist = tmp_path / "allowlist-claim-writeback.json"
    allowlist.write_text('{"allowed": ["verify_claim"]}\n', encoding="utf-8")
    runtime = tmp_path / "runtime-claim-writeback.json"
    runtime.write_text(
        json.dumps(
            {
                "schema": "autosci_runtime_evidence.v1",
                "task_id": "claim-writeback-runtime",
                "status": "completed",
                "exit_code": 0,
                "evidence_ids": ["runtime:claim-writeback"],
            }
        ),
        encoding="utf-8",
    )
    claims = tmp_path / "claims-write.json"
    claims.write_text(
        json.dumps(
            {
                "schema": "research_claims.v1",
                "task_id": "claims-write",
                "status": "completed",
                "outputs": {"claims": [{"claim_id": claim_id, "text": "Approved claim writeback.", "evidence_ids": ["claim:write"]}]},
            }
        ),
        encoding="utf-8",
    )
    result = tmp_path / "result-write.json"
    result.write_text(
        json.dumps(
            {
                "schema": "experiment_result.v1",
                "task_id": "result-write",
                "status": "completed",
                "outputs": {"result": {"experiment_id": "exp-write", "outcome": "supports", "evidence_ids": ["experiment:write"]}},
            }
        ),
        encoding="utf-8",
    )
    code = tmp_path / "code-write.json"
    code.write_text(
        json.dumps(
            {
                "schema": "code_evidence_map.v1",
                "task_id": "code-write",
                "status": "completed",
                "outputs": {
                    "mappings": [
                        {
                            "mapping_id": "code-map-write",
                            "claim_id": claim_id,
                            "evidence_ids": ["code:write"],
                            "files": ["experiments/write_eval.py"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review-write.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-write",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "recommendation": "pass_with_caveats",
                        "evidence_ids": ["review:write"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-eval",
        claim_id,
        "--wiki-root",
        str(wiki_root),
        "--claims-evidence",
        str(claims),
        "--experiment-result-evidence",
        str(result),
        "--code-evidence",
        str(code),
        "--review-llm-evidence",
        str(review),
        "--write",
        "--approval-ref",
        "approval-exp-eval-write",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(idea_path),
        "--execute-approved",
        "--run-id",
        "shim-exp-eval-writeback",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    writeback_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "claim_verdict_writeback_json")
    writeback = json.loads((tmp_path / writeback_artifact["path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "completed"
    assert writeback["outputs"]["write"]["applied"] is True
    updated = idea_path.read_text(encoding="utf-8")
    assert "claim_verdict: supported" in updated
    assert "claim_verdict_confidence: 0.72" in updated
    assert "claim_verdict_evidence:" in updated
    assert (wiki_root / "log.md").exists()
    assert "Claim Verdict Writeback" in (wiki_root / "log.md").read_text(encoding="utf-8")
    assert "claim_verdict_written" in (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    open_questions = wiki_root / "graph/open_questions.md"
    assert open_questions.exists()
    assert "[topic:skillgen] Need cross-domain validation before publication." in open_questions.read_text(encoding="utf-8")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" not in artifacts
    approval_proof = json.loads((tmp_path / artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    wiki_proof = json.loads((tmp_path / artifacts["wiki_mutation_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert approval_proof["proofs"][0]["native_skill"] == "exp-eval"
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert wiki_proof["proofs"][0]["native_skill"] == "exp-eval"
    assert wiki_proof["proofs"][0]["categories"] == ["wiki_mutation_evidence"]
    assert any(ref.endswith("claim_verdict_writeback.json") for ref in wiki_proof["proofs"][0]["evidence_refs"])
    boundary_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "experiment_evaluation_final_verdict_boundary_json"
    )
    boundary = json.loads((tmp_path / boundary_artifact["path"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "final_verdict_ready"
    assert boundary["final_verdict_ready"] is True
    assert boundary["experiment_result_ready"] is True
    assert boundary["claim_evidence_linked"] is True
    assert boundary["code_evidence_linked"] is True
    assert boundary["review_llm_completed"] is True
    assert boundary["writeback_completed"] is True
    verdict = evidence["outputs"]["verdicts"][0]
    assert verdict["final_verdict_ready"] is True


def test_autosci_skill_shim_exp_eval_parity_demo_auto_writes_wiki(tmp_path: Path) -> None:
    claim_id = "claim-skillgen-parity-write"
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    idea_path = wiki_root / "ideas" / f"{claim_id}.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Parity Writeback Idea\nstatus: candidate\n---\n# SkillGen Parity Writeback Idea\n",
        encoding="utf-8",
    )
    claims = tmp_path / "claims-parity-write.json"
    claims.write_text(
        json.dumps(
            {
                "schema": "research_claims.v1",
                "task_id": "claims-parity-write",
                "status": "completed",
                "outputs": {
                    "claims": [
                        {
                            "claim_id": claim_id,
                            "text": "Parity policy can write verified local claim verdicts.",
                            "evidence_ids": ["claim:parity-write"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    result = tmp_path / "result-parity-write.json"
    result.write_text(
        json.dumps(
            {
                "schema": "experiment_result.v1",
                "task_id": "result-parity-write",
                "status": "completed",
                "outputs": {
                    "result": {
                        "experiment_id": "exp-parity-write",
                        "outcome": "supports",
                        "evidence_ids": ["experiment:parity-write"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    code = tmp_path / "code-parity-write.json"
    code.write_text(
        json.dumps(
            {
                "schema": "code_evidence_map.v1",
                "task_id": "code-parity-write",
                "status": "completed",
                "outputs": {
                    "mappings": [
                        {
                            "mapping_id": "code-map-parity-write",
                            "claim_id": claim_id,
                            "evidence_ids": ["code:parity-write"],
                            "files": ["experiments/parity_write_eval.py"],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "review-parity-write.json"
    review.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-parity-write",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "recommendation": "pass_with_caveats",
                        "evidence_ids": ["review:parity-write"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$exp-eval",
        claim_id,
        "--wiki-root",
        str(wiki_root),
        "--claims-evidence",
        str(claims),
        "--experiment-result-evidence",
        str(result),
        "--code-evidence",
        str(code),
        "--review-llm-evidence",
        str(review),
        "--write",
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-exp-eval-parity-writeback",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    writeback_artifact = next(artifact for artifact in evidence["artifacts"] if artifact["type"] == "claim_verdict_writeback_json")
    writeback = json.loads((tmp_path / writeback_artifact["path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "completed"
    assert writeback["outputs"]["write"]["applied"] is True
    policy = writeback["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:verify_claim:")
    updated = idea_path.read_text(encoding="utf-8")
    assert "claim_verdict: supported" in updated
    assert "claim_verdict_evidence:" in updated
    assert "claim_verdict_written" in (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:verify_claim:")
    verdict = evidence["outputs"]["verdicts"][0]
    assert verdict["final_verdict_ready"] is True


def test_autosci_web_visualization_compatibility_tools_generate_graph_artifacts(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir()
    (wiki_root / "graph").mkdir()
    (wiki_root / "papers/skillgen.md").write_text("# SkillGen\n\nGenerated skill paper.\n", encoding="utf-8")
    (wiki_root / "ideas/idea-001.md").write_text("# Idea 001\n\nEvaluate generated skills.\n", encoding="utf-8")
    (wiki_root / "graph/edges.jsonl").write_text(
        json.dumps(
            {
                "source": "papers/skillgen.md",
                "target": "ideas/idea-001.md",
                "relation": "inspires",
                "operation": "confirm",
                "evidence_ids": ["paper:skillgen"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert (REPO / "tools/visualize.py").exists()
    assert (REPO / "tools/serve.py").exists()
    assert (REPO / "app/index.html").exists()
    assert (REPO / "app/modules/graph.js").exists()
    assert (REPO / "app/modules/main.js").exists()
    assert (REPO / "app/modules/reader.js").exists()
    assert (REPO / "app/app.css").exists()
    index_html = (REPO / "app/index.html").read_text(encoding="utf-8")
    reader_js = (REPO / "app/modules/reader.js").read_text(encoding="utf-8")
    app_css = (REPO / "app/app.css").read_text(encoding="utf-8")
    assert "OmegaWiki" in index_html
    assert "/modules/main.js" in index_html
    assert "renderTagWordCloud" in reader_js
    assert "Top tags" in reader_js
    assert ".word-cloud-section" in app_css

    obsidian = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools/visualize.py"),
            "generate-obsidian-config",
            "--wiki-root",
            str(wiki_root),
        ],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert obsidian.returncode == 0, obsidian.stderr
    assert (wiki_root / ".obsidian/graph.json").exists()

    canvas = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools/visualize.py"),
            "generate-canvas",
            "--wiki-root",
            str(wiki_root),
            "--graph-out",
            str(tmp_path / "graph.json"),
        ],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert canvas.returncode == 0, canvas.stderr
    canvas_summary = json.loads(canvas.stdout)
    assert canvas_summary["nodes"] >= 2
    assert canvas_summary["edges"] == 1
    assert (wiki_root / "graph/autosci.canvas").exists()
    graph_data = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    assert graph_data["schema"] == "autosci_web_graph.v1"
    assert len(graph_data["nodes"]) >= 2
    assert graph_data["edges"][0]["relation"] == "inspires"

    health = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools/serve.py"),
            "--wiki-root",
            str(wiki_root),
            "--health-check",
        ],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert health.returncode == 0, health.stderr
    health_payload = json.loads(health.stdout)
    assert health_payload["ok"] is True
    assert health_payload["node_count"] >= 2
    assert health_payload["edge_count"] == 1


def test_autosci_skill_shim_records_approval_runtime_contract_for_gated_actions(tmp_path: Path) -> None:
    allowlist = tmp_path / "allowlist.json"
    runtime = tmp_path / "runtime.json"
    before = tmp_path / "before-state.json"
    after = tmp_path / "after-state.json"
    allowlist.write_text(json.dumps({"commands": ["browser-render-poster"]}), encoding="utf-8")
    runtime.write_text(
        json.dumps(
            {
                "exit_code": 0,
                "browser_rendered": True,
                "overflow_probe": "passed",
                "png_exported": True,
                "log": "approved render completed",
            }
        ),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"poster_png": False}), encoding="utf-8")
    after.write_text(json.dumps({"poster_png": True}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$poster",
        "report-001",
        "--approval-ref",
        "approval-123",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-poster-approval-contract",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["execution_status"] == "gated"
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["approval_ref"] == "approval-123"
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    assert evidence["inputs"]["approval_ref"] == "approval-123"
    contract_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "approval_contract_json"
    )
    contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
    assert contract["approval_ref"] == "approval-123"
    assert contract["approved"] is True
    assert contract["ready_for_execution"] is True
    assert contract["execution_verified"] is True
    assert contract["semantic_runtime"]["verified"] is True
    assert contract["missing"] == []
    assert contract["side_effects"] == ["browser_render", "overflow_probe", "png_export"]

    validation_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "poster_validation_json"
    )
    validation = json.loads((tmp_path / validation_artifact["path"]).read_text(encoding="utf-8"))
    assert validation["approval_contract"]["approval_state"] == "verified"
    assert validation["runtime_semantic"]["verified"] is True
    assert validation["browser_rendered"] is True
    assert validation["png_exported"] is True


def test_autosci_skill_shim_accepts_poster_render_flag_without_execution(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$poster",
        "report-001",
        "--render",
        "--run-id",
        "shim-poster-render-flag",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "poster"
    assert summary["execution_status"] == "gated"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["render"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "build_poster"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    assert evidence["inputs"]["render_requested"] is True
    validation_artifact = next(
        artifact for artifact in evidence["artifacts"] if artifact["type"] == "poster_validation_json"
    )
    validation = json.loads((tmp_path / validation_artifact["path"]).read_text(encoding="utf-8"))
    assert validation["browser_rendered"] is False
    assert validation["png_exported"] is False


def test_autosci_skill_shim_poster_builds_native_content_from_paper_dir(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    sections = paper_dir / "sections"
    sections.mkdir(parents=True)
    (paper_dir / "main.tex").write_text(
        "\\title{SkillGen Poster Paper}\n"
        "\\author{Research Team}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\input{sections/intro}\n"
        "\\input{sections/method}\n"
        "\\input{sections/results}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (sections / "intro.tex").write_text(
        "\\section{Introduction}\nSkill generation needs source-grounded validation. This poster summarizes the motivation.\n",
        encoding="utf-8",
    )
    (sections / "method.tex").write_text(
        "\\section{Method}\nWe build a verifier-gated skill selection pipeline. The method keeps evidence ids attached.\n",
        encoding="utf-8",
    )
    (sections / "results.tex").write_text(
        "\\section{Results}\nThe baseline ablation completed successfully. The result section records the main evidence.\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$poster",
        str(paper_dir),
        "--venue",
        "ICLR 2026",
        "--no-figures",
        "--run-id",
        "shim-poster-native-content",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "poster"
    action = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    bundle_files = evidence["outputs"]["bundle"]["files"]
    file_map = {item["type"]: item["path"] for item in bundle_files}
    assert "poster_dag_json" in file_map
    assert "poster_outline_html" in file_map
    assert "poster_generation_report_json" in file_map
    assert "poster_validate_result_json" in file_map
    report = json.loads((tmp_path / file_map["poster_generation_report_json"]).read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["distillation_mode"] == "extractive_local"
    dag = json.loads((tmp_path / file_map["poster_dag_json"]).read_text(encoding="utf-8"))
    assert sum(1 for node in dag["nodes"] if node.get("level") == 1) >= 3
    html_text = (tmp_path / file_map["poster_html"]).read_text(encoding="utf-8")
    assert "SkillGen Poster Paper" in html_text
    assert "ICLR 2026" in html_text
    validation = json.loads((tmp_path / file_map["poster_validation_json"]).read_text(encoding="utf-8"))
    assert validation["content_pipeline_status"] == "completed"


def test_autosci_skill_shim_poster_attaches_review_llm_critique_boundary(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    sections = paper_dir / "sections"
    sections.mkdir(parents=True)
    (paper_dir / "main.tex").write_text(
        "\\title{SkillGen Review Poster}\n"
        "\\author{Research Team}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\input{sections/intro}\n"
        "\\input{sections/method}\n"
        "\\input{sections/results}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (sections / "intro.tex").write_text("\\section{Introduction}\nThe poster motivates source-grounded skill verification.\n", encoding="utf-8")
    (sections / "method.tex").write_text("\\section{Method}\nThe poster describes a verifier-gated content pipeline.\n", encoding="utf-8")
    (sections / "results.tex").write_text("\\section{Results}\nThe poster reports evidence-linked validation outcomes.\n", encoding="utf-8")
    review_llm = tmp_path / "poster-review-llm.json"
    review_llm.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "poster-review-llm-proof",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "score": 8.6,
                        "recommendation": "accept_with_minor_edits",
                        "focus": "poster critique/refine",
                        "evidence_ids": ["poster-review:evidence"],
                        "review_llm": {
                            "status": "completed",
                            "provider": "openai_compatible",
                            "model": "gpt-4.1-mini",
                            "evidence_ids": ["poster-review:llm"],
                        },
                    },
                    "findings": [
                        {"severity": "minor", "issue": "Clarify the method block", "recommendation": "Tighten wording"}
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$poster",
        str(paper_dir),
        "--venue",
        "ICLR 2026",
        "--no-figures",
        "--review",
        "--review-llm-evidence",
        str(review_llm),
        "--run-id",
        "shim-poster-review-llm",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    action = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    file_map = {item["type"]: item["path"] for item in evidence["outputs"]["bundle"]["files"]}
    boundary = json.loads((tmp_path / file_map["poster_review_llm_boundary_json"]).read_text(encoding="utf-8"))
    validation = json.loads((tmp_path / file_map["poster_validation_json"]).read_text(encoding="utf-8"))
    report = json.loads((tmp_path / file_map["poster_generation_report_json"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "completed"
    assert boundary["review_llm_completed"] is True
    assert validation["review_llm_completed"] is True
    assert "review_model_runtime_proof_manifest_json" in file_map
    assert all("not requested" not in item for item in report["limitations"])


def test_autosci_skill_shim_uses_semantic_runtime_evidence_for_gated_results(tmp_path: Path) -> None:
    def contract_files(
        prefix: str,
        action: str,
        runtime_payload: dict[str, object],
        *,
        after_name: str = "after.json",
    ) -> tuple[Path, Path, Path, Path]:
        allowlist = tmp_path / f"{prefix}-allowlist.json"
        runtime = tmp_path / f"{prefix}-runtime.json"
        before = tmp_path / f"{prefix}-before.json"
        after = tmp_path / after_name
        allowlist.write_text(json.dumps({"approved": True, "scope": prefix}), encoding="utf-8")
        runtime_record = {
            "action": action,
            "status": "completed",
            "approval_ref": f"approval-{prefix}",
            "command_run": f"approved-{prefix}-runtime",
            "evidence_ids": [f"runtime:{prefix}"],
            "checks": [{"check": "exit_code", "status": "ok", "detail": "exit_code=0"}],
            **runtime_payload,
        }
        runtime.write_text(
            json.dumps(
                {
                    "schema": "autosci_runtime_evidence.v1",
                    "task_id": f"task-{prefix}",
                    "sprint_id": f"sprint-{prefix}",
                    "node_id": f"node-{prefix}",
                    "status": "completed",
                    "inputs": {"approval_ref": f"approval-{prefix}"},
                    "outputs": {"runtime": runtime_record},
                    "artifacts": [{"type": "runtime_after", "path": str(after)}],
                    "provenance": {
                        "operator_id": "test",
                        "implementation_package": "test",
                        "timestamp": "2026-06-24T00:00:00Z",
                    },
                    "limitations": ["Approved runtime evidence was supplied by the test fixture."],
                }
            ),
            encoding="utf-8",
        )
        before.write_text(json.dumps({"before": prefix}), encoding="utf-8")
        if after.suffix == ".pdf":
            after.write_bytes(MINIMAL_STRUCTURAL_PDF)
        else:
            after.write_text(json.dumps({"after": prefix}), encoding="utf-8")
        return allowlist, runtime, before, after

    allowlist, runtime, before, after = contract_files(
        "daily",
        "daily_arxiv_prepare_finalize",
        {
            "exit_code": 0,
            "candidates": [
                {
                    "arxiv_id": "2606.12345",
                    "title": "Runtime Verified Agent Discovery",
                    "candidate_id": "2606.12345",
                    "source_channels": ["arxiv"],
                    "ranking_score": 1.0,
                    "ranking_rationale": "Approved arXiv runtime fetch returned this candidate.",
                    "dedup_status": "unknown",
                    "fetch_status": "fetched",
                }
            ],
        },
    )
    daily = run_shim(
        tmp_path,
        "$daily-arxiv",
        "agents",
        "--approval-ref",
        "approval-daily",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-daily-runtime-verified",
    )
    assert daily.returncode == 0, daily.stderr
    daily_summary = json.loads(daily.stdout)
    daily_action = json.loads(Path(daily_summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"][0]
    assert daily_action["status"] == "passed"
    daily_evidence = json.loads(Path(daily_action["evidence_path"]).read_text(encoding="utf-8"))
    assert daily_evidence["status"] == "completed"
    assert daily_evidence["outputs"]["candidates"][0]["title"] == "Runtime Verified Agent Discovery"
    daily_contract = json.loads(
        (
            tmp_path
            / next(artifact for artifact in daily_evidence["artifacts"] if artifact["type"] == "approval_contract_json")["path"]
        ).read_text(encoding="utf-8")
    )
    assert daily_contract["semantic_runtime"]["verified"] is True

    allowlist, runtime, before, after = contract_files(
        "pilot",
        "run_pilot_experiment",
        {
            "exit_code": 0,
            "outcome": "supports",
            "result_collected": True,
            "metrics": [{"name": "accuracy", "value": 0.91}],
        },
    )
    pilot = run_shim(
        tmp_path,
        "$exp-pilot-run",
        "pilot-001",
        "--approval-ref",
        "approval-pilot",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--execute-approved",
        "--run-id",
        "shim-pilot-runtime-verified",
    )
    assert pilot.returncode == 0, pilot.stderr
    pilot_summary = json.loads(pilot.stdout)
    pilot_action = json.loads(Path(pilot_summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"][0]
    assert pilot_action["status"] == "passed"
    pilot_evidence = json.loads(Path(pilot_action["evidence_path"]).read_text(encoding="utf-8"))
    assert pilot_evidence["status"] == "completed"
    assert pilot_evidence["outputs"]["result"]["outcome"] == "supports"
    assert pilot_evidence["outputs"]["result"]["metrics"] == [{"name": "accuracy", "value": 0.91}]
    pilot_boundary = pilot_evidence["outputs"]["result"]["pilot_final_acceptance_boundary"]
    assert pilot_boundary["stage"] == "pilot_run"
    assert pilot_boundary["status"] == "pilot_runtime_ready"
    assert pilot_boundary["pilot_runtime_ready"] is True
    assert pilot_boundary["final_pilot_acceptance_ready"] is False
    assert pilot_boundary["pilot_verdict_ready"] is False
    assert pilot_boundary["writeback_completed"] is False
    assert "exp-pilot-eval" in pilot_boundary["limitations"][0]
    assert any(artifact["type"] == "pilot_run_final_acceptance_boundary_json" for artifact in pilot_evidence["artifacts"])
    pilot_artifacts = {artifact["type"]: artifact["path"] for artifact in pilot_evidence["artifacts"]}
    assert "approval_runtime_proof_manifest_json" in pilot_artifacts
    assert "side_effect_runtime_proof_manifest_json" in pilot_artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" not in pilot_artifacts
    assert "wiki_experiment_state" not in pilot_artifacts
    pilot_approval_proof = json.loads((tmp_path / pilot_artifacts["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    pilot_side_effect_proof = json.loads((tmp_path / pilot_artifacts["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert pilot_approval_proof["proofs"][0]["native_skill"] == "exp-pilot-run"
    assert pilot_approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert pilot_side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]

    paper_dir = tmp_path / "runtime-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nRuntime verified compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    allowlist, runtime, before, after = contract_files(
        "compile",
        "compile_paper",
        {"exit_code": 0, "pdf_generated": True, "pdf_path": str(tmp_path / "compiled-runtime.pdf")},
        after_name="compiled-runtime.pdf",
    )
    compile_proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--approval-ref",
        "approval-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--runtime-evidence",
        str(runtime),
        "--before-artifact",
        str(before),
        "--after-artifact",
        str(after),
        "--run-id",
        "shim-paper-compile-runtime-verified",
    )
    assert compile_proc.returncode == 0, compile_proc.stderr
    compile_summary = json.loads(compile_proc.stdout)
    compile_action = json.loads(Path(compile_summary["evidence_path"]).read_text(encoding="utf-8"))["outputs"]["skill_run"]["actions"][0]
    assert compile_action["status"] == "passed"
    compile_evidence = json.loads(Path(compile_action["evidence_path"]).read_text(encoding="utf-8"))
    assert compile_evidence["status"] == "completed"
    checklist_artifact = next(
        artifact for artifact in compile_evidence["artifacts"] if artifact["type"] == "paper_compile_checklist_json"
    )
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["runtime_semantic"]["verified"] is True
    assert any(row["check"] == "runtime_semantic_verified" and row["status"] == "ok" for row in checklist["checks"])
    compile_artifacts = {artifact["type"]: artifact["path"] for artifact in compile_evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in compile_artifacts
    proof = json.loads((tmp_path / compile_artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "paper-compile"
    assert proof_entry["categories"] == [
        "external_runtime_evidence",
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "provider_source_evidence",
    ]
    assert proof_entry["collection_mode"] == "approved_side_effect"


def test_autosci_skill_shim_executes_approved_paper_compile_executor(tmp_path: Path) -> None:
    paper_dir = tmp_path / "approved-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nApproved executor compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_latexmk = fake_bin / "latexmk"
    fake_latexmk.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path('main.pdf').write_bytes({MINIMAL_STRUCTURAL_PDF!r})\n"
        "print('fake latexmk completed')\n",
        encoding="utf-8",
    )
    fake_latexmk.chmod(0o755)
    allowlist = tmp_path / "compile-allowlist.json"
    before = tmp_path / "compile-before.json"
    allowlist.write_text(json.dumps({"executables": ["latexmk"]}), encoding="utf-8")
    before.write_text(json.dumps({"paper_dir": str(paper_dir), "pdf_exists": False}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--approval-ref",
        "approval-execute-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-paper-compile-executor",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    bundle_files = evidence["outputs"]["bundle"]["files"]
    assert any(item["type"] == "compiled_pdf" and item["path"].endswith("main.pdf") for item in bundle_files)
    assert any(item["type"] == "compile_runtime_evidence_json" for item in bundle_files)
    checklist_artifact = next(item for item in bundle_files if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["runtime_semantic"]["verified"] is True
    assert checklist["approval_contract"]["semantic_runtime"]["verified"] is True
    assert "approved side-effect executor" in " ".join(evidence["limitations"])
    report_artifact = next(item for item in bundle_files if item["type"] == "paper_compile_report_json")
    report = json.loads((tmp_path / report_artifact["path"]).read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["toolchain"]["selected_executor"] == "latexmk"
    assert report["execution"]["runtime_semantic_verified"] is True
    assert report["pdf"]["compiled_pdf_verified"] is True


def test_autosci_skill_shim_paper_compile_parity_demo_auto_executes_executor(tmp_path: Path) -> None:
    paper_dir = tmp_path / "parity-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nParity demo compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_latexmk = fake_bin / "latexmk"
    fake_latexmk.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path('main.pdf').write_bytes({MINIMAL_STRUCTURAL_PDF!r})\n"
        "print('fake parity latexmk completed')\n",
        encoding="utf-8",
    )
    fake_latexmk.chmod(0o755)

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-paper-compile-parity-demo-executor",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:compile_paper:")
    bundle_files = evidence["outputs"]["bundle"]["files"]
    file_map = {item["type"]: item["path"] for item in bundle_files}
    assert "gate_policy_decision_json" in file_map
    assert "gate_policy_allowlist_json" in file_map
    assert "compile_runtime_evidence_json" in file_map
    assert any(item["type"] == "compiled_pdf" and item["path"].endswith("main.pdf") for item in bundle_files)
    checklist = json.loads((tmp_path / file_map["paper_compile_checklist_json"]).read_text(encoding="utf-8"))
    assert checklist["toolchain"]["selected_executor"] == "latexmk"
    assert checklist["runtime_semantic"]["verified"] is True
    contract = checklist["approval_contract"]
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:compile_paper:")
    allowlist_sidecar = json.loads((tmp_path / file_map["gate_policy_allowlist_json"]).read_text(encoding="utf-8"))
    assert "latexmk" in allowlist_sidecar["executables"]


def test_autosci_skill_shim_rejects_invalid_paper_compile_pdf(tmp_path: Path) -> None:
    paper_dir = tmp_path / "invalid-pdf-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nInvalid PDF executor compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_latexmk = fake_bin / "latexmk"
    fake_latexmk.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "Path('main.pdf').write_text('%PDF-1.4\\n', encoding='utf-8')\n"
        "print('fake latexmk emitted invalid pdf')\n",
        encoding="utf-8",
    )
    fake_latexmk.chmod(0o755)
    allowlist = tmp_path / "compile-allowlist.json"
    before = tmp_path / "compile-before.json"
    allowlist.write_text(json.dumps({"executables": ["latexmk"]}), encoding="utf-8")
    before.write_text(json.dumps({"paper_dir": str(paper_dir), "pdf_exists": False}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--approval-ref",
        "approval-invalid-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-paper-compile-invalid-pdf",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    assert not any(item["type"] == "compiled_pdf" for item in evidence["outputs"]["bundle"]["files"])
    checklist_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json"
    )
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["runtime_semantic"]["verified"] is False
    assert checklist["runtime_semantic"]["detail"]["pdf_integrity"][0]["valid"] is False
    assert checklist["verified_pdf_files"] == []
    assert action["status"] == "schema_only"


def test_autosci_skill_shim_executes_approved_paper_compile_with_pdflatex_fallback(tmp_path: Path) -> None:
    paper_dir = tmp_path / "approved-pdflatex-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nApproved pdflatex fallback compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_pdflatex = fake_bin / "pdflatex"
    fake_pdflatex.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path('main.pdf').write_bytes({MINIMAL_STRUCTURAL_PDF!r})\n"
        "print('fake pdflatex completed')\n",
        encoding="utf-8",
    )
    fake_pdflatex.chmod(0o755)
    allowlist = tmp_path / "compile-pdflatex-allowlist.json"
    before = tmp_path / "compile-pdflatex-before.json"
    allowlist.write_text(json.dumps({"executables": ["pdflatex"]}), encoding="utf-8")
    before.write_text(json.dumps({"paper_dir": str(paper_dir), "pdf_exists": False}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--approval-ref",
        "approval-execute-pdflatex-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-paper-compile-pdflatex-executor",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    checklist_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json"
    )
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["toolchain"]["selected_executor"] == "pdflatex"
    assert checklist["runtime_semantic"]["verified"] is True
    runtime_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "compile_runtime_evidence_json"
    )
    runtime = json.loads((tmp_path / runtime_artifact["path"]).read_text(encoding="utf-8"))
    assert runtime["outputs"]["runtime"]["tex_executor"] == "pdflatex"
    assert "paper-compile-runtime:pdflatex" in runtime["outputs"]["runtime"]["evidence_ids"]


def test_autosci_skill_shim_paper_compile_missing_tool_inconclusive(tmp_path: Path) -> None:
    paper_dir = tmp_path / "missing-tool-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nMissing tool compile.\n\\end{document}\n",
        encoding="utf-8",
    )
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    allowlist = tmp_path / "compile-missing-tool-allowlist.json"
    before = tmp_path / "compile-missing-tool-before.json"
    allowlist.write_text(
        json.dumps({"executables": ["latexmk", "pdflatex", "xelatex", "lualatex"]}),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"paper_dir": str(paper_dir), "pdf_exists": False}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--approval-ref",
        "approval-missing-tex-tool",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-paper-compile-missing-tool",
        extra_env={"PATH": str(empty_path)},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    assert action["status"] == "schema_only"
    bundle_files = evidence["outputs"]["bundle"]["files"]
    assert not any(item["type"] == "compiled_pdf" for item in bundle_files)
    checklist_artifact = next(item for item in bundle_files if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    assert checklist["toolchain"]["tex_executors"] == {}
    assert checklist["toolchain"]["selected_executor"] == ""
    assert any(row["check"] == "tex_executor_available" and row["status"] == "warn" for row in checklist["checks"])
    runtime_artifact = next(item for item in bundle_files if item["type"] == "compile_runtime_evidence_json")
    runtime = json.loads((tmp_path / runtime_artifact["path"]).read_text(encoding="utf-8"))
    assert runtime["outputs"]["runtime"]["status"] == "inconclusive"
    assert runtime["outputs"]["runtime"]["available_tex_executors"] == []
    assert any(
        row["check"] == "tex_executor_available" and row["status"] == "error"
        for row in runtime["outputs"]["runtime"]["checks"]
    )
    report_artifact = next(item for item in bundle_files if item["type"] == "paper_compile_report_json")
    report = json.loads((tmp_path / report_artifact["path"]).read_text(encoding="utf-8"))
    assert report["status"] == "inconclusive"
    assert report["toolchain"]["available_tex_executors"] == []
    assert report["toolchain"]["selected_executor"] == ""
    assert report["execution"]["runtime_semantic_verified"] is False


def test_autosci_skill_shim_executes_approved_poster_executor(tmp_path: Path) -> None:
    paper_dir = tmp_path / "poster-paper"
    sections = paper_dir / "sections"
    sections.mkdir(parents=True)
    (paper_dir / "main.tex").write_text(
        "\\title{Approved Poster Executor}\n"
        "\\author{Research Team}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\input{sections/intro}\n"
        "\\input{sections/method}\n"
        "\\input{sections/results}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (sections / "intro.tex").write_text("\\section{Introduction}\nApproved poster rendering needs native HTML.\n", encoding="utf-8")
    (sections / "method.tex").write_text("\\section{Method}\nThe bridge builds poster content from paper source.\n", encoding="utf-8")
    (sections / "results.tex").write_text("\\section{Results}\nThe renderer exports a verified PNG.\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_renderer = fake_bin / "poster-renderer"
    fake_renderer.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "html, png, validation = sys.argv[1:4]\n"
        "assert Path(html).exists()\n"
        "Path(png).write_bytes(b'\\x89PNG\\r\\n\\x1a\\n')\n"
        "Path(validation).write_text(json.dumps({\n"
        "  'browser_rendered': True,\n"
        "  'png_exported': True,\n"
        "  'overflow_probe': 'passed'\n"
        "}), encoding='utf-8')\n"
        "print('fake poster renderer completed')\n",
        encoding="utf-8",
    )
    fake_renderer.chmod(0o755)
    allowlist = tmp_path / "poster-allowlist.json"
    before = tmp_path / "poster-before.json"
    allowlist.write_text(
        json.dumps({"poster_render_command": [str(fake_renderer), "{html}", "{png}", "{validation}"]}),
        encoding="utf-8",
    )
    before.write_text(json.dumps({"poster_png": False}), encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$poster",
        str(paper_dir),
        "--approval-ref",
        "approval-execute-poster",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--execute-approved",
        "--run-id",
        "shim-poster-executor",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "build_poster"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    bundle_files = evidence["outputs"]["bundle"]["files"]
    assert any(item["type"] == "poster_runtime_evidence_json" for item in bundle_files)
    assert any(item["type"] == "poster_runtime_after_artifact" and item["path"].endswith("poster.png") for item in bundle_files)
    file_map = {item["type"]: item["path"] for item in bundle_files}
    assert "approval_runtime_proof_manifest_json" in file_map
    assert "side_effect_runtime_proof_manifest_json" in file_map
    assert "provider_source_runtime_proof_manifest_json" not in file_map
    assert "wiki_mutation_runtime_proof_manifest_json" not in file_map
    validation_artifact = next(item for item in bundle_files if item["type"] == "poster_validation_json")
    validation = json.loads((tmp_path / validation_artifact["path"]).read_text(encoding="utf-8"))
    assert validation["runtime_semantic"]["verified"] is True
    assert validation["browser_rendered"] is True
    assert validation["png_exported"] is True
    contract_artifact = next(item for item in bundle_files if item["type"] == "approval_contract_json")
    contract = json.loads((tmp_path / contract_artifact["path"]).read_text(encoding="utf-8"))
    approval_proof = json.loads((tmp_path / file_map["approval_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    side_effect_proof = json.loads((tmp_path / file_map["side_effect_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    assert contract["semantic_runtime"]["verified"] is True
    assert approval_proof["proofs"][0]["native_skill"] == "poster"
    assert approval_proof["proofs"][0]["categories"] == ["external_runtime_evidence", "approval_boundary_evidence"]
    assert side_effect_proof["proofs"][0]["categories"] == ["side_effect_execution_evidence"]
    assert "approved side-effect executor" in " ".join(evidence["limitations"])


def test_autosci_skill_shim_poster_parity_demo_auto_executes_renderer(tmp_path: Path) -> None:
    paper_dir = tmp_path / "poster-parity-paper"
    sections = paper_dir / "sections"
    sections.mkdir(parents=True)
    (paper_dir / "main.tex").write_text(
        "\\title{Parity Poster Executor}\n"
        "\\author{Research Team}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\input{sections/intro}\n"
        "\\input{sections/method}\n"
        "\\input{sections/results}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    (sections / "intro.tex").write_text("\\section{Introduction}\nParity poster rendering needs native HTML.\n", encoding="utf-8")
    (sections / "method.tex").write_text("\\section{Method}\nThe bridge builds poster content from paper source.\n", encoding="utf-8")
    (sections / "results.tex").write_text("\\section{Results}\nThe renderer exports a verified PNG.\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_renderer = fake_bin / "poster-renderer"
    fake_renderer.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "html, png, validation = sys.argv[1:4]\n"
        "assert Path(html).exists()\n"
        "Path(png).write_bytes(b'\\x89PNG\\r\\n\\x1a\\n')\n"
        "Path(validation).write_text(json.dumps({\n"
        "  'browser_rendered': True,\n"
        "  'png_exported': True,\n"
        "  'overflow_probe': 'passed'\n"
        "}), encoding='utf-8')\n"
        "print('fake parity poster renderer completed')\n",
        encoding="utf-8",
    )
    fake_renderer.chmod(0o755)
    allowlist = tmp_path / "poster-parity-allowlist.json"
    allowlist.write_text(
        json.dumps({"poster_render_command": [str(fake_renderer), "{html}", "{png}", "{validation}"]}),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$poster",
        str(paper_dir),
        "--allowlist-evidence",
        str(allowlist),
        "--gate-mode",
        "parity_demo",
        "--run-id",
        "shim-poster-parity-demo-renderer",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "build_poster"
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    policy = evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "parity_demo"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:parity_demo:build_poster:")
    bundle_files = evidence["outputs"]["bundle"]["files"]
    file_map = {item["type"]: item["path"] for item in bundle_files}
    assert "gate_policy_decision_json" in file_map
    assert "poster_runtime_evidence_json" in file_map
    assert "poster_runtime_after_artifact" in file_map
    validation = json.loads((tmp_path / file_map["poster_validation_json"]).read_text(encoding="utf-8"))
    assert validation["runtime_semantic"]["verified"] is True
    contract = json.loads((tmp_path / file_map["approval_contract_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["approval_ref"].startswith("policy:auto:parity_demo:build_poster:")


def test_autosci_skill_shim_accepts_paper_compile_checklist_without_bundle_fallback(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nSkillGen paper draft.\n\\end{document}\n",
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--run-id",
        "shim-paper-compile-native",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "paper-compile"
    assert summary["execution_status"] == "gated"
    assert summary["action_count"] == 1
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == str(paper_dir)
    assert payload["inputs"]["native_options"]["checklist"] is True
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "compile_paper"
    assert action["schema"] == "publication_bundle.v1"
    assert action["gate_status"] == "schema_only"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "inconclusive"
    bundle = evidence["outputs"]["bundle"]
    assert bundle["publication_type"] == "paper"
    assert any(item["type"] == "paper_compile_checklist_json" for item in bundle["files"])
    assert any(item["type"] == "paper_compile_diagnostics_markdown" for item in bundle["files"])
    assert any(item["type"] == "latex_source" for item in bundle["files"])
    assert not any(item["type"] == "compiled_pdf" for item in bundle["files"])
    checklist_path = tmp_path / "artifacts/autosci/runs/shim-paper-compile-native/paper_compile_checklist.json"
    diagnostics_path = tmp_path / "artifacts/autosci/runs/shim-paper-compile-native/paper_compile_diagnostics.md"
    assert checklist_path.exists()
    assert diagnostics_path.exists()
    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
    assert checklist["status"] == "inconclusive"
    assert checklist["latex_files"] == ["paper/main.tex"]
    assert "compiled PDF" in diagnostics_path.read_text(encoding="utf-8")


def test_autosci_skill_shim_paper_compile_checklist_records_submission_checks(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper-submission-checks"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Jane Researcher}\n"
        "\\begin{document}\n"
        "SkillGen paper draft with [UNCONFIRMED] citation note.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--run-id",
        "shim-paper-compile-submission-checks",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    checklist_artifact = next(item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    boundary_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "publication_submission_boundary_json"
    )
    boundary = json.loads((tmp_path / boundary_artifact["path"]).read_text(encoding="utf-8"))
    submission = {row["check"]: row for row in checklist["submission_checks"]}
    assert submission["unconfirmed_marker_scan"]["status"] == "warn"
    assert submission["anonymity_check"]["status"] == "warn"
    assert submission["page_limit_check"]["status"] == "warn"
    assert submission["font_size_check"]["status"] == "warn"
    assert "paper-submission-checks/main.tex" in submission["unconfirmed_marker_scan"]["evidence"]
    assert any(row["check"] == "unconfirmed_marker_scan" for row in checklist["checks"])
    assert checklist["submission_boundary"]["schema"] == "autosci_publication_submission_boundary.v1"
    assert checklist["submission_boundary"]["status"] == "submission_incomplete"
    assert checklist["submission_boundary"]["submission_ready"] is False
    assert boundary == checklist["submission_boundary"]
    assert "unconfirmed_marker_scan" in boundary["blocking_checks"]
    assert "anonymity_check" in boundary["blocking_checks"]
    assert "page_limit_check" in boundary["blocking_checks"]
    assert "font_size_check" in boundary["blocking_checks"]
    assert any(row["check"] == "publication_submission_boundary" for row in checklist["checks"])
    diagnostics_path = next(item["path"] for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_diagnostics_markdown")
    diagnostics = (tmp_path / diagnostics_path).read_text(encoding="utf-8")
    assert "Submission Checks" in diagnostics
    assert "Submission Boundary" in diagnostics
    assert "Font-size compliance is unconfirmed" in diagnostics
    assert any("Submission readiness includes warnings" in item for item in evidence["limitations"])
    assert any("does not prove submission readiness" in item for item in evidence["limitations"])


def test_autosci_skill_shim_paper_compile_submission_boundary_accepts_cli_evidence(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper-submission-ready"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "SkillGen paper draft with resolved citations.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    write_structural_pdf(paper_dir / "main.pdf")
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--anonymous",
        "--page-limit",
        "8",
        "--verified-page-count",
        "6",
        "--min-font-size",
        "10",
        "--verified-min-font-size",
        "11",
        "--run-id",
        "shim-paper-compile-submission-ready",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["anonymous"] is True
    assert payload["inputs"]["native_options"]["page_limit"] == 8.0
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    checklist_artifact = next(item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    boundary_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "publication_submission_boundary_json"
    )
    boundary = json.loads((tmp_path / boundary_artifact["path"]).read_text(encoding="utf-8"))
    assert boundary == checklist["submission_boundary"]
    assert boundary["status"] == "submission_ready"
    assert boundary["submission_ready"] is True
    assert boundary["blocking_checks"] == []
    assert boundary["check_statuses"]["unconfirmed_marker_scan"] == "ok"
    assert boundary["check_statuses"]["anonymity_check"] == "ok"
    assert boundary["check_statuses"]["page_limit_check"] == "ok"
    assert boundary["check_statuses"]["font_size_check"] == "ok"
    assert not any("does not prove submission readiness" in item for item in evidence["limitations"])


def test_autosci_skill_shim_paper_compile_submission_profile_supplies_venue_requirements(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper-submission-profile"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "SkillGen paper draft with resolved citations.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    write_structural_pdf(paper_dir / "main.pdf")
    profile = tmp_path / "iclr-submission-profile.json"
    profile.write_text(
        json.dumps(
            {
                "schema": "autosci_submission_profile.v1",
                "venue": "ICLR",
                "evidence_ids": ["venue-profile:iclr"],
                "requirements": {
                    "submission_mode": "double_blind",
                    "anonymous": True,
                    "page_limit": 8,
                    "min_font_size": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--submission-profile",
        str(profile),
        "--verified-page-count",
        "6",
        "--verified-min-font-size",
        "11",
        "--run-id",
        "shim-paper-compile-submission-profile",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["submission_profile"] == str(profile)
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    checklist_artifact = next(item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    boundary = checklist["submission_boundary"]
    assert boundary["submission_ready"] is True
    assert boundary["venue_submission_ready"] is False
    assert boundary["venue_status"] == "venue_submission_incomplete"
    assert boundary["venue_blocking_checks"] == ["pdf_inspection"]
    assert boundary["submission_profile"]["status"] == "loaded"
    assert boundary["submission_profile"]["venue"] == "ICLR"
    assert boundary["submission_profile"]["evidence_ids"] == ["venue-profile:iclr"]
    assert set(boundary["submission_profile"]["applied_fields"]) >= {
        "anonymous",
        "page_limit",
        "min_font_size",
        "submission_mode",
    }
    assert boundary["check_statuses"]["anonymity_check"] == "ok"
    assert boundary["check_statuses"]["page_limit_check"] == "ok"
    assert boundary["check_statuses"]["font_size_check"] == "ok"
    profile_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "venue_submission_profile_json"
    )
    assert profile_artifact["sha256"]
    diagnostics_path = next(
        item["path"] for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_diagnostics_markdown"
    )
    diagnostics = (tmp_path / diagnostics_path).read_text(encoding="utf-8")
    assert "venue_submission_ready: False" in diagnostics
    assert "pdf_inspection_status: missing" in diagnostics


def test_autosci_skill_shim_paper_compile_pdf_inspection_satisfies_venue_readiness(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper-pdf-inspection"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "SkillGen paper draft with resolved citations.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    pdf_path = paper_dir / "main.pdf"
    write_structural_pdf(pdf_path)
    profile = tmp_path / "iclr-pdf-profile.json"
    profile.write_text(
        json.dumps(
            {
                "schema": "autosci_submission_profile.v1",
                "venue": "ICLR",
                "evidence_ids": ["venue-profile:iclr"],
                "requirements": {
                    "submission_mode": "double_blind",
                    "anonymous": True,
                    "page_limit": 8,
                    "min_font_size": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    inspection = tmp_path / "pdf-inspection.json"
    inspection.write_text(
        json.dumps(
            {
                "schema": "autosci_pdf_inspection.v1",
                "status": "completed",
                "evidence_ids": ["pdf-inspection:main"],
                "outputs": {
                    "inspection": {
                        "pdf_path": str(pdf_path),
                        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        "page_count": 6,
                        "min_font_size": 11,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--submission-profile",
        str(profile),
        "--pdf-inspection",
        str(inspection),
        "--run-id",
        "shim-paper-compile-pdf-inspection",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["pdf_inspection"] == str(inspection)
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    checklist_artifact = next(item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    boundary = checklist["submission_boundary"]
    assert boundary["submission_ready"] is True
    assert boundary["venue_submission_ready"] is True
    assert boundary["venue_status"] == "venue_submission_ready"
    assert boundary["venue_blocking_checks"] == []
    assert boundary["pdf_inspection"]["status"] == "loaded"
    assert boundary["pdf_inspection"]["evidence_ids"] == ["pdf-inspection:main"]
    assert set(boundary["pdf_inspection"]["applied_fields"]) == {
        "verified_page_count",
        "verified_min_font_size",
    }
    assert boundary["check_statuses"]["page_limit_check"] == "ok"
    assert boundary["check_statuses"]["font_size_check"] == "ok"
    inspection_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "pdf_inspection_json"
    )
    assert inspection_artifact["sha256"]
    diagnostics_path = next(
        item["path"] for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_diagnostics_markdown"
    )
    diagnostics = (tmp_path / diagnostics_path).read_text(encoding="utf-8")
    assert "venue_submission_ready: True" in diagnostics
    assert "pdf_inspection_status: loaded" in diagnostics


def test_autosci_skill_shim_paper_compile_submission_audit_marks_audit_ready(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper-submission-audit"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "SkillGen paper draft with resolved citations.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    pdf_path = paper_dir / "main.pdf"
    write_structural_pdf(pdf_path)
    profile = tmp_path / "audit-profile.json"
    profile.write_text(
        json.dumps(
            {
                "schema": "autosci_submission_profile.v1",
                "venue": "ICLR",
                "evidence_ids": ["venue-profile:iclr"],
                "requirements": {
                    "submission_mode": "double_blind",
                    "anonymous": True,
                    "page_limit": 8,
                    "min_font_size": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    inspection = tmp_path / "audit-pdf-inspection.json"
    inspection.write_text(
        json.dumps(
            {
                "schema": "autosci_pdf_inspection.v1",
                "status": "completed",
                "evidence_ids": ["pdf-inspection:audit-main"],
                "outputs": {
                    "inspection": {
                        "pdf_path": str(pdf_path),
                        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        "page_count": 6,
                        "min_font_size": 11,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    audit = tmp_path / "submission-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_publication_submission_audit.v1",
                "status": "completed",
                "evidence_ids": ["submission-audit:iclr"],
                "outputs": {
                    "audit": {
                        "venue": "ICLR",
                        "submission_ready": True,
                        "portal_submission_completed": False,
                        "checks": [
                            {"check": "anonymity", "status": "ok"},
                            {"check": "page_limit", "status": "ok"},
                            {"check": "font_size", "status": "ok"},
                            {"check": "unconfirmed_markers", "status": "ok"},
                        ],
                        "blocking_checks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--submission-profile",
        str(profile),
        "--pdf-inspection",
        str(inspection),
        "--submission-audit",
        str(audit),
        "--run-id",
        "shim-paper-compile-submission-audit",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["submission_audit"] == str(audit)
    action = payload["outputs"]["skill_run"]["actions"][0]
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    checklist_artifact = next(item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    boundary = checklist["submission_boundary"]
    assert boundary["venue_submission_ready"] is True
    assert boundary["submission_audit_ready"] is True
    assert boundary["submission_audit_status"] == "submission_audit_ready"
    assert boundary["submission_audit_blocking_checks"] == []
    assert boundary["portal_submission_completed"] is False
    assert boundary["submission_audit"]["status"] == "loaded"
    assert boundary["submission_audit"]["audit_verified"] is True
    assert boundary["submission_audit"]["evidence_ids"] == ["submission-audit:iclr"]
    audit_artifact = next(
        item for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "publication_submission_audit_json"
    )
    assert audit_artifact["sha256"]
    diagnostics_path = next(
        item["path"] for item in evidence["outputs"]["bundle"]["files"] if item["type"] == "paper_compile_diagnostics_markdown"
    )
    diagnostics = (tmp_path / diagnostics_path).read_text(encoding="utf-8")
    assert "submission_audit_ready: True" in diagnostics
    assert "portal_submission_completed: False" in diagnostics


def test_autosci_skill_shim_paper_compile_approved_runtime_submission_audit_closes_boundaries(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper-runtime-submission-audit"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "SkillGen paper draft with approved compile and submission audit.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_latexmk = fake_bin / "latexmk"
    fake_latexmk.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path('main.pdf').write_bytes({MINIMAL_STRUCTURAL_PDF!r})\n"
        "print('fake audited latexmk completed')\n",
        encoding="utf-8",
    )
    fake_latexmk.chmod(0o755)
    allowlist = tmp_path / "runtime-audit-compile-allowlist.json"
    before = tmp_path / "runtime-audit-compile-before.json"
    allowlist.write_text(json.dumps({"executables": ["latexmk"]}), encoding="utf-8")
    before.write_text(json.dumps({"paper_dir": str(paper_dir), "pdf_exists": False}), encoding="utf-8")
    profile = tmp_path / "runtime-audit-profile.json"
    profile.write_text(
        json.dumps(
            {
                "schema": "autosci_submission_profile.v1",
                "venue": "ICLR",
                "evidence_ids": ["venue-profile:runtime-audit"],
                "requirements": {
                    "submission_mode": "double_blind",
                    "anonymous": True,
                    "page_limit": 8,
                    "min_font_size": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    pdf_path = paper_dir / "main.pdf"
    inspection = tmp_path / "runtime-audit-pdf-inspection.json"
    inspection.write_text(
        json.dumps(
            {
                "schema": "autosci_pdf_inspection.v1",
                "status": "completed",
                "evidence_ids": ["pdf-inspection:runtime-audit-main"],
                "outputs": {
                    "inspection": {
                        "pdf_path": str(pdf_path),
                        "page_count": 6,
                        "min_font_size": 11,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    audit = tmp_path / "runtime-audit-submission-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_publication_submission_audit.v1",
                "status": "completed",
                "evidence_ids": ["submission-audit:runtime-audit"],
                "outputs": {
                    "audit": {
                        "venue": "ICLR",
                        "submission_ready": True,
                        "portal_submission_completed": False,
                        "checks": [
                            {"check": "anonymity", "status": "ok"},
                            {"check": "page_limit", "status": "ok"},
                            {"check": "font_size", "status": "ok"},
                            {"check": "unconfirmed_markers", "status": "ok"},
                        ],
                        "blocking_checks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$paper-compile",
        str(paper_dir),
        "--checklist",
        "--approval-ref",
        "approval-runtime-submission-audit-compile",
        "--allowlist-evidence",
        str(allowlist),
        "--before-artifact",
        str(before),
        "--submission-profile",
        str(profile),
        "--pdf-inspection",
        str(inspection),
        "--submission-audit",
        str(audit),
        "--execute-approved",
        "--run-id",
        "shim-paper-compile-runtime-submission-audit",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["status"] == "passed"
    evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["status"] == "completed"
    bundle_files = evidence["outputs"]["bundle"]["files"]
    assert any(item["type"] == "compiled_pdf" and item["path"].endswith("main.pdf") for item in bundle_files)
    assert any(item["type"] == "compile_runtime_evidence_json" for item in bundle_files)
    assert any(item["type"] == "publication_submission_audit_json" for item in bundle_files)

    checklist_artifact = next(item for item in bundle_files if item["type"] == "paper_compile_checklist_json")
    checklist = json.loads((tmp_path / checklist_artifact["path"]).read_text(encoding="utf-8"))
    boundary = checklist["submission_boundary"]
    assert checklist["runtime_semantic"]["verified"] is True
    assert checklist["approval_contract"]["execution_verified"] is True
    assert boundary["venue_submission_ready"] is True
    assert boundary["submission_audit_ready"] is True
    assert boundary["venue_status"] == "venue_submission_ready"
    assert boundary["submission_audit_status"] == "submission_audit_ready"
    assert boundary["submission_audit_blocking_checks"] == []
    assert boundary["portal_submission_completed"] is False
    assert boundary["check_statuses"]["page_limit_check"] == "ok"
    assert boundary["check_statuses"]["font_size_check"] == "ok"

    artifacts = {artifact["type"]: artifact["path"] for artifact in evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "paper-compile"
    assert proof_entry["collection_mode"] == "approved_side_effect"
    assert proof_entry["categories"] == [
        "external_runtime_evidence",
        "approval_boundary_evidence",
        "side_effect_execution_evidence",
        "provider_source_evidence",
    ]
    diagnostics_path = next(
        item["path"] for item in bundle_files if item["type"] == "paper_compile_diagnostics_markdown"
    )
    diagnostics = (tmp_path / diagnostics_path).read_text(encoding="utf-8")
    assert "| runtime_semantic_verified | ok |" in diagnostics
    assert "venue_submission_ready: True" in diagnostics
    assert "submission_audit_ready: True" in diagnostics


def test_autosci_skill_shim_runs_ideate_from_wiki_and_discovery_sources(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\nSkill generation exposes an inference-time adaptation gap.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/adaptation.md").write_text(
        "---\ntitle: Inference-Time Adaptation\n---\n# Inference-Time Adaptation\n\nA reusable method with open evaluation questions.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/verifier.md").write_text(
        "---\ntitle: Verifier-Gated Skill Selection\n---\n# Verifier-Gated Skill Selection\n\nA method with complementary robustness tradeoffs.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/open_questions.md").write_text(
        "# Open Questions\n\n- How should generated skills be validated against baseline tools?\n",
        encoding="utf-8",
    )
    discovery_dir = tmp_path / "artifacts/autosci/runs/discover-seed"
    discovery_dir.mkdir(parents=True)
    discovery_path = discovery_dir / "literature_discovery.json"
    discovery_path.write_text(
        json.dumps(
            {
                "schema": "literature_discovery.v1",
                "task_id": "discover-seed",
                "sprint_id": "test",
                "node_id": "discover",
                "status": "completed",
                "inputs": {},
                "outputs": {
                    "candidates": [
                        {
                            "paper_id": "paper-discovery-001",
                            "title": "Recent Agent Skill Adaptation",
                            "summary": "A recent paper about adapting agent skills at inference time.",
                        }
                    ]
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--discovery-evidence",
        str(discovery_path),
        "--max-ideas",
        "2",
        "--run-id",
        "shim-ideate-real-sources",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ideate"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["target"] == "agent skill learning"
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    evaluation_evidence = json.loads(Path(actions[1]["evidence_path"]).read_text(encoding="utf-8"))
    ideas = idea_evidence["outputs"]["ideas"]
    assert ideas
    assert sum(1 for idea in ideas if idea["selected_for_write"] is True) == 2
    assert any(idea.get("selection_reason") == "Not selected because max_ideas=2 was reached." for idea in ideas)
    assert ideas[0]["source_mode"] == "mixed"
    assert ideas[0]["promotion_ready"] is False
    assert ideas[0]["final_promotion_boundary"]["status"] == "idea_promotion_incomplete"
    assert all("fixture" not in json.dumps(idea).lower() for idea in ideas)
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    assert "ideate_final_promotion_boundary_json" in artifacts
    assert "ideate_growth_report_json" in artifacts
    assert "provider_source_runtime_proof_manifest_json" in artifacts
    boundary = json.loads((tmp_path / artifacts["ideate_final_promotion_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["schema"] == "autosci_ideate_final_promotion_boundary.v1"
    assert boundary["status"] == "ideate_promotion_incomplete"
    assert boundary["source_evidence_ready"] is True
    assert boundary["failed_idea_banlist_checked"] is True
    assert boundary["novelty_review_gate_references_present"] is False
    assert boundary["generation_path_coverage"]["present_paths"] == ["A", "B", "C", "D", "E"]
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    assert pipeline_report["schema"] == "autosci_ideate_pipeline_report.v1"
    assert pipeline_report["status"] == "incomplete"
    assert pipeline_report["max_ideas"] == 2
    assert pipeline_report["selected_for_write_count"] == 2
    assert pipeline_report["generation_path_coverage"]["status"] == "complete"
    assert pipeline_report["generation_path_coverage"]["missing_paths"] == []
    growth_report = json.loads((tmp_path / artifacts["ideate_growth_report_json"]).read_text(encoding="utf-8"))
    assert growth_report["schema"] == "autosci_ideate_growth_report.v1"
    assert growth_report["candidate_count"] == len(ideas)
    assert growth_report["selected_for_write_count"] == 2
    assert growth_report["writeback"]["requested"] is False
    assert growth_report["writeback"]["actual_wiki_idea_write_count"] == 0
    assert growth_report["wiki_scan"]["source_mode"] == "mixed"
    source_proof = json.loads((tmp_path / artifacts["provider_source_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "ideate"
    assert source_proof_entry["categories"] == ["provider_source_evidence"]
    assert source_proof_entry["collection_mode"] == "manual_review"
    assert not any(category == "external_runtime_evidence" for category in source_proof_entry["categories"])
    assert any(ref.endswith("methods/adaptation.md") for ref in source_proof_entry["evidence_refs"])
    assert any(ref.endswith("literature_discovery.json") for ref in source_proof_entry["evidence_refs"])
    assert any(ref.endswith("ideate_growth_report.json") for ref in source_proof_entry["evidence_refs"])
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["recommendation"] in {"advance", "revise"}
    assert evaluation["review_mode"] == "local_surrogate"
    assert evaluation["review_available"] is False
    assert evaluation["closest_prior_work"]
    assert evaluation["review_score"] != "N/A"


def test_autosci_skill_shim_ideate_active_idea_dedup_filters_duplicate(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\nSkill generation exposes an inference-time adaptation gap.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/adaptation.md").write_text(
        "---\ntitle: Inference-Time Adaptation\n---\n# Inference-Time Adaptation\n\nA reusable method with open evaluation questions.\n",
        encoding="utf-8",
    )
    (wiki_root / "ideas/existing-agent-skill-gap.md").write_text(
        "\n".join(
            [
                "---",
                "idea_id: idea-existing-agent-skill-gap",
                "slug: existing-agent-skill-gap",
                "title: Close the evidence gap around agent skill learning",
                "status: proposed",
                "---",
                "# Close the evidence gap around agent skill learning",
                "",
                "An active idea already covers this agent skill learning evidence gap.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (wiki_root / "graph/open_questions.md").write_text(
        "# Open Questions\n\n- How should generated skills be validated against baseline tools?\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--wiki-root",
        str(wiki_root),
        "--skip-validation",
        "--skip-pilot",
        "--run-id",
        "shim-ideate-active-dedup",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    idea_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    ideas = idea_evidence["outputs"]["ideas"]
    duplicate = next(idea for idea in ideas if idea["idea_id"] == "idea-wiki-discovery-001")
    assert duplicate["status"] == "filtered"
    assert duplicate["duplicate_status"] == "duplicate"
    assert duplicate["selected_for_write"] is False
    assert "existing-agent-skill-gap" in duplicate["duplicate_of"]
    assert duplicate["promotion_ready"] is False
    assert "idea overlaps failed or duplicate idea banlist" in duplicate["final_promotion_boundary"]["blocking_reasons"]
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    boundary = json.loads((tmp_path / artifacts["ideate_final_promotion_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["active_idea_dedup_checked"] is True
    assert boundary["active_idea_count"] == 1
    growth_report = json.loads((tmp_path / artifacts["ideate_growth_report_json"]).read_text(encoding="utf-8"))
    assert growth_report["wiki_scan"]["active_idea_count"] == 1
    assert growth_report["filtered_or_blocked_count"] >= 1


def test_autosci_skill_shim_ideate_uses_model_command_for_brainstorm(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\nSkill generation exposes an inference-time adaptation gap.\n",
        encoding="utf-8",
    )
    model_command = tmp_path / "ideate_model_command.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "request = json.loads(sys.stdin.read())",
                "assert request['action'] == 'generate_ideas'",
                "assert request['context']['topic'] == 'agent skill learning'",
                "payload = {",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'Model brainstorm grounded in SkillGen paper evidence.',",
                "        'confidence': 0.72,",
                "        'provider': 'test-model-provider',",
                "        'model': 'gpt-4.1-mini-test-double',",
                "        'evidence_ids': ['wiki:papers/skillgen'],",
                "        'ideas': [",
                "            {",
                "                'idea_id': 'idea-model-skillgen-001',",
                "                'title': 'Verifier-gated skill transfer benchmark',",
                "                'hypothesis': 'Verifier-gated generated skills transfer more reliably across held-out agent tasks.',",
                "                'approach': 'Build a benchmark that compares generated skills with and without verifier gates across held-out tasks.',",
                "                'novelty_hypothesis': 'The contribution is a source-grounded transfer benchmark for generated agent skills.',",
                "                'origin_evidence_ids': ['wiki:papers/skillgen'],",
                "                'duplicate_status': 'unknown',",
                "            }",
                "        ],",
                "    },",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--run-id",
        "shim-ideate-model-command",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ideate"
    assert summary["action_count"] == 2

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    assert idea_evidence["status"] == "completed"
    idea = idea_evidence["outputs"]["ideas"][0]
    assert idea["idea_id"] == "idea-model-skillgen-001"
    assert idea["generation_path"] == "model-command"
    assert idea["model"] == "gpt-4.1-mini-test-double"
    assert "wiki:papers/skillgen" in idea["origin_evidence_ids"]
    assert idea["promotion_ready"] is False
    assert idea["final_promotion_boundary"]["status"] == "idea_promotion_incomplete"
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    artifact_types = set(artifacts)
    assert {
        "model_command_request_json",
        "model_command_stdout_json",
        "model_command_stderr",
        "model_runtime_proof_manifest_json",
    } <= artifact_types
    assert "ideate_final_promotion_boundary_json" in artifacts
    assert "ideate_pipeline_report_json" in artifacts
    request_artifact = next(item for item in idea_evidence["artifacts"] if item["type"] == "model_command_request_json")
    assert re.fullmatch(r"[a-f0-9]{64}", request_artifact["sha256"])
    request_payload = json.loads((tmp_path / request_artifact["path"]).read_text(encoding="utf-8"))
    assert request_payload["action"] == "generate_ideas"
    assert "A:landscape-driven" in request_payload["prompt"]
    assert "E:cross-domain-transfer" in request_payload["prompt"]
    boundary = json.loads((tmp_path / artifacts["ideate_final_promotion_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["model_brainstorm_completed"] is True
    assert boundary["model_name"] == "gpt-4.1-mini-test-double"
    assert boundary["final_promotion_ready"] is False
    assert boundary["generation_path_coverage"]["status"] == "missing"
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    assert pipeline_report["schema"] == "autosci_ideate_pipeline_report.v1"
    assert pipeline_report["status"] == "incomplete"
    assert pipeline_report["required_generation_paths"]["A"] == "landscape-driven"
    assert pipeline_report["generation_path_coverage"]["missing_paths"] == ["A", "B", "C", "D", "E"]
    assert "independent Review LLM brainstorm evidence is missing or incomplete" in pipeline_report["blocking_reasons"]
    proof = json.loads((tmp_path / artifacts["model_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "ideate"
    assert proof_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    assert str(Path(actions[0]["evidence_path"]).relative_to(tmp_path)) in proof_entry["evidence_refs"]
    assert "novelty/review gate evidence references are missing" in boundary["blocking_reasons"]

    evaluation_evidence = json.loads(Path(actions[1]["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["idea_id"] == "idea-model-skillgen-001"
    assert evaluation["review_mode"] == "local_surrogate"


def test_autosci_skill_shim_ideate_promotes_with_model_novelty_and_review_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\nSkill generation exposes an inference-time adaptation gap.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/adaptation.md").write_text(
        "---\ntitle: Inference-Time Adaptation\n---\n# Inference-Time Adaptation\n\nA reusable method with open evaluation questions.\n",
        encoding="utf-8",
    )
    (wiki_root / "ideas/existing-control.md").write_text(
        "---\nidea_id: idea-existing-control\nslug: existing-control\nstatus: proposed\n---\n# Existing Control\n\nA control idea keeps wiki maturity non-empty.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/open_questions.md").write_text(
        "# Open Questions\n\n- How should generated skills be validated against baseline tools?\n",
        encoding="utf-8",
    )
    external_path = tmp_path / "ideate-external-novelty.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "inputs": {"query": "agent skill learning"},
                "outputs": {
                    "sources": [
                        {
                            "id": "web:ideate-001",
                            "provider": "web",
                            "title": "Agent Skill Learning Prior Work",
                            "summary": "External novelty source for agent skill learning.",
                        },
                        {
                            "id": "web:ideate-002",
                            "provider": "web",
                            "title": "Independent Agent Skill Evaluation",
                            "summary": "Second external prior-work source for agent skill evaluation.",
                        },
                    ]
                },
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    review_path = tmp_path / "ideate-review-llm.json"
    review_path.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "ideate-review-llm",
                "sprint_id": "ideate-review-llm",
                "node_id": "ideate-review-llm",
                "status": "completed",
                "inputs": {"target": "agent skill learning"},
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:ideate",
                        "target": "agent skill learning",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "standard",
                        "focus": "novelty",
                        "score": 0.81,
                        "recommendation": "pass_with_review_required",
                        "evidence_ids": ["review-llm:ideate"],
                    },
                    "final_acceptance_boundary": {"final_acceptance_ready": True},
                    "findings": [],
                    "artifact": {"artifact_id": "artifact:ideate"},
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "review-llm-test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    model_command = tmp_path / "ideate_model_command_full.py"
    model_command.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "request = json.loads(sys.stdin.read())",
                "paths = [",
                "    ('A:landscape-driven', 'Landscape gap benchmark'),",
                "    ('B:incremental', 'Incremental verifier ablation'),",
                "    ('C:combination', 'Skill memory and verifier fusion'),",
                "    ('D:innovation', 'Novel adaptive skill audit'),",
                "    ('E:cross-domain-transfer', 'Cross-domain skill transfer probe'),",
                "]",
                "ideas = []",
                "for index, (path, title) in enumerate(paths, start=1):",
                "    ideas.append({",
                "        'idea_id': f'idea-model-path-{index:03d}',",
                "        'title': title,",
                "        'hypothesis': f'{title} improves source-grounded agent skill learning evaluation.',",
                "        'approach': f'Run a bounded pilot for {title} against cited SkillGen baselines.',",
                "        'novelty_hypothesis': f'{title} is novel relative to supplied external novelty evidence.',",
                "        'origin_evidence_ids': ['wiki:papers/skillgen', 'external:web:ideate-001'],",
                "        'duplicate_status': 'new',",
                "        'generation_path': path,",
                "    })",
                "payload = {",
                "    'schema': 'autosci_model_response.v1',",
                "    'status': 'completed',",
                "    'outputs': {",
                "        'answer': 'Five-path model brainstorm grounded in SkillGen paper evidence.',",
                "        'confidence': 0.82,",
                "        'provider': 'test-model-provider',",
                "        'model': 'gpt-4.1-mini-test-double',",
                "        'evidence_ids': ['wiki:papers/skillgen', 'external:web:ideate-001'],",
                "        'ideas': ideas,",
                "    },",
                "}",
                "print(json.dumps(payload))",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--wiki-root",
        str(wiki_root),
        "--model-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(model_command))}",
        "--novelty-evidence",
        str(external_path),
        "--review-llm-evidence",
        str(review_path),
        "--write",
        "--approval-ref",
        "approval-ideate-full",
        "--execute-approved",
        "--skip-pilot",
        "--run-id",
        "shim-ideate-full-evidence-boundary",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    ideas = idea_evidence["outputs"]["ideas"]
    assert len(ideas) == 5
    assert {idea["generation_path"][0] for idea in ideas} == {"A", "B", "C", "D", "E"}
    assert all(idea["promotion_ready"] is True for idea in ideas)
    boundary = json.loads((tmp_path / artifacts["ideate_final_promotion_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["status"] == "final_promotion_ready"
    assert boundary["final_promotion_ready"] is True
    assert boundary["generation_path_coverage"]["status"] == "complete"
    assert boundary["external_novelty_evidence_completed"] is True
    assert boundary["review_llm_evidence_completed"] is True
    assert boundary["novelty_review_gate_ready"] is True
    assert boundary["blocking_reasons"] == []
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    phases = {phase["name"]: phase for phase in pipeline_report["phases"]}
    assert phases["phase1_landscape_scan"]["status"] == "completed"
    assert phases["phase2_dual_model_brainstorm"]["status"] == "completed"
    assert phases["phase3_filter_and_validation"]["status"] == "completed"
    assert phases["phase4_wiki_write"]["status"] == "completed"
    assert phases["phase5_pilot_handoff"]["status"] == "skipped"
    assert pipeline_report["pipeline_ready"] is True
    assert pipeline_report["status"] == "completed"
    growth_report = json.loads((tmp_path / artifacts["ideate_growth_report_json"]).read_text(encoding="utf-8"))
    assert growth_report["promotion_ready_count"] == 5
    assert growth_report["final_promotion_ready"] is True
    assert growth_report["pipeline_ready"] is True
    assert growth_report["writeback"]["requested"] is True
    assert growth_report["writeback"]["approved"] is True
    assert growth_report["writeback"]["phase_status"] == "completed"
    assert growth_report["writeback"]["actual_wiki_idea_write_count"] == 5
    assert growth_report["pilot_handoff"]["phase_status"] == "skipped"
    workspace = payload["outputs"]["skill_run"]["workspace"]
    assert workspace["include_idea_pages"] is True
    for index in range(1, 6):
        assert (wiki_root / f"ideas/idea-model-path-{index:03d}.md").exists()
    proof_artifact = next(
        artifact
        for artifact in payload["artifacts"]
        if artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["native_skill"] == "ideate"
    assert proof_entry["collection_mode"] == "approved_side_effect"
    assert any(ref.endswith("wiki/ideas/idea-model-path-001.md") for ref in proof_entry["evidence_refs"])


def _write_ideate_full_evidence_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\nSkill generation exposes an inference-time adaptation gap.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/adaptation.md").write_text(
        "---\ntitle: Inference-Time Adaptation\n---\n# Inference-Time Adaptation\n\nA reusable method with open evaluation questions.\n",
        encoding="utf-8",
    )
    (wiki_root / "ideas/existing-control.md").write_text(
        "---\nidea_id: idea-existing-control\nslug: existing-control\nstatus: proposed\n---\n# Existing Control\n\nA control idea keeps wiki maturity non-empty.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/open_questions.md").write_text(
        "# Open Questions\n\n- How should generated skills be validated against baseline tools?\n",
        encoding="utf-8",
    )
    external_path = tmp_path / "ideate-external-novelty.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "outputs": {"sources": [{"id": "web:ideate-001", "provider": "web"}]},
            }
        ),
        encoding="utf-8",
    )
    review_path = tmp_path / "ideate-review-llm.json"
    review_path.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "recommendation": "pass_with_review_required",
                        "evidence_ids": ["review-llm:ideate"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    model_path = tmp_path / "ideate-model-evidence.json"
    ideas = []
    for index, path_code in enumerate(["A:landscape-driven", "B:incremental", "C:combination", "D:innovation", "E:cross-domain-transfer"], start=1):
        ideas.append(
            {
                "idea_id": f"idea-pilot-path-{index:03d}",
                "title": f"Pilot path {index}",
                "hypothesis": "Pilot-ready source-grounded idea.",
                "approach": "Run a bounded pilot against SkillGen baselines.",
                "origin_evidence_ids": ["wiki:papers/skillgen", "external:web:ideate-001"],
                "duplicate_status": "new",
                "generation_path": path_code,
            }
        )
    model_path.write_text(
        json.dumps(
            {
                "schema": "autosci_model_response.v1",
                "status": "completed",
                "outputs": {
                    "answer": "Five pilot-ready ideas.",
                    "provider": "test-model-provider",
                    "model": "gpt-4.1-mini-test-double",
                    "evidence_ids": ["wiki:papers/skillgen", "external:web:ideate-001"],
                    "ideas": ideas,
                },
            }
        ),
        encoding="utf-8",
    )
    return wiki_root, external_path, review_path, model_path


def test_autosci_skill_shim_ideate_approved_write_requires_pilot_handoff_or_skip(tmp_path: Path) -> None:
    wiki_root, external_path, review_path, model_path = _write_ideate_full_evidence_inputs(tmp_path)

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--wiki-root",
        str(wiki_root),
        "--model-evidence",
        str(model_path),
        "--novelty-evidence",
        str(external_path),
        "--review-llm-evidence",
        str(review_path),
        "--write",
        "--approval-ref",
        "approval-ideate-no-pilot",
        "--execute-approved",
        "--run-id",
        "shim-ideate-pilot-required",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    boundary = json.loads((tmp_path / artifacts["ideate_final_promotion_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["final_promotion_ready"] is True
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    phases = {phase["name"]: phase for phase in pipeline_report["phases"]}
    assert phases["phase5_pilot_handoff"]["status"] == "pending"
    assert "pilot handoff or pilot runtime evidence is missing" in phases["phase5_pilot_handoff"]["blocking_reasons"]
    assert pipeline_report["pipeline_ready"] is False
    pilot_boundary = json.loads((tmp_path / artifacts["ideate_pilot_handoff_boundary_json"]).read_text(encoding="utf-8"))
    assert pilot_boundary["pilot_handoff_ready"] is False
    assert payload["outputs"]["skill_run"]["workspace"]["include_idea_pages"] is False
    assert not (wiki_root / "ideas/idea-pilot-path-001.md").exists()
    assert not (wiki_root / "graph/edges.jsonl").exists()


def test_autosci_skill_shim_ideate_pilot_handoff_closes_phase5_and_allows_projection(tmp_path: Path) -> None:
    wiki_root, external_path, review_path, model_path = _write_ideate_full_evidence_inputs(tmp_path)
    pilot_handoff_path = tmp_path / "ideate-pilot-handoff.json"
    pilot_handoff_path.write_text(
        json.dumps(
            {
                "schema": "autosci_ideate_pilot_handoff.v1",
                "status": "completed",
                "evidence_ids": ["pilot-handoff:ideate"],
                "outputs": {
                    "handoff": {
                        "pilot_handoff_ready": True,
                        "target_idea_ids": ["idea-pilot-path-001"],
                        "evidence_ids": ["pilot-handoff:ideate"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--wiki-root",
        str(wiki_root),
        "--model-evidence",
        str(model_path),
        "--novelty-evidence",
        str(external_path),
        "--review-llm-evidence",
        str(review_path),
        "--pilot-handoff-evidence",
        str(pilot_handoff_path),
        "--write",
        "--approval-ref",
        "approval-ideate-pilot-handoff",
        "--execute-approved",
        "--run-id",
        "shim-ideate-pilot-handoff",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    phases = {phase["name"]: phase for phase in pipeline_report["phases"]}
    assert phases["phase5_pilot_handoff"]["status"] == "completed"
    assert phases["phase5_pilot_handoff"]["completed"] is True
    assert pipeline_report["pipeline_ready"] is True
    growth_report = json.loads((tmp_path / artifacts["ideate_growth_report_json"]).read_text(encoding="utf-8"))
    assert growth_report["pilot_handoff"]["phase_status"] == "completed"
    assert growth_report["pilot_handoff"]["completed"] is True
    pilot_boundary = json.loads((tmp_path / artifacts["ideate_pilot_handoff_boundary_json"]).read_text(encoding="utf-8"))
    assert pilot_boundary["status"] == "pilot_handoff_ready"
    assert pilot_boundary["evidence_ids"] == ["pilot-handoff:ideate"]
    pilot_proof = json.loads((tmp_path / artifacts["pilot_handoff_runtime_proof_manifest_json"]).read_text(encoding="utf-8"))
    proof_entry = pilot_proof["proofs"][0]
    assert proof_entry["native_skill"] == "ideate"
    assert "pilot_handoff_evidence" in proof_entry["categories"]
    assert any(ref.endswith("ideate-pilot-handoff.json") for ref in proof_entry["evidence_refs"])
    assert payload["outputs"]["skill_run"]["workspace"]["include_idea_pages"] is True
    assert (wiki_root / "ideas/idea-pilot-path-001.md").exists()
    edges_text = (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    assert "generated_from" in edges_text
    assert "has_pilot_handoff" in edges_text
    assert "ideas/idea-pilot-path-001.md" in edges_text
    assert "pilot-handoff:ideate" in edges_text
    workspace_proof_artifact = next(
        artifact
        for artifact in payload["artifacts"]
        if artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
    )
    workspace_proof = json.loads((tmp_path / workspace_proof_artifact["path"]).read_text(encoding="utf-8"))
    workspace_proof_entry = workspace_proof["proofs"][0]
    assert any(ref.endswith("wiki/graph/edges.jsonl") for ref in workspace_proof_entry["evidence_refs"])


def test_autosci_skill_shim_wiki_state_resolver_parses_entities_and_edges(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "experiments").mkdir(parents=True)
    (wiki_root / "outputs/exp-skillgen").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work on generated skills.\n",
        encoding="utf-8",
    )
    (wiki_root / "ideas/skillgen.md").write_text(
        "\n".join(
            [
                "---",
                "id: idea-skillgen",
                "slug: skillgen",
                "title: SkillGen Idea",
                "status: proposed",
                "novelty_score: 0.82",
                "linked_experiments: [exp-skillgen]",
                "---",
                "# SkillGen Idea",
                "",
                "Generated skills for inference-time agents.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (wiki_root / "experiments/exp-skillgen.md").write_text(
        "\n".join(
            [
                "---",
                "experiment_id: exp-skillgen",
                "idea_id: idea-skillgen",
                "slug: exp-skillgen",
                "status: collected",
                "run_log: ../outputs/exp-skillgen/run_log.json",
                "---",
                "# SkillGen Experiment",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (wiki_root / "outputs/exp-skillgen/result.md").write_text(
        "---\noutput_id: output-skillgen\nexperiment_id: exp-skillgen\nstatus: ready\n---\n# Result\n",
        encoding="utf-8",
    )
    (wiki_root / "outputs/exp-skillgen/run_log.json").write_text('{"ok": true}\n', encoding="utf-8")
    (wiki_root / "graph/edges.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"source": "idea-skillgen", "target": "exp-skillgen", "relation": "tested_by"}),
                json.dumps({"source": "exp-skillgen", "target": "output-skillgen", "relation": "produced"}),
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$ideate",
        "skillgen",
        "--from-wiki",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-wiki-state-resolver",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    resolver_artifact = next(artifact for artifact in idea_evidence["artifacts"] if artifact["type"] == "wiki_state_resolver_json")
    resolver = json.loads((tmp_path / resolver_artifact["path"]).read_text(encoding="utf-8"))

    assert resolver["schema"] == "autosci_wiki_state_resolver.v1"
    assert resolver["status"] == "completed"
    assert resolver["resolution"]["target_type"] == "idea"
    assert resolver["resolution"]["target_id"] == "idea-skillgen"
    assert resolver["resolution"]["fallback_used"] is False
    assert resolver["ideas"][0]["novelty_score"] == 0.82
    assert resolver["ideas"][0]["linked_experiments"] == ["exp-skillgen"]
    assert resolver["experiments"][0]["run_log_exists"] is True
    assert resolver["experiments"][0]["linked_outputs"] == ["output-skillgen"]
    assert len(resolver["graph_edges"]) == 2
    assert resolver["graph_errors"] == []

    evaluation_evidence = json.loads(Path(actions[1]["evidence_path"]).read_text(encoding="utf-8"))
    assert any(artifact["type"] == "wiki_state_resolver_json" for artifact in evaluation_evidence["artifacts"])


def test_autosci_skill_shim_exp_status_resolves_wiki_experiment_without_default_fallback(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "experiments").mkdir(parents=True)
    (wiki_root / "outputs/exp-skillgen").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "experiments/exp-skillgen.md").write_text(
        "\n".join(
            [
                "---",
                "experiment_id: exp-skillgen",
                "slug: exp-skillgen",
                "status: running",
                "run_log: ../outputs/exp-skillgen/run_log.json",
                "---",
                "# SkillGen Experiment",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (wiki_root / "outputs/exp-skillgen/run_log.json").write_text('{"status": "running"}\n', encoding="utf-8")

    proc = run_shim(
        tmp_path,
        "$exp-status",
        "exp-skillgen",
        "--wiki-root",
        str(wiki_root),
        "--run-id",
        "shim-exp-status-wiki-state",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    status_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))

    assert status_evidence["outputs"]["status_report"]["experiment_id"] == "exp-skillgen"
    assert status_evidence["outputs"]["status_report"]["experiment_id"] != "exp-001"
    resolver_artifact = next(artifact for artifact in status_evidence["artifacts"] if artifact["type"] == "wiki_state_resolver_json")
    resolver = json.loads((tmp_path / resolver_artifact["path"]).read_text(encoding="utf-8"))
    assert resolver["resolution"]["target_type"] == "experiment"
    assert resolver["resolution"]["target_id"] == "exp-skillgen"
    assert resolver["experiments"][0]["run_log_exists"] is True


def test_autosci_skill_shim_ideate_without_sources_is_inconclusive_not_fixture(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--run-id",
        "shim-ideate-missing-sources",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ideate"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 2

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    evaluation_evidence = json.loads(Path(actions[1]["evidence_path"]).read_text(encoding="utf-8"))
    idea = idea_evidence["outputs"]["ideas"][0]
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert idea_evidence["status"] == "inconclusive"
    assert idea["source_mode"] == "missing"
    assert idea["status"] == "blocked"
    assert idea["promotion_ready"] is False
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    assert "ideate_final_promotion_boundary_json" in artifacts
    boundary = json.loads((tmp_path / artifacts["ideate_final_promotion_boundary_json"]).read_text(encoding="utf-8"))
    assert boundary["source_evidence_ready"] is False
    assert "source-backed idea evidence is missing" in boundary["blocking_reasons"]
    assert evaluation["recommendation"] == "inconclusive"
    assert "fixture" not in json.dumps(idea_evidence).lower()


def test_autosci_skill_shim_ideate_skip_validation_skips_evaluation_action(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--skip-validation",
        "--skip-pilot",
        "--run-id",
        "shim-ideate-skip-validation",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ideate"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    assert [action["action"] for action in actions] == ["generate_ideas"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    phases = {phase["name"]: phase for phase in pipeline_report["phases"]}
    assert phases["phase3_filter_and_validation"]["status"] == "skipped"
    assert phases["phase5_pilot_handoff"]["status"] == "skipped"
    assert pipeline_report["pipeline_ready"] is False


def test_autosci_skill_shim_ideate_write_request_stays_approval_gated(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "methods").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "graph").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Paper\n---\n# SkillGen Paper\n\nSkill generation exposes an inference-time adaptation gap.\n",
        encoding="utf-8",
    )
    (wiki_root / "methods/adaptation.md").write_text(
        "---\ntitle: Inference-Time Adaptation\n---\n# Inference-Time Adaptation\n\nA reusable method with open evaluation questions.\n",
        encoding="utf-8",
    )
    (wiki_root / "graph/open_questions.md").write_text(
        "# Open Questions\n\n- How should generated skills be validated against baseline tools?\n",
        encoding="utf-8",
    )
    before_ideas = sorted(path.name for path in (wiki_root / "ideas").glob("*.md"))

    proc = run_shim(
        tmp_path,
        "$ideate",
        "agent skill learning",
        "--from-wiki",
        "--wiki-root",
        str(wiki_root),
        "--write",
        "--skip-validation",
        "--skip-pilot",
        "--run-id",
        "shim-ideate-write-approval-gated",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "ideate"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    assert payload["inputs"]["native_options"]["write"] is True
    assert payload["outputs"]["skill_run"]["workspace"]["include_idea_pages"] is False
    actions = payload["outputs"]["skill_run"]["actions"]
    idea_evidence = json.loads(Path(actions[0]["evidence_path"]).read_text(encoding="utf-8"))
    assert idea_evidence["inputs"]["write"] is True
    assert idea_evidence["inputs"]["native_options"]["write"] is True
    artifacts = {artifact["type"]: artifact["path"] for artifact in idea_evidence["artifacts"]}
    pipeline_report = json.loads((tmp_path / artifacts["ideate_pipeline_report_json"]).read_text(encoding="utf-8"))
    phases = {phase["name"]: phase for phase in pipeline_report["phases"]}
    assert phases["phase4_wiki_write"]["status"] == "pending_approval"
    assert phases["phase4_wiki_write"]["completed"] is False
    assert "approved writeback evidence is missing" in phases["phase4_wiki_write"]["blocking_reasons"]
    assert pipeline_report["pipeline_ready"] is False
    after_ideas = sorted(path.name for path in (wiki_root / "ideas").glob("*.md"))
    assert after_ideas == before_ideas


def test_autosci_skill_shim_runs_novelty_target_with_local_sources(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work studies generated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    (wiki_root / "ideas/failed-skillgen.md").write_text(
        "---\ntitle: Failed SkillGen Duplicate\nstatus: failed\nfailure_reason: too similar to generated skills prior work\n---\n# Failed SkillGen Duplicate\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "generated skills for inference-time agents",
        "--from-wiki",
        "--run-id",
        "shim-novelty-local",
        extra_env={"AUTOSCI_DISABLE_NETWORK_FETCH": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "novelty"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert not any(
        artifact["type"] == "wiki_mutation_runtime_proof_manifest_json"
        for artifact in evaluation_evidence["artifacts"]
    )
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["source_mode"] == "target"
    assert evaluation["closest_prior_work"]
    assert evaluation["review_mode"] == "local_surrogate"
    assert evaluation["review_llm"]["status"] == "unavailable"
    assert evaluation["external_novelty"]["status"] == "unavailable"
    boundary = evaluation["final_acceptance_boundary"]
    assert boundary["schema"] == "autosci_novelty_final_acceptance_boundary.v1"
    assert boundary["final_acceptance_ready"] is False
    assert boundary["status"] == "novelty_acceptance_incomplete"
    assert any("external_novelty status" in reason for reason in boundary["blocking_reasons"])
    assert any(
        artifact["type"] == "novelty_final_acceptance_boundary_json"
        for artifact in evaluation_evidence["artifacts"]
    )
    assert evaluation["recommendation"] in {"revise", "reject", "inconclusive"}
    assert "fixture" not in json.dumps(evaluation_evidence).lower()


def test_autosci_skill_shim_novelty_defaults_to_online_fetch_when_available(tmp_path: Path) -> None:
    semantic_payload = tmp_path / "semantic_scholar_mock.json"
    archive_dir = tmp_path / "novelty-archive"
    archive_dir.mkdir()
    semantic_payload.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "paperId": "s2-123",
                        "title": "Online Prior Work on Generated Skills",
                        "abstract": "Synthetic benchmark for inference-time agents.",
                        "url": "https://example.invalid/s2-123",
                        "authors": [{"name": "Open Researcher"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "generated skills for inference-time agents",
        "--from-wiki",
        "--run-id",
        "shim-novelty-default-online",
        extra_env={
            "AUTOSCI_SEMANTIC_SCHOLAR_SEARCH_URL": f"file://{semantic_payload}",
            "AUTOSCI_NOVELTY_PAYLOAD_ARCHIVE_DIR": str(archive_dir),
        },
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]

    assert evaluation["source_mode"] == "target"
    assert evaluation["external_novelty"]["status"] == "completed"
    assert evaluation["external_novelty"]["source_count"] >= 1
    provider_status = next(
        item for item in evaluation["external_novelty"]["provider_statuses"] if item.get("provider") == "semantic_scholar"
    )
    assert provider_status["raw_payload_ref"] == semantic_payload.as_uri()
    assert provider_status["raw_payload_archive_status"] == "completed"
    assert Path(provider_status["raw_payload_archive_path"]).is_file()


def test_autosci_skill_shim_novelty_uses_supplied_external_evidence(tmp_path: Path) -> None:
    external_path = tmp_path / "semantic-scholar-novelty.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "inputs": {"query": "generated skills for inference-time agents"},
                "outputs": {
                    "sources": [
                        {
                            "id": "s2-001",
                            "provider": "semantic_scholar",
                            "paperId": "s2-001",
                            "title": "Generated Skills for Inference-Time Agents",
                            "summary": "Prior work studies generated skills for inference-time agent adaptation.",
                            "url": "https://example.invalid/s2-001",
                        }
                    ]
                },
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "generated skills for inference-time agents",
        "--novelty-evidence",
        str(external_path),
        "--run-id",
        "shim-novelty-external",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "novelty"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["source_mode"] == "target"
    assert evaluation["review_mode"] == "local_surrogate"
    assert evaluation["review_llm"]["status"] == "unavailable"
    assert evaluation["external_novelty"]["status"] == "completed"
    assert evaluation["external_novelty"]["provenance"]["status"] == "passed"
    boundary = evaluation["final_acceptance_boundary"]
    assert boundary["final_acceptance_ready"] is False
    assert boundary["external_novelty_status"] == "completed"
    assert boundary["external_novelty_provenance_status"] == "passed"
    assert boundary["review_llm_status"] == "unavailable"
    assert any("review_llm status" in reason for reason in boundary["blocking_reasons"])
    assert "raw_payload_sha256" in evaluation["external_novelty"]["provenance"]["required_fields"]
    provider_status = evaluation["external_novelty"]["provider_statuses"][0]
    assert re.fullmatch(r"[a-f0-9]{64}", provider_status["raw_payload_sha256"])
    assert provider_status["raw_payload_refs"] == [str(external_path)]
    assert provider_status["raw_payload_archive_status"] == "completed"
    assert Path(provider_status["raw_payload_archive_path"]).exists()
    assert evaluation["external_source_count"] == 1
    assert evaluation["closest_prior_work"][0]["source_id"].startswith("external:semantic_scholar:")
    assert str(external_path) in evaluation["external_novelty"]["checked_paths"]
    artifact_paths = [artifact["path"] for artifact in evaluation_evidence["artifacts"]]
    assert any("external_novelty_payloads" in path for path in artifact_paths)
    artifact_types = {artifact["type"] for artifact in evaluation_evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in artifact_types
    assert "review_model_runtime_proof_manifest_json" not in artifact_types
    provider_proof_artifact = next(
        artifact
        for artifact in evaluation_evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    provider_proof = json.loads((tmp_path / provider_proof_artifact["path"]).read_text(encoding="utf-8"))
    provider_entry = provider_proof["proofs"][0]
    assert provider_entry["native_skill"] == "novelty"
    assert provider_entry["categories"] == ["provider_source_evidence"]
    assert provider_entry["collection_mode"] == "manual_review"
    assert any(ref.endswith("semantic-scholar-novelty.json") for ref in provider_entry["evidence_refs"])
    assert "fixture" not in json.dumps(evaluation_evidence).lower()


def test_autosci_skill_shim_novelty_requires_provider_specific_semantic_scholar_id(tmp_path: Path) -> None:
    external_path = tmp_path / "semantic-scholar-url-only.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "inputs": {"query": "generated skills for inference-time agents"},
                "outputs": {
                    "sources": [
                        {
                            "provider": "semantic_scholar",
                            "title": "Generated Skills for Inference-Time Agents",
                            "summary": "Prior work studies generated skills for inference-time agent adaptation.",
                            "url": "https://example.invalid/s2-url-only",
                        }
                    ]
                },
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "generated skills for inference-time agents",
        "--novelty-evidence",
        str(external_path),
        "--run-id",
        "shim-novelty-semantic-url-only",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    external = evaluation_evidence["outputs"]["evaluations"][0]["external_novelty"]
    assert external["status"] == "completed"
    assert external["provenance"]["status"] == "failed"
    assert external["provenance"]["provider_schemas"] == ["semantic_scholar"]
    assert any("semantic_scholar requires paperId" in issue for issue in external["provenance"]["issues"])


def test_autosci_skill_shim_novelty_online_fetch_degrades_when_network_disabled(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$novelty",
        "generated skills for inference-time agents",
        "--online",
        "--run-id",
        "shim-novelty-online-disabled",
        extra_env={"AUTOSCI_DISABLE_NETWORK_FETCH": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["external_novelty"]["status"] == "unavailable"
    assert "disabled" in evaluation["external_novelty"]["reason"]


def test_autosci_skill_shim_novelty_online_fetch_uses_configured_web_provider(tmp_path: Path) -> None:
    web_payload = tmp_path / "web-novelty.json"
    web_payload.write_text(
        json.dumps(
            {
                "organic": [
                    {
                        "title": "Generated Skills for Inference-Time Agents",
                        "link": "https://example.invalid/generated-skills",
                        "snippet": "A web result about generated skills for inference-time agents.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proc = run_shim(
        tmp_path,
        "$novelty",
        "generated skills for inference-time agents",
        "--online",
        "--run-id",
        "shim-novelty-online-web",
        extra_env={
            "AUTOSCI_NOVELTY_PROVIDERS": "web",
            "AUTOSCI_WEB_SEARCH_EVIDENCE_URL": web_payload.as_uri(),
        },
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    external = evaluation["external_novelty"]
    assert external["status"] == "completed"
    assert external["source_count"] == 1
    assert external["provider_statuses"][0]["provider"] == "web"
    assert external["provider_statuses"][0]["status"] == "completed"
    assert re.fullmatch(r"[a-f0-9]{64}", external["provider_statuses"][0]["raw_payload_sha256"])
    assert external["provider_statuses"][0]["raw_payload_archive_status"] == "completed"
    assert Path(external["provider_statuses"][0]["raw_payload_archive_path"]).exists()
    assert external["provenance"]["status"] == "passed"
    artifact_paths = [artifact["path"] for artifact in evaluation_evidence["artifacts"]]
    assert any("external_novelty_payloads" in path for path in artifact_paths)
    assert evaluation["closest_prior_work"][0]["source_id"].startswith("external:web:")
    assert "fixture" not in json.dumps(evaluation_evidence).lower()


def test_autosci_skill_shim_novelty_http_provider_marks_external_runtime(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = {
                "organic": [
                    {
                        "title": "Generated Skills for Inference-Time Agents",
                        "link": "https://example.invalid/generated-skills-http",
                        "snippet": "An HTTP provider result about generated skills for inference-time agents.",
                    }
                ]
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/search"
        proc = run_shim(
            tmp_path,
            "$novelty",
            "generated skills for inference-time agents",
            "--online",
            "--run-id",
            "shim-novelty-online-http-web",
            extra_env={
                "AUTOSCI_DISABLE_NETWORK_FETCH": "0",
                "AUTOSCI_NOVELTY_PROVIDERS": "web",
                "AUTOSCI_WEB_SEARCH_EVIDENCE_URL": endpoint,
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    external = evaluation_evidence["outputs"]["evaluations"][0]["external_novelty"]
    assert external["status"] == "completed"
    assert external["provider_statuses"][0]["raw_payload_ref"].startswith("http://127.0.0.1:")

    provider_proof_artifact = next(
        artifact
        for artifact in evaluation_evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    provider_proof = json.loads((tmp_path / provider_proof_artifact["path"]).read_text(encoding="utf-8"))
    provider_entry = provider_proof["proofs"][0]
    assert provider_entry["categories"] == ["provider_source_evidence", "external_runtime_evidence"]
    assert provider_entry["collection_mode"] == "live_provider"
    assert any(ref.startswith("http://127.0.0.1:") for ref in provider_entry["evidence_refs"])


def test_autosci_skill_shim_novelty_write_skips_without_external_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work studies generated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    idea_path = wiki_root / "ideas/skillgen-writeback.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Writeback\nstatus: proposed\nnovelty_score: 0\n---\n# SkillGen Writeback\n\nGenerated skills for inference-time agents.\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "skillgen-writeback",
        "--from-wiki",
        "--write",
        "--run-id",
        "shim-novelty-write",
        extra_env={"AUTOSCI_DISABLE_NETWORK_FETCH": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "novelty"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    updated = idea_path.read_text(encoding="utf-8")
    assert "novelty_score: 0" in updated
    assert not (wiki_root / "log.md").exists()

    result_path = tmp_path / "artifacts/autosci/runs/shim-novelty-write/evaluate_ideas.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    sidecars = result["sidecar_evidence_paths"]
    assert result["novelty_writeback_path"] in sidecars
    writeback = json.loads((tmp_path / result["novelty_writeback_path"]).read_text(encoding="utf-8"))
    assert writeback["schema"] == "novelty_writeback.v1"
    assert writeback["status"] == "inconclusive"
    assert writeback["outputs"]["write"]["applied"] is False
    assert writeback["outputs"]["write"]["external_novelty_status"] == "unavailable"
    assert writeback["outputs"]["write"]["review_llm_status"] == "unavailable"
    assert "completed external novelty evidence is required" in " ".join(writeback["limitations"])


def test_autosci_skill_shim_novelty_write_skips_without_review_llm_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work studies generated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    idea_path = wiki_root / "ideas/skillgen-writeback.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Writeback\nstatus: proposed\nnovelty_score: 0\n---\n# SkillGen Writeback\n\nGenerated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    external_path = tmp_path / "semantic-scholar-writeback.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "inputs": {"query": "skillgen-writeback"},
                "outputs": {
                    "sources": [
                            {
                                "id": "s2-writeback-001",
                            "provider": "semantic_scholar",
                            "paperId": "s2-writeback-001",
                            "title": "SkillGen Writeback and Generated Skills for Inference-Time Agents",
                                "summary": "External prior work evidence for generated skills.",
                            },
                            {
                                "id": "s2-writeback-002",
                                "provider": "semantic_scholar",
                                "paperId": "s2-writeback-002",
                                "title": "Independent Evaluation of Generated Agent Skills",
                                "summary": "Second external prior-work source for generated skills.",
                            },
                    ]
                },
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "skillgen-writeback",
        "--from-wiki",
        "--novelty-evidence",
        str(external_path),
        "--write",
        "--run-id",
        "shim-novelty-write-external-no-review",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "novelty"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    updated = idea_path.read_text(encoding="utf-8")
    assert "novelty_score: 0" in updated
    assert not (wiki_root / "log.md").exists()

    result_path = tmp_path / "artifacts/autosci/runs/shim-novelty-write-external-no-review/evaluate_ideas.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    writeback = json.loads((tmp_path / result["novelty_writeback_path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "inconclusive"
    assert writeback["outputs"]["write"]["applied"] is False
    assert writeback["outputs"]["write"]["external_novelty_status"] == "completed"
    assert writeback["outputs"]["write"]["external_novelty_provenance_status"] == "passed"
    assert writeback["outputs"]["write"]["review_llm_status"] == "unavailable"
    assert "completed Review LLM evidence is required" in " ".join(writeback["limitations"])


def test_autosci_skill_shim_novelty_write_updates_with_external_and_review_llm_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work studies generated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    idea_path = wiki_root / "ideas/skillgen-writeback.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Writeback\nstatus: proposed\nnovelty_score: 0\n---\n# SkillGen Writeback\n\nGenerated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    external_path = tmp_path / "semantic-scholar-writeback.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "inputs": {"query": "skillgen-writeback"},
                "outputs": {
                    "sources": [
                        {
                            "id": "s2-writeback-001",
                            "provider": "semantic_scholar",
                            "paperId": "s2-writeback-001",
                            "title": "SkillGen Writeback and Generated Skills for Inference-Time Agents",
                            "summary": "External prior work evidence for generated skills.",
                        },
                        {
                            "id": "s2-writeback-002",
                            "provider": "semantic_scholar",
                            "paperId": "s2-writeback-002",
                            "title": "Independent Evaluation of Generated Agent Skills",
                            "summary": "Second external prior-work source for generated skills.",
                        },
                    ]
                },
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    review_llm_path = tmp_path / "review-llm-writeback.json"
    review_llm_path.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-llm-writeback",
                "sprint_id": "review-llm-writeback",
                "node_id": "review-llm-writeback",
                "status": "completed",
                "inputs": {"target": "skillgen-writeback"},
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:skillgen-writeback",
                        "target": "skillgen-writeback",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "standard",
                        "focus": "novelty",
                        "score": 0.62,
                        "recommendation": "pass_with_review_required",
                        "evidence_ids": ["review-llm:writeback"],
                    },
                    "findings": [],
                    "artifact": {"artifact_id": "artifact:skillgen-writeback"},
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "review-llm-test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "skillgen-writeback",
        "--from-wiki",
        "--novelty-evidence",
        str(external_path),
        "--review-llm-evidence",
        str(review_llm_path),
        "--write",
        "--run-id",
        "shim-novelty-write-reviewed",
    )
    assert proc.returncode == 0, proc.stderr

    updated = idea_path.read_text(encoding="utf-8")
    assert "novelty_score: 0" not in updated
    assert re.search(r"^novelty_score: [1-5]$", updated, flags=re.M)
    log_text = (wiki_root / "log.md").read_text(encoding="utf-8")
    assert "novelty | wrote novelty_score=" in log_text
    assert "review-llm:writeback" in log_text
    edges_text = (wiki_root / "graph/edges.jsonl").read_text(encoding="utf-8")
    assert "novelty_evaluated" in edges_text
    assert "review-llm:writeback" in edges_text
    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert "ideas/skillgen-writeback.md" in index_text
    context_text = (wiki_root / "graph/context_brief.md").read_text(encoding="utf-8")
    assert "Mutation target:" in context_text

    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["review_mode"] == "review_llm"
    assert evaluation["review_available"] is True
    assert evaluation["review_llm"]["status"] == "completed"
    boundary = evaluation["final_acceptance_boundary"]
    assert boundary["final_acceptance_ready"] is True
    assert boundary["status"] == "final_acceptance_ready"
    assert boundary["external_novelty_status"] == "completed"
    assert boundary["external_novelty_provenance_status"] == "passed"
    assert boundary["review_llm_status"] == "completed"
    assert "review-llm:writeback" in evaluation["evidence_ids"]
    evaluation_artifacts = {artifact["type"]: artifact for artifact in evaluation_evidence["artifacts"]}
    assert "provider_source_runtime_proof_manifest_json" in evaluation_artifacts
    assert "review_model_runtime_proof_manifest_json" in evaluation_artifacts
    assert "wiki_mutation_runtime_proof_manifest_json" in evaluation_artifacts
    provider_proof = json.loads(
        (tmp_path / evaluation_artifacts["provider_source_runtime_proof_manifest_json"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    assert provider_proof["proofs"][0]["categories"] == ["provider_source_evidence"]
    review_proof = json.loads(
        (tmp_path / evaluation_artifacts["review_model_runtime_proof_manifest_json"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    review_entry = review_proof["proofs"][0]
    assert review_entry["native_skill"] == "novelty"
    assert review_entry["categories"] == ["review_llm_or_model_evidence", "external_runtime_evidence"]
    assert any(ref.endswith("review-llm-writeback.json") for ref in review_entry["evidence_refs"])
    wiki_mutation_proof = json.loads(
        (tmp_path / evaluation_artifacts["wiki_mutation_runtime_proof_manifest_json"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    wiki_mutation_entry = wiki_mutation_proof["proofs"][0]
    assert wiki_mutation_entry["native_skill"] == "novelty"
    assert wiki_mutation_entry["categories"] == ["wiki_mutation_evidence"]
    assert wiki_mutation_entry["collection_mode"] == "approved_side_effect"
    assert any(ref.endswith("novelty_writeback.json") for ref in wiki_mutation_entry["evidence_refs"])
    assert any(ref.endswith("wiki/graph/edges.jsonl") for ref in wiki_mutation_entry["evidence_refs"])

    result_path = tmp_path / "artifacts/autosci/runs/shim-novelty-write-reviewed/evaluate_ideas.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    writeback = json.loads((tmp_path / result["novelty_writeback_path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "completed"
    assert writeback["outputs"]["write"]["applied"] is True
    assert writeback["outputs"]["write"]["external_novelty_status"] == "completed"
    assert writeback["outputs"]["write"]["external_novelty_provenance_status"] == "passed"
    assert writeback["outputs"]["write"]["review_llm_status"] == "completed"
    assert writeback["outputs"]["write"]["final_acceptance_status"] == "final_acceptance_ready"
    assert writeback["outputs"]["write"]["final_acceptance_ready"] is True
    assert writeback["outputs"]["write"]["edge_path"].endswith("wiki/graph/edges.jsonl")
    assert any(path.endswith("wiki/index.md") for path in writeback["outputs"]["write"]["rebuilt_paths"])
    artifact_types = {artifact["type"] for artifact in writeback["artifacts"]}
    assert {"wiki_graph_edges", "wiki_rebuild"}.issubset(artifact_types)


def test_autosci_skill_shim_novelty_write_uses_review_llm_command_bridge(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work studies generated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    idea_path = wiki_root / "ideas/skillgen-writeback.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Writeback\nstatus: proposed\nnovelty_score: 0\n---\n# SkillGen Writeback\n\nGenerated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    external_path = tmp_path / "semantic-scholar-writeback.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "inputs": {"query": "skillgen-writeback"},
                "outputs": {
                    "sources": [
                        {
                            "id": "s2-writeback-001",
                            "provider": "semantic_scholar",
                            "paperId": "s2-writeback-001",
                            "title": "SkillGen Writeback and Generated Skills for Inference-Time Agents",
                            "summary": "External prior work evidence for generated skills.",
                        },
                        {
                            "id": "s2-writeback-002",
                            "provider": "semantic_scholar",
                            "paperId": "s2-writeback-002",
                            "title": "Independent Evaluation of Generated Agent Skills",
                            "summary": "Second external prior-work source for generated skills.",
                        },
                    ]
                },
                "provenance": {
                    "operator_id": "test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    command_path = tmp_path / "review_llm_command.py"
    command_path.write_text(
        """
import json
import sys

request = json.loads(sys.stdin.read())
target = request["inputs"].get("target", "N/A")
print(json.dumps({
    "schema": "artifact_review.v1",
    "status": "completed",
    "outputs": {
        "review": {
            "artifact_id": "artifact:" + target,
            "target": target,
            "review_mode": "review_llm",
            "review_available": True,
            "difficulty": request.get("difficulty", "standard"),
            "focus": request.get("focus", "novelty"),
            "score": 0.61,
            "recommendation": "pass_with_review_required",
            "evidence_ids": ["review-llm:command-writeback"]
        },
        "findings": []
    }
}))
""".lstrip(),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "skillgen-writeback",
        "--from-wiki",
        "--novelty-evidence",
        str(external_path),
        "--review-llm-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(command_path))}",
        "--write",
        "--run-id",
        "shim-novelty-write-review-command",
    )
    assert proc.returncode == 0, proc.stderr

    updated = idea_path.read_text(encoding="utf-8")
    assert "novelty_score: 0" not in updated
    assert (wiki_root / "graph/edges.jsonl").exists()
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["review_mode"] == "review_llm"
    assert evaluation["review_llm"]["status"] == "completed"
    assert evaluation["review_llm"]["invocation_mode"] == "command"
    assert "review-llm:command-writeback" in evaluation["evidence_ids"]
    assert any(
        artifact["type"] == "review_model_runtime_proof_manifest_json"
        for artifact in evaluation_evidence["artifacts"]
    )


def test_autosci_skill_shim_novelty_write_skips_external_without_provenance(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "ideas").mkdir(parents=True)
    (wiki_root / "papers/skillgen.md").write_text(
        "---\ntitle: SkillGen Prior Work\n---\n# SkillGen Prior Work\n\nPrior work studies generated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    idea_path = wiki_root / "ideas/skillgen-writeback.md"
    idea_path.write_text(
        "---\ntitle: SkillGen Writeback\nstatus: proposed\nnovelty_score: 0\n---\n# SkillGen Writeback\n\nGenerated skills for inference-time agents.\n",
        encoding="utf-8",
    )
    external_path = tmp_path / "semantic-scholar-bad-provenance.json"
    external_path.write_text(
        json.dumps(
            {
                "schema": "external_novelty_sources.v1",
                "status": "completed",
                "outputs": {
                    "sources": [
                        {
                            "provider": "semantic_scholar",
                            "title": "SkillGen Writeback Prior Work",
                            "summary": "A source row without durable identifiers or retrieval metadata.",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$novelty",
        "skillgen-writeback",
        "--from-wiki",
        "--novelty-evidence",
        str(external_path),
        "--write",
        "--run-id",
        "shim-novelty-write-bad-provenance",
    )
    assert proc.returncode == 0, proc.stderr
    updated = idea_path.read_text(encoding="utf-8")
    assert "novelty_score: 0" in updated
    assert not (wiki_root / "log.md").exists()

    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    evaluation_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    evaluation = evaluation_evidence["outputs"]["evaluations"][0]
    assert evaluation["external_novelty"]["status"] == "completed"
    assert evaluation["external_novelty"]["provenance"]["status"] == "failed"

    result_path = tmp_path / "artifacts/autosci/runs/shim-novelty-write-bad-provenance/evaluate_ideas.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    writeback = json.loads((tmp_path / result["novelty_writeback_path"]).read_text(encoding="utf-8"))
    assert writeback["status"] == "inconclusive"
    assert writeback["outputs"]["write"]["applied"] is False
    assert writeback["outputs"]["write"]["external_novelty_status"] == "completed"
    assert writeback["outputs"]["write"]["external_novelty_provenance_status"] == "failed"
    assert "provider provenance did not pass" in " ".join(writeback["limitations"])


def test_autosci_skill_shim_runs_review_as_artifact_review(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "outputs").mkdir(parents=True)
    review_target = wiki_root / "outputs/skillgen-review.md"
    review_target.write_text(
        "---\ntitle: SkillGen Review Target\n---\n# SkillGen Review Target\n\n"
        "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table.\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$review",
        "skillgen-review",
        "--from-wiki",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--run-id",
        "shim-review-artifact",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "review"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "review_artifact"
    assert action["schema"] == "artifact_review.v1"
    assert action["gate_status"] == "passed"
    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    review = review_evidence["outputs"]["review"]
    assert review["review_mode"] == "local_surrogate"
    assert review["review_available"] is False
    assert review["difficulty"] == "hard"
    assert review["focus"] == "method"
    assert review["review_llm"]["status"] == "unavailable"
    assert review["review_llm"]["tool"] == "mcp__llm-review__chat"
    assert review["recommendation"] in {"pass_with_review_required", "revise", "revise_required"}
    boundary = review_evidence["outputs"]["final_acceptance_boundary"]
    assert boundary["schema"] == "autosci_review_final_acceptance_boundary.v1"
    assert boundary["final_acceptance_ready"] is False
    assert boundary["status"] == "review_llm_incomplete"
    assert any("review_mode" in reason for reason in boundary["blocking_reasons"])
    assert any(artifact["type"] == "review_final_acceptance_boundary_json" for artifact in review_evidence["artifacts"])
    assert not any(artifact["type"] == "review_model_runtime_proof_manifest_json" for artifact in review_evidence["artifacts"])
    source_proof_artifact = next(
        artifact
        for artifact in review_evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    source_proof = json.loads((tmp_path / source_proof_artifact["path"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "review"
    assert source_proof_entry["categories"] == ["provider_source_evidence"]
    assert any(ref.endswith("outputs/skillgen-review.md") for ref in source_proof_entry["evidence_refs"])
    assert "fixture" not in json.dumps(review_evidence).lower()


def test_autosci_skill_shim_review_missing_slug_does_not_use_repo_workspace_fallback(tmp_path: Path) -> None:
    proc = run_shim(
        tmp_path,
        "$review",
        "idea-001",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--run-id",
        "shim-review-missing-slug",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "review"
    assert summary["execution_status"] == "partial"
    assert summary["action_count"] == 1
    assert summary["passed_count"] == 0
    assert summary["schema_only_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "review_artifact"
    assert action["gate_status"] == "schema_only"
    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    artifact = review_evidence["outputs"]["artifact"]
    assert review_evidence["status"] == "inconclusive"
    assert artifact["path"] == "N/A"
    checked = "\n".join(artifact["checked_paths"])
    assert "harness/artifacts/autosci/workspace/wiki/ideas/idea-001.md" not in checked
    assert any(str(tmp_path) in item for item in artifact["checked_paths"])


def test_autosci_skill_shim_review_resolves_harness_prefixed_workspace_path(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts" / "autosci" / "workspace" / "wiki"
    review_target = wiki_root / "ideas" / "idea-001.md"
    review_target.parent.mkdir(parents=True, exist_ok=True)
    review_target.write_text(
        "---\ntitle: Idea 001\n---\n# Idea 001\n\n"
        "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table.\n",
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$review",
        "harness/artifacts/autosci/workspace/wiki/ideas/idea-001.md",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--run-id",
        "shim-review-prefixed-workspace-path",
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["skill"] == "review"
    assert summary["execution_status"] == "partial"

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    artifact = review_evidence["outputs"]["artifact"]
    assert artifact["path"] != "N/A"
    assert artifact["path"].endswith("artifacts/autosci/workspace/wiki/ideas/idea-001.md")
    assert Path(artifact["path"]).is_absolute() and Path(artifact["path"]).exists()


def test_autosci_skill_shim_review_uses_supplied_review_llm_evidence(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "outputs").mkdir(parents=True)
    review_target = wiki_root / "outputs/skillgen-review-llm.md"
    review_target.write_text(
        "---\ntitle: SkillGen Review LLM Target\n---\n# SkillGen Review LLM Target\n\n"
        "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table.\n",
        encoding="utf-8",
    )
    llm_evidence = tmp_path / "review-llm-evidence.json"
    llm_evidence.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "task_id": "review-llm-task",
                "sprint_id": "review-llm-sprint",
                "node_id": "review-llm-node",
                "status": "completed",
                "inputs": {"target": "skillgen-review-llm"},
                "outputs": {
                    "review": {
                        "artifact_id": "artifact:skillgen-review-llm",
                        "target": "skillgen-review-llm",
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "hard",
                        "focus": "method",
                        "score": 0.42,
                        "recommendation": "revise_required",
                        "evidence_ids": ["review-llm:001"],
                    },
                    "findings": [
                        {
                            "finding_id": "review-llm.method-risk",
                            "severity": "high",
                            "category": "method",
                            "evidence": "The independent reviewer found a method risk.",
                            "suggestion": "Add an ablation and failure-mode analysis before promotion.",
                        }
                    ],
                    "artifact": {"artifact_id": "artifact:skillgen-review-llm"},
                },
                "artifacts": [],
                "provenance": {
                    "operator_id": "review-llm-test",
                    "implementation_package": "test",
                    "timestamp": "2026-06-24T00:00:00Z",
                },
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$review",
        "skillgen-review-llm",
        "--from-wiki",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--review-llm-evidence",
        str(llm_evidence),
        "--run-id",
        "shim-review-llm-evidence",
    )
    assert proc.returncode == 2, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["schema"] == "artifact_review.v1"
    assert action["gate_status"] == "failed"

    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    review = review_evidence["outputs"]["review"]
    assert review["review_mode"] == "review_llm"
    assert review["review_available"] is True
    assert review["review_llm"]["status"] == "completed"
    assert review["review_llm"]["source_path"] == str(llm_evidence)
    boundary = review_evidence["outputs"]["final_acceptance_boundary"]
    assert boundary["final_acceptance_ready"] is False
    assert boundary["status"] == "review_llm_incomplete"
    assert boundary["proof_verdict"] == "not_supported"
    assert boundary["reviewer_independence_status"] == "same_provider_limitation"
    assert "review-llm:001" in boundary["evidence_ids"]
    assert not any(
        artifact["type"] == "review_model_runtime_proof_manifest_json"
        for artifact in review_evidence["artifacts"]
    )
    source_proof_artifact = next(
        artifact
        for artifact in review_evidence["artifacts"]
        if artifact["type"] == "provider_source_runtime_proof_manifest_json"
    )
    source_proof = json.loads((tmp_path / source_proof_artifact["path"]).read_text(encoding="utf-8"))
    source_proof_entry = source_proof["proofs"][0]
    assert source_proof_entry["native_skill"] == "review"
    assert source_proof_entry["categories"] == ["provider_source_evidence"]
    assert any(ref.endswith("outputs/skillgen-review-llm.md") for ref in source_proof_entry["evidence_refs"])
    assert review["score"] <= 0.42
    assert review["recommendation"] == "revise_required"
    finding_ids = {finding["finding_id"] for finding in review_evidence["outputs"]["findings"]}
    assert "review-llm.method-risk" in finding_ids


def test_autosci_skill_shim_review_uses_review_llm_command_bridge(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "outputs").mkdir(parents=True)
    review_target = wiki_root / "outputs/skillgen-review-command.md"
    review_target.write_text(
        "---\ntitle: SkillGen Review Command Target\n---\n# SkillGen Review Command Target\n\n"
        "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table.\n",
        encoding="utf-8",
    )
    command_path = tmp_path / "review_llm_command.py"
    command_path.write_text(
        """
import json
import sys

request = json.loads(sys.stdin.read())
target = request["inputs"].get("target", "N/A")
print(json.dumps({
    "schema": "artifact_review.v1",
    "status": "completed",
    "outputs": {
        "review": {
            "artifact_id": "artifact:" + target,
            "target": target,
            "review_mode": "review_llm",
            "review_available": True,
            "difficulty": request.get("difficulty", "standard"),
            "focus": request.get("focus", "method"),
            "score": 0.52,
            "recommendation": "revise",
            "evidence_ids": ["review-llm:command"]
        },
        "findings": [{
            "finding_id": "review-llm.command-finding",
            "severity": "medium",
            "category": "method",
            "evidence": "Command bridge reviewed the target artifact.",
            "suggestion": "Keep the method evidence attached before promotion."
        }]
    }
}))
""".lstrip(),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "$review",
        "skillgen-review-command",
        "--from-wiki",
        "--difficulty",
        "hard",
        "--focus",
        "method",
        "--review-llm-command",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(command_path))}",
        "--run-id",
        "shim-review-llm-command",
    )
    assert proc.returncode == 2, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    review = review_evidence["outputs"]["review"]
    assert review["review_mode"] == "review_llm"
    assert review["review_available"] is True
    assert review["review_llm"]["status"] == "completed"
    assert review["review_llm"]["invocation_mode"] == "command"
    assert "review-llm:command" in review["evidence_ids"]
    boundary = review_evidence["outputs"]["final_acceptance_boundary"]
    assert boundary["final_acceptance_ready"] is False
    assert boundary["invocation_mode"] == "command"
    assert "review-llm:command" in boundary["evidence_ids"]
    assert boundary["reviewer_independence_status"] == "same_provider_limitation"
    assert not any(
        artifact["type"] == "review_model_runtime_proof_manifest_json"
        for artifact in review_evidence["artifacts"]
    )


def test_autosci_skill_shim_review_invokes_openai_compatible_provider(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "outputs").mkdir(parents=True)
    review_target = wiki_root / "outputs/skillgen-review-provider.md"
    review_target.write_text(
        "---\ntitle: SkillGen Provider Review Target\n---\n# SkillGen Provider Review Target\n\n"
        "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table.\n",
        encoding="utf-8",
    )
    source_text = "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table."
    proof_source = tmp_path / "skillgen-review-provider.source.txt"
    proof_source.write_text(source_text + "\n", encoding="utf-8")
    proof_bundle = tmp_path / "skillgen-review-provider.proof.json"
    proof_bundle.write_text(
        json.dumps(
            {
                "schema": "scientific_review_proof.v1",
                "writer": {"provider": "openai", "model": "writer-model"},
                "artifact": {
                    "path": str(review_target),
                    "sha256": hashlib.sha256(review_target.read_bytes()).hexdigest(),
                },
                "claims": [
                    {
                        "claim_id": "claim.provider-review-method",
                        "claim": source_text,
                        "source": {
                            "source_id": "source.provider-review-method",
                            "path": str(proof_source),
                            "sha256": hashlib.sha256(proof_source.read_bytes()).hexdigest(),
                        },
                        "evidence_span": {"start": 0, "end": len(source_text), "text": source_text},
                        "acceptance_criterion": "The provider reviewer must reload and check the persisted method claim.",
                        "residual_risk": "The HTTP server is a unit-test transport fixture, not live-provider acceptance evidence.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            captured["authorization"] = self.headers.get("authorization", "")
            captured["payload"] = json.loads(body)
            content = json.dumps(
                {
                    "schema": "artifact_review.v1",
                    "status": "completed",
                    "outputs": {
                        "review": {
                            "artifact_id": "artifact:skillgen-review-provider",
                            "target": "skillgen-review-provider",
                            "review_mode": "review_llm",
                            "review_available": True,
                            "difficulty": "hard",
                            "focus": "method",
                            "score": 0.61,
                            "recommendation": "revise",
                            "evidence_ids": ["review-llm:provider"],
                        },
                        "findings": [
                            {
                                "finding_id": "review-llm.provider-finding",
                                "severity": "medium",
                                "category": "method",
                                "evidence": "Provider review saw method evidence but requested one more ablation.",
                                "suggestion": "Add an ablation result before promotion.",
                            }
                        ],
                    },
                }
            )
            response = json.dumps(
                {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 40, "total_tokens": 60},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions"
        proc = run_shim(
            tmp_path,
            "$review",
            "skillgen-review-provider",
            "--from-wiki",
            "--review",
            "--difficulty",
            "hard",
            "--focus",
            "method",
            "--review-llm-provider",
            "openai_compatible",
            "--review-llm-model",
            "gpt-4.1-mini",
            "--review-llm-endpoint",
            endpoint,
            "--proof-bundle",
            str(proof_bundle),
            "--run-id",
            "shim-review-llm-provider",
            extra_env={"OPENAI_API_KEY": "test-provider-key", "OPENROUTER_API_KEY": ""},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert proc.returncode == 0, proc.stderr
    assert captured["authorization"] == "Bearer test-provider-key"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["model"] == "gpt-4.1-mini"
    assert "response_format" not in request_payload

    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    review = review_evidence["outputs"]["review"]
    review_llm = review["review_llm"]
    assert review["review_mode"] == "review_llm"
    assert review["review_available"] is True
    assert review_llm["status"] == "completed"
    assert review_llm["invocation_mode"] == "provider"
    assert review_llm["model"] == "gpt-4.1-mini"
    assert review_llm["provider"] == "openai_compatible"
    independence = review["proof_contract"]["reviewer_separation"]["independence"]
    assert independence["status"] == "independent_provider"
    assert independence["execution_bound"] is True
    assert independence["writer"]["provider"] == "openai"
    assert independence["reviewer"]["provider"] == "openai_compatible"
    assert Path(review_llm["source_path"]).exists()
    assert "review-llm:provider" in review["evidence_ids"]
    boundary = review_evidence["outputs"]["final_acceptance_boundary"]
    assert boundary["final_acceptance_ready"] is True
    assert boundary["invocation_mode"] == "provider"
    assert boundary["provider"] == "openai_compatible"
    assert boundary["model"] == "gpt-4.1-mini"
    proof_artifact = next(
        artifact
        for artifact in review_evidence["artifacts"]
        if artifact["type"] == "review_model_runtime_proof_manifest_json"
    )
    proof = json.loads((tmp_path / proof_artifact["path"]).read_text(encoding="utf-8"))
    proof_entry = proof["proofs"][0]
    assert proof_entry["collection_mode"] == "live_provider"
    assert proof_entry["categories"] == [
        "review_llm_or_model_evidence",
        "external_runtime_evidence",
        "provider_source_evidence",
    ]
    assert proof_entry["provenance"]["source"] == "openai_compatible"


def test_autosci_skill_shim_review_normalizes_flat_openai_payload_without_status(tmp_path: Path) -> None:
    wiki_root = tmp_path / "artifacts/autosci/workspace/wiki"
    (wiki_root / "outputs").mkdir(parents=True)
    review_target = wiki_root / "outputs/flat-openai-review-provider.md"
    review_target.write_text(
        "---\ntitle: Flat OpenAI Review Target\n---\n# Flat OpenAI Review Target\n\n"
        "The method uses a dataset, metric, baseline, evidence artifact, and claim-linked result table.\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            captured["authorization"] = self.headers.get("authorization", "")
            captured["payload"] = json.loads(body)
            content = json.dumps(
                {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "difficulty": "hard",
                        "focus": "method",
                        "score": 0.12,
                        "recommendation": "revise_required",
                        "evidence_ids": ["review-llm:flat-openai-response"],
                    },
                    "findings": [
                        {
                            "finding_id": "review-llm.flat-openai-response",
                            "severity": "high",
                            "category": "method",
                            "evidence": "The response contains a valid review but no top-level status envelope.",
                            "suggestion": "Normalize the otherwise valid provider response with an audit warning.",
                        }
                    ],
                }
            )
            response = json.dumps(
                {
                    "choices": [{"message": {"content": content}}],
                    "model": "gpt-4.1-mini-test",
                    "usage": {"prompt_tokens": 20, "completion_tokens": 40, "total_tokens": 60},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions"
        proc = run_shim(
            tmp_path,
            "$review",
            "flat-openai-review-provider",
            "--from-wiki",
            "--review",
            "--difficulty",
            "hard",
            "--focus",
            "method",
            "--review-llm-provider",
            "openai",
            "--review-llm-model",
            "gpt-4.1-mini",
            "--review-llm-endpoint",
            endpoint,
            "--run-id",
            "shim-flat-openai-review-provider",
            extra_env={"OPENAI_API_KEY": "test-provider-key", "OPENROUTER_API_KEY": ""},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert proc.returncode == 2, proc.stderr
    assert captured["authorization"] == "Bearer test-provider-key"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    response_format = request_payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    response_schema = response_format["json_schema"]["schema"]
    assert response_schema["required"] == ["schema", "status", "outputs"]
    assert response_schema["properties"]["status"]["enum"] == ["completed", "inconclusive"]
    assert "test-provider-key" not in json.dumps(request_payload)

    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    review_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    review = review_evidence["outputs"]["review"]
    review_llm = review["review_llm"]
    assert review["review_mode"] == "review_llm"
    assert review["review_available"] is True
    assert review_llm["status"] == "completed"
    assert review_llm["invocation_mode"] == "provider"
    assert review_llm["provider"] == "openai"
    assert review_llm["normalization_warnings"] == [
        "Review LLM response omitted top-level status; inferred completed from a valid review envelope."
    ]
    boundary = review_evidence["outputs"]["final_acceptance_boundary"]
    assert boundary["final_acceptance_ready"] is False
    assert boundary["status"] == "review_llm_incomplete"
    assert boundary["proof_verdict"] == "not_supported"


def test_autosci_skill_shim_keeps_setup_gated(tmp_path: Path) -> None:
    secret_value = "sk-test-setup-secret"
    proc = run_shim(
        tmp_path,
        "skill",
        "setup",
        "--run-id",
        "shim-setup",
        extra_env={"OPENAI_API_KEY": secret_value, "AUTOSCI_REVIEW_LLM_MODEL": "gpt-4.1-mini"},
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["execution_status"] == "gated"
    assert summary["side_effect_policy"] == "approval_required"
    assert summary["action_count"] == 1
    assert summary["passed_count"] == 1

    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    assert action["action"] == "setup_status"
    assert action["schema"] == "workflow_evolution.v1"
    setup_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    assert setup_evidence["outputs"]["evolution"]["approval_state"] == "proposed"
    assert setup_evidence["outputs"]["evolution"]["review"]["protected_core_edits_applied"] is False
    review = setup_evidence["outputs"]["evolution"]["review"]
    assert review["setup_status"]["secrets_redacted"] is True
    assert review["setup_status"]["configured_count"] >= 1
    artifacts = {artifact["type"]: artifact["path"] for artifact in setup_evidence["artifacts"]}
    assert "setup_status_json" in artifacts
    status = json.loads((tmp_path / artifacts["setup_status_json"]).read_text(encoding="utf-8"))
    assert status["schema"] == "autosci_setup_status.v1"
    assert status["summary"]["review_llm_ready"] is True
    openai = next(item for item in status["keys"] if item["key"] == "OPENAI_API_KEY")
    assert openai["configured"] is True
    assert openai["process_env_set"] is True
    assert openai["value_recorded"] is False
    assert secret_value not in json.dumps(setup_evidence)
    assert secret_value not in json.dumps(status)

    evidence_path = Path(summary["evidence_path"])
    gate = run_gate(evidence_path)
    result = assert_gate_inconclusive_without_reasons(gate)
    assert result["warnings"]


def test_autosci_skill_shim_setup_autosci_native_writes_explicit_dotenv_without_secret_leakage(tmp_path: Path) -> None:
    secret_value = "phase22-test-autosci-native-setup-secret"
    approved_env = tmp_path / "approved-setup.env"
    dotenv_path = tmp_path / "runtime/.env"
    approved_env.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=" + secret_value,
                "AUTOSCI_REVIEW_LLM_MODEL=gpt-4.1-mini",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = run_shim(
        tmp_path,
        "skill",
        "setup",
        "--after-artifact",
        str(approved_env),
        "--setup-dotenv-path",
        str(dotenv_path),
        "--gate-mode",
        "autosci_native",
        "--run-id",
        "shim-setup-autosci-native-write",
    )
    assert proc.returncode == 0, proc.stderr
    assert dotenv_path.exists()
    dotenv_text = dotenv_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" + secret_value in dotenv_text
    assert "AUTOSCI_REVIEW_LLM_MODEL=gpt-4.1-mini" in dotenv_text

    summary = json.loads(proc.stdout)
    payload = json.loads(Path(summary["evidence_path"]).read_text(encoding="utf-8"))
    action = payload["outputs"]["skill_run"]["actions"][0]
    setup_evidence = json.loads(Path(action["evidence_path"]).read_text(encoding="utf-8"))
    review = setup_evidence["outputs"]["evolution"]["review"]
    assert review["protected_core_edits_applied"] is True
    assert review["application_state"] == "applied"
    assert review["setup_config_execution"]["executed"] is True
    assert review["setup_config_execution"]["keys_written"] == [
        "AUTOSCI_REVIEW_LLM_MODEL",
        "OPENAI_API_KEY",
    ]
    assert review["setup_status"]["secrets_redacted"] is True
    policy = setup_evidence["outputs"]["policy_decision"]
    assert policy["mode"] == "autosci_native"
    assert policy["execute_side_effects"] is True
    assert policy["synthetic_approval_ref"].startswith("policy:auto:autosci_native:setup_status:")

    artifacts = {artifact["type"]: artifact["path"] for artifact in setup_evidence["artifacts"]}
    assert "gate_policy_decision_json" in artifacts
    assert "gate_policy_allowlist_json" in artifacts
    assert "setup_before_snapshot_json" in artifacts
    assert "setup_after_snapshot_json" in artifacts
    assert "setup_config_runtime_evidence_json" in artifacts
    assert "approval_runtime_proof_manifest_json" in artifacts
    assert "side_effect_runtime_proof_manifest_json" in artifacts
    contract = json.loads((tmp_path / artifacts["approval_contract_json"]).read_text(encoding="utf-8"))
    runtime = json.loads((tmp_path / artifacts["setup_config_runtime_evidence_json"]).read_text(encoding="utf-8"))
    status = json.loads((tmp_path / artifacts["setup_status_json"]).read_text(encoding="utf-8"))
    assert contract["policy_auto_approved"] is True
    assert contract["execution_verified"] is True
    assert contract["setup_config_applied"] is True
    assert runtime["secret_values_recorded"] is False
    assert runtime["keys_written"] == ["AUTOSCI_REVIEW_LLM_MODEL", "OPENAI_API_KEY"]
    assert status["summary"]["review_llm_ready"] is True
    assert secret_value not in json.dumps(setup_evidence)
    assert secret_value not in json.dumps(contract)
    assert secret_value not in json.dumps(runtime)
    assert secret_value not in json.dumps(status)
