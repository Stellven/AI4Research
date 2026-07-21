from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
TOOL = REPO / "tools" / "review_model_runtime_proof.py"
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


def test_review_llm_evidence_writes_runtime_proof_manifest(tmp_path: Path) -> None:
    evidence = tmp_path / "artifacts/runtime/novelty/review-llm.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "review_llm",
                        "review_available": True,
                        "score": 0.72,
                        "recommendation": "pass_with_review_required",
                        "evidence_ids": ["review-llm:novelty"],
                        "review_llm": {
                            "provider": "openai-compatible",
                            "model": "gpt-5.5",
                        },
                    },
                    "findings": [],
                },
                "provenance": {"timestamp": "2026-06-29T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "artifacts/runtime/novelty/review-llm.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-evidence",
            str(evidence),
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
    assert proof_entry["categories"] == ["review_llm_or_model_evidence"]
    assert proof_entry["collection_mode"] == "manual_review"
    assert proof_entry["production_ready"] is True
    assert proof_entry["provenance"]["source"] == "openai-compatible"
    assert proof_entry["provenance"]["artifact_kind"] == "artifact_review"
    assert proof_entry["evidence_refs"] == ["artifacts/runtime/novelty/review-llm.json"]


def test_model_response_writes_runtime_proof_manifest(tmp_path: Path) -> None:
    evidence = tmp_path / "artifacts/runtime/ask/model-response.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        json.dumps(
            {
                "schema": "autosci_model_response.v1",
                "status": "completed",
                "outputs": {
                    "answer": "The wiki evidence supports the claim.",
                    "confidence": 0.83,
                    "evidence_ids": ["model:ask-support"],
                    "provider": "command",
                    "model": "local-reviewer",
                },
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "artifacts/runtime/ask/model-response.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-evidence",
            str(evidence),
            "--native-skill",
            "ask",
            "--runtime-proof-out",
            str(proof),
            "--collection-mode",
            "manual_review",
        )
    )
    assert result["status"] == "completed"
    manifest = json.loads(proof.read_text(encoding="utf-8"))
    proof_entry = manifest["proofs"][0]
    assert proof_entry["native_skill"] == "ask"
    assert proof_entry["provenance"]["source"] == "command"
    assert proof_entry["provenance"]["artifact_kind"] == "model_response"
    assert proof_entry["evidence_refs"] == ["artifacts/runtime/ask/model-response.json"]


def test_local_surrogate_review_is_not_runtime_proof(tmp_path: Path) -> None:
    evidence = tmp_path / "local-surrogate-review.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "artifact_review.v1",
                "status": "completed",
                "outputs": {
                    "review": {
                        "review_mode": "local_surrogate",
                        "review_available": False,
                        "evidence_ids": ["artifact:local"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    proof = tmp_path / "surrogate.proof.json"
    result = payload(
        run_tool(
            tmp_path,
            "from-evidence",
            str(evidence),
            "--native-skill",
            "review",
            "--runtime-proof-out",
            str(proof),
        )
    )
    assert result["status"] == "inconclusive"
    assert result["runtime_proof_manifest_status"] == "not_written"
    assert not proof.exists()


def test_review_model_runtime_proof_tool_is_exposed_for_model_dependent_routes() -> None:
    config = json.loads(ROUTE_CONFIG.read_text(encoding="utf-8"))
    routes = {item["native_skill"]: item for item in config["routes"]}
    expected = {
        "ask",
        "check",
        "daily-arxiv",
        "exp-design",
        "exp-eval",
        "ideate",
        "novelty",
        "paper-draft",
        "paper-plan",
        "rebuttal",
        "research",
        "review",
    }
    for skill in expected:
        assert "tools/review_model_runtime_proof.py from-evidence" in routes[skill]["primary_tools"]
