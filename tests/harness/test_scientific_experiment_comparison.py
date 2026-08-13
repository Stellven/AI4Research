from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "harness" / "lib"))
from scientific_experiment_comparison import InvalidComparison, compare  # noqa: E402

PROTOCOL_COMMIT = "1614a96b3b1ffbde1df6876457c113321d2567c0"
PROTOCOL_BLOB = "bda32ee57ad484672782188fb64b4f948ad52e78"
PROTOCOL_PATH = "tests/journeys/phase22/fixtures/significant/scientific_comparison/protocol.json"
DATASET = REPO / "tests/journeys/phase22/fixtures/significant/scientific_comparison/labeled_retrieval.jsonl"
TRUST_REGISTRY = REPO / "tests/journeys/phase22/fixtures/significant/trust_registry.json"
ATTESTATION = {
    "protocol_repo": REPO,
    "protocol_commit": PROTOCOL_COMMIT,
    "protocol_path": PROTOCOL_PATH,
    "protocol_blob": PROTOCOL_BLOB,
    "trust_registry": TRUST_REGISTRY,
    "trust_registry_sha256": hashlib.sha256(TRUST_REGISTRY.read_bytes()).hexdigest(),
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _results(tmp_path: Path, deltas: list[float] | None = None) -> list[Path]:
    deltas = deltas or [1.0] * 8
    assert len(deltas) == 8
    queries = []
    for index, delta in enumerate(deltas, 1):
        pair = f"query-{index:02d}"
        queries.append({
            "query_id": pair,
            "base_ndcg_at_k": 0.0,
            "rerank_ndcg_at_k": delta,
            "provenance_ids": [f"source:{pair}"],
        })
    observation = tmp_path / "observations.json"
    observation.write_text(json.dumps({
        "schema_version": "solar.retrieval_reranker.v1",
        "status": "accepted",
        "source": {"path": str(DATASET), "sha256": _hash(DATASET), "rows": 20},
        "queries": queries,
    }), encoding="utf-8")
    observation_hash = _hash(observation)
    dataset_hash = _hash(DATASET)
    paths = []
    for query in queries:
      for arm, metric in (("base_score", query["base_ndcg_at_k"]), ("linear_reranker", query["rerank_ndcg_at_k"])):
        pair = query["query_id"]
        doc = {
            "schema": "experiment_result.v1",
            "task_id": "task-unit",
            "sprint_id": "sprint-unit",
            "node_id": "experiment-run",
            "status": "completed",
            "inputs": {"observation": {
                "observation_id": f"{pair}-{arm}",
                "pair_id": pair,
                "arm": arm,
                "replicate_id": f"replicate-{pair}-{arm}",
                "independence_value": pair,
                "source_artifact_sha256": observation_hash,
            }},
            "outputs": {"result": {
                "experiment_id": f"experiment-{pair}-{arm}",
                "outcome": "supports" if metric else "inconclusive",
                "metrics": [{"name": "ndcg_at_1", "value": metric, "unit": "score"}],
                "evidence_ids": [f"retrieval-observation:{pair}"],
                "execution_mode": "production_local",
                "command_run": "python retrieval_reranker.py train",
                "logs": ["query metric extracted from production reranker output"],
            }},
            "artifacts": [
                {"type": "labeled_dataset", "path": str(DATASET), "sha256": dataset_hash},
                {"type": "production_metric_observations", "path": str(observation), "sha256": observation_hash},
            ],
            "provenance": {"operator_id": "retrieval_reranker.py", "implementation_package": "harness/lib/retrieval_reranker.py", "timestamp": "2026-08-15T09:01:00Z"},
            "limitations": ["Unit fixture."],
        }
        path = tmp_path / f"{pair}-{arm}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        paths.append(path)
    return paths


def test_accepts_git_attested_protocol_and_hashed_observations(tmp_path: Path) -> None:
    report = compare(_results(tmp_path), **ATTESTATION)
    assert report["status"] == "accepted"
    assert report["sample"]["paired_count"] == 8
    assert report["effect"]["variant_minus_baseline"] == 1.0
    assert report["protocol_attestation"]["blob"] == PROTOCOL_BLOB
    assert all(source["canonical_experiment_result_gate"]["ok"] for source in report["sources"])


def test_rejects_mutable_result_metric_attack(tmp_path: Path) -> None:
    paths = _results(tmp_path)
    attacked = json.loads(paths[0].read_text(encoding="utf-8"))
    attacked["outputs"]["result"]["metrics"][0]["value"] = 100
    paths[0].write_text(json.dumps(attacked), encoding="utf-8")
    with pytest.raises(InvalidComparison, match="result_metric_disagrees_with_hashed_observation"):
        compare(paths, **ATTESTATION)


def test_embedded_result_plan_cannot_override_attested_protocol(tmp_path: Path) -> None:
    paths = _results(tmp_path)
    attacked = json.loads(paths[0].read_text(encoding="utf-8"))
    attacked["inputs"]["comparison"] = {
        "alpha": 1.0,
        "expected_pair_ids": [f"query-{index:02d}" for index in range(1, 5)],
    }
    paths[0].write_text(json.dumps(attacked), encoding="utf-8")
    report = compare(paths, **ATTESTATION)
    assert report["analysis_plan"]["alpha"] == 0.05
    assert len(report["analysis_plan"]["pre_registered_pairs"]) == 8


def test_rejects_wrong_out_of_band_protocol_blob(tmp_path: Path) -> None:
    with pytest.raises(InvalidComparison, match="protocol_blob_attestation_mismatch"):
        compare(_results(tmp_path), **{**ATTESTATION, "protocol_blob": "0" * 40})


def test_rejects_result_that_claims_to_precede_protocol_commit(tmp_path: Path) -> None:
    paths = _results(tmp_path)
    attacked = json.loads(paths[0].read_text(encoding="utf-8"))
    attacked["provenance"]["timestamp"] = "2026-08-12T08:00:00Z"
    paths[0].write_text(json.dumps(attacked), encoding="utf-8")
    with pytest.raises(InvalidComparison, match="result_precedes_protocol_attestation"):
        compare(paths, **ATTESTATION)


def test_rejects_missing_pair_cherry_pick(tmp_path: Path) -> None:
    with pytest.raises(InvalidComparison, match="cherry_picked_or_missing_pairs"):
        compare(_results(tmp_path)[:-2], **ATTESTATION)


def test_rejects_result_missing_canonical_execution_logs(tmp_path: Path) -> None:
    paths = _results(tmp_path)
    attacked = json.loads(paths[0].read_text(encoding="utf-8"))
    attacked["outputs"]["result"]["logs"] = []
    paths[0].write_text(json.dumps(attacked), encoding="utf-8")
    with pytest.raises(InvalidComparison, match="canonical_experiment_result_gate.*logs"):
        compare(paths, **ATTESTATION)


def test_rejects_tampered_observation_artifact_even_if_result_unchanged(tmp_path: Path) -> None:
    paths = _results(tmp_path)
    attacked = json.loads(paths[0].read_text(encoding="utf-8"))
    observation = Path(attacked["artifacts"][1]["path"])
    payload = json.loads(observation.read_text(encoding="utf-8"))
    payload["queries"][0]["base_ndcg_at_k"] = 999
    observation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InvalidComparison, match="artifact_hash_mismatch"):
        compare(paths, **ATTESTATION)
