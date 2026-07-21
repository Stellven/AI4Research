"""Activation proof for S03 gate slots and S04 view registry."""

from __future__ import annotations

import json
from pathlib import Path

import research.survey.cli as survey_cli
import research.survey.gates.argument_density  # noqa: F401
import research.survey.gates.controversy_matrix  # noqa: F401
import research.survey.gates.source_quality_distribution  # noqa: F401
from research.survey.gates._registry import _registry
from research.survey.gates.compile_gate_report import GATE_SLOTS

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_gate_registry_contains_real_registered_gates_and_four_visible_slots() -> None:
    expected = json.loads((FIXTURES / "expected_gate_registry.json").read_text())
    assert sorted(_registry._store) == expected["registered_gate_names"]
    assert GATE_SLOTS == expected["gate_report_slots"]


def test_view_registry_contains_five_view_formatters() -> None:
    expected = json.loads((FIXTURES / "expected_view_registry.json").read_text())
    assert sorted(survey_cli.VIEW_REGISTRY) == expected["view_names"]
    for entry in survey_cli.VIEW_REGISTRY.values():
        assert callable(entry["format"])
        assert callable(entry["to_dict"])

