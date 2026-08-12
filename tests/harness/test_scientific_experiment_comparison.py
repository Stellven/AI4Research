from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness" / "lib"))
from scientific_experiment_comparison import InvalidComparison, compare  # noqa: E402


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _results(tmp_path: Path, deltas: list[float]) -> list[Path]:
    artifact = tmp_path / "observations.json"
    artifact.write_text(json.dumps({"observed": deltas}), encoding="utf-8")
    artifact_hash = _hash(artifact)
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"analysis": "pre-registered"}), encoding="utf-8")
    protocol_hash = _hash(protocol)
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"cases": len(deltas)}), encoding="utf-8")
    dataset_hash = _hash(dataset)
    pair_ids = [f"pair-{index}" for index in range(len(deltas))]
    paths = []
    for index, (pair_id, delta) in enumerate(zip(pair_ids, deltas)):
        for arm, value in (("baseline", 1.0), ("variant", 1.0 + delta)):
            plan = {
                "analysis_plan": "paired_randomization_test_v1",
                "study_id": "unit-study",
                "arm": arm,
                "baseline_arm": "baseline",
                "variant_arm": "variant",
                "pair_id": pair_id,
                "replicate_id": f"replicate-{index}-{arm}",
                "independence_unit": "case",
                "independence_value": f"case-{index}",
                "protocol_sha256": protocol_hash,
                "dataset_sha256": dataset_hash,
                "expected_pair_ids": pair_ids,
                "primary_metric": "accuracy",
                "metric_unit": "fraction",
                "higher_is_better": True,
                "alpha": 0.05,
                "minimum_pairs": 4,
            }
            doc = {
                "schema": "experiment_result.v1",
                "task_id": "task-unit",
                "sprint_id": "sprint-unit",
                "node_id": "experiment-run",
                "status": "completed",
                "inputs": {"comparison": plan},
                "outputs": {"result": {
                    "experiment_id": f"experiment-{index}-{arm}",
                    "outcome": "supports",
                    "metrics": [{"name": "accuracy", "value": value, "unit": "fraction"}],
                    "evidence_ids": [f"observation-{index}"],
                }},
                "artifacts": [
                    {"type": "pre_registered_protocol", "path": str(protocol), "sha256": protocol_hash},
                    {"type": "labeled_dataset", "path": str(dataset), "sha256": dataset_hash},
                    {"type": "raw_observations", "path": str(artifact), "sha256": artifact_hash},
                ],
                "provenance": {"operator_id": "unit-runner", "implementation_package": "tests/unit", "timestamp": "2026-08-12T08:00:00Z"},
                "limitations": ["Unit fixture."],
            }
            path = tmp_path / f"{index}-{arm}.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            paths.append(path)
    return paths


def test_accepts_complete_hash_bound_pre_registered_effect(tmp_path: Path) -> None:
    report = compare(_results(tmp_path, [1, 1, 1, 1, 1, 1]))
    assert report["status"] == "accepted"
    assert report["conclusion"] == "supports_variant_within_declared_study"
    assert report["sample"]["paired_count"] == 6
    assert report["effect"]["variant_minus_baseline"] == 1
    assert report["uncertainty"]["two_sided_sign_flip_p_value"] == pytest.approx(0.03125)
    assert report["uncertainty"]["bounded_significant_at_alpha"] is True
    assert len(report["sources"]) == 12


def test_reports_valid_non_significant_sample_as_inconclusive(tmp_path: Path) -> None:
    report = compare(_results(tmp_path, [1, -1, 1, -1, 1, -1]))
    assert report["status"] == "inconclusive"
    assert report["conclusion"] == "inconclusive_no_bounded_significant_difference"
    assert report["uncertainty"]["bounded_significant_at_alpha"] is False


def test_rejects_cherry_picked_missing_pair(tmp_path: Path) -> None:
    paths = _results(tmp_path, [1, 1, 1, 1, 1, 1])[:-2]
    with pytest.raises(InvalidComparison, match="cherry_picked_or_missing_pairs"):
        compare(paths)


def test_rejects_mismatched_protocol(tmp_path: Path) -> None:
    paths = _results(tmp_path, [1, 1, 1, 1])
    changed = json.loads(paths[-1].read_text(encoding="utf-8"))
    other_protocol = tmp_path / "other-protocol.json"
    other_protocol.write_text(json.dumps({"analysis": "changed"}), encoding="utf-8")
    changed["inputs"]["comparison"]["protocol_sha256"] = _hash(other_protocol)
    changed["artifacts"][0] = {
        "type": "pre_registered_protocol",
        "path": str(other_protocol),
        "sha256": _hash(other_protocol),
    }
    paths[-1].write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(InvalidComparison, match="mismatched_pre_registered_plan"):
        compare(paths)


def test_rejects_tampered_observation_artifact(tmp_path: Path) -> None:
    paths = _results(tmp_path, [1, 1, 1, 1])
    artifact = Path(json.loads(paths[0].read_text(encoding="utf-8"))["artifacts"][0]["path"])
    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(InvalidComparison, match="artifact_hash_mismatch"):
        compare(paths)


def test_rejects_duplicate_experiment_identity(tmp_path: Path) -> None:
    paths = _results(tmp_path, [1, 1, 1, 1])
    first = json.loads(paths[0].read_text(encoding="utf-8"))
    second = json.loads(paths[1].read_text(encoding="utf-8"))
    second["outputs"]["result"]["experiment_id"] = first["outputs"]["result"]["experiment_id"]
    paths[1].write_text(json.dumps(second), encoding="utf-8")
    with pytest.raises(InvalidComparison, match="duplicate_experiment_id"):
        compare(paths)
