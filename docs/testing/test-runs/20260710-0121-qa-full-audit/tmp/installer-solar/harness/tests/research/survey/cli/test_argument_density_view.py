"""Tests for argument_density_view — S04 N2.

≥ 6 tests: format output structure, 5 dimension columns, low_density list,
to_dict round-trip, fixtures load, edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.research.survey.schemas import (
    ArgumentDensityProfile,
    DimensionIndicator,
    NotApplicableEntry,
)
from lib.research.survey.cli.argument_density_view import (
    format_argument_density,
    to_dict_argument_density,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_full() -> ArgumentDensityProfile:
    return ArgumentDensityProfile(
        section_id="s1",
        dimension_coverages={
            "mechanism_comparison": "present",
            "method_taxonomy": "present",
            "evaluation_protocol": "present",
            "failure_negative_evidence": "present",
            "engineering_implication": "present",
        },
        density_score=1.0,
        detected_indicators=[
            DimensionIndicator(dimension="mechanism_comparison", span_text="X vs Y", confidence="high"),
            DimensionIndicator(dimension="method_taxonomy", span_text="category types", confidence="high"),
            DimensionIndicator(dimension="evaluation_protocol", span_text="benchmark metrics", confidence="high"),
            DimensionIndicator(dimension="failure_negative_evidence", span_text="limitation found", confidence="high"),
            DimensionIndicator(dimension="engineering_implication", span_text="production deployment", confidence="high"),
        ],
        not_applicable_entries=[],
        issues=[],
    )


def _profile_partial() -> ArgumentDensityProfile:
    return ArgumentDensityProfile(
        section_id="s3",
        dimension_coverages={
            "mechanism_comparison": "present",
            "method_taxonomy": "absent",
            "evaluation_protocol": "present",
            "failure_negative_evidence": "absent",
            "engineering_implication": "absent",
        },
        density_score=0.4,
        detected_indicators=[
            DimensionIndicator(dimension="mechanism_comparison", span_text="X vs Y", confidence="high"),
            DimensionIndicator(dimension="evaluation_protocol", span_text="benchmark", confidence="high"),
        ],
        not_applicable_entries=[],
        issues=["low_density_dimensions:method_taxonomy,failure_negative_evidence,engineering_implication"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatArgumentDensity:
    def test_output_contains_section_id(self) -> None:
        output = format_argument_density(_profile_full())
        assert "section_id:      s1" in output

    def test_output_contains_all_5_dimensions(self) -> None:
        output = format_argument_density(_profile_full())
        for dim in [
            "mechanism_comparison",
            "method_taxonomy",
            "evaluation_protocol",
            "failure_negative_evidence",
            "engineering_implication",
        ]:
            assert dim in output, f"missing dimension: {dim}"

    def test_low_density_sections_listed(self) -> None:
        output = format_argument_density(_profile_partial())
        assert "low_density_flags" in output
        assert "method_taxonomy" in output

    def test_not_applicable_entries_displayed(self) -> None:
        profile = ArgumentDensityProfile(
            section_id="bg1",
            dimension_coverages={
                "mechanism_comparison": "absent",
                "method_taxonomy": "absent",
                "evaluation_protocol": "absent",
                "failure_negative_evidence": "not_applicable",
                "engineering_implication": "not_applicable",
            },
            density_score=0.0,
            detected_indicators=[],
            not_applicable_entries=[
                NotApplicableEntry(dimension="failure_negative_evidence", reason="background section"),
                NotApplicableEntry(dimension="engineering_implication", reason="background section"),
            ],
            issues=["low_density_dimensions:mechanism_comparison,method_taxonomy,evaluation_protocol"],
        )
        output = format_argument_density(profile)
        assert "not_applicable: 2" in output
        assert "failure_negative_evidence: background section" in output

    def test_density_score_formatted(self) -> None:
        output = format_argument_density(_profile_full())
        assert "density_score:   1.00" in output
        output2 = format_argument_density(_profile_partial())
        assert "density_score:   0.40" in output2


class TestToDictArgumentDensity:
    def test_round_trip_to_dict(self) -> None:
        profile = _profile_full()
        d = to_dict_argument_density(profile)
        assert d["section_id"] == "s1"
        assert d["density_score"] == 1.0
        assert d["dimension_coverages"]["mechanism_comparison"] == "present"
        assert len(d["detected_indicators"]) == 5

    def test_to_dict_with_not_applicable(self) -> None:
        profile = ArgumentDensityProfile(
            section_id="bg1",
            dimension_coverages={"mechanism_comparison": "absent"},
            density_score=0.0,
            detected_indicators=[],
            not_applicable_entries=[
                NotApplicableEntry(dimension="engineering_implication", reason="background"),
            ],
        )
        d = to_dict_argument_density(profile)
        assert len(d["not_applicable_entries"]) == 1
        assert d["not_applicable_entries"][0]["dimension"] == "engineering_implication"


class TestFixtures:
    def test_partial_fixture_loads(self) -> None:
        data = json.loads((FIXTURES / "argument_density_partial.json").read_text())
        assert data["section_id"] == "s3"
        assert data["density_score"] == 0.4
        assert "low_density" in data["issues"][0]

    def test_full_fixture_loads(self) -> None:
        data = json.loads((FIXTURES / "argument_density_full.json").read_text())
        assert data["section_id"] == "s1"
        assert data["density_score"] == 1.0
        assert all(v == "present" for v in data["dimension_coverages"].values())
