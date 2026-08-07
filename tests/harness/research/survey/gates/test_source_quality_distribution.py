"""Tests for source_quality_distribution gate (N3).

Covers: high canonical, low canonical, paper-only, web-stuffing, type missing,
zero-source, mixed, typed taxonomy, stuffing pattern 1, stuffing pattern 2.
"""

from __future__ import annotations

import pytest

from lib.research.survey.schemas import EvidencePack, SourceQualityDistribution, StuffingAlert
from lib.research.survey.gates._registry import _registry as global_reg
from lib.research.survey.gates.source_quality_distribution import (
    build_source_quality_distribution,
    detect_stuffing_alerts,
    source_quality_gate,
)


def _pack(
    section_id: str = "s1",
    source_types: list[str] | None = None,
    source_ids: list[str] | None = None,
) -> EvidencePack:
    if source_types is None:
        source_types = []
    if source_ids is None:
        source_ids = [f"src_{i}" for i in range(len(source_types))]
    return EvidencePack(
        pack_id=f"pack_{section_id}",
        section_id=section_id,
        evidence_ids=[],
        claim_ids=[],
        source_ids=source_ids,
        source_types=source_types,
        contradiction_slots=[],
        status="ready",
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    global_reg.clear()
    # Re-import to re-register the decorator (module-level side-effect)
    import importlib
    import lib.research.survey.gates.source_quality_distribution as sqm
    importlib.reload(sqm)
    yield
    global_reg.clear()


# ---------------------------------------------------------------------------
# 1. High canonical distribution — all 4 high-authority types present
# ---------------------------------------------------------------------------

def test_high_canonical():
    pack = _pack(source_types=["paper", "code", "official", "benchmark", "web"])
    result = build_source_quality_distribution(pack)
    assert result.verdict == "pass"
    assert result.primary_ratio > 0.0
    assert result.canonical_coverage["paper"] is True
    assert result.canonical_coverage["code"] is True
    assert result.canonical_coverage["official"] is True
    assert result.canonical_coverage["benchmark"] is True
    assert len(result.verdict_reasons) == 0


# ---------------------------------------------------------------------------
# 2. Low canonical — mostly web/blog
# ---------------------------------------------------------------------------

def test_low_canonical():
    pack = _pack(source_types=["web", "blog", "wiki", "web"])
    result = build_source_quality_distribution(pack)
    assert result.verdict == "fail"
    assert result.primary_ratio == 0.0
    assert "no_primary_sources" in result.verdict_reasons


# ---------------------------------------------------------------------------
# 3. Paper-only — single type
# ---------------------------------------------------------------------------

def test_paper_only():
    pack = _pack(source_types=["paper", "paper", "paper"])
    result = build_source_quality_distribution(pack)
    assert result.primary_ratio == 1.0
    assert result.canonical_coverage["paper"] is True
    assert result.canonical_coverage["code"] is False
    # Missing canonical types → warning
    assert "missing_canonical_types:" in " ".join(result.verdict_reasons)


# ---------------------------------------------------------------------------
# 4. Web stuffing detected
# ---------------------------------------------------------------------------

def test_web_stuffing():
    pack = _pack(
        source_types=["paper", "web", "web", "web", "web"],
        source_ids=["p1", "s1", "s2", "s3", "s4"],
    )
    urls = [
        "https://arxiv.org/paper1",
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
        "https://example.com/d",
    ]
    result = build_source_quality_distribution(pack, source_urls=urls)
    assert len(result.stuffing_alerts) >= 1
    assert result.stuffing_alerts[0].domain == "example.com"
    assert result.stuffing_alerts[0].count == 4
    assert "stuffing_detected:example.com" in " ".join(result.verdict_reasons)


# ---------------------------------------------------------------------------
# 5. Type missing — no benchmark
# ---------------------------------------------------------------------------

def test_type_missing():
    pack = _pack(source_types=["paper", "code", "official"])
    result = build_source_quality_distribution(pack)
    assert result.canonical_coverage["benchmark"] is False
    assert "missing_canonical_types:" in " ".join(result.verdict_reasons)


# ---------------------------------------------------------------------------
# 6. Zero sources — hard fail
# ---------------------------------------------------------------------------

def test_zero_sources():
    pack = _pack(source_types=[])
    result = build_source_quality_distribution(pack)
    assert result.verdict == "fail"
    assert result.primary_ratio == 0.0
    assert "no_sources_found" in result.verdict_reasons


# ---------------------------------------------------------------------------
# 7. Mixed distribution — high + low + unknown type
# ---------------------------------------------------------------------------

def test_mixed_with_unknown():
    pack = _pack(source_types=["paper", "web", "blog", "custom_type"])
    result = build_source_quality_distribution(pack)
    assert result.source_type_counts["custom_type"] == 1
    assert "unknown_source_type:custom_type" in " ".join(result.verdict_reasons)
    assert result.verdict in ("warning", "fail")


# ---------------------------------------------------------------------------
# 8. Typed taxonomy — verify taxonomy_version field
# ---------------------------------------------------------------------------

def test_taxonomy_version():
    pack = _pack(source_types=["paper"])
    result = build_source_quality_distribution(pack)
    assert "paper" in result.taxonomy_version
    assert "benchmark" in result.taxonomy_version


# ---------------------------------------------------------------------------
# 9. Stuffing pattern — same domain, different paths
# ---------------------------------------------------------------------------

def test_stuffing_pattern_subdirectories():
    ids = [f"blog_{i}" for i in range(5)]
    pack = _pack(source_types=["blog"] * 5, source_ids=ids)
    urls = [
        "https://medium.com/@user/post-1",
        "https://medium.com/@user/post-2",
        "https://medium.com/@user/post-3",
        "https://medium.com/@user/post-4",
        "https://medium.com/@user/post-5",
    ]
    result = build_source_quality_distribution(pack, source_urls=urls)
    assert any(a.domain == "medium.com" for a in result.stuffing_alerts)


# ---------------------------------------------------------------------------
# 10. Stuffing pattern — barely below threshold (no alert)
# ---------------------------------------------------------------------------

def test_stuffing_below_threshold():
    pack = _pack(
        source_types=["web", "web"],
        source_ids=["w1", "w2"],
    )
    urls = ["https://example.com/a", "https://example.com/b"]
    result = build_source_quality_distribution(pack, source_urls=urls)
    assert len(result.stuffing_alerts) == 0


# ---------------------------------------------------------------------------
# 11. Gate registered in registry
# ---------------------------------------------------------------------------

def test_gate_registered():
    assert "source_quality" in global_reg.list()
    fn = global_reg.get("source_quality")
    pack = _pack(source_types=["paper"])
    result = fn(pack)
    assert isinstance(result, SourceQualityDistribution)


# ---------------------------------------------------------------------------
# 12. detect_stuffing_alerts standalone
# ---------------------------------------------------------------------------

def test_detect_stuffing_standalone():
    ids = ["a", "b", "c"]
    urls = ["https://x.com/1", "https://x.com/2", "https://x.com/3"]
    alerts = detect_stuffing_alerts(ids, urls, min_group_size=3)
    assert len(alerts) == 1
    assert alerts[0].domain == "x.com"
