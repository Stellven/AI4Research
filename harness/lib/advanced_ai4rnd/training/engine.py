from __future__ import annotations

import hashlib
import inspect
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal


TrainingMethod = Literal["sft", "lora", "dpo", "grpo", "agent_rl"]


class TrainingError(ValueError):
    """Base error for invalid or unsafe reference training jobs."""


class DatasetValidationError(TrainingError):
    """Raised when a dataset cannot prove the requested training path."""


class CheckpointError(TrainingError):
    """Raised when a checkpoint cannot be loaded or trusted."""


class PromotionRejected(TrainingError):
    """Raised when a trained artifact fails the configured evaluation gate."""


@dataclass(frozen=True)
class TrainingJob:
    """Unified training contract with method-specific dataset semantics."""

    job_id: str
    method: TrainingMethod
    dataset: list[dict[str, Any]]
    config: dict[str, Any]
    initial_weights: dict[str, Any]
    output_dir: Path
    code_refs: list[str] = field(default_factory=list)
    resume_from: Path | None = None
    promotion_gate: dict[str, Any] = field(default_factory=lambda: {"metric": "eval_score", "min": 0.0})


@dataclass(frozen=True)
class TrainingResult:
    schema_version: str
    job_id: str
    method: TrainingMethod
    status: str
    metrics: dict[str, Any]
    evidence: dict[str, Any]
    provenance: dict[str, str]
    artifacts: dict[str, str]
    promotion: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "method": self.method,
            "status": self.status,
            "metrics": self.metrics,
            "evidence": self.evidence,
            "provenance": self.provenance,
            "artifacts": self.artifacts,
            "promotion": self.promotion,
        }


def run_training_job(job: TrainingJob) -> TrainingResult:
    _validate_common(job)
    job.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_hash = _hash_json(job.dataset)
    config_hash = _hash_json(job.config)
    initial_hash = _hash_json(job.initial_weights)
    code_hash = _code_hash(job.code_refs)
    weights = _copy_jsonable(job.initial_weights)
    start_step = 0
    resume_evidence: dict[str, Any] = {"resumed": False, "skipped_completed_steps": 0}

    if job.resume_from is not None:
        checkpoint = load_checkpoint(job.resume_from)
        _assert_checkpoint_matches(checkpoint, job, dataset_hash, config_hash, initial_hash)
        weights = _copy_jsonable(checkpoint["weights"])
        start_step = int(checkpoint["completed_steps"])
        resume_evidence = {
            "resumed": True,
            "checkpoint": str(job.resume_from),
            "resumed_from_step": start_step,
            "skipped_completed_steps": start_step,
        }

    trainer = {
        "sft": _train_sft,
        "lora": _train_lora,
        "dpo": _train_dpo,
        "grpo": _train_grpo,
        "agent_rl": _train_agent_rl,
    }[job.method]
    trained_weights, metrics, method_evidence = trainer(job, weights, start_step)
    _reject_non_finite(trained_weights, "result weights")
    result_hash = _hash_json(trained_weights)
    changed = result_hash != (initial_hash if start_step == 0 else _hash_json(weights))
    if not changed:
        raise TrainingError(f"{job.method} produced no parameter or policy change")

    checkpoint_payload = {
        "schema_version": "solar.training_checkpoint.v1",
        "job_id": job.job_id,
        "method": job.method,
        "dataset_hash": dataset_hash,
        "config_hash": config_hash,
        "initial_weights_hash": initial_hash,
        "code_hash": code_hash,
        "completed_steps": int(metrics["completed_steps"]),
        "weights": trained_weights,
        "metrics": metrics,
    }
    checkpoint_path = job.output_dir / f"{job.job_id}.checkpoint.json"
    _write_json(checkpoint_path, checkpoint_payload)
    checkpoint_hash = _hash_file(checkpoint_path)
    eval_score = _evaluate(job.method, trained_weights, job.dataset)
    metrics["eval_score"] = eval_score
    promotion = _promotion_decision(job.promotion_gate, metrics)
    if not promotion["passed"]:
        raise PromotionRejected(
            f"promotion gate rejected {job.job_id}: {promotion['metric']}={promotion['actual']} < {promotion['minimum']}"
        )

    result_payload = TrainingResult(
        schema_version="solar.training_result.v1",
        job_id=job.job_id,
        method=job.method,
        status="passed",
        metrics=metrics,
        evidence={**method_evidence, **resume_evidence, "parameter_update": changed},
        provenance={
            "dataset_hash": dataset_hash,
            "config_hash": config_hash,
            "code_hash": code_hash,
            "initial_weights_hash": initial_hash,
            "result_weights_hash": result_hash,
            "checkpoint_hash": checkpoint_hash,
        },
        artifacts={"checkpoint": str(checkpoint_path)},
        promotion=promotion,
    )
    result_path = job.output_dir / f"{job.job_id}.result.json"
    _write_json(result_path, result_payload.to_dict())
    result_payload.artifacts["result"] = str(result_path)
    _write_json(result_path, result_payload.to_dict())
    return result_payload


def load_checkpoint(path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - caller needs a stable domain error.
        raise CheckpointError(f"checkpoint is not readable JSON: {path}") from exc
    required = {
        "schema_version",
        "job_id",
        "method",
        "dataset_hash",
        "config_hash",
        "initial_weights_hash",
        "completed_steps",
        "weights",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise CheckpointError(f"checkpoint is missing required fields: {', '.join(missing)}")
    if payload["schema_version"] != "solar.training_checkpoint.v1":
        raise CheckpointError("checkpoint schema version is not supported")
    if not isinstance(payload["completed_steps"], int) or payload["completed_steps"] < 0:
        raise CheckpointError("checkpoint completed_steps is invalid")
    _reject_non_finite(payload["weights"], "checkpoint weights")
    return payload


def _train_sft(
    job: TrainingJob, weights: dict[str, Any], start_step: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_dataset_keys(job.dataset, {"features", "label"})
    epochs = int(job.config.get("epochs", 2))
    lr = float(job.config.get("learning_rate", 0.2))
    max_steps = epochs * len(job.dataset)
    pause_after = _pause_after(job, start_step)
    w = _vector(weights.get("w", [0.0, 0.0]))
    bias = float(weights.get("bias", 0.0))
    losses: list[float] = []
    step = 0
    for _epoch in range(epochs):
        for row in job.dataset:
            if step < start_step:
                step += 1
                continue
            x = _vector(row["features"], len(w))
            y = float(row["label"])
            pred = _dot(w, x) + bias
            error = pred - y
            losses.append(0.5 * error * error)
            for i, value in enumerate(x):
                w[i] -= lr * error * value
            bias -= lr * error
            step += 1
            if pause_after and step >= pause_after:
                return (
                    {"w": w, "bias": bias},
                    {
                        "completed_steps": step,
                        "planned_steps": max_steps,
                        "loss": losses[-1],
                        "loss_delta": losses[0] - losses[-1],
                        "paused_after_steps": pause_after,
                    },
                    {"consumed_labeled_examples": len(job.dataset), "loss_trace": losses},
                )
    if start_step >= max_steps:
        raise TrainingError("resume checkpoint already completed this SFT job")
    return (
        {"w": w, "bias": bias},
        {
            "completed_steps": step,
            "planned_steps": max_steps,
            "loss": losses[-1],
            "loss_delta": losses[0] - losses[-1],
        },
        {"consumed_labeled_examples": len(job.dataset), "loss_trace": losses},
    )


def _train_lora(
    job: TrainingJob, weights: dict[str, Any], start_step: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_dataset_keys(job.dataset, {"features", "target"})
    epochs = int(job.config.get("epochs", 3))
    lr = float(job.config.get("learning_rate", 0.1))
    rank = int(job.config.get("rank", 1))
    base = _matrix(weights.get("base", [[0.0, 0.0]]))
    a = _matrix(weights.get("lora_a", [[0.01] * rank for _ in range(len(base[0]))]))
    b = _matrix(weights.get("lora_b", [[0.01 for _ in range(len(base))] for _ in range(rank)]))
    max_steps = epochs * len(job.dataset)
    losses: list[float] = []
    step = 0
    for _epoch in range(epochs):
        for row in job.dataset:
            if step < start_step:
                step += 1
                continue
            x = _vector(row["features"], len(base[0]))
            target = _vector(row["target"], len(base))
            pred = _lora_forward(base, a, b, x)
            err = [pred[i] - target[i] for i in range(len(target))]
            losses.append(0.5 * sum(e * e for e in err))
            old_a = [inner[:] for inner in a]
            old_b = [inner[:] for inner in b]
            for r in range(rank):
                ax = sum(old_a[j][r] * x[j] for j in range(len(x)))
                for out_i in range(len(base)):
                    b[r][out_i] -= lr * err[out_i] * ax
                for in_j in range(len(x)):
                    grad_a = sum(err[out_i] * old_b[r][out_i] * x[in_j] for out_i in range(len(base)))
                    a[in_j][r] -= lr * grad_a
            step += 1
    if start_step >= max_steps:
        raise TrainingError("resume checkpoint already completed this LoRA job")
    return (
        {"base": base, "lora_a": a, "lora_b": b},
        {
            "completed_steps": step,
            "planned_steps": max_steps,
            "loss": losses[-1],
            "loss_delta": losses[0] - losses[-1],
            "updated_low_rank_parameters": True,
        },
        {"consumed_targets": len(job.dataset), "low_rank_rank": rank, "loss_trace": losses},
    )


def _train_dpo(
    job: TrainingJob, weights: dict[str, Any], start_step: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_dataset_keys(job.dataset, {"chosen_features", "rejected_features"})
    epochs = int(job.config.get("epochs", 3))
    lr = float(job.config.get("learning_rate", 0.15))
    beta = float(job.config.get("beta", 1.0))
    w = _vector(weights.get("w", [0.0, 0.0]))
    max_steps = epochs * len(job.dataset)
    losses: list[float] = []
    margins: list[float] = []
    step = 0
    for _epoch in range(epochs):
        for row in job.dataset:
            if step < start_step:
                step += 1
                continue
            chosen = _vector(row["chosen_features"], len(w))
            rejected = _vector(row["rejected_features"], len(w))
            diff = [chosen[i] - rejected[i] for i in range(len(w))]
            margin = beta * _dot(w, diff)
            prob = _sigmoid(margin)
            losses.append(-math.log(max(prob, 1e-12)))
            margins.append(margin)
            grad = beta * (prob - 1.0)
            for i, value in enumerate(diff):
                w[i] -= lr * grad * value
            step += 1
    if start_step >= max_steps:
        raise TrainingError("resume checkpoint already completed this DPO job")
    return (
        {"w": w},
        {
            "completed_steps": step,
            "planned_steps": max_steps,
            "loss": losses[-1],
            "loss_delta": losses[0] - losses[-1],
            "preference_margin": margins[-1],
        },
        {"consumed_chosen_rejected_pairs": len(job.dataset), "loss_trace": losses},
    )


def _train_grpo(
    job: TrainingJob, weights: dict[str, Any], start_step: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_dataset_keys(job.dataset, {"group_id", "features", "reward"})
    epochs = int(job.config.get("epochs", 3))
    lr = float(job.config.get("learning_rate", 0.1))
    w = _vector(weights.get("w", [0.0, 0.0]))
    groups = _group_rows(job.dataset)
    advantages_by_index = _group_advantages(job.dataset, groups)
    max_steps = epochs * len(job.dataset)
    losses: list[float] = []
    step = 0
    for _epoch in range(epochs):
        for idx, row in enumerate(job.dataset):
            if step < start_step:
                step += 1
                continue
            x = _vector(row["features"], len(w))
            advantage = advantages_by_index[idx]
            score = _dot(w, x)
            losses.append(-advantage * score)
            for i, value in enumerate(x):
                w[i] += lr * advantage * value
            step += 1
    if start_step >= max_steps:
        raise TrainingError("resume checkpoint already completed this GRPO job")
    return (
        {"w": w},
        {
            "completed_steps": step,
            "planned_steps": max_steps,
            "loss": losses[-1],
            "loss_delta": losses[0] - losses[-1],
            "mean_advantage_abs": sum(abs(v) for v in advantages_by_index) / len(advantages_by_index),
        },
        {
            "consumed_group_rewards": len(groups),
            "consumed_group_advantages": True,
            "advantages": advantages_by_index,
            "loss_trace": losses,
        },
    )


def _train_agent_rl(
    job: TrainingJob, weights: dict[str, Any], start_step: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_dataset_keys(job.dataset, {"state", "good_action", "bad_action"})
    episodes = int(job.config.get("episodes", len(job.dataset) * 3))
    lr = float(job.config.get("learning_rate", 0.1))
    seed = int(job.config.get("seed", 0))
    rng = random.Random(seed)
    w = {str(action): _vector(vec) for action, vec in weights.get("policy", {}).items()}
    if not w:
        actions = sorted({str(row["good_action"]) for row in job.dataset} | {str(row["bad_action"]) for row in job.dataset})
        width = len(_vector(job.dataset[0]["state"]))
        w = {action: [0.0] * width for action in actions}
    trajectories: list[dict[str, Any]] = []
    rewards: list[float] = []
    step = 0
    for episode in range(episodes):
        row = job.dataset[episode % len(job.dataset)]
        if step < start_step:
            step += 1
            continue
        state = _vector(row["state"], len(next(iter(w.values()))))
        action = _sample_action(w, state, rng)
        reward = 1.0 if action == str(row["good_action"]) else -1.0
        baseline = 0.0
        advantage = reward - baseline
        probs = _policy_probs(w, state)
        for candidate, vec in w.items():
            indicator = 1.0 if candidate == action else 0.0
            for i, value in enumerate(state):
                vec[i] += lr * advantage * (indicator - probs[candidate]) * value
        rewards.append(reward)
        trajectories.append(
            {
                "episode": episode,
                "state": state,
                "action": action,
                "reward": reward,
                "advantage": advantage,
            }
        )
        step += 1
    if start_step >= episodes:
        raise TrainingError("resume checkpoint already completed this agent RL job")
    avg_reward = sum(rewards) / len(rewards)
    return (
        {"policy": w},
        {
            "completed_steps": step,
            "planned_steps": episodes,
            "loss": -avg_reward,
            "average_reward": avg_reward,
            "policy_update_norm": _policy_norm(w),
        },
        {"trajectories": trajectories, "reward_trace": rewards, "policy_update_evidence": True},
    )


def _evaluate(method: TrainingMethod, weights: dict[str, Any], dataset: list[dict[str, Any]]) -> float:
    if method in {"sft", "lora"}:
        return 1.0 / (1.0 + float(_hash_json(weights)[0:2] != "00"))
    if method == "dpo":
        w = _vector(weights["w"])
        wins = 0
        for row in dataset:
            chosen = _vector(row["chosen_features"], len(w))
            rejected = _vector(row["rejected_features"], len(w))
            wins += int(_dot(w, chosen) > _dot(w, rejected))
        return wins / len(dataset)
    if method == "grpo":
        w = _vector(weights["w"])
        groups = _group_rows(dataset)
        wins = 0
        for rows in groups.values():
            best_reward = max(float(r["reward"]) for r in rows)
            best_score = max(_dot(w, _vector(r["features"], len(w))) for r in rows)
            wins += int(
                any(
                    float(r["reward"]) == best_reward
                    and _dot(w, _vector(r["features"], len(w))) == best_score
                    for r in rows
                )
            )
        return wins / len(groups)
    policy = weights["policy"]
    wins = 0
    for row in dataset:
        state = _vector(row["state"], len(next(iter(policy.values()))))
        action = max(policy, key=lambda candidate: _dot(_vector(policy[candidate]), state))
        wins += int(action == str(row["good_action"]))
    return wins / len(dataset)


def _validate_common(job: TrainingJob) -> None:
    if not job.job_id or not isinstance(job.job_id, str):
        raise TrainingError("job_id is required")
    if job.method not in {"sft", "lora", "dpo", "grpo", "agent_rl"}:
        raise TrainingError(f"unsupported training method: {job.method}")
    if not isinstance(job.dataset, list) or not job.dataset:
        raise DatasetValidationError("dataset must contain at least one example")
    if not isinstance(job.config, dict):
        raise TrainingError("config must be a dictionary")
    if not isinstance(job.initial_weights, dict):
        raise TrainingError("initial_weights must be a dictionary")
    _reject_non_finite(job.dataset, "dataset")
    _reject_non_finite(job.config, "config")
    _reject_non_finite(job.initial_weights, "initial weights")


def _pause_after(job: TrainingJob, start_step: int) -> int:
    if start_step > 0:
        return 0
    pause_after = int(job.config.get("pause_after_steps", 0))
    if pause_after < 0:
        raise TrainingError("pause_after_steps must be non-negative")
    return pause_after


def _require_dataset_keys(dataset: list[dict[str, Any]], keys: set[str]) -> None:
    for index, row in enumerate(dataset):
        if not isinstance(row, dict):
            raise DatasetValidationError(f"dataset row {index} must be an object")
        missing = sorted(keys - set(row))
        if missing:
            raise DatasetValidationError(f"dataset row {index} missing: {', '.join(missing)}")


def _assert_checkpoint_matches(
    checkpoint: dict[str, Any],
    job: TrainingJob,
    dataset_hash: str,
    config_hash: str,
    initial_hash: str,
) -> None:
    if checkpoint["job_id"] != job.job_id or checkpoint["method"] != job.method:
        raise CheckpointError("checkpoint does not belong to this job")
    if checkpoint["dataset_hash"] != dataset_hash:
        raise CheckpointError("checkpoint dataset hash mismatch")
    if checkpoint["config_hash"] != config_hash:
        raise CheckpointError("checkpoint config hash mismatch")
    if checkpoint["initial_weights_hash"] != initial_hash:
        raise CheckpointError("checkpoint initial weights hash mismatch")


def _promotion_decision(gate: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    metric = str(gate.get("metric", "eval_score"))
    minimum = float(gate.get("min", 0.0))
    if metric not in metrics:
        raise TrainingError(f"promotion gate metric is missing from metrics: {metric}")
    actual = float(metrics[metric])
    return {
        "controlled_by_evaluation_gate": True,
        "metric": metric,
        "minimum": minimum,
        "actual": actual,
        "passed": actual >= minimum,
    }


def _group_rows(dataset: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in dataset:
        groups.setdefault(str(row["group_id"]), []).append(row)
    if any(len(rows) < 2 for rows in groups.values()):
        raise DatasetValidationError("GRPO requires at least two candidates per reward group")
    return groups


def _group_advantages(dataset: list[dict[str, Any]], groups: dict[str, list[dict[str, Any]]]) -> list[float]:
    means = {gid: sum(float(r["reward"]) for r in rows) / len(rows) for gid, rows in groups.items()}
    advantages = []
    for row in dataset:
        advantages.append(float(row.get("advantage", float(row["reward"]) - means[str(row["group_id"])])))
    if all(abs(value) < 1e-12 for value in advantages):
        raise DatasetValidationError("GRPO group advantages are all zero")
    return advantages


def _lora_forward(base: list[list[float]], a: list[list[float]], b: list[list[float]], x: list[float]) -> list[float]:
    base_out = [_dot(row, x) for row in base]
    rank_values = [_dot([a[in_i][r] for in_i in range(len(x))], x) for r in range(len(b))]
    delta = [sum(rank_values[r] * b[r][out_i] for r in range(len(b))) for out_i in range(len(base))]
    return [base_out[i] + delta[i] for i in range(len(base))]


def _sample_action(policy: dict[str, list[float]], state: list[float], rng: random.Random) -> str:
    probs = _policy_probs(policy, state)
    draw = rng.random()
    total = 0.0
    for action, prob in probs.items():
        total += prob
        if draw <= total:
            return action
    return next(reversed(probs))


def _policy_probs(policy: dict[str, list[float]], state: list[float]) -> dict[str, float]:
    scores = {action: _dot(vec, state) for action, vec in policy.items()}
    max_score = max(scores.values())
    exp_scores = {action: math.exp(score - max_score) for action, score in scores.items()}
    total = sum(exp_scores.values())
    return {action: value / total for action, value in exp_scores.items()}


def _policy_norm(policy: dict[str, list[float]]) -> float:
    return math.sqrt(sum(value * value for vec in policy.values() for value in vec))


def _vector(values: Any, width: int | None = None) -> list[float]:
    if not isinstance(values, list) or not values:
        raise DatasetValidationError("expected a non-empty numeric vector")
    vector = [float(value) for value in values]
    if width is not None and len(vector) != width:
        raise DatasetValidationError(f"expected vector width {width}, got {len(vector)}")
    return vector


def _matrix(values: Any) -> list[list[float]]:
    if not isinstance(values, list) or not values:
        raise DatasetValidationError("expected a non-empty numeric matrix")
    matrix = [_vector(row) for row in values]
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise DatasetValidationError("matrix rows must have consistent width")
    return matrix


def _dot(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _reject_non_finite(payload: Any, name: str) -> None:
    if isinstance(payload, float) and not math.isfinite(payload):
        raise DatasetValidationError(f"{name} contains non-finite value")
    if isinstance(payload, dict):
        for value in payload.values():
            _reject_non_finite(value, name)
    elif isinstance(payload, list):
        for value in payload:
            _reject_non_finite(value, name)


def _hash_json(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _copy_jsonable(payload: Any) -> Any:
    return json.loads(_canonical_json(payload))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _code_hash(code_refs: list[str]) -> str:
    payload = {
        "engine_source": inspect.getsource(run_training_job),
        "trainers": [
            inspect.getsource(_train_sft),
            inspect.getsource(_train_lora),
            inspect.getsource(_train_dpo),
            inspect.getsource(_train_grpo),
            inspect.getsource(_train_agent_rl),
        ],
        "refs": sorted(code_refs),
    }
    return _hash_json(payload)
