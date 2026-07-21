"""ThesisExtractor (Direction A rule core) + recall kill-criterion metric."""
from lib.influence.models import Author, Statement
from lib.influence.thesis_extractor import (
    EXTRACTION_SOURCE,
    cluster_statements,
    extract_theses,
    thesis_recall,
)


def _stmt(sid, text, entities):
    return Statement(statement_id=sid, source="x_backend", text=text,
                     author=Author("x", "@u", "U"), entities=entities)


def _corpus():
    return [
        _stmt("s1", "GPT-5 capability jump is underestimated by current forecasts.", ["GPT-5"]),
        _stmt("s2", "GPT-5 will exceed scaling law predictions from 2024.", ["GPT-5"]),
        _stmt("s3", "Diffusion models are converging with autoregressive ones.", ["diffusion"]),
    ]


def test_clustering_groups_by_entity():
    clusters = cluster_statements(_corpus())
    assert set(clusters) == {"GPT-5", "diffusion"}
    assert len(clusters["GPT-5"]) == 2


def test_extract_produces_thesis_per_cluster():
    theses = extract_theses(_corpus())
    assert len(theses) == 2
    for t in theses:
        assert t.claim
        assert t.derived_from_statements
        assert t.extraction_source == EXTRACTION_SOURCE


def test_confidence_scales_with_corroboration():
    theses = {t.viewpoint_cluster: t for t in extract_theses(_corpus())}
    assert theses["gpt-5"].confidence > theses["diffusion"].confidence


def test_thesis_recall_meets_direction_a_threshold():
    theses = extract_theses(_corpus())
    recall = thesis_recall(theses, expected_clusters=["GPT-5", "diffusion"])
    # Direction A kill criterion is recall < 0.5; rule core must clear it.
    assert recall >= 0.5


def test_claim_refiner_hook_changes_source_tag():
    theses = extract_theses(_corpus(), claim_refiner=lambda base, members: "REFINED: " + base)
    assert all(t.claim.startswith("REFINED:") for t in theses)
    assert all(t.extraction_source == "rule_plus_refiner_v0" for t in theses)
