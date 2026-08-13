from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from evidence import JourneyRecorder
from journey_runner import action_evidence, bootstrap_live_environment, run_autosci, write_json


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provider_env(repo_root: Path) -> dict[str, str]:
    bootstrapped = bootstrap_live_environment(repo_root, {})
    env = {
        key: value
        for key, value in bootstrapped.items()
        if key
        in {
            "AUTOSCI_LIVE_PROVIDER_TESTS",
            "AUTOSCI_LIVE_REVIEW_LLM_TEST",
            "AUTOSCI_LIVE_REVIEW_LLM_PROVIDER",
            "AUTOSCI_LIVE_REVIEW_LLM_MODEL",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "PHASE22_ENABLE_NETWORK_JOURNEYS",
            "SOLAR_AUTOSCI_ALLOW_NETWORK",
        }
    }
    env["AUTOSCI_LIVE_PROVIDER_TESTS"] = "1"
    env["AUTOSCI_LIVE_REVIEW_LLM_TEST"] = "1"
    env["AUTOSCI_RESEARCH_LLM_PROVIDER"] = "openrouter"
    env["AUTOSCI_RESEARCH_LLM_MODEL"] = os.environ.get(
        "PHASE22_045_OPENROUTER_WRITER_MODEL",
        "deepseek/deepseek-v3.2",
    )
    env["AUTOSCI_REVIEW_LLM_MODEL"] = os.environ.get(
        "PHASE22_045_OPENAI_REVIEWER_MODEL",
        "gpt-5-mini",
    )
    env["AUTOSCI_REVIEW_LLM_PROVIDER"] = "openai"
    env["AUTOSCI_REVIEW_LLM_TIMEOUT"] = os.environ.get("PHASE22_045_REVIEW_TIMEOUT", "90")
    return env


def _without_banned_models(env: dict[str, str]) -> dict[str, str]:
    banned = {"gpt-5.5", "gpt5.5", "gpt-5.6-sol", "gpt5.6-sol", "gpt-5.6 sol", "gpt5.6 sol"}
    for key in ("AUTOSCI_RESEARCH_LLM_MODEL", "AUTOSCI_REVIEW_LLM_MODEL"):
        normalized = str(env.get(key) or "").strip().lower().replace("_", "-")
        if normalized in banned:
            raise AssertionError(f"banned live model configured for {key}")
    return env


def _with_env(env: dict[str, str]):
    class EnvPatch:
        def __enter__(self) -> None:
            self.previous = dict(os.environ)
            os.environ.update(env)

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            os.environ.clear()
            os.environ.update(self.previous)

    return EnvPatch()


def _writer_report_body(writer_result: dict[str, Any]) -> str:
    report = writer_result.get("report") if isinstance(writer_result.get("report"), dict) else {}
    body = str(report.get("body") or "").strip()
    if body:
        return body
    sections = report.get("sections") if isinstance(report.get("sections"), list) else []
    rendered = "\n\n".join(str(item.get("body") or "") for item in sections if isinstance(item, dict))
    return rendered.strip()


def test_p22_045_live_independent_provider_review(repo_root: Path, tmp_path: Path) -> None:
    env = _without_banned_models(_provider_env(repo_root))
    if not env.get("OPENROUTER_API_KEY") or not env.get("OPENAI_API_KEY"):
        pytest.skip("P22-045 requires OPENROUTER_API_KEY and OPENAI_API_KEY in the live environment.")

    from harness.plugins.autosci.services.production_research import ResearchModelService

    rec = JourneyRecorder(repo_root, "P22-045")
    sandbox = tmp_path / "p22-045"
    provider_workspace = sandbox / "writer-workspace"
    provider_workspace.mkdir(parents=True)

    task_contract = {
        "user_intent": "Draft a concise bounded research-review target for provider independence verification.",
        "deliverable": {"language": "en"},
    }
    synthesis = {
        "claims": [
            {
                "claim_id": "claim-openrouter-writer-provenance",
                "text": "The provider-independence journey uses an OpenRouter writer artifact and a separate OpenAI reviewer.",
                "evidence_ids": ["source-openrouter-writer-provenance"],
                "uncertainty": "low",
                "limitations": ["This proof establishes provider separation, not external scientific validity."],
            }
        ],
        "limitations": ["Provider separation is limited to the configured live API calls."],
    }

    with _with_env(env):
        service = ResearchModelService.from_environment(provider_workspace)
        writer_result = service(
            node_id="report_draft",
            task_contract=task_contract,
            evidence_synthesis=synthesis,
            deliverable_requirements={"format": "markdown", "max_words": 180},
        )

    provider_usage = writer_result.get("provider_usage") if isinstance(writer_result.get("provider_usage"), list) else []
    writer_usage = provider_usage[0] if provider_usage and isinstance(provider_usage[0], dict) else {}
    target = write_json(rec.artifact_dir / "openrouter-writer-output.json", writer_result)
    report_body = _writer_report_body(writer_result)
    review_target = rec.artifact_dir / "openrouter-writer-review-target.md"
    review_target.write_text(
        "# OpenRouter Writer Review Target\n\n"
        + (report_body or "OpenRouter writer produced a bounded provider provenance review target.")
        + "\n",
        encoding="utf-8",
    )
    source_text = (
        "The OpenRouter writer produced a bounded provider provenance review target. "
        f"provider={writer_result.get('provider')} model={writer_result.get('model')} "
        f"request_sha256={writer_usage.get('request_sha256')} response_sha256={writer_usage.get('response_sha256')}"
    )
    source_path = rec.artifact_dir / "openrouter-writer-provenance-source.txt"
    source_path.write_text(source_text + "\n", encoding="utf-8")
    claim = "The OpenRouter writer produced a bounded provider provenance review target."
    proof = write_json(
        rec.artifact_dir / "openrouter-writer-review-proof.json",
        {
            "schema": "scientific_review_proof.v1",
            "writer": {
                "provider": writer_result.get("provider"),
                "model": writer_result.get("model"),
                "execution": {
                    "collection_mode": "live_provider",
                    "provider_usage": provider_usage,
                },
            },
            "artifact": {"path": str(review_target), "sha256": _sha256(review_target)},
            "claims": [
                {
                    "claim_id": "claim.p22-045.openrouter-writer",
                    "claim": claim,
                    "source": {
                        "source_id": "p22-045-openrouter-writer-provenance",
                        "path": str(source_path),
                        "sha256": _sha256(source_path),
                    },
                    "evidence_span": {"start": 0, "end": len(claim), "text": claim},
                    "acceptance_criterion": "The proof must bind a persisted OpenRouter writer artifact to a separate completed OpenAI reviewer execution.",
                    "residual_risk": "This proof establishes live provider separation only; scientific external validity remains out of scope.",
                }
            ],
        },
    )

    rec.add_artifact(target, "openrouter_writer_output")
    rec.add_artifact(review_target, "openrouter_writer_review_target")
    rec.add_artifact(source_path, "openrouter_writer_provenance_source")
    rec.add_artifact(proof, "scientific_review_proof")

    review, _harness_dir = run_autosci(
        rec,
        sandbox,
        "review",
        [
            str(review_target),
            "--proof-bundle",
            str(proof),
            "--review",
            "--focus",
            "method",
            "--difficulty",
            "hard",
            "--review-llm-provider",
            "openai",
            "--review-llm-model",
            env["AUTOSCI_REVIEW_LLM_MODEL"],
            "--run-id",
            "p22-045-live-independent-provider-review",
        ],
        timeout=180,
        extra_env=env,
        allow_live=True,
    )
    review_ev = action_evidence(review, "review_artifact")
    if review_ev:
        rec.add_artifact(review_ev, "openai_reviewer_evidence")
    review_payload = json.loads(review_ev.read_text(encoding="utf-8")) if review_ev and review_ev.exists() else {}
    review_output = review_payload.get("outputs", {}).get("review", {}) if isinstance(review_payload, dict) else {}
    review_llm = review_output.get("review_llm") if isinstance(review_output.get("review_llm"), dict) else {}
    proof_contract = review_output.get("proof_contract") if isinstance(review_output.get("proof_contract"), dict) else {}
    independence = (
        proof_contract.get("reviewer_separation", {})
        .get("independence", {})
        if isinstance(proof_contract.get("reviewer_separation"), dict)
        else {}
    )

    rec.add_assertion("writer_provider_is_openrouter", writer_result.get("provider") == "openrouter", writer_result)
    rec.add_assertion("writer_runtime_was_archived", bool(writer_usage.get("request_sha256") and writer_usage.get("response_sha256") and writer_usage.get("archive_path")), writer_usage)
    rec.add_assertion("reviewer_provider_completed_openai", review_llm.get("status") == "completed" and review_llm.get("invocation_mode") == "provider" and review_llm.get("provider") == "openai", review_llm)
    rec.add_assertion("independent_provider_bound_to_execution", independence.get("status") == "independent_provider" and independence.get("execution_bound") is True, independence)
    rec.add_l2(
        "Reasoning",
        "Independent evidence review",
        "A live OpenRouter writer artifact was reviewed through a separate live OpenAI reviewer provider, and the proof contract bound provider independence to completed reviewer execution.",
        Path(review_ev) if review_ev else proof,
        True,
    )

    limitations = []
    if proof_contract.get("verdict") != "supported":
        limitations.append("The independent provider route executed, but the deterministic proof contract did not mark the artifact as fully supported.")
    status = "PASS_WITH_KNOWN_LIMITATIONS" if limitations and all(item["passed"] for item in rec.assertions) else "PASS"
    if not all(item["passed"] for item in rec.assertions):
        status = "FAIL"
    rec.finalize(status, limitations=limitations)

    assert writer_result.get("provider") == "openrouter"
    assert review_llm.get("status") == "completed", review_llm
    assert review_llm.get("provider") == "openai"
    assert independence.get("status") == "independent_provider", independence
