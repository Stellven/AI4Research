from __future__ import annotations

import json
from pathlib import Path

from harness.plugins.autosci.services.production_research import (
    LiteratureDiscoveryService,
    apply_discovery_relevance_gate,
)


def _candidate(index: int, title: str, summary: str, provider: str = "openalex") -> dict:
    return {
        "source_id": f"{provider}:{index}",
        "canonical_id": f"https://example.test/{provider}/{index}",
        "title": title,
        "url": f"https://example.test/{provider}/{index}",
        "provider": provider,
        "metadata": {"year": 2026},
        "provenance": {"provider": provider, "query": "fixture"},
        "content_summary": summary,
    }


def test_grid_storage_battery_gate_rejects_unrelated_public_provider_results() -> None:
    query = "Collect the relevant literature evidence base for grid-storage battery chemistry comparison."
    candidates = [
        _candidate(1, "Sodium-ion batteries for stationary grid storage", "Battery chemistry, safety, cost and lifetime."),
        _candidate(2, "Lithium-sulfur batteries for electrical grids", "Grid storage battery performance and readiness."),
        _candidate(3, "Water quality in the Amazon River", "A survey of pollutants and fish health."),
        _candidate(4, "Evidence-based medicine in primary care", "Clinical decision-making methods."),
        _candidate(5, "Exercise countermeasures for astronaut health", "Muscle loss during space flight."),
        _candidate(6, "Cooling control for generic energy systems", "Control theory and optimization."),
        _candidate(7, "Recycling policy and circular materials", "Waste policy across municipalities."),
        _candidate(8, "Educational software review", "Student learning outcomes."),
        _candidate(9, "Remote work and creativity", "Employee wellbeing and retention."),
        _candidate(10, "Microplastics in drinking water", "Exposure pathways and public health."),
    ]

    accepted, audit = apply_discovery_relevance_gate(query, candidates)

    # Two relevant papers out of ten is an honest incomplete result, not a
    # final-ready shortlist. The audit still records both relevant papers and
    # every rejection so the decision is reproducible.
    assert accepted == []
    assert audit["status"] == "incomplete"
    assert audit["minimum_relevant_candidates"] == 3
    assert audit["accepted_candidate_count"] == 2
    assert audit["rejected_candidate_count"] == 8
    amazon = next(item for item in audit["decisions"] if "Amazon" in item["title"])
    assert amazon["accepted"] is False
    assert amazon["reason"] == "insufficient_topic_term_overlap"


def test_grid_storage_battery_gate_publishes_only_relevant_candidates_when_threshold_is_met() -> None:
    query = """Collect literature for a grid-storage battery comparison.

Authoritative discovery scope:
- [R2] Compare the four specified battery chemistries. Required coverage: lithium-ion, sodium-ion, solid-state, and lithium-sulfur batteries
- [R3] Evaluate every requested criterion. Required coverage: energy density, lifetime, safety, material availability, cost, and commercial readiness
"""
    candidates = [
        _candidate(1, "Sodium-ion batteries for stationary grid storage", "Battery chemistry and lifetime."),
        _candidate(2, "Solid-state batteries for grid applications", "Storage safety and commercial readiness."),
        _candidate(3, "Lithium-sulfur grid battery systems", "Energy storage cost and cycle life."),
        _candidate(4, "Amazon River water quality", "Freshwater ecology."),
    ]

    accepted, audit = apply_discovery_relevance_gate(query, candidates)

    assert audit["status"] == "passed"
    assert audit["gate_mode"] == "required_coverage"
    assert [item["source_id"] for item in accepted] == ["openalex:1", "openalex:2", "openalex:3"]
    assert all(item["relevance_gate"]["status"] == "accepted" for item in accepted)
    assert all("provider" in item["provenance"] for item in accepted)


def test_authoritative_coverage_rejects_generic_networked_battery_control_paper() -> None:
    query = """Collect literature for a grid-storage battery comparison.

Authoritative discovery scope:
- [R2] Compare the four specified battery chemistries. Required coverage: lithium-ion, sodium-ion, solid-state, and lithium-sulfur batteries
- [R3] Evaluate every requested criterion. Required coverage: energy density, lifetime, safety, material availability, cost, and commercial readiness
"""
    generic_control = _candidate(
        1,
        "Distributed control of networked battery energy storage systems",
        "A control architecture for energy storage dispatch, stability, and grid services.",
    )

    accepted, audit = apply_discovery_relevance_gate(query, [generic_control])

    assert accepted == []
    assert len(audit["coverage_anchor_groups"]) == 2
    chemistry_group = audit["coverage_anchor_groups"][0]
    assert {"lithium", "sodium", "solid", "sulfur"}.issubset(chemistry_group["anchor_terms"])
    decision = audit["decisions"][0]
    assert decision["reason"] == "required_coverage_anchor_missing"
    assert "coverage-1" in decision["unmatched_coverage_groups"]


def test_generic_research_words_do_not_make_an_unrelated_candidate_relevant() -> None:
    accepted, audit = apply_discovery_relevance_gate(
        "collect relevant research evidence and produce a literature report",
        [_candidate(1, "Unrelated clinical report", "Research evidence and study results")],
    )

    assert accepted == []
    assert audit["query_terms"] == []
    assert audit["blocking_reasons"] == ["query_has_no_specific_topic_terms"]


def test_service_archives_incomplete_relevance_audit_and_returns_no_candidates(tmp_path: Path) -> None:
    raw_candidates = [
        _candidate(1, "Sodium-ion batteries for stationary grid storage", "Battery chemistry and lifetime."),
        _candidate(2, "Amazon River water quality", "Freshwater ecology."),
        _candidate(3, "Astronaut health review", "Exercise countermeasures."),
        _candidate(4, "Evidence-based medicine", "Primary care decision making."),
    ]

    def backend(**_kwargs):
        return {
            "status": "completed",
            "candidates": [
                {
                    "candidate_id": item["source_id"],
                    "paperId": item["source_id"],
                    "title": item["title"],
                    "source_ref": item["url"],
                    "abstract": item["content_summary"],
                    "source_channels": ["search_s2"],
                }
                for item in raw_candidates
            ],
            "limitations": [],
        }

    service = LiteratureDiscoveryService(tmp_path, backend=backend, limit=4, max_attempts_per_provider=1)
    service._arxiv = lambda _query: ([], {"provider": "arxiv"})
    service._europe_pmc = lambda _query: ([], {"provider": "europe_pmc"})
    service._openalex = lambda _query: ([], {"provider": "openalex"})
    service._crossref = lambda _query: ([], {"provider": "crossref"})

    result = service(
        seed_snapshot={"seeds": [{"seed_kind": "topic", "content": "grid storage battery chemistry"}]},
        payload={},
    )

    assert result["status"] == "inconclusive"
    assert result["candidates"] == []
    gate = result["relevance_gate"]
    assert gate["accepted_candidate_count"] == 1
    audit_path = tmp_path / gate["audit_path"]
    assert audit_path.is_file()
    archived = json.loads(audit_path.read_text(encoding="utf-8"))
    assert archived["schema"] == "autosci_discovery_relevance_audit.v1"
    assert archived["status"] == "incomplete"


def test_semantic_scholar_attempt_records_key_mode_without_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-secret-never-archive")
    service = LiteratureDiscoveryService(tmp_path)

    attempt = service._record_discovery_attempt(
        provider="semantic_scholar",
        url="https://api.semanticscholar.org/graph/v1/paper/search?query=battery",
        attempt=1,
        status="completed",
        status_code=200,
        body=b"{}",
        retry_wait_seconds=0,
    )

    request_path = tmp_path / attempt["request_path"]
    archived = json.loads(request_path.read_text(encoding="utf-8"))
    assert archived["credential_mode"] == "api_key"
    assert "test-secret-never-archive" not in request_path.read_text(encoding="utf-8")
