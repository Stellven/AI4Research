"""Tests for gate_report_view — CLI formatting and dict conversion."""

from __future__ import annotations

import json
import pathlib

from lib.research.survey.cli.gate_report_view import (
    format_gate_report,
    to_dict_gate_report,
)
from lib.research.survey.schemas import GateReport, GateVerdict

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _report_all_pass() -> GateReport:
    report = GateReport(
        report_id="gate_report_abc123def456",
        run_metadata={"run": "test_all_pass"},
        gate_verdicts={
            "source_quality": GateVerdict(gate_id="source_quality", verdict="pass", evidence_refs=["src_1"], report_section={"registered_name": "source_quality"}),
            "argument_density": GateVerdict(gate_id="argument_density", verdict="pass", evidence_refs=[], report_section={"registered_name": "argument_density"}),
            "controversy_matrix": GateVerdict(gate_id="controversy_matrix", verdict="pass", evidence_refs=["c1", "c2"], report_section={"registered_name": "controversy_matrix"}),
            "exploration_log": GateVerdict(gate_id="exploration_log", verdict="pass", evidence_refs=[], report_section={"registered_name": "exploration_log"}),
        },
        artifact_paths={"gate_report": "/tmp/gate_report.json", "elimination_log": "/tmp/elimination.jsonl"},
        scorecard_ref={},
    )
    report.partial_verdicts = []
    return report


def _report_mixed() -> GateReport:
    report = GateReport(
        report_id="gate_report_mixed789ghi",
        run_metadata={"run": "test_mixed"},
        gate_verdicts={
            "source_quality": GateVerdict(gate_id="source_quality", verdict="fail", evidence_refs=["src_1", "src_2"], report_section={"registered_name": "source_quality"}),
            "argument_density": GateVerdict(gate_id="argument_density", verdict="warning", evidence_refs=[], report_section={"registered_name": "argument_density"}),
            "controversy_matrix": GateVerdict(gate_id="controversy_matrix", verdict="pass", evidence_refs=["c1"], report_section={"registered_name": "controversy_matrix"}),
            "exploration_log": GateVerdict(gate_id="exploration_log", verdict="not_applicable", evidence_refs=[], report_section={"reason": "gate_not_registered"}),
        },
        artifact_paths={"gate_report": "/tmp/gate_report.json"},
        scorecard_ref={},
    )
    report.partial_verdicts = ["exploration_log"]
    return report


# ---------------------------------------------------------------------------
# 1. format contains 4 gate verdict rows
# ---------------------------------------------------------------------------

def test_format_shows_4_gates():
    text = format_gate_report(_report_all_pass())
    assert "source_quality" in text
    assert "argument_density" in text
    assert "controversy_matrix" in text
    assert "exploration_log" in text


# ---------------------------------------------------------------------------
# 2. format shows artifact_paths
# ---------------------------------------------------------------------------

def test_format_shows_artifact_paths():
    text = format_gate_report(_report_all_pass())
    assert "artifact_paths:" in text
    assert "/tmp/gate_report.json" in text
    assert "/tmp/elimination.jsonl" in text


# ---------------------------------------------------------------------------
# 3. format shows summary verdict (worst = fail for mixed)
# ---------------------------------------------------------------------------

def test_format_summary_worst_verdict():
    text = format_gate_report(_report_mixed())
    assert "summary:" in text
    assert "fail" in text


# ---------------------------------------------------------------------------
# 4. format shows partial_verdicts
# ---------------------------------------------------------------------------

def test_format_shows_partial_verdicts():
    text = format_gate_report(_report_mixed())
    assert "partial_verdicts:" in text
    assert "exploration_log" in text


# ---------------------------------------------------------------------------
# 5. to_dict is JSON serializable with all fields
# ---------------------------------------------------------------------------

def test_to_dict_serializable():
    d = to_dict_gate_report(_report_all_pass())
    serialized = json.dumps(d)
    parsed = json.loads(serialized)
    assert parsed["report_id"] == "gate_report_abc123def456"
    assert len(parsed["gate_verdicts"]) == 4
    assert parsed["gate_verdicts"]["source_quality"]["verdict"] == "pass"
    assert parsed["artifact_paths"]["gate_report"] == "/tmp/gate_report.json"


# ---------------------------------------------------------------------------
# 6. to_dict includes partial_verdicts
# ---------------------------------------------------------------------------

def test_to_dict_includes_partial():
    d = to_dict_gate_report(_report_mixed())
    assert "partial_verdicts" in d
    assert d["partial_verdicts"] == ["exploration_log"]


# ---------------------------------------------------------------------------
# 7. Fixture: all-pass matches
# ---------------------------------------------------------------------------

def test_all_pass_fixture_matches():
    with open(FIXTURES / "gate_report_all_pass.json") as f:
        fixture = json.load(f)
    d = to_dict_gate_report(_report_all_pass())
    assert fixture["report_id"] == d["report_id"]
    assert set(fixture["gate_verdicts"].keys()) == set(d["gate_verdicts"].keys())
    assert fixture["gate_verdicts"]["source_quality"]["verdict"] == d["gate_verdicts"]["source_quality"]["verdict"]


# ---------------------------------------------------------------------------
# 8. Fixture: mixed matches
# ---------------------------------------------------------------------------

def test_mixed_fixture_matches():
    with open(FIXTURES / "gate_report_mixed.json") as f:
        fixture = json.load(f)
    d = to_dict_gate_report(_report_mixed())
    assert fixture["report_id"] == d["report_id"]
    assert fixture["gate_verdicts"]["source_quality"]["verdict"] == "fail"
    assert fixture["gate_verdicts"]["exploration_log"]["verdict"] == "not_applicable"
