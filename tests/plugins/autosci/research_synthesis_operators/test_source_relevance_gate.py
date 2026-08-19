"""Task-query relevance must not depend on how a source arrived.

Observed before this gate: a CRISPR base-editing request accepted five
Retrieval-Augmented Generation papers from the frozen source pack and produced a
"source-linked, evidence-backed" report from them, passing every gate. The
identical paper was classified off_topic when it arrived by live search and
content_described when it arrived in the pack -- the same bytes judged by
provenance rather than by relevance.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.plugins.autosci.operators.research_synthesis.base import (  # noqa: E402
    distill_search_query,
    research_query_terms,
)
from harness.plugins.autosci.operators.research_synthesis.source_validation import (  # noqa: E402
    _relevance_class,
)

CRISPR_REQUEST = (
    "Research and compare CRISPR base-editing off-target detection methods and their "
    "reliability benchmarks using at least three real public scholarly sources. Produce a "
    "source-linked report with evidence IDs, methods, conclusions, limitations, and "
    "independent review."
)
RAG_PAPER = {
    "title": "A Survey on RAG Meeting LLMs: Towards Retrieval-Augmented Large Language Models",
    "content_summary": "Retrieval augmented generation for large language models survey.",
}


@pytest.mark.parametrize("channel", ["source_pack", "live_search", "", "unknown"])
def test_off_topic_source_is_rejected_on_every_channel(channel: str) -> None:
    source = dict(RAG_PAPER, acquisition_channel=channel)
    assert _relevance_class(source, CRISPR_REQUEST)["class"] == "off_topic"


def test_on_topic_pack_source_is_still_accepted() -> None:
    source = {
        "title": "Off-target detection for CRISPR base editing",
        "content_summary": "Benchmarks for base-editing off-target detection.",
        "acquisition_channel": "source_pack",
    }
    assert _relevance_class(source, CRISPR_REQUEST)["class"] != "off_topic"


def test_relevance_records_its_query_binding_for_audit() -> None:
    result = _relevance_class(dict(RAG_PAPER, acquisition_channel="source_pack"), CRISPR_REQUEST)
    binding = result["query_binding"]
    assert binding["matched_terms"] == []
    assert binding["acquisition_channel"] == "source_pack"
    assert binding["query_sha256"]


def test_a_request_with_no_topic_cannot_reject_anything() -> None:
    """"Synthesize supplied research evidence" is pure instruction. Relevance is
    indeterminate, not off-topic; gating here would reject the very pack the
    request defers to."""
    assert research_query_terms("Synthesize supplied research evidence.") == set()
    source = {"title": "Alpha Evidence", "acquisition_channel": "source_pack"}
    assert _relevance_class(source, "Synthesize supplied research evidence.")["class"] != "off_topic"


def test_provider_query_carries_the_topic_not_the_deliverable() -> None:
    """The whole request was sent to the bibliographic providers, so the
    instruction buried the topic and live search returned "Applied
    bibliometrics" and "image-based profiling" for a CRISPR request."""
    distilled = distill_search_query(CRISPR_REQUEST)
    assert distilled.split()[0] == "crispr"
    for topical in ("crispr", "base-editing", "off-target", "detection"):
        assert topical in distilled
    for boilerplate in ("produce", "scholarly", "conclusions", "independent", "evidence"):
        assert boilerplate not in distilled.split()


def test_topical_words_are_not_stripped_from_the_query() -> None:
    """Over-stripping would discard real signal, so words that can carry subject
    meaning stay in even though they also appear in the deliverable sentence."""
    terms = research_query_terms(CRISPR_REQUEST)
    for topical in ("methods", "benchmarks", "detection", "reliability"):
        assert topical in terms
    assert "synthesis" not in {"synthesize", "synthesise"} & terms


def test_generic_methodology_overlap_alone_is_not_relevance() -> None:
    """Nearly every research paper says "methods" and "benchmarks". A CRISPR
    request accepted "Searching for Best Practices in Retrieval-Augmented
    Generation" on those two words alone, and "Progress and new challenges in
    image-based profiling" on "methods" and "reliability"."""
    for title, summary in [
        ("Searching for Best Practices in Retrieval-Augmented Generation",
         "evaluating methods and benchmarks across approaches"),
        ("Progress and new challenges in image-based profiling",
         "profiling methods and their reliability"),
    ]:
        source = {"title": title, "content_summary": summary, "acquisition_channel": "source_pack"}
        result = _relevance_class(source, CRISPR_REQUEST)
        assert result["class"] == "off_topic", title
        assert result["query_binding"]["matched_subject_terms"] == []


def test_subject_overlap_is_what_earns_acceptance() -> None:
    source = {
        "title": "Off-target detection for CRISPR base editing",
        "content_summary": "Benchmarks for base-editing off-target detection.",
        "acquisition_channel": "source_pack",
    }
    result = _relevance_class(source, CRISPR_REQUEST)
    assert result["class"] != "off_topic"
    assert "crispr" in result["query_binding"]["matched_subject_terms"]


def test_the_original_rag_pack_still_passes_its_own_request() -> None:
    """The fix must discriminate, not just reject. The five frozen RAG sources
    are correct evidence for the RAG request and must stay accepted."""
    rag_request = (
        "Research and compare retrieval-augmented generation evaluation methods and "
        "reliability benchmarks using at least three real public scholarly sources."
    )
    for title in (
        "A Survey on RAG Meeting LLMs: Towards Retrieval-Augmented Large Language Models",
        "Benchmarking Large Language Models in Retrieval-Augmented Generation",
        "Retrieval-Augmented Generation for Large Language Models: A Survey",
    ):
        source = {"title": title, "content_summary": title, "acquisition_channel": "source_pack"}
        assert _relevance_class(source, rag_request)["class"] != "off_topic", title


def test_generic_terms_stay_in_relevance_but_leave_the_search_query() -> None:
    """Generic methodology words still count as query terms for relevance, but
    they are useless for lexical retrieval and every extra term narrows the
    result set. Measured against OpenAlex for the Mamba request: 7 terms -> 39
    hits of generic surveys, 3 terms -> 11,673 hits topped by the canonical
    paper."""
    assert "methods" in research_query_terms(CRISPR_REQUEST)
    assert "methods" not in distill_search_query(CRISPR_REQUEST).split()


def test_search_query_is_bounded_and_subject_led() -> None:
    query = distill_search_query(CRISPR_REQUEST).split()
    assert len(query) <= 5, "an unbounded query narrows lexical retrieval to noise"
    assert query[0] == "crispr"


def test_comparison_connectives_are_not_subject_terms() -> None:
    """"is X better than Y" is a comparison, not a topic."""
    request = "research whether mamba architecture is better than transformer architecture or JEPA"
    query = distill_search_query(request).split()
    for filler in ("better", "than", "whether"):
        assert filler not in query
    assert "mamba" in query and "transformer" in query


def test_hyphenated_deliverable_compounds_do_not_spend_a_query_slot() -> None:
    """"evidence-linked" is one token, so listing its parts did not stop it.

    The query budget is five terms. A compound made entirely of deliverable
    words was consuming one of them, which is a fifth of the retrieval signal
    spent on vocabulary shared by every request this workflow accepts.
    """
    request = (
        "produce an evidence-linked research report on CRISPR off-target effects "
        "in high-content screening and verify the claims"
    )
    query = distill_search_query(request).split()

    assert "evidence-linked" not in query
    assert query == ["crispr", "off-target", "effects", "high-content", "screening"]


def test_subject_compounds_survive_the_stopword_rule() -> None:
    """The rule drops a compound only when every part is deliverable vocabulary."""
    # "off" and "target" are not deliverable words, so the compound is a topic.
    assert "off-target" in research_query_terms("CRISPR off-target effects")
    assert "retrieval-augmented" in research_query_terms("retrieval-augmented generation")
    # Both halves are deliverable vocabulary, so the compound is not a topic.
    assert "evidence-linked" not in research_query_terms("an evidence-linked report")
    assert "source-linked" not in research_query_terms("a source-linked report")
