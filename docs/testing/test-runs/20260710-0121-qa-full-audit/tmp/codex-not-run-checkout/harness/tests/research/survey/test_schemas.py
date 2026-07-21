"""Round-trip tests for S03 N1 schema extensions.

Covers the 12 new dataclasses appended to lib/research/survey/schemas.py per
S02 architecture specs (source-quality / argument-density / contradiction-matrix /
exploration / gate-report). Each test exercises to_dict() round-trip and verifies
schema_version + key fields land in the serialised dict.

Existing 12 dataclasses (SurveyRun ... SurveyScorecard) are NOT modified by N1;
their round-trip coverage lives in tests/research_survey/test_schemas.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research.survey import schemas  # noqa: E402


def _roundtrip(obj):
    payload = schemas.to_dict(obj)
    assert isinstance(payload, dict), f"to_dict must yield a dict, got {type(payload)}"
    assert payload.get("schema_version") == schemas.SCHEMA_VERSION
    return payload


# --- O1 source-quality-arch ---------------------------------------------------


def test_stuffing_alert_roundtrip():
    alert = schemas.StuffingAlert(
        domain="example.com",
        count=5,
        source_ids=["src-1", "src-2"],
        confidence="high",
    )
    d = _roundtrip(alert)
    assert d["domain"] == "example.com"
    assert d["count"] == 5
    assert d["source_ids"] == ["src-1", "src-2"]
    assert d["confidence"] == "high"


def test_source_quality_distribution_roundtrip_with_nested_alert():
    sqd = schemas.SourceQualityDistribution(
        section_id="ch1.s1",
        source_type_counts={"paper": 3, "web": 1, "code": 2},
        primary_ratio=0.75,
        stuffing_alerts=[
            schemas.StuffingAlert(domain="blog.io", count=4, source_ids=["src-a", "src-b"]),
        ],
        canonical_coverage={"paper": True, "code": True, "official": False, "benchmark": False},
        verdict="warning",
        verdict_reasons=["missing_canonical:official", "missing_canonical:benchmark"],
        taxonomy_version="taxonomy.v1",
    )
    d = _roundtrip(sqd)
    assert d["section_id"] == "ch1.s1"
    assert d["primary_ratio"] == 0.75
    assert d["verdict"] == "warning"
    assert d["taxonomy_version"] == "taxonomy.v1"
    # Nested dataclass should be recursively converted.
    assert d["stuffing_alerts"][0]["domain"] == "blog.io"
    assert d["stuffing_alerts"][0]["source_ids"] == ["src-a", "src-b"]
    assert d["canonical_coverage"]["paper"] is True


# --- O2 argument-density-arch -------------------------------------------------


def test_not_applicable_entry_roundtrip():
    nae = schemas.NotApplicableEntry(
        dimension="evaluation_protocol",
        reason="theoretical background section, no benchmarks expected",
    )
    d = _roundtrip(nae)
    assert d["dimension"] == "evaluation_protocol"
    assert d["reason"].startswith("theoretical")


def test_dimension_indicator_roundtrip():
    di = schemas.DimensionIndicator(
        dimension="method_taxonomy",
        span_text="We classify methods into three categories: A, B, C.",
        confidence="medium",
    )
    d = _roundtrip(di)
    assert d["dimension"] == "method_taxonomy"
    assert "three categories" in d["span_text"]
    assert d["confidence"] == "medium"


def test_argument_density_profile_roundtrip_with_nested_indicators():
    profile = schemas.ArgumentDensityProfile(
        section_id="ch2.s3",
        dimension_coverages={
            "mechanism_comparison": "present",
            "method_taxonomy": "absent",
            "evaluation_protocol": "not_applicable",
            "failure_negative_evidence": "present",
            "engineering_implication": "absent",
        },
        density_score=0.4,
        detected_indicators=[
            schemas.DimensionIndicator(
                dimension="mechanism_comparison",
                span_text="X outperforms Y on benchmark Z",
                confidence="high",
            ),
            schemas.DimensionIndicator(
                dimension="failure_negative_evidence",
                span_text="Method P fails when input dimension exceeds 1024",
                confidence="medium",
            ),
        ],
        not_applicable_entries=[
            schemas.NotApplicableEntry(
                dimension="evaluation_protocol",
                reason="background only",
            )
        ],
        issues=["low_density"],
    )
    d = _roundtrip(profile)
    assert d["section_id"] == "ch2.s3"
    assert d["density_score"] == 0.4
    assert d["dimension_coverages"]["mechanism_comparison"] == "present"
    assert d["dimension_coverages"]["evaluation_protocol"] == "not_applicable"
    assert len(d["detected_indicators"]) == 2
    assert d["detected_indicators"][0]["dimension"] == "mechanism_comparison"
    assert d["not_applicable_entries"][0]["reason"] == "background only"
    assert "low_density" in d["issues"]


def test_argument_density_profile_minimal_defaults():
    profile = schemas.ArgumentDensityProfile(
        section_id="ch1.s1",
        dimension_coverages={"mechanism_comparison": "absent"},
        density_score=0.0,
        detected_indicators=[],
    )
    d = _roundtrip(profile)
    assert d["not_applicable_entries"] == []
    assert d["issues"] == []


# --- O3 contradiction-matrix-arch ---------------------------------------------


def test_claim_evidence_link_roundtrip():
    link = schemas.ClaimEvidenceLink(
        evidence_id="ev-1",
        source_id="src-7",
        source_type="paper",
        relation_strength="strong",
    )
    d = _roundtrip(link)
    assert d["evidence_id"] == "ev-1"
    assert d["source_type"] == "paper"
    assert d["relation_strength"] == "strong"


def test_contradiction_matrix_roundtrip_with_three_buckets():
    sup = schemas.ClaimEvidenceLink(
        evidence_id="e-sup",
        source_id="s-sup",
        source_type="paper",
        relation_strength="strong",
    )
    con = schemas.ClaimEvidenceLink(
        evidence_id="e-con",
        source_id="s-con",
        source_type="benchmark",
        relation_strength="moderate",
    )
    unc = schemas.ClaimEvidenceLink(
        evidence_id="e-unc",
        source_id="s-unc",
        source_type="web-generic",
        relation_strength="weak",
    )
    matrix = schemas.ContradictionMatrix(
        claim_id="claim:c1",
        claim_text="Mechanism X is more sample-efficient than Y",
        supporting_evidence=[sup],
        contradicting_evidence=[con],
        uncertain_evidence=[unc],
        chapter_ids=["ch1", "ch3"],
        synthesis_referenced=True,
    )
    d = _roundtrip(matrix)
    assert d["claim_id"] == "claim:c1"
    assert d["synthesis_referenced"] is True
    assert d["supporting_evidence"][0]["evidence_id"] == "e-sup"
    assert d["contradicting_evidence"][0]["relation_strength"] == "moderate"
    assert d["uncertain_evidence"][0]["source_type"] == "web-generic"
    assert d["chapter_ids"] == ["ch1", "ch3"]


def test_contradiction_matrix_decorative_case_empty_buckets():
    matrix = schemas.ContradictionMatrix(
        claim_id="claim:c2",
        claim_text="No counter-evidence",
        supporting_evidence=[],
        contradicting_evidence=[],
        uncertain_evidence=[],
        chapter_ids=["ch5"],
        synthesis_referenced=False,
    )
    d = _roundtrip(matrix)
    assert d["contradicting_evidence"] == []
    assert d["uncertain_evidence"] == []
    assert d["synthesis_referenced"] is False


# --- O4 exploration-arch ------------------------------------------------------


def test_elimination_record_roundtrip_full():
    record = schemas.EliminationRecord(
        direction_id="dir-7",
        direction_name="quantised inference latency",
        score=0.42,
        kill_reason="source_authority_ratio below sibling directions",
        evidence_refs=["src-1", "src-2", "src-3"],
        decision_ts="2026-05-17T10:00:00Z",
        direction_query="quantisation latency benchmarks",
        candidate_count=5,
        score_breakdown={"source_authority_ratio": 0.30, "novelty_signal": 0.55},
    )
    d = _roundtrip(record)
    assert d["direction_id"] == "dir-7"
    assert d["kill_reason"].startswith("source_authority_ratio")
    assert d["evidence_refs"] == ["src-1", "src-2", "src-3"]
    assert d["decision_ts"].endswith("Z")
    assert d["score_breakdown"]["novelty_signal"] == 0.55


def test_elimination_record_minimal_optional_fields():
    record = schemas.EliminationRecord(
        direction_id="dir-1",
        direction_name="weak angle",
        score=0.1,
        kill_reason="retrieval_timeout",
        evidence_refs=["src-x"],
        decision_ts="2026-05-17T10:05:00Z",
    )
    d = _roundtrip(record)
    assert d["candidate_count"] == 0
    assert d["score_breakdown"] == {}
    assert d["direction_query"] == ""


def test_exploration_direction_active_minimal():
    direction = schemas.ExplorationDirection(
        direction_id="dir-A",
        direction_name="X angle",
        query="X mechanism",
        status="active",
    )
    d = _roundtrip(direction)
    assert d["status"] == "active"
    assert d["source_matrix"] is None
    assert d["elimination_record"] is None


def test_exploration_direction_with_elimination_record_nested():
    elim = schemas.EliminationRecord(
        direction_id="dir-B",
        direction_name="weak Y",
        score=0.05,
        kill_reason="no contradiction coverage",
        evidence_refs=["src-9"],
        decision_ts="2026-05-17T10:10:00Z",
    )
    direction = schemas.ExplorationDirection(
        direction_id="dir-B",
        direction_name="weak Y",
        query="Y limits",
        status="eliminated",
        elimination_record=elim,
    )
    d = _roundtrip(direction)
    assert d["status"] == "eliminated"
    # Nested dataclass round-trips via asdict.
    assert d["elimination_record"]["kill_reason"] == "no contradiction coverage"
    assert d["elimination_record"]["direction_id"] == "dir-B"


def test_exploration_direction_with_source_matrix_nested():
    matrix = schemas.SourceMatrix(
        section_id="ch1.s1",
        required_source_types=["paper", "code"],
        recommended_source_types=["benchmark"],
        min_sources=3,
        min_evidence=2,
    )
    direction = schemas.ExplorationDirection(
        direction_id="dir-M",
        direction_name="matrix-bound angle",
        query="anything",
        status="selected",
        source_matrix=matrix,
    )
    d = _roundtrip(direction)
    assert d["source_matrix"]["section_id"] == "ch1.s1"
    assert d["source_matrix"]["required_source_types"] == ["paper", "code"]


def test_exploration_run_result_roundtrip():
    sel = schemas.ExplorationDirection(
        direction_id="dir-S",
        direction_name="kept",
        query="qA",
        status="selected",
    )
    kill = schemas.ExplorationDirection(
        direction_id="dir-K",
        direction_name="dropped",
        query="qB",
        status="eliminated",
    )
    result = schemas.ExplorationRunResult(
        run_id="run-xyz",
        selected_directions=[sel],
        eliminated_directions=[kill],
        elimination_log_path="/tmp/run-xyz/elimination_log.jsonl",
    )
    d = _roundtrip(result)
    assert d["run_id"] == "run-xyz"
    assert len(d["selected_directions"]) == 1
    assert len(d["eliminated_directions"]) == 1
    assert d["elimination_log_path"].endswith("elimination_log.jsonl")
    assert d["source_matrix_consumed"] is None


# --- O5 gate-report-arch ------------------------------------------------------


def test_gate_verdict_roundtrip():
    gv = schemas.GateVerdict(
        gate_id="source_quality",
        verdict="pass",
        evidence_refs=["claim:c1", "claim:c2"],
        report_section={"primary_ratio": 0.8, "stuffing_alerts": 0},
    )
    d = _roundtrip(gv)
    assert d["gate_id"] == "source_quality"
    assert d["verdict"] == "pass"
    assert d["evidence_refs"] == ["claim:c1", "claim:c2"]
    assert d["report_section"]["primary_ratio"] == 0.8


def test_gate_report_roundtrip_with_four_gate_verdicts():
    verdicts = {
        "source_quality": schemas.GateVerdict(
            gate_id="source_quality",
            verdict="pass",
            evidence_refs=[],
            report_section={},
        ),
        "argument_density": schemas.GateVerdict(
            gate_id="argument_density",
            verdict="warn",
            evidence_refs=["section:ch2.s3"],
            report_section={"low_density": True},
        ),
        "controversy_matrix": schemas.GateVerdict(
            gate_id="controversy_matrix",
            verdict="fail",
            evidence_refs=[],
            report_section={"decorative_warning": True},
        ),
        "exploration_log": schemas.GateVerdict(
            gate_id="exploration_log",
            verdict="pass",
            evidence_refs=["dir-A"],
            report_section={"selected_count": 2, "eliminated_count": 1},
        ),
    }
    report = schemas.GateReport(
        report_id="run-abc-123",
        run_metadata={
            "sample_id": "sample-x",
            "topic": "deep research",
            "started_at": "2026-05-17T09:00:00Z",
            "finished_at": "2026-05-17T09:30:00Z",
            "runner_version": "v1",
        },
        gate_verdicts=verdicts,
        artifact_paths={
            "gate_report.json": "gate_report.json",
            "elimination_log.jsonl": "elimination_log.jsonl",
            "contradiction_matrix.json": "contradiction_matrix.json",
        },
        scorecard_ref={
            "path": "scorecard.json",
            "verdict": "pass",
            "generated_at": "2026-05-17T09:30:00Z",
        },
    )
    d = _roundtrip(report)
    assert d["report_id"] == "run-abc-123"
    assert set(d["gate_verdicts"].keys()) == {
        "source_quality",
        "argument_density",
        "controversy_matrix",
        "exploration_log",
    }
    # Nested GateVerdict round-trips via asdict.
    assert d["gate_verdicts"]["argument_density"]["verdict"] == "warn"
    assert d["gate_verdicts"]["controversy_matrix"]["report_section"]["decorative_warning"] is True
    assert d["artifact_paths"]["elimination_log.jsonl"] == "elimination_log.jsonl"
    assert d["scorecard_ref"]["verdict"] == "pass"
    assert d["run_metadata"]["runner_version"] == "v1"


# --- coverage guards ----------------------------------------------------------


def test_new_dataclasses_carry_schema_version_field():
    """Every new dataclass declares schema_version (parity with existing 12)."""
    new_names = [
        "StuffingAlert",
        "SourceQualityDistribution",
        "NotApplicableEntry",
        "DimensionIndicator",
        "ArgumentDensityProfile",
        "ClaimEvidenceLink",
        "ContradictionMatrix",
        "EliminationRecord",
        "ExplorationDirection",
        "ExplorationRunResult",
        "GateVerdict",
        "GateReport",
    ]
    for name in new_names:
        cls = getattr(schemas, name)
        assert "schema_version" in cls.__dataclass_fields__, name


def test_to_dict_is_identity_for_non_dataclass_scalars_and_collections():
    assert schemas.to_dict(42) == 42
    assert schemas.to_dict("hello") == "hello"
    assert schemas.to_dict(None) is None
    nested = {
        "alert": schemas.StuffingAlert(domain="a.com", count=1, source_ids=["s"]),
        "list": [schemas.GateVerdict(gate_id="g", verdict="pass", evidence_refs=[])],
    }
    d = schemas.to_dict(nested)
    assert d["alert"]["domain"] == "a.com"
    assert d["list"][0]["gate_id"] == "g"
