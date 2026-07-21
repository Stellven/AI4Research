"""Activation proof verifier for S05 runtime artifacts."""

from __future__ import annotations

import json
from pathlib import Path

EXPECTED_STAGES = {
    "source_quality_gate",
    "argument_density_gate",
    "controversy_matrix_gate",
    "exploration_gate",
    "global_consistency_pass",
    "gate_report_aggregator",
}

ROOT = Path(__file__).resolve().parents[4]
PROOF = ROOT / "runtime" / "survey-continue" / "sample-run-001" / "activation_proof.jsonl"


def _read_stages(path: Path) -> set[str]:
    return {
        json.loads(line)["stage"]
        for line in path.read_text().splitlines()
        if line.strip()
    }


def test_activation_proof_has_all_six_expected_stages() -> None:
    assert _read_stages(PROOF) == EXPECTED_STAGES


def test_activation_proof_detects_missing_stage(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    path.write_text('{"stage":"source_quality_gate","fired":true}\n')
    assert _read_stages(path) != EXPECTED_STAGES


def test_activation_proof_all_rows_reference_artifacts() -> None:
    rows = [json.loads(line) for line in PROOF.read_text().splitlines()]
    assert rows
    assert all(row["fired"] is True for row in rows)
    assert all(row["artifact_path"] for row in rows)
    assert all(row["ts_relative"].startswith("t+") for row in rows)


def test_activation_proof_empty_file_is_not_valid(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    assert _read_stages(path) == set()

