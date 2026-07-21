import pytest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.schema import RunRecord, RunState  # noqa: E402
from ai_influence_youtube_report.state_machine import transition_run  # noqa: E402


def test_success_transition_records_log_and_artifact() -> None:
    record = RunRecord(run_id="run-1", state=RunState.CREATED)

    next_record = transition_run(
        record,
        RunState.GRADED,
        artifact_updates={"gate": "gate.json"},
        log_entry={"step": "L2.gate", "outcome": "ok"},
    )

    assert next_record.state == RunState.GRADED
    assert next_record.phase_artifacts["gate"] == "gate.json"
    assert next_record.step_log[-1]["step"] == "L2.gate"


def test_invalid_transition_is_rejected() -> None:
    record = RunRecord(run_id="run-1", state=RunState.CREATED)

    with pytest.raises(ValueError, match="invalid run transition"):
        transition_run(record, RunState.ARCHIVED)


def test_terminal_state_cannot_transition() -> None:
    record = RunRecord(run_id="run-1", state=RunState.RUN_REJECTED_T3_ONLY)

    with pytest.raises(ValueError, match="terminal"):
        transition_run(record, RunState.GRADED)
