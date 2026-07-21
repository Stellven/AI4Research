"""Tests for source_quality_view — CLI formatting and dict conversion."""

from __future__ import annotations

import json
import pathlib

from lib.research.survey.cli.source_quality_view import (
    format_source_quality,
    to_dict_source_quality,
)
from lib.research.survey.schemas import SourceQualityDistribution, StuffingAlert

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _dist_pass() -> SourceQualityDistribution:
    return SourceQualityDistribution(
        section_id="s1",
        source_type_counts={"paper": 3, "code": 1, "official": 1, "benchmark": 1},
        primary_ratio=1.0,
        stuffing_alerts=[],
        canonical_coverage={"paper": True, "code": True, "official": True, "benchmark": True},
        verdict="pass",
        verdict_reasons=[],
        taxonomy_version="paper,code,official,benchmark,web,blog,wiki",
    )


def _dist_stuffing() -> SourceQualityDistribution:
    return SourceQualityDistribution(
        section_id="s2",
        source_type_counts={"web": 5, "blog": 3},
        primary_ratio=0.0,
        stuffing_alerts=[
            StuffingAlert(
                domain="example.com",
                count=4,
                source_ids=["src_0", "src_1", "src_2", "src_3"],
            ),
        ],
        canonical_coverage={"paper": False, "code": False, "official": False, "benchmark": False},
        verdict="fail",
        verdict_reasons=[
            "no_primary_sources",
            "missing_canonical_types:paper,code,official,benchmark",
            "stuffing_detected:example.com",
        ],
        taxonomy_version="paper,code,official,benchmark,web,blog,wiki",
    )


# ---------------------------------------------------------------------------
# 1. format_source_quality returns string with required fields
# ---------------------------------------------------------------------------

def test_format_pass_contains_fields():
    text = format_source_quality(_dist_pass())
    assert "canonical_coverage:" in text
    assert "primary_ratio:" in text
    assert "stuffing_alerts:" in text
    assert "verdict:             pass" in text


# ---------------------------------------------------------------------------
# 2. format shows stuffing alerts
# ---------------------------------------------------------------------------

def test_format_stuffing_shows_alerts():
    text = format_source_quality(_dist_stuffing())
    assert "stuffing_alerts:     1" in text
    assert "domain=example.com" in text
    assert "count=4" in text


# ---------------------------------------------------------------------------
# 3. format shows verdict reasons
# ---------------------------------------------------------------------------

def test_format_shows_reasons():
    text = format_source_quality(_dist_stuffing())
    assert "reason:" in text
    assert "no_primary_sources" in text
    assert "stuffing_detected:example.com" in text


# ---------------------------------------------------------------------------
# 4. format shows missing canonical types
# ---------------------------------------------------------------------------

def test_format_shows_missing_canonical():
    text = format_source_quality(_dist_stuffing())
    assert "missing:" in text
    assert "paper" in text


# ---------------------------------------------------------------------------
# 5. to_dict_source_quality produces serializable dict
# ---------------------------------------------------------------------------

def test_to_dict_is_json_serializable():
    d = to_dict_source_quality(_dist_pass())
    serialized = json.dumps(d)
    parsed = json.loads(serialized)
    assert parsed["section_id"] == "s1"
    assert parsed["verdict"] == "pass"
    assert parsed["primary_ratio"] == 1.0
    assert parsed["canonical_coverage"]["paper"] is True


# ---------------------------------------------------------------------------
# 6. to_dict round-trips stuffing alert
# ---------------------------------------------------------------------------

def test_to_dict_stuffing_alert():
    d = to_dict_source_quality(_dist_stuffing())
    assert len(d["stuffing_alerts"]) == 1
    alert = d["stuffing_alerts"][0]
    assert alert["domain"] == "example.com"
    assert alert["count"] == 4
    assert alert["source_ids"] == ["src_0", "src_1", "src_2", "src_3"]


# ---------------------------------------------------------------------------
# 7. Fixture files are valid JSON matching to_dict output shape
# ---------------------------------------------------------------------------

def test_pass_fixture_matches_schema():
    with open(FIXTURES / "source_quality_pass.json") as f:
        fixture = json.load(f)
    d = to_dict_source_quality(_dist_pass())
    assert fixture["section_id"] == d["section_id"]
    assert fixture["verdict"] == d["verdict"]
    assert fixture["primary_ratio"] == d["primary_ratio"]
    assert set(fixture["canonical_coverage"].keys()) == set(d["canonical_coverage"].keys())


def test_stuffing_fixture_matches_schema():
    with open(FIXTURES / "source_quality_fail_stuffing.json") as f:
        fixture = json.load(f)
    d = to_dict_source_quality(_dist_stuffing())
    assert fixture["section_id"] == d["section_id"]
    assert fixture["verdict"] == d["verdict"]
    assert len(fixture["stuffing_alerts"]) == len(d["stuffing_alerts"])
    assert fixture["stuffing_alerts"][0]["domain"] == d["stuffing_alerts"][0]["domain"]
