from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from evaluators.scientific import lifecycle_runtime_gate


def _write_paper(path: Path, *, job_id: str = "job-runtime", node_id: str = "paper_ingest") -> str:
    payload = {
        "schema": "research_paper.v1",
        "task_id": f"task.{job_id}.{node_id}",
        "sprint_id": job_id,
        "node_id": node_id,
        "status": "completed",
        "inputs": {"source_ref": "runtime-paper.md"},
        "outputs": {
            "paper": {
                "paper_id": "paper.runtime",
                "title": "Runtime Paper",
                "source_type": "markdown",
                "source_ref": "runtime-paper.md",
                "parse_status": "parsed",
                "sections": [{"section_id": "sec.abstract", "title": "Abstract"}],
            }
        },
        "artifacts": [{"type": "normalized_paper", "path": "unavailable:test fixture"}],
        "provenance": {
            "operator_id": "ScientificPaperIngestor",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": "2026-06-25T00:00:00Z",
        },
        "limitations": [],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_runtime_sidecars(tmp_path: Path) -> tuple[str, str]:
    operator_result = tmp_path / "operator-result.json"
    bridge_result = tmp_path / "bridge-result.json"
    operator_result.write_text(
        json.dumps({"status": "completed", "exit_code": 0}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bridge_result.write_text(
        json.dumps({"ok": True, "action": "ingest_paper", "status": "completed"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(operator_result), str(bridge_result)


def _runtime_payload(tmp_path: Path) -> dict:
    artifact = tmp_path / "research_paper.v1.json"
    digest = _write_paper(artifact)
    operator_result, bridge_result = _write_runtime_sidecars(tmp_path)
    return {
        "schema": "scientific_lifecycle.v1",
        "workflow_id": "scientific_paper_ingestion_v1",
        "job_id": "job-runtime",
        "lifecycle_status": "passed",
        "required_nodes": ["paper_ingest"],
        "node_results": {
            "paper_ingest": {
                "job_id": "job-runtime",
                "node_id": "paper_ingest",
                "status": "passed",
                "gate": "G_PAPER_INGEST",
                "operator_result_path": operator_result,
                "bridge_result_path": bridge_result,
                "artifact_path": str(artifact),
                "artifact_sha256": digest,
                "expected_schema": "research_paper.v1",
            }
        },
        "gate_results": {
            "paper_ingest": {
                "job_id": "job-runtime",
                "node_id": "paper_ingest",
                "status": "passed",
                "gate": "G_PAPER_INGEST",
            }
        },
    }


def test_lifecycle_runtime_gate_accepts_job_scoped_artifact(tmp_path: Path) -> None:
    result = lifecycle_runtime_gate.evaluate(_runtime_payload(tmp_path))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_lifecycle_runtime_gate_rejects_empty_result_maps() -> None:
    payload = {
        "schema": "scientific_lifecycle.v1",
        "workflow_id": "scientific_paper_ingestion_v1",
        "job_id": "job-runtime",
        "required_nodes": ["paper_ingest"],
        "node_results": {},
        "gate_results": {},
    }

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "node_results must be a non-empty map" in result.reasons
    assert "gate_results must be a non-empty map" in result.reasons


def test_lifecycle_runtime_gate_rejects_missing_node_result(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["required_nodes"] = ["paper_ingest", "claim_extract"]

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "node_results.claim_extract is required" in result.reasons


def test_lifecycle_runtime_gate_accepts_explicit_blocked_required_node(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["required_nodes"] = ["paper_ingest", "report_plan"]
    payload["lifecycle_status"] = "blocked"
    payload["blocked_nodes"] = {
        "report_plan": {
            "job_id": "job-runtime",
            "node_id": "report_plan",
            "status": "blocked",
            "reason": "Waiting for completed Review LLM evidence.",
            "required_evidence": ["artifact_review.v1 review_mode=review_llm"],
            "unblock_condition": "Provide completed artifact_review.v1 before report planning.",
        }
    }

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "inconclusive"
    assert result.reasons == []
    assert "blocked waiting for external evidence" in " ".join(result.warnings)


def test_lifecycle_runtime_gate_rejects_unstructured_blocked_node(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["required_nodes"] = ["paper_ingest", "report_plan"]
    payload["lifecycle_status"] = "blocked"
    payload["blocked_nodes"] = {"report_plan": {"status": "blocked"}}

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "reason is required" in joined
    assert "required_evidence must be a non-empty list" in joined
    assert "unblock_condition is required" in joined


def test_lifecycle_runtime_gate_rejects_wrong_job_artifact(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    artifact = tmp_path / "wrong-job.json"
    digest = _write_paper(artifact, job_id="other-job")
    payload["node_results"]["paper_ingest"]["artifact_path"] = str(artifact)
    payload["node_results"]["paper_ingest"]["artifact_sha256"] = digest

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "artifact sprint_id must match job_id job-runtime" in " ".join(result.reasons)


def test_lifecycle_runtime_gate_rejects_missing_artifact(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["node_results"]["paper_ingest"]["artifact_path"] = str(tmp_path / "missing.json")

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "artifact_path does not exist" in " ".join(result.reasons)


def test_lifecycle_runtime_gate_rejects_hash_mismatch(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["node_results"]["paper_ingest"]["artifact_sha256"] = "0" * 64

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "artifact_sha256 mismatch" in " ".join(result.reasons)


def test_lifecycle_runtime_gate_rejects_inconclusive_node(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["node_results"]["paper_ingest"]["status"] = "inconclusive"

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "status must be passed" in " ".join(result.reasons)


def test_lifecycle_runtime_gate_rejects_missing_runtime_result_paths(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["node_results"]["paper_ingest"].pop("operator_result_path")
    payload["node_results"]["paper_ingest"]["bridge_result_path"] = str(tmp_path / "missing-bridge.json")

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "operator_result_path is required" in joined
    assert "bridge_result_path does not exist" in joined


def test_lifecycle_runtime_gate_rejects_missing_gate_name(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["node_results"]["paper_ingest"].pop("gate")

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "node_results.paper_ingest.gate is required" in " ".join(result.reasons)


def test_lifecycle_runtime_gate_rejects_bridge_owned_lifecycle(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["execution_owner"] = "autosci_bridge.run_research_lifecycle"
    payload["node_results"]["paper_ingest"]["action"] = "run_research_lifecycle"

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "autosci_bridge lifecycle projection" in joined
    assert "bridge-owned lifecycle action" in joined


def test_lifecycle_runtime_gate_rejects_black_box_runner(tmp_path: Path) -> None:
    payload = _runtime_payload(tmp_path)
    payload["nodes"] = [{"id": "paper_ingest", "logical_operator": "AutoSciRunner"}]

    result = lifecycle_runtime_gate.evaluate(payload)

    assert result.ok is False
    assert "AutoSciRunner" in " ".join(result.reasons)
