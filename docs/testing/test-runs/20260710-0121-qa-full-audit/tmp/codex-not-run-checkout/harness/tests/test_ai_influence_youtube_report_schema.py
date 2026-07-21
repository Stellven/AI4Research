import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.schema import (  # noqa: E402
    GateDecision,
    RunRecord,
    RunState,
    TranscriptGrade,
)


def test_gate_decision_json_shape() -> None:
    decision = GateDecision(
        video_id="abc123",
        grade=TranscriptGrade.T1,
        entity_recall=0.8,
        wer=0.2,
        segment_density=0.7,
        evidence_notes=["usable"],
        gated_at="2026-05-29T00:00:00Z",
    )

    payload = decision.to_dict()

    assert payload["schema_version"] == "gate_decision.v1"
    assert payload["grade"] == "T1"
    assert payload["video_id"] == "abc123"


def test_run_record_json_shape() -> None:
    record = RunRecord(run_id="run-1", state=RunState.CREATED)

    payload = record.to_dict()

    assert payload["schema_version"] == "run_record.v1"
    assert payload["state"] == "created"
    assert payload["phase_artifacts"] == {}
