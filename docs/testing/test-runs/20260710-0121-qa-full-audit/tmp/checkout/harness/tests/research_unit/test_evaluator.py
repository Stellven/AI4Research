"""Tests for deterministic DeepResearch artifact evaluator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research.evaluator import evaluate_artifacts  # noqa: E402


def _write_good_artifacts(root: Path, **eval_overrides) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "final.md").write_text("# Final\n\nContinuous thought evidence supports latent reasoning systems [cite:ev_1]\n", encoding="utf-8")
    (root / "sources.jsonl").write_text(
        json.dumps({
            "id": "src_1",
            "source_type": "paper",
            "title": "Paper Abstract",
            "url": "https://arxiv.org/abs/2501.00001",
        }) + "\n",
        encoding="utf-8",
    )
    (root / "sections.jsonl").write_text(
        json.dumps(
            {
                "id": "sec_db_1",
                "section_type": "evidence_synthesis",
                "title": "Evidence Synthesis",
                "content": (
                    "# Evidence Synthesis\n\n"
                    "This section analyzes the runtime architecture, projection gate, deployment boundary, "
                    "and evaluation policy for latent reasoning systems. The implementation should preserve "
                    "audit evidence and failure recovery while separating model exploration from control-plane "
                    "orchestration. Supported claim [cite:ev_1]\n"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "claims.jsonl").write_text(
        "\n".join(
            json.dumps({"id": f"cl_{idx}", "claim_text": text})
            for idx, text in enumerate(
                [
                    "Latent-space reasoning moves intermediate computation into hidden states rather than explicit token chains.",
                    "Recurrent depth can add test-time computation through repeated blocks or hidden-state refinement.",
                    "Soft thought vectors can be projected into existing language models as intermediate reasoning state.",
                ],
                start=1,
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "evidence.jsonl").write_text(
        "\n".join(
            json.dumps({"id": f"ev_{idx}", "content": text})
            for idx, text in enumerate(
                [
                    "Abstract: Continuous thought and hidden-state reasoning can reduce dependence on visible chain-of-thought tokens.",
                    "Faithfulness remains difficult because latent trajectories are harder to inspect than explicit text.",
                ],
                start=1,
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "report_ast.json").write_text(
        json.dumps({"chapters": [{"sections": [{"section_id": "ch1/sec1", "db_section_id": "sec_db_1", "section_type": "evidence_synthesis"}]}]}),
        encoding="utf-8",
    )
    (root / "final.bibliography.json").write_text("[]", encoding="utf-8")
    payload = {
        "run_id": "run-good",
        "source_count": 1,
        "evidence_count": 1,
        "claim_count": 1,
        "section_count": 1,
        "unsupported_rate": 0.0,
        "citation_accuracy": 1.0,
        "status": "passed",
        "output_dir": str(root),
        "final_md": str(root / "final.md"),
    }
    payload.update(eval_overrides)
    path = root / "run-good-research_eval.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_evaluate_artifacts_passes_complete_artifact_set(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is True
    assert result["verdict"] == "PASS"
    assert result["metrics"]["report_ast_sections"] == 1
    assert result["metrics"]["covered_sections"] == 1
    assert result["metrics"]["section_missing_citation_count"] == 0
    assert result["metrics"]["source_type_count"] == 1
    assert result["metrics"]["source_type_invalid_count"] == 0
    assert result["artifact_exists"]["final_md"] is True


def test_evaluate_artifacts_accepts_smoke_metric_aliases_and_named_evidence_ids(tmp_path):
    eval_json = _write_good_artifacts(
        tmp_path,
        unsupported_rate=None,
        citation_accuracy=None,
        unsupported_claim_rate=0.0,
        citation_span_accuracy=1.0,
    )
    (tmp_path / "final.md").write_text("# Final\n\nSupported claim about self attention evidence [cite:ev_vaswani_self_attention]\n", encoding="utf-8")
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps({"id": "ev_vaswani_self_attention", "content": "Supported claim about self attention evidence."}) + "\n",
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is True
    assert result["metrics"]["unsupported_rate"] == 0.0
    assert result["metrics"]["citation_accuracy"] == 1.0


def test_evaluate_artifacts_fails_missing_claims(tmp_path):
    eval_json = _write_good_artifacts(tmp_path, claim_count=0, citation_accuracy=0.0)

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is False
    assert result["verdict"] == "FAIL"
    assert "claim_count_zero" in result["errors"]
    assert any(err.startswith("citation_accuracy_too_low") for err in result["errors"])


def test_evaluate_artifacts_fails_final_without_citations(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    (tmp_path / "final.md").write_text("# Final\n\nNo citation marker.\n", encoding="utf-8")

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is False
    assert "final_md_missing_evidence_citations" in result["errors"]


def test_evaluate_artifacts_fails_metadata_noise(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    (tmp_path / "final.md").write_text(
        "# Final\n\n"
        "Title: A\nURL: https://example.com/a\nPublisher: X\nPublished: 2025\n"
        "Supported claim [cite:ev_abcdef1234567890]\n",
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is False
    assert any(err.startswith("final_md_metadata_noise") for err in result["errors"])


def test_evaluate_artifacts_fails_section_without_citation(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    (tmp_path / "sections.jsonl").write_text(
        json.dumps(
            {
                "id": "sec_db_1",
                "section_type": "evidence_synthesis",
                "title": "Evidence Synthesis",
                "content": "This section has enough architecture analysis text but no evidence marker. " * 8,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is False
    assert result["metrics"]["section_missing_citation_count"] == 1
    assert any(err.startswith("section_coverage_missing_citations") for err in result["errors"])


def test_evaluate_artifacts_warns_on_single_source_type(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)

    result = evaluate_artifacts(eval_json)

    assert result["ok"] is True
    assert result["metrics"]["source_type_count"] == 1
    assert "source_diversity_single_type:1<2" in result["warnings"]


def test_evaluate_artifacts_technical_architecture_profile_warns_without_strict(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)

    result = evaluate_artifacts(eval_json, research_profile="technical_architecture")

    assert result["ok"] is True
    assert result["metrics"]["research_profile"] == "technical_architecture"
    assert result["metrics"]["strict_profile"] is False
    assert any(warn.startswith("profile_technical_architecture_source_type_count_low") for warn in result["warnings"])
    assert any(warn.startswith("profile_technical_architecture_missing_recommended_source_types") for warn in result["warnings"])


def test_evaluate_artifacts_technical_architecture_profile_fails_when_strict_and_source_poor(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)

    result = evaluate_artifacts(eval_json, research_profile="technical_architecture", strict_profile=True)

    assert result["ok"] is False
    assert result["metrics"]["strict_profile"] is True
    assert any(err.startswith("profile_technical_architecture_source_type_count_too_low") for err in result["errors"])


def test_evaluate_artifacts_technical_architecture_profile_passes_with_required_source_mix(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    (tmp_path / "sources.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "src_1", "source_type": "paper", "title": "Paper Abstract", "url": "https://arxiv.org/abs/2501.00001"}),
                json.dumps({"id": "src_2", "source_type": "code", "title": "Code", "url": "https://github.com/example/repo"}),
                json.dumps({"id": "src_3", "source_type": "official_doc", "title": "Docs", "url": "https://docs.example.com/architecture"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json, research_profile="technical_architecture", strict_profile=True)

    assert result["ok"] is True
    assert result["metrics"]["source_type_count"] == 3
    assert result["metrics"]["profile_required_source_types"] == ["paper"]
    assert result["metrics"]["source_type_invalid_count"] == 0
    assert result["metrics"]["source_authority_average"] >= 0.85
    assert result["metrics"]["source_high_authority_count"] >= 2


def test_evaluate_artifacts_strict_profile_fails_invalid_source_type_label(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    (tmp_path / "sources.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "src_1", "source_type": "paper", "title": "Paper", "url": "https://arxiv.org/abs/2501.00001"}),
                json.dumps({"id": "src_2", "source_type": "code", "title": "Not Code", "url": "https://example.com/blog-post"}),
                json.dumps({"id": "src_3", "source_type": "official_doc", "title": "Docs", "url": "https://docs.example.com/architecture"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json, research_profile="technical_architecture", strict_profile=True)

    assert result["ok"] is False
    assert result["metrics"]["source_type_invalid_count"] == 1
    assert any(warn.startswith("source_type_validation_invalid") for warn in result["warnings"])
    assert any(err.startswith("profile_technical_architecture_invalid_source_type_count") for err in result["errors"])


def test_evaluate_artifacts_strict_profile_fails_low_authority_source_mix(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    (tmp_path / "sources.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "src_1", "source_type": "paper", "title": "Abstract-like vendor note", "url": "https://example.com/latent-paper"}),
                json.dumps({"id": "src_2", "source_type": "code", "title": "Repository mirror", "url": "https://example.com/repo"}),
                json.dumps({"id": "src_3", "source_type": "official_doc", "title": "Docs mirror", "url": "https://example.com/docs"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json, research_profile="technical_architecture", strict_profile=True)

    assert result["ok"] is False
    assert result["metrics"]["source_authority_average"] < 0.55
    assert any(err.startswith("profile_technical_architecture_source_authority_too_low") for err in result["errors"])
    assert any(err.startswith("profile_technical_architecture_high_authority_sources_too_low") for err in result["errors"])


def test_evaluate_artifacts_uses_external_policy_override(tmp_path, monkeypatch):
    eval_json = _write_good_artifacts(tmp_path)
    policy = {
        "version": 99,
        "high_authority_threshold": 0.95,
        "profiles": {
            "general": {
                "min_source_types": 1,
                "warn_source_types": 1,
                "required_source_types": [],
                "warn_missing_source_types": [],
                "min_covered_section_ratio": 1.0,
                "max_low_analysis_density_ratio": 1.0,
                "min_authority_score": 0.95,
                "min_high_authority_sources": 1,
            }
        },
        "source_authority": {
            "paper": [
                {"score": 0.42, "host_contains": ["arxiv.org"]},
                {"score": 0.30, "default": True},
            ],
            "unknown": [{"score": 0.30, "default": True}],
        },
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("SOLAR_RESEARCH_POLICY_PATH", str(policy_path))

    result = evaluate_artifacts(eval_json, research_profile="general", strict_profile=True)

    assert result["ok"] is False
    assert result["metrics"]["source_authority_average"] == 0.42
    assert result["metrics"]["source_authority_policy_path"] == str(policy_path)
    assert any(err.startswith("profile_general_source_authority_too_low") for err in result["errors"])


def test_evaluate_artifacts_requires_expert_synthesis_gate(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    expert = tmp_path / "expert_synthesis.md"
    expert.write_text(
        "# Expert\n\n"
        "## Insight Scorecard\n\n"
        "| Dimension | Score | Rationale |\n"
        "|---|---:|---|\n"
        "| Source strength | 4/5 | paper sources |\n"
        "| Architecture abstraction | 4/5 | taxonomy |\n"
        "| Auditability | 4/5 | projection |\n\n"
        "## Architecture Taxonomy\n\n"
        "Taxonomy table.\n\n"
        "## Source Strength\n\n"
        "Source strength is high.\n\n"
        "## Design Tradeoffs\n\n"
        "Tradeoff: deployability vs. purity.\n\n"
        "## Contradictions and Uncertainty\n\n"
        "Uncertainty remains around faithfulness.\n\n"
        "A production runtime should treat latent reasoning as a controlled execution mode rather than a free-form hidden scratchpad.\n"
        "The architecture needs an audit projection layer that maps selected latent state into evidence, claims, actions, and replayable events.\n"
        "Deployment should start with adapters because they preserve rollback boundaries while native recurrent models mature.\n"
        "Evaluation must measure action reliability, citation support, and projection faithfulness instead of only final answer quality.\n"
        "The main design risk is that token savings can hide unobservable reasoning failures unless the runtime enforces evidence gates.\n"
        "A practical roadmap should separate model experimentation from harness policy, so failed latent methods can be swapped out without changing the control plane.\n\n"
        "## Implementation Roadmap\n\n"
        "- **P0:** baseline.\n"
        "- **P1:** runtime.\n"
        "- **P2:** scale.\n"
        + ("Evidence text.\n" * 120),
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json, expert_md=expert, require_expert=True)

    assert result["ok"] is True
    assert result["metrics"]["expert_has_taxonomy"] is True
    assert result["metrics"]["expert_roadmap_mentions"] >= 3
    assert result["metrics"]["expert_has_source_strength"] is True
    assert result["metrics"]["expert_has_contradiction_uncertainty"] is True
    assert result["metrics"]["expert_insight_scorecard_rows"] == 3
    assert result["metrics"]["expert_novelty_ratio"] >= 0.45
    assert result["metrics"]["expert_insight_density"] >= 0.20
    assert result["metrics"]["expert_independent_insight_lines"] >= 5


def test_evaluate_artifacts_fails_expert_synthesis_that_only_repeats_source_claims(tmp_path):
    eval_json = _write_good_artifacts(tmp_path)
    repeated_source = (
        "Latent-space reasoning moves intermediate computation into hidden states rather than explicit token chains."
    )
    expert = tmp_path / "expert_synthesis.md"
    expert.write_text(
        "# Expert\n\n"
        "## Insight Scorecard\n\n"
        "| Dimension | Score | Rationale |\n"
        "|---|---:|---|\n"
        "| Source strength | 4/5 | paper sources |\n"
        "| Architecture abstraction | 4/5 | taxonomy |\n"
        "| Auditability | 4/5 | projection |\n\n"
        "## Architecture Taxonomy\n\n"
        + ((repeated_source + "\n") * 18)
        + "\n## Source Strength\n\nSource strength is high.\n\n"
        "## Design Tradeoffs\n\nTradeoff: deployability vs. purity.\n\n"
        "## Contradictions and Uncertainty\n\nUncertainty remains around faithfulness.\n\n"
        "## Implementation Roadmap\n\n"
        "- **P0:** baseline.\n"
        "- **P1:** runtime.\n"
        "- **P2:** scale.\n"
        + ((repeated_source + "\n") * 120),
        encoding="utf-8",
    )

    result = evaluate_artifacts(eval_json, expert_md=expert, require_expert=True)

    assert result["ok"] is False
    assert any(err.startswith("expert_synthesis_too_redundant") for err in result["errors"])
    assert any(err.startswith("expert_synthesis_independent_insight_lines_too_low") for err in result["errors"])
