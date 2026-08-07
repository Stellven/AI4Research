from __future__ import annotations

import pytest

from research_orchestration import ResearchIntentError, classify_research_intent


def test_chinese_url_technical_trend_report() -> None:
    result = classify_research_intent("请基于 https://example.com/ai-agent 写一份技术趋势分析报告")

    assert result["seed_kind"] == "url"
    assert result["workflow_kind"] == "research_synthesis"
    assert result["run_mode"] == "execute"
    assert result["requires_user_confirmation"] is False
    assert "url_report_synthesis_signal" in result["reason_codes"]


def test_english_url_report() -> None:
    result = classify_research_intent("Create a report from https://example.org/systems")

    assert result["seed_kind"] == "url"
    assert result["workflow_kind"] == "research_synthesis"


def test_url_seed_without_report_word_still_routes_to_research_synthesis() -> None:
    result = classify_research_intent("Use https://example.org/systems in Chinese")

    assert result["seed_kind"] == "url"
    assert result["workflow_kind"] == "research_synthesis"
    assert result["requires_user_confirmation"] is False
    assert "url_seed_synthesis_signal" in result["reason_codes"]


def test_local_pdf_routes_to_paper_ingestion() -> None:
    result = classify_research_intent("Ingest the local paper file C:/papers/skillgen.pdf")

    assert result["seed_kind"] == "pdf"
    assert result["workflow_kind"] == "paper_ingestion"


def test_markdown_routes_to_paper_ingestion() -> None:
    result = classify_research_intent("Ingest this Markdown paper file", seed_inputs=[{"path": "papers/skillgen.md"}])

    assert result["seed_kind"] == "markdown"
    assert result["workflow_kind"] == "paper_ingestion"


def test_pure_topic_survey_routes_to_literature_synthesis() -> None:
    result = classify_research_intent("Survey the literature on verifier-guided agent skill learning")

    assert result["seed_kind"] == "topic"
    assert result["workflow_kind"] == "literature_synthesis"


def test_full_scientific_hypothesis_routes_to_lifecycle() -> None:
    result = classify_research_intent(
        "Run a full lifecycle to test the hypothesis that verifier feedback improves agent skill reuse."
    )

    assert result["seed_kind"] == "topic"
    assert result["workflow_kind"] == "scientific_lifecycle"
    assert result["requires_user_confirmation"] is False


def test_workflow_failure_repair_routes_to_workflow_evolution() -> None:
    result = classify_research_intent("Postmortem a failed workflow and propose a repair plan")

    assert result["workflow_kind"] == "workflow_evolution"
    assert "workflow_evolution_signal" in result["reason_codes"]


def test_explicit_override_wins_after_validation() -> None:
    result = classify_research_intent(
        "Survey this topic",
        explicit_workflow="workflow_evolution",
    )

    assert result["seed_kind"] == "topic"
    assert result["workflow_kind"] == "workflow_evolution"
    assert "explicit_workflow_selected" in result["reason_codes"]


@pytest.mark.parametrize("mode", ["resume", "import_evidence"])
def test_external_evidence_allows_resume_and_import(mode: str) -> None:
    result = classify_research_intent(
        "Continue from external evidence bundle",
        seed_inputs=[{"seed_kind": "external_evidence"}],
        run_mode=mode,
    )

    assert result["seed_kind"] == "external_evidence"
    assert result["run_mode"] == mode
    assert result["workflow_kind"] == "scientific_lifecycle"


def test_external_evidence_rejects_execute() -> None:
    with pytest.raises(ResearchIntentError, match="external_evidence"):
        classify_research_intent(
            "Use external evidence bundle",
            seed_inputs=[{"seed_kind": "external_evidence"}],
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"explicit_workflow": "paper_magic"}, "explicit_workflow"),
        ({"run_mode": "rerun"}, "run_mode"),
        ({"seed_inputs": [{"seed_kind": "spreadsheet"}]}, "external_evidence|seed_inputs|seed_kind|workflow|run_mode"),
    ],
)
def test_illegal_enums_raise(kwargs: dict, match: str) -> None:
    with pytest.raises(ResearchIntentError, match=match):
        classify_research_intent("Create a research report", **kwargs)


def test_empty_prompt_raises() -> None:
    with pytest.raises(ResearchIntentError, match="prompt"):
        classify_research_intent("  ")


def test_ambiguous_task_requires_confirmation_with_conservative_workflow() -> None:
    result = classify_research_intent("Research better agent memory")

    assert result["workflow_kind"] == "literature_synthesis"
    assert result["requires_user_confirmation"] is True
    assert result["confidence"] < 0.5
    assert "ambiguous_conservative_literature_suggestion" in result["reason_codes"]


def test_same_input_repeated_runs_return_same_result() -> None:
    kwargs = {
        "prompt": "请基于 https://example.com/agents 写趋势报告",
        "seed_inputs": [{"url": "https://example.com/agents"}],
    }

    first = classify_research_intent(**kwargs)
    repeated = [classify_research_intent(**kwargs) for _ in range(5)]

    assert repeated == [first] * 5
