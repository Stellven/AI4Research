from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
AUTOSCI_ROOT = REPO / "harness" / "plugins" / "autosci"
sys.path.insert(0, str(AUTOSCI_ROOT))

from backends import novelty_review  # noqa: E402
from backends.novelty_review import evaluate_novelty_and_review  # noqa: E402


REVIEW_ENV_VARS = (
    "AUTOSCI_REVIEW_LLM_EVIDENCE",
    "AUTOSCI_REVIEW_LLM_COMMAND",
    "AUTOSCI_REVIEW_LLM_PROVIDER",
    "AUTOSCI_REVIEW_LLM_ENDPOINT",
    "AUTOSCI_REVIEW_LLM_AUTO",
    "AUTOSCI_REVIEW_LLM_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
)


def _disable_live_review(monkeypatch) -> None:
    for name in REVIEW_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _idea() -> dict[str, object]:
    return {
        "idea_id": "idea-phase22-skillgen",
        "title": "Generated Skills for Inference-Time Agents",
        "summary": "Generate task-specific skills for inference-time agent workflows.",
        "hypothesis": "Generated skills improve agent execution quality.",
    }


def test_atomic_technical_opportunity_screening__external_conflict(monkeypatch, tmp_path: Path) -> None:
    _disable_live_review(monkeypatch)
    evidence_path = tmp_path / "external_novelty.json"
    evidence_path.write_text(
        json.dumps(
            {
                "query": "Generated Skills for Inference-Time Agents",
                "fetched_at": "2026-07-27T00:00:00Z",
                "sources": [
                    {
                        "provider": "semantic_scholar",
                        "paperId": "s2-001",
                        "title": "Generated Skills for Inference-Time Agents",
                        "abstract": "Skill generation for inference-time agents improves task execution.",
                        "url": "https://example.test/paper",
                        "year": 2025,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_novelty_and_review(
        _idea(),
        {
            "novelty_evidence": str(evidence_path),
            "novelty_payload_archive_dir": str(tmp_path / "archive"),
            "allow_network_fetch": False,
        },
        workspace_root=tmp_path,
        repository_root=REPO,
    )

    outputs = result
    assert outputs["external_novelty"]["status"] == "completed"
    assert outputs["external_novelty"]["source_count"] == 1
    assert outputs["external_novelty"]["provenance"]["status"] == "passed"
    assert outputs["external_novelty"]["provenance"]["provider_schemas"] == ["semantic_scholar"]
    assert outputs["closest_prior_work"][0]["source_id"] == "external:semantic_scholar:s2-001"
    assert outputs["closest_prior_work"][0]["similarity"] >= 0.5
    assert outputs["novelty"] < 0.55
    assert outputs["recommendation"] in {"revise", "reject"}


def test_atomic_technical_opportunity_screening__provider_unavailable(monkeypatch, tmp_path: Path) -> None:
    _disable_live_review(monkeypatch)
    wiki_root = tmp_path / "wiki"
    (wiki_root / "papers").mkdir(parents=True)
    (wiki_root / "papers" / "agent_workflow_baselines.md").write_text(
        "# Agent Workflow Baselines\n\nBaseline agent workflow evaluation without live external providers.\n",
        encoding="utf-8",
    )

    result = evaluate_novelty_and_review(
        _idea(),
        {
            "wiki_root": str(wiki_root),
            "online_novelty": True,
            "allow_network_fetch": False,
            "novelty_providers": ["web"],
        },
        workspace_root=tmp_path,
        repository_root=REPO,
    )

    outputs = result
    assert outputs["external_novelty"]["status"] == "unavailable"
    assert outputs["external_novelty"]["source_count"] == 0
    assert outputs["external_novelty"]["reason"] == "Online novelty fetch disabled: inputs.allow_network_fetch=false"
    assert outputs["external_novelty"]["provider_statuses"] == []
    assert outputs["external_novelty"]["provenance"]["status"] == "unavailable"
    assert "External OpenAlex/Web/Semantic Scholar/DeepXiv novelty evidence is unavailable or invalid." in outputs["risks"]
    assert outputs["review_llm"]["status"] == "unavailable"


def test_atomic_technical_opportunity_screening__openalex_live_shape_has_auditable_provenance(
    monkeypatch, tmp_path: Path
) -> None:
    _disable_live_review(monkeypatch)

    def fake_fetch(url: str, *, query: str, limit: int, **_kwargs) -> dict[str, object]:
        assert "api.openalex.org" in url
        assert query == "generated agent skills"
        assert limit == 3
        return {
            "results": [
                {
                    "id": "https://openalex.org/W1234567890",
                    "doi": "https://doi.org/10.1000/openalex-proof",
                    "title": "Generated Agent Skills with Verifier Feedback",
                }
            ]
        }

    monkeypatch.setattr(novelty_review, "_fetch_json_url", fake_fetch)
    result = evaluate_novelty_and_review(
        _idea(),
        {
            "topic": "generated agent skills",
            "online_novelty": True,
            "novelty_providers": ["openalex"],
            "max_external_sources": 3,
            "novelty_payload_archive_dir": str(tmp_path / "archive"),
        },
        workspace_root=tmp_path,
        repository_root=REPO,
    )

    external = result["external_novelty"]
    assert external["status"] == "completed"
    assert external["source_count"] == 1
    assert external["provenance"]["status"] == "passed"
    assert external["provenance"]["provider_schemas"] == ["openalex"]
    assert result["closest_prior_work"][0]["source_id"] == "external:openalex:https://openalex.org/W1234567890"
    provider = external["provider_statuses"][0]
    assert provider["raw_payload_archive_status"] == "completed"
