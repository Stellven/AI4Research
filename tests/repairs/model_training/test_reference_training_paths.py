from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "harness" / "lib"))

from advanced_ai4rnd.training import (  # noqa: E402
    CheckpointError,
    DatasetValidationError,
    PromotionRejected,
    TrainingJob,
    run_training_job,
)


def _job(method: str, tmp_path: Path, **overrides):
    fixtures = {
        "sft": {
            "dataset": [
                {"features": [1.0, 0.0], "label": 1.0},
                {"features": [0.0, 1.0], "label": -1.0},
            ],
            "initial_weights": {"w": [0.0, 0.0], "bias": 0.0},
            "config": {"epochs": 3, "learning_rate": 0.25},
        },
        "lora": {
            "dataset": [
                {"features": [1.0, 0.0], "target": [1.0]},
                {"features": [0.0, 1.0], "target": [-1.0]},
            ],
            "initial_weights": {
                "base": [[0.0, 0.0]],
                "lora_a": [[0.2], [-0.2]],
                "lora_b": [[0.1]],
            },
            "config": {"epochs": 4, "learning_rate": 0.2, "rank": 1},
        },
        "dpo": {
            "dataset": [
                {"chosen_features": [1.0, 0.0], "rejected_features": [0.0, 1.0]},
                {"chosen_features": [1.0, 1.0], "rejected_features": [-1.0, 0.0]},
            ],
            "initial_weights": {"w": [0.0, 0.0]},
            "config": {"epochs": 3, "learning_rate": 0.2, "beta": 1.0},
        },
        "grpo": {
            "dataset": [
                {"group_id": "g1", "features": [1.0, 0.0], "reward": 1.0},
                {"group_id": "g1", "features": [0.0, 1.0], "reward": -1.0},
                {"group_id": "g2", "features": [1.0, 1.0], "reward": 2.0},
                {"group_id": "g2", "features": [-1.0, 0.0], "reward": 0.0},
            ],
            "initial_weights": {"w": [0.0, 0.0]},
            "config": {"epochs": 3, "learning_rate": 0.1},
        },
        "agent_rl": {
            "dataset": [
                {"state": [1.0, 0.0], "good_action": "accept", "bad_action": "reject"},
                {"state": [0.0, 1.0], "good_action": "reject", "bad_action": "accept"},
            ],
            "initial_weights": {"policy": {"accept": [0.0, 0.0], "reject": [0.0, 0.0]}},
            "config": {"episodes": 8, "learning_rate": 0.2, "seed": 7},
        },
    }
    payload = fixtures[method] | overrides
    return TrainingJob(
        job_id=f"test-{method}",
        method=method,
        dataset=payload["dataset"],
        config=payload["config"],
        initial_weights=payload["initial_weights"],
        output_dir=tmp_path / method,
        resume_from=payload.get("resume_from"),
        promotion_gate=payload.get("promotion_gate", {"metric": "eval_score", "min": 0.0}),
    )


@pytest.mark.parametrize("method", ["sft", "lora", "dpo", "grpo", "agent_rl"])
def test_each_training_method_runs_cpu_reference_job(method, tmp_path):
    result = run_training_job(_job(method, tmp_path))

    assert result.status == "passed"
    assert result.metrics["completed_steps"] == result.metrics["planned_steps"]
    assert result.evidence["parameter_update"] is True
    assert Path(result.artifacts["checkpoint"]).exists()
    assert result.provenance["dataset_hash"]
    assert result.provenance["config_hash"]
    assert result.provenance["code_hash"]
    assert result.provenance["initial_weights_hash"] != result.provenance["result_weights_hash"]
    assert result.promotion["controlled_by_evaluation_gate"] is True
    assert result.promotion["passed"] is True


def test_lora_updates_low_rank_parameters(tmp_path):
    result = run_training_job(_job("lora", tmp_path))
    checkpoint = json.loads(Path(result.artifacts["checkpoint"]).read_text(encoding="utf-8"))

    assert checkpoint["weights"]["lora_a"] != [[0.2], [-0.2]]
    assert checkpoint["weights"]["lora_b"] != [[0.1]]
    assert result.metrics["updated_low_rank_parameters"] is True


def test_dpo_consumes_chosen_rejected_preference(tmp_path):
    result = run_training_job(_job("dpo", tmp_path))

    assert result.evidence["consumed_chosen_rejected_pairs"] == 2
    assert result.metrics["preference_margin"] > 0


def test_grpo_consumes_group_reward_advantage(tmp_path):
    result = run_training_job(_job("grpo", tmp_path))

    assert result.evidence["consumed_group_rewards"] == 2
    assert result.evidence["consumed_group_advantages"] is True
    assert result.metrics["mean_advantage_abs"] > 0


def test_sft_consumes_labeled_examples_and_updates_loss(tmp_path):
    result = run_training_job(_job("sft", tmp_path))

    assert result.evidence["consumed_labeled_examples"] == 2
    assert result.metrics["loss_delta"] > 0


def test_agent_rl_records_trajectory_reward_and_policy_update(tmp_path):
    result = run_training_job(_job("agent_rl", tmp_path))

    assert len(result.evidence["trajectories"]) == 8
    assert result.evidence["reward_trace"]
    assert result.evidence["policy_update_evidence"] is True
    assert result.metrics["policy_update_norm"] > 0


def test_resume_loads_checkpoint_and_skips_completed_steps(tmp_path):
    partial = _job("sft", tmp_path, config={"epochs": 3, "learning_rate": 0.25, "pause_after_steps": 2})
    first = run_training_job(partial)
    assert first.metrics["completed_steps"] == 2
    assert first.metrics["planned_steps"] == 6
    resumed = TrainingJob(
        job_id=partial.job_id,
        method="sft",
        dataset=partial.dataset,
        config=partial.config,
        initial_weights=partial.initial_weights,
        output_dir=tmp_path / "resume",
        resume_from=Path(first.artifacts["checkpoint"]),
        promotion_gate={"metric": "eval_score", "min": 0.0},
    )

    result = run_training_job(resumed)

    assert result.evidence["resumed"] is True
    assert result.evidence["resumed_from_step"] == 2
    assert result.evidence["skipped_completed_steps"] == 2
    assert result.metrics["completed_steps"] == 6


def test_invalid_dataset_nan_and_corrupt_checkpoint_are_rejected(tmp_path):
    with pytest.raises(DatasetValidationError):
        run_training_job(_job("sft", tmp_path, dataset=[{"features": [1.0, 2.0]}]))
    with pytest.raises(DatasetValidationError):
        run_training_job(_job("sft", tmp_path, dataset=[{"features": [float("nan"), 0.0], "label": 1.0}]))
    corrupt = tmp_path / "bad.checkpoint.json"
    corrupt.write_text("{not-json", encoding="utf-8")
    with pytest.raises(CheckpointError):
        run_training_job(_job("sft", tmp_path, resume_from=corrupt))


def test_promotion_requires_evaluation_gate(tmp_path):
    with pytest.raises(PromotionRejected):
        run_training_job(_job("dpo", tmp_path, promotion_gate={"metric": "eval_score", "min": 1.1}))
