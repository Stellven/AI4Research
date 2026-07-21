"""Negative control: single-dimension prose exposes low density."""

from __future__ import annotations

import json
from pathlib import Path

from research.survey.gates.argument_density import argument_density_gate
from research.survey.schemas import SectionReview

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nc_single_dim_density.json"


def test_single_dimension_density_has_low_density_issue() -> None:
    data = json.loads(FIXTURE.read_text())
    profile = argument_density_gate(
        SectionReview(data["section_id"], "pass", 0.0, 1.0, 0.5, 0.0),
        data["text"],
    )
    absent = [name for name, status in profile.dimension_coverages.items() if status == "absent"]
    assert profile.dimension_coverages["mechanism_comparison"] == "present"
    assert len(absent) >= 4
    assert profile.density_score < 0.5
    assert any(issue.startswith("low_density_dimensions:") for issue in profile.issues)

