"""Tests for compile_gate_report aggregator."""

from __future__ import annotations

import pytest

from lib.research.survey.gates._registry import _registry as global_reg
from lib.research.survey.gates.compile_gate_report import compile_gate_report
from lib.research.survey.schemas import EvidencePack, SectionReview


def _pack(source_types=None):
    return EvidencePack(
        pack_id="p1", section_id="s1",
        evidence_ids=[], claim_ids=[],
        source_ids=[f"src_{i}" for i in range(len(source_types or []))],
        source_types=source_types or [],
        contradiction_slots=[], status="ready",
    )


def _section():
    return SectionReview(
        section_id="s1", verdict="pass",
        unsupported_claim_rate=0.0, citation_span_accuracy=1.0,
        source_diversity_score=0.8, repetition_score=0.1,
    )


# Ensure all gate modules are imported (triggers @register_gate decorators).
# These are no-ops if already imported.
import lib.research.survey.gates.source_quality_distribution  # noqa: F401
import lib.research.survey.gates.argument_density  # noqa: F401
import lib.research.survey.gates.controversy_matrix  # noqa: F401


@pytest.fixture(autouse=True)
def _ensure_registered():
    # Gates registered at import time; just ensure they're present.
    # If a previous test cleared the registry, re-register by re-importing
    # is unsafe (DuplicateGateError). Instead we save/restore.
    snapshot = dict(global_reg._store)
    global_reg._store.clear()
    global_reg._store.update(snapshot)
    yield


# ---------------------------------------------------------------------------
# 1. All 4 gate slots present — all verdicts populated or degraded
# ---------------------------------------------------------------------------

def test_all_gates_present():
    report = compile_gate_report(
        evidence_pack=_pack(["paper"]),
        section=_section(),
        text="some text",
        claim_evidence_rows=[],
    )
    assert "source_quality" in report.gate_verdicts
    assert "argument_density" in report.gate_verdicts
    assert "controversy_matrix" in report.gate_verdicts
    assert "exploration_log" in report.gate_verdicts
    assert report.gate_verdicts["source_quality"].verdict in (
        "pass", "warning", "fail",
    )
    assert report.gate_verdicts["controversy_matrix"].report_section[
        "registered_name"
    ] in ("controversy_matrix", "controversy")
    assert "exploration_log" in report.partial_verdicts


# ---------------------------------------------------------------------------
# 2. One gate missing — partial degrades
# ---------------------------------------------------------------------------

def test_one_gate_missing():
    saved = dict(global_reg._store)
    global_reg._store.clear()
    # Only keep source_quality
    global_reg._store["source_quality"] = saved["source_quality"]

    report = compile_gate_report(evidence_pack=_pack(["paper"]))
    assert report.gate_verdicts["source_quality"].verdict in (
        "pass", "warning", "fail",
    )
    assert report.gate_verdicts["argument_density"].verdict == "not_applicable"
    assert report.gate_verdicts["controversy_matrix"].verdict == "not_applicable"
    assert report.gate_verdicts["exploration_log"].verdict == "not_applicable"
    assert sorted(report.partial_verdicts) == [
        "argument_density",
        "controversy_matrix",
        "exploration_log",
    ]

    global_reg._store.update(saved)


# ---------------------------------------------------------------------------
# 3. No gates registered — all not_applicable
# ---------------------------------------------------------------------------

def test_no_gates_registered():
    saved = dict(global_reg._store)
    global_reg._store.clear()
    try:
        report = compile_gate_report()
        for slot in (
            "source_quality",
            "argument_density",
            "controversy_matrix",
            "exploration_log",
        ):
            assert report.gate_verdicts[slot].verdict == "not_applicable"
    finally:
        global_reg._store.update(saved)


# ---------------------------------------------------------------------------
# 4. GateReport has required fields
# ---------------------------------------------------------------------------

def test_report_fields():
    report = compile_gate_report(run_metadata={"run": "test"})
    assert report.report_id.startswith("gate_report_")
    assert isinstance(report.gate_verdicts, dict)
    assert isinstance(report.artifact_paths, dict)
    assert isinstance(report.scorecard_ref, dict)
    assert isinstance(report.partial_verdicts, list)
    assert isinstance(report.run_metadata["partial_verdicts"], list)


def test_report_id_is_deterministic():
    left = compile_gate_report(run_metadata={"run": "stable"}).report_id
    right = compile_gate_report(run_metadata={"run": "stable"}).report_id
    assert left == right
