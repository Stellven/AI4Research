"""Validate that emitted run.json conforms to PRD §7 minimum fields.

S03 N6 acceptance: write_run_artifacts produces a run.json that contains every
required field declared in the BenchmarkRunResult schema. These tests pin the
on-disk contract so downstream consumers (status banner, autopilot, scorecard)
don't break silently on a field rename.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.lib.benchmark.reports import write_run_artifacts
from harness.lib.benchmark.schemas import (
    SCHEMA_VERSION,
    BenchmarkRunResult,
    asdict_run_result,
)


# PRD §7 minimum required field set (matches BenchmarkRunResult dataclass).
_REQUIRED_FIELDS = frozenset({
    "schema_version",
    "run_id",
    "benchmark",
    "benchmark_version",
    "dataset",
    "adapter",
    "agent",
    "model",
    "env",
    "tasks_requested",
    "tasks_completed",
    "score",
    "pass_count",
    "fail_count",
    "pending_count",
    "started_at",
    "completed_at",
    "duration_sec",
    "command",
    "exit_code",
    "stdout_path",
    "stderr_path",
    "artifacts",
    "verdict",
    "failure_modes",
    "limitations",
})

_VALID_VERDICTS = frozenset({"ok", "pending", "error"})


def _make_result(**overrides):
    base = dict(
        schema_version=SCHEMA_VERSION,
        run_id="bench-20260521010000-deadbeef",
        benchmark="terminal-bench",
        benchmark_version="2.0",
        dataset="terminal-bench@2.0",
        adapter="harbor",
        agent="claude-code",
        model="claude-opus-4-7",
        env="docker",
        tasks_requested=("hello-world-cli",),
        tasks_completed=(),
        score=None,
        pass_count=0,
        fail_count=0,
        pending_count=1,
        started_at="2026-05-21T01:00:00Z",
        completed_at="2026-05-21T01:00:01Z",
        duration_sec=1.0,
        command=("harbor", "run", "--dataset", "terminal-bench@2.0"),
        exit_code=None,
        stdout_path=None,
        stderr_path=None,
        artifacts=(),
        verdict="ok",
        failure_modes=(),
        limitations=("dry_run: no actual execution",),
    )
    base.update(overrides)
    return BenchmarkRunResult(**base)


@pytest.fixture
def isolated_reports_dir(tmp_path, monkeypatch):
    base = tmp_path / "reports" / "benchmark"
    base.mkdir(parents=True)
    monkeypatch.setenv("SOLAR_BENCH_REPORTS_DIR", str(base))
    return base


def test_run_json_contains_all_required_fields(isolated_reports_dir, tmp_path):
    result = _make_result()
    run_dir = tmp_path / "runs" / result.run_id
    write_run_artifacts(run_dir, result)

    run_json_path = run_dir / "run.json"
    assert run_json_path.is_file(), "run.json was not written"
    data = json.loads(run_json_path.read_text(encoding="utf-8"))

    missing = _REQUIRED_FIELDS - data.keys()
    assert not missing, f"run.json missing required fields: {sorted(missing)}"


def test_run_json_schema_version_locked(isolated_reports_dir, tmp_path):
    result = _make_result()
    run_dir = tmp_path / "runs" / result.run_id
    write_run_artifacts(run_dir, result)
    data = json.loads((run_dir / "run.json").read_text())
    assert data["schema_version"] == "benchmark.run.v1"


def test_run_json_verdict_is_valid(isolated_reports_dir, tmp_path):
    for verdict in _VALID_VERDICTS:
        result = _make_result(verdict=verdict, run_id=f"bench-test-{verdict}")
        run_dir = tmp_path / "runs" / result.run_id
        write_run_artifacts(run_dir, result)
        data = json.loads((run_dir / "run.json").read_text())
        assert data["verdict"] in _VALID_VERDICTS


def test_run_json_tuples_serialized_as_lists(isolated_reports_dir, tmp_path):
    """asdict_run_result must convert tuple[str, ...] fields to JSON lists."""
    result = _make_result(
        tasks_requested=("a", "b", "c"),
        command=("harbor", "run"),
        failure_modes=("note1",),
        limitations=("lim1",),
    )
    run_dir = tmp_path / "runs" / result.run_id
    write_run_artifacts(run_dir, result)
    data = json.loads((run_dir / "run.json").read_text())
    assert isinstance(data["tasks_requested"], list)
    assert data["tasks_requested"] == ["a", "b", "c"]
    assert isinstance(data["command"], list)
    assert isinstance(data["failure_modes"], list)
    assert isinstance(data["limitations"], list)


def test_run_json_roundtrip_preserves_values(isolated_reports_dir, tmp_path):
    result = _make_result(
        run_id="bench-20260521120000-aabbccdd",
        verdict="pending",
        pending_count=3,
        failure_modes=("harbor_cli", "docker"),
    )
    run_dir = tmp_path / "runs" / result.run_id
    write_run_artifacts(run_dir, result)
    data = json.loads((run_dir / "run.json").read_text())
    assert data["run_id"] == "bench-20260521120000-aabbccdd"
    assert data["verdict"] == "pending"
    assert data["pending_count"] == 3
    assert data["failure_modes"] == ["harbor_cli", "docker"]


def test_latest_pointer_mirrors_run_json(isolated_reports_dir, tmp_path):
    """The latest-terminal-bench-2.json copy must equal the run.json bytes."""
    result = _make_result()
    run_dir = tmp_path / "runs" / result.run_id
    written = write_run_artifacts(run_dir, result)

    run_json_text = (run_dir / "run.json").read_text(encoding="utf-8")
    latest_json = Path(written["latest_json"]).read_text(encoding="utf-8")
    assert json.loads(latest_json) == json.loads(run_json_text)


def test_asdict_round_trip_satisfies_schema():
    """Pure data-shape check that doesn't touch disk."""
    result = _make_result()
    data = asdict_run_result(result)
    missing = _REQUIRED_FIELDS - data.keys()
    assert not missing, missing
