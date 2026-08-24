"""Three-tier hints propose templates without bypassing the planner.

research.evidence_to_poc.v1 declares no explicit trigger markers, so
match_trigger can never select it from prompt text and the caller had to name
the workflow id. The dashboard profile did that for EVERY prompt, which meant
"fix a bug in my parser" would still compile the 15-node research topology.
The deterministic classifier now supplies planner metadata only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[3] / "harness"
if str(HARNESS / "lib") not in sys.path:
    sys.path.insert(0, str(HARNESS / "lib"))

from workflow_router import classify_research_request  # noqa: E402


@pytest.mark.parametrize("request_text", [
    "fix the null pointer bug in my parser",
    "rename this variable across the repo",
    "deploy the service to staging",
])
def test_non_research_requests_do_not_select_the_fixed_workflow(request_text: str) -> None:
    result = classify_research_request(request_text)
    assert result["tier"] == "simple"
    assert result["workflow_id"] is None
    assert result["candidate_workflow_id"] is None


@pytest.mark.parametrize("request_text", [
    "Research and compare CRISPR base-editing off-target detection methods using scholarly sources.",
    "Give me a literature survey of state-of-the-art retrieval evaluation with citations.",
])
def test_research_without_build_intent_is_part_a_only(request_text: str) -> None:
    result = classify_research_request(request_text)
    assert result["tier"] == "research_report"
    assert result["execution_profile"] == "part_a_only"
    assert result["workflow_id"] is None
    assert result["candidate_workflow_id"] == "research.evidence_to_poc.v1"
    assert result["routing_authority"] == "planner"
    assert result["auto_instantiate"] is False


@pytest.mark.parametrize("request_text", [
    "give me a deep research report and PoC verification and benchmarking for if mamba "
    "architecture is better than transformer architecture or JEPA",
    "Research RAG evaluation methods, then design and run a benchmark to verify the results.",
])
def test_research_with_build_intent_is_part_a_plus_poc(request_text: str) -> None:
    result = classify_research_request(request_text)
    assert result["tier"] == "research_poc"
    assert result["execution_profile"] == "part_a_plus_poc"
    assert result["workflow_id"] is None
    assert result["candidate_workflow_id"] == "research.evidence_to_poc.v1"


def test_discussing_benchmarks_is_not_asking_to_run_one() -> None:
    """"compare reliability benchmarks" is a report request; the word alone must
    not pull in Part B."""
    result = classify_research_request(
        "Research and compare the reliability benchmarks used for RAG evaluation in the literature."
    )
    assert result["execution_profile"] == "part_a_only"


def test_classification_records_why_it_routed() -> None:
    result = classify_research_request(
        "Research whether mamba beats transformers and build a prototype benchmark."
    )
    assert result["research_markers"], "the decision must name the markers it saw"
    assert result["poc_markers"]
    assert result["reason"]


def test_scholarly_vocabulary_widens_the_research_tier():
    """Markers an ordinary engineering request would not use."""
    for request, tier in [
        ("do a meta-analysis of published results on sparse attention", "research_report"),
        ("find arxiv preprints on retrieval augmented generation", "research_report"),
        ("summarize the related work on sparse mixture of experts", "research_report"),
        # "empirical" is also a build-or-run marker: an empirical comparison
        # means something has to be measured, so Part B applies.
        ("give me an empirical comparison of two schedulers", "research_poc"),
    ]:
        assert classify_research_request(request)["tier"] == tier, request


def test_engineering_vocabulary_is_not_mistaken_for_research():
    """A false positive costs a fifteen-node run; a false negative costs a rephrase.

    That asymmetry is why bare "investigate", "compare" and "evidence" are not
    research markers, even though each of them appears in real research asks.
    """
    for request in [
        "investigate this crash in the parser",
        "add evidence logging to the harness",
        "compare the two config files",
        "benchmark my sorting function",
        "fix the failing test in source_validation.py",
    ]:
        assert classify_research_request(request)["tier"] == "simple", request
