from __future__ import annotations

import json
import sys
from pathlib import Path

LIB_DIR = (Path(__file__).resolve().parents[2] / 'harness') / "lib"
sys.path.insert(0, str(LIB_DIR))

from advanced_ai4rnd_operator import execute_operator


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_bayesian_optimizer_runs_real_objective_and_records_taskgraph(tmp_path):
    result = execute_operator(
        {
            "operator_kind": "optimizer",
            "algorithm": "bayesian_optimization",
            "run_id": "bo-reference-run",
            "sprint_id": "sprint-bo",
            "node_id": "N-bo",
            "task_id": "task-bo",
            "artifact_root": str(tmp_path / "artifacts"),
            "inputs": {
                "search_space": [-3, -2, -1, 0, 1, 2, 3],
                "objective": {"type": "quadratic", "target": 2, "offset": 10, "scale": 1},
            },
            "parameters": {"rounds": 5, "initial_points": [-3]},
        },
        sprints_dir=tmp_path / "sprints",
        evidence_dir=tmp_path / "evidence",
    )

    assert result["status"] == "passed"
    assert result["metrics"]["rounds_completed"] == 5
    assert result["metrics"]["unique_points_evaluated"] > 1
    assert result["metrics"]["score_delta"] > 0
    assert result["best"]["score"] > -15
    assert Path(result["artifacts"]["result"]).is_file()
    assert result["output_hash"]

    graph = _load_json(result["artifacts"]["artifact_graph"])
    assert graph["nodes"]["policy_candidate"]["kind"] == "routing_policy_candidate"
    assert graph["edges"][0]["relation"] == "optimized_into"

    state = _load_json(tmp_path / "sprints" / "sprint-bo.task_dag.state.json")
    node = state["node_results"]["N-bo"]
    assert node["status"] == "passed"
    assert node["advanced_ai4rnd"]["metrics"]["best_score"] == result["metrics"]["best_score"]
    assert node["advanced_ai4rnd"]["output_hash"] == result["output_hash"]

    ledger_lines = (tmp_path / "evidence" / "sprint-bo.jsonl").read_text(encoding="utf-8").splitlines()
    evidence = json.loads(ledger_lines[-1])
    assert evidence["verification_results"]["status"] == "passed"
    assert evidence["verification_results"]["output_hash"] == result["output_hash"]


def test_sft_linear_adapter_trains_versioned_artifact_with_lineage(tmp_path):
    result = execute_operator(
        {
            "operator_kind": "trainer",
            "algorithm": "sft_linear_adapter",
            "run_id": "sft-reference-run",
            "sprint_id": "sprint-sft",
            "node_id": "N-sft",
            "task_id": "task-sft",
            "artifact_root": str(tmp_path / "artifacts"),
            "inputs": {
                "base_model_alias": "thunderomlx",
                "dataset_license": "internal-test",
                "train_dataset": [
                    {"text": "approve safe reliable plan", "label": "accept"},
                    {"text": "approve tested helpful answer", "label": "accept"},
                    {"text": "reject unsafe secret leak", "label": "reject"},
                    {"text": "reject brittle untested hack", "label": "reject"},
                ],
                "holdout_dataset": [
                    {"text": "safe tested plan", "label": "accept"},
                    {"text": "unsafe secret hack", "label": "reject"},
                ],
            },
            "parameters": {"epochs": 60, "learning_rate": 0.4},
        },
        sprints_dir=tmp_path / "sprints",
        evidence_dir=tmp_path / "evidence",
    )

    assert result["status"] == "passed"
    assert result["model_version_id"].startswith("thunderomlx.sft-linear.")
    assert result["metrics"]["holdout_accuracy"] > result["metrics"]["baseline_holdout_accuracy"]
    assert result["metrics"]["train_accuracy"] == 1.0
    assert result["output_hash"]

    adapter = _load_json(result["artifacts"]["adapter"])
    assert adapter["version_id"] == result["model_version_id"]
    assert adapter["base_model_id"] == "thunderomlx"
    assert set(adapter["labels"]) == {"accept", "reject"}

    manifest = _load_json(result["artifacts"]["manifest"])
    assert manifest["adapter_hash"] == result["output_hash"]
    assert manifest["dataset_hash"] == result["dataset_hash"]
    assert {"from": "thunderomlx", "to": result["model_version_id"], "relation": "adapted_from"} in manifest["lineage"]

    graph = _load_json(result["artifacts"]["artifact_graph"])
    assert graph["nodes"][result["model_version_id"]]["kind"] == "model_version"
    assert graph["nodes"][f"dataset.{result['dataset_hash']}"]["license"] == "internal-test"

    state = _load_json(tmp_path / "sprints" / "sprint-sft.task_dag.state.json")
    node = state["node_results"]["N-sft"]
    assert node["status"] == "passed"
    assert node["advanced_ai4rnd"]["artifacts"]["manifest"] == result["artifacts"]["manifest"]


def test_unsupported_algorithms_do_not_fake_pass_and_record_failure_state(tmp_path):
    result = execute_operator(
        {
            "operator_kind": "trainer",
            "algorithm": "lora",
            "run_id": "unsupported-run",
            "sprint_id": "sprint-lora",
            "node_id": "N-lora",
            "task_id": "task-lora",
            "artifact_root": str(tmp_path / "artifacts"),
            "inputs": {},
            "parameters": {},
        },
        sprints_dir=tmp_path / "sprints",
        evidence_dir=tmp_path / "evidence",
    )

    assert result["status"] == "unsupported"
    assert result["result_state"] == "STILL_NOT_AVAILABLE"
    assert result["task_graph_status"] == "failed"
    assert result["output_hash"] is None
    assert not (tmp_path / "artifacts" / "unsupported-run").exists()

    state = _load_json(tmp_path / "sprints" / "sprint-lora.task_dag.state.json")
    node = state["node_results"]["N-lora"]
    assert node["status"] == "failed"
    assert node["advanced_ai4rnd"]["status"] == "unsupported"

    ledger_lines = (tmp_path / "evidence" / "sprint-lora.jsonl").read_text(encoding="utf-8").splitlines()
    evidence = json.loads(ledger_lines[-1])
    assert evidence["verification_results"]["status"] == "unsupported"
