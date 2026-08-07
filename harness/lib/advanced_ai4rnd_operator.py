#!/usr/bin/env python3
"""Executable advanced AI4RnD optimizer/trainer operator contract.

The module intentionally keeps the shipped surface small:

* ``bayesian_optimization`` is a real local optimizer over a bounded numeric
  search grid using a tiny Gaussian-process surrogate and expected improvement.
* ``sft_linear_adapter`` is a CPU-safe supervised adapter run that trains a
  bag-of-words softmax policy and writes a versioned artifact.
* CPU reference optimization and training methods are adapted through this
  same TaskGraph operator instead of being exposed as a second control plane.
* Named routing, retrieval, and evaluator primitives without a product task
  envelope continue to return explicit ``unsupported`` records.

All successful and failed executions can write TaskGraph runtime state and an
append-only evidence ledger without mutating the TaskGraph spec.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import model_registry
except Exception:  # pragma: no cover - only hit outside harness/lib path setup
    model_registry = None  # type: ignore[assignment]

try:
    import task_graph_state_io as task_state
except Exception:  # pragma: no cover
    task_state = None  # type: ignore[assignment]

try:
    from evidence_ledger import EvidenceLedger, build_scheduler_decision
except Exception:  # pragma: no cover
    EvidenceLedger = None  # type: ignore[assignment]
    build_scheduler_decision = None  # type: ignore[assignment]

try:
    from advanced_ai4rnd.optimization import (
        ALGORITHMS as REFERENCE_OPTIMIZER_NAMES,
        run_reference_optimizer,
    )
    from advanced_ai4rnd.training import TrainingJob, run_training_job
except Exception:  # pragma: no cover - fail closed when the optional package is absent
    REFERENCE_OPTIMIZER_NAMES = ()
    run_reference_optimizer = None  # type: ignore[assignment]
    TrainingJob = None  # type: ignore[assignment,misc]
    run_training_job = None  # type: ignore[assignment]

REFERENCE_TRAINER_NAMES = frozenset({"sft", "lora", "dpo", "grpo", "agent_rl"})
SUPPORTED_OPTIMIZERS = frozenset({"bayesian_optimization", *REFERENCE_OPTIMIZER_NAMES})
SUPPORTED_TRAINERS = frozenset({"sft_linear_adapter", *REFERENCE_TRAINER_NAMES})
PHYSICAL_OPERATOR_ID = "autosci-advanced-ai4rnd-worker"

OPTIONAL_ADAPTERS = {
    "gepa": "Use harness/integrations/gepa_optimizer for GEPA artifact optimization.",
    "bandit_routing": "Bandit routing is not shipped in this reference operator.",
    "cost_aware_rl": "Cost-aware RL is not shipped in this reference operator.",
    "reward_modeling": "Reward-model training is not shipped in this reference operator.",
    "judge_calibration": "Judge calibration is not shipped in this reference operator.",
    "self_rag": "Self-RAG training is not shipped in this reference operator.",
    "reranker_training": "Reranker training is not shipped in this reference operator.",
}


class AdvancedOperatorError(RuntimeError):
    """Raised when a supported operator receives invalid input."""


@dataclasses.dataclass(frozen=True)
class OperatorEnvelope:
    operator_kind: str
    algorithm: str
    run_id: str
    sprint_id: str
    node_id: str
    task_id: str
    artifact_root: Path
    inputs: Mapping[str, Any]
    parameters: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OperatorEnvelope":
        kind = str(payload.get("operator_kind") or "").strip().lower()
        algorithm = str(payload.get("algorithm") or "").strip().lower()
        if kind not in {"optimizer", "trainer"}:
            raise AdvancedOperatorError("operator_kind must be optimizer or trainer")
        if not re.fullmatch(r"[a-z0-9_.-]+", algorithm or ""):
            raise AdvancedOperatorError("algorithm must be a non-empty safe identifier")

        run_id = str(payload.get("run_id") or f"adv-{uuid.uuid4().hex[:12]}").strip()
        sprint_id = str(payload.get("sprint_id") or run_id).strip()
        node_id = str(payload.get("node_id") or algorithm).strip()
        task_id = str(payload.get("task_id") or f"{sprint_id}:{node_id}").strip()
        artifact_root = Path(payload.get("artifact_root") or Path.cwd() / "advanced-ai4rnd-runs")
        inputs = payload.get("inputs") or {}
        parameters = payload.get("parameters") or {}
        metadata = payload.get("metadata") or {}
        if not isinstance(inputs, Mapping):
            raise AdvancedOperatorError("inputs must be an object")
        if not isinstance(parameters, Mapping):
            raise AdvancedOperatorError("parameters must be an object")
        if not isinstance(metadata, Mapping):
            raise AdvancedOperatorError("metadata must be an object")
        return cls(
            operator_kind=kind,
            algorithm=algorithm,
            run_id=run_id,
            sprint_id=sprint_id,
            node_id=node_id,
            task_id=task_id,
            artifact_root=artifact_root,
            inputs=inputs,
            parameters=parameters,
            metadata=metadata,
        )


def execute_operator(
    payload: Mapping[str, Any],
    *,
    sprints_dir: Path | None = None,
    evidence_dir: Path | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Execute an optimizer/trainer envelope and record TaskGraph evidence."""
    envelope = OperatorEnvelope.from_mapping(payload)
    try:
        if envelope.operator_kind == "optimizer":
            result = _execute_optimizer(envelope)
        else:
            result = _execute_trainer(envelope, registry_path=registry_path)
    except Exception as exc:
        result = _failure_result(envelope, exc)

    _record_task_graph_state(envelope, result, sprints_dir=sprints_dir)
    _record_evidence(envelope, result, evidence_dir=evidence_dir)
    return result


def _execute_optimizer(envelope: OperatorEnvelope) -> dict[str, Any]:
    if envelope.algorithm not in SUPPORTED_OPTIMIZERS:
        return _unsupported_result(envelope)
    if envelope.algorithm == "bayesian_optimization":
        return _run_bayesian_optimization(envelope)
    return _run_reference_optimizer(envelope)


def _execute_trainer(
    envelope: OperatorEnvelope,
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    if envelope.algorithm not in SUPPORTED_TRAINERS:
        return _unsupported_result(envelope)
    if envelope.algorithm == "sft_linear_adapter":
        return _run_sft_linear_adapter(envelope, registry_path=registry_path)
    return _run_reference_trainer(envelope)


def _run_reference_optimizer(envelope: OperatorEnvelope) -> dict[str, Any]:
    if run_reference_optimizer is None:
        raise AdvancedOperatorError("reference optimizer package is unavailable")
    resume_from = envelope.parameters.get("resume_from") or envelope.inputs.get("resume_from")
    raw = run_reference_optimizer(
        envelope.algorithm,
        envelope.inputs.get("problem") or envelope.inputs,
        run_dir=envelope.artifact_root / envelope.run_id,
        seed=int(envelope.parameters.get("seed", 0)),
        run_id=envelope.run_id,
        max_steps=envelope.parameters.get("max_steps"),
        resume_from=resume_from,
        interrupt_after_steps=envelope.parameters.get("interrupt_after_steps"),
        fail_once_steps=envelope.parameters.get("fail_once_steps"),
    )
    passed = raw.get("status") == "passed"
    result_path = Path(str((raw.get("artifacts") or {}).get("result") or ""))
    output_hash = _hash_file(result_path) if result_path.is_file() else None
    metric_names = (
        "baseline_accuracy", "best_accuracy", "baseline_objective",
        "best_objective", "objective_delta", "steps_completed",
    )
    return {
        "schema_version": "solar.advanced_ai4rnd.operator_result.v1",
        "status": "passed" if passed else str(raw.get("status") or "failed"),
        "task_graph_status": "passed" if passed else "failed",
        "result_state": "FULLY_IMPLEMENTED" if passed else "FAIL",
        "capability_scope": "cpu_reference",
        "operator_kind": envelope.operator_kind,
        "algorithm": envelope.algorithm,
        "run_id": envelope.run_id,
        "sprint_id": envelope.sprint_id,
        "node_id": envelope.node_id,
        "metrics": {name: raw[name] for name in metric_names if name in raw},
        "artifacts": dict(raw.get("artifacts") or {}),
        "output_hash": output_hash,
        "reference_result": raw,
    }


def _run_reference_trainer(envelope: OperatorEnvelope) -> dict[str, Any]:
    if TrainingJob is None or run_training_job is None:
        raise AdvancedOperatorError("reference training package is unavailable")
    dataset = envelope.inputs.get("dataset")
    config = envelope.inputs.get("config") or envelope.parameters.get("config") or envelope.parameters
    initial_weights = envelope.inputs.get("initial_weights")
    if not isinstance(dataset, list):
        raise AdvancedOperatorError("inputs.dataset must be a list")
    if not isinstance(config, Mapping):
        raise AdvancedOperatorError("inputs.config or parameters must be an object")
    if not isinstance(initial_weights, Mapping):
        raise AdvancedOperatorError("inputs.initial_weights must be an object")
    resume_value = envelope.inputs.get("resume_from") or envelope.parameters.get("resume_from")
    promotion_gate = envelope.inputs.get("promotion_gate") or envelope.parameters.get("promotion_gate")
    code_refs = envelope.inputs.get("code_refs") or []
    if not isinstance(code_refs, list):
        raise AdvancedOperatorError("inputs.code_refs must be a list")
    job = TrainingJob(
        job_id=envelope.run_id,
        method=envelope.algorithm,
        dataset=dataset,
        config=dict(config),
        initial_weights=dict(initial_weights),
        output_dir=envelope.artifact_root / envelope.run_id,
        code_refs=[str(item) for item in code_refs],
        resume_from=Path(str(resume_value)) if resume_value else None,
        promotion_gate=dict(promotion_gate or {"metric": "eval_score", "min": 0.0}),
    )
    raw = run_training_job(job).to_dict()
    artifacts = dict(raw.get("artifacts") or {})
    return {
        "schema_version": "solar.advanced_ai4rnd.operator_result.v1",
        "status": "passed",
        "task_graph_status": "passed",
        "result_state": "FULLY_IMPLEMENTED",
        "capability_scope": "cpu_reference",
        "operator_kind": envelope.operator_kind,
        "algorithm": envelope.algorithm,
        "run_id": envelope.run_id,
        "sprint_id": envelope.sprint_id,
        "node_id": envelope.node_id,
        "metrics": dict(raw.get("metrics") or {}),
        "artifacts": artifacts,
        "output_hash": (raw.get("provenance") or {}).get("result_weights_hash"),
        "training_evidence": dict(raw.get("evidence") or {}),
        "promotion": dict(raw.get("promotion") or {}),
        "provenance": dict(raw.get("provenance") or {}),
    }


def _unsupported_result(envelope: OperatorEnvelope) -> dict[str, Any]:
    reason = OPTIONAL_ADAPTERS.get(envelope.algorithm, "Algorithm is not supported by this operator.")
    return {
        "schema_version": "solar.advanced_ai4rnd.operator_result.v1",
        "status": "unsupported",
        "task_graph_status": "failed",
        "result_state": "STILL_NOT_AVAILABLE",
        "operator_kind": envelope.operator_kind,
        "algorithm": envelope.algorithm,
        "run_id": envelope.run_id,
        "sprint_id": envelope.sprint_id,
        "node_id": envelope.node_id,
        "reason": reason,
        "metrics": {},
        "artifacts": {},
        "output_hash": None,
    }


def _failure_result(envelope: OperatorEnvelope, exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": "solar.advanced_ai4rnd.operator_result.v1",
        "status": "failed",
        "task_graph_status": "failed",
        "result_state": "FAIL",
        "operator_kind": envelope.operator_kind,
        "algorithm": envelope.algorithm,
        "run_id": envelope.run_id,
        "sprint_id": envelope.sprint_id,
        "node_id": envelope.node_id,
        "reason": f"{type(exc).__name__}: {exc}",
        "metrics": {},
        "artifacts": {},
        "output_hash": None,
    }


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_bayesian_optimization(envelope: OperatorEnvelope) -> dict[str, Any]:
    grid = _coerce_grid(envelope.inputs.get("search_space"))
    if len(grid) < 2:
        raise AdvancedOperatorError("search_space must contain at least two numeric points")
    rounds = int(envelope.parameters.get("rounds", min(5, len(grid))))
    rounds = max(1, min(rounds, len(grid)))
    objective = envelope.inputs.get("objective")
    if not isinstance(objective, Mapping):
        raise AdvancedOperatorError("inputs.objective must be an object")

    initial_points = _coerce_grid(envelope.parameters.get("initial_points") or [grid[0]])
    observations: list[dict[str, Any]] = []
    evaluated: set[float] = set()
    for x in initial_points:
        if x in grid and x not in evaluated and len(observations) < rounds:
            observations.append(_evaluate_objective(objective, x, iteration=len(observations)))
            evaluated.add(x)

    while len(observations) < rounds:
        x_next = _select_expected_improvement(grid, observations, evaluated)
        observations.append(_evaluate_objective(objective, x_next, iteration=len(observations)))
        evaluated.add(x_next)

    best = max(observations, key=lambda item: float(item["score"]))
    first = observations[0]
    metrics = {
        "rounds_completed": len(observations),
        "initial_score": float(first["score"]),
        "best_score": float(best["score"]),
        "score_delta": float(best["score"]) - float(first["score"]),
        "best_x": float(best["x"]),
        "unique_points_evaluated": len({float(item["x"]) for item in observations}),
    }
    run_dir = envelope.artifact_root / envelope.run_id
    artifact_graph = {
        "schema_version": "solar.advanced_ai4rnd.artifact_graph.v1",
        "created_at": _now(),
        "run_id": envelope.run_id,
        "nodes": {
            "objective": {
                "id": "objective",
                "kind": "objective",
                "hash": _sha256_text(_canonical_json(objective)),
            },
            "policy_candidate": {
                "id": f"policy.bayesian_optimization.{envelope.run_id}",
                "kind": "routing_policy_candidate",
                "algorithm": envelope.algorithm,
                "best_x": float(best["x"]),
                "best_score": float(best["score"]),
            },
        },
        "edges": [
            {"from": "objective", "to": "policy_candidate", "relation": "optimized_into"}
        ],
        "metrics": metrics,
    }
    result_payload = {
        "schema_version": "solar.advanced_ai4rnd.bayesian_optimization.v1",
        "algorithm": envelope.algorithm,
        "parameters": dict(envelope.parameters),
        "search_space": grid,
        "history": observations,
        "best": best,
        "metrics": metrics,
        "artifact_graph": artifact_graph,
    }
    result_path = run_dir / "optimizer_result.json"
    graph_path = run_dir / "artifact_graph.json"
    _atomic_write_json(result_path, result_payload)
    _atomic_write_json(graph_path, artifact_graph)
    output_hash = _hash_file(result_path)
    return {
        "schema_version": "solar.advanced_ai4rnd.operator_result.v1",
        "status": "passed",
        "task_graph_status": "passed",
        "result_state": "FULLY_IMPLEMENTED",
        "operator_kind": envelope.operator_kind,
        "algorithm": envelope.algorithm,
        "run_id": envelope.run_id,
        "sprint_id": envelope.sprint_id,
        "node_id": envelope.node_id,
        "metrics": metrics,
        "artifacts": {
            "result": str(result_path),
            "artifact_graph": str(graph_path),
        },
        "output_hash": output_hash,
        "best": best,
    }


def _coerce_grid(value: Any) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AdvancedOperatorError("search space must be a list of numeric values")
    out = sorted({float(item) for item in value})
    return out


def _evaluate_objective(objective: Mapping[str, Any], x: float, *, iteration: int) -> dict[str, Any]:
    kind = str(objective.get("type") or "").strip().lower()
    if kind != "quadratic":
        raise AdvancedOperatorError("only local quadratic objectives are supported")
    target = float(objective.get("target", 0.0))
    offset = float(objective.get("offset", 1.0))
    scale = float(objective.get("scale", 1.0))
    score = offset - scale * ((x - target) ** 2)
    return {
        "iteration": iteration,
        "x": float(x),
        "score": float(score),
        "objective_hash": _sha256_text(_canonical_json(objective)),
    }


def _select_expected_improvement(
    grid: Sequence[float],
    observations: Sequence[Mapping[str, Any]],
    evaluated: set[float],
) -> float:
    remaining = [x for x in grid if x not in evaluated]
    if not observations:
        return remaining[0]
    xs = [float(item["x"]) for item in observations]
    ys = [float(item["score"]) for item in observations]
    best_y = max(ys)
    best_item: tuple[float, float] | None = None
    for x in remaining:
        mean, var = _gp_predict(xs, ys, x)
        sigma = math.sqrt(max(var, 1e-12))
        z = (mean - best_y) / sigma
        ei = (mean - best_y) * _normal_cdf(z) + sigma * _normal_pdf(z)
        item = (ei, -abs(x - xs[-1]))
        if best_item is None or item > best_item:
            best_item = item
            chosen = x
    return chosen  # type: ignore[possibly-undefined]


def _gp_predict(xs: Sequence[float], ys: Sequence[float], x_star: float) -> tuple[float, float]:
    length_scale = max((max(xs) - min(xs)) if len(xs) > 1 else 1.0, 1.0) / 2.0
    n = len(xs)
    kernel = [
        [_rbf(xs[i], xs[j], length_scale) + (1e-6 if i == j else 0.0) for j in range(n)]
        for i in range(n)
    ]
    alpha = _solve(kernel, list(ys))
    k_star = [_rbf(x_star, xi, length_scale) for xi in xs]
    mean = sum(k * a for k, a in zip(k_star, alpha))
    v = _solve(kernel, k_star)
    var = max(1e-9, 1.0 - sum(k * vi for k, vi in zip(k_star, v)))
    return float(mean), float(var)


def _rbf(a: float, b: float, length_scale: float) -> float:
    return math.exp(-((a - b) ** 2) / (2 * length_scale * length_scale))


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    aug = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            aug[pivot][col] = 1e-12
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        aug[col] = [v / div for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [v - factor * aug[col][i] for i, v in enumerate(aug[row])]
    return [aug[i][-1] for i in range(n)]


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _run_sft_linear_adapter(
    envelope: OperatorEnvelope,
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    train_rows = _validate_dataset(envelope.inputs.get("train_dataset"), "train_dataset")
    holdout_rows = _validate_dataset(envelope.inputs.get("holdout_dataset"), "holdout_dataset")
    license_id = str(envelope.inputs.get("dataset_license") or "").strip()
    if license_id not in {"CC0", "MIT", "Apache-2.0", "internal-test"}:
        raise AdvancedOperatorError("dataset_license must be CC0, MIT, Apache-2.0, or internal-test")

    base_model_alias = str(envelope.inputs.get("base_model_alias") or "thunderomlx").strip()
    base_model_id = _resolve_base_model(base_model_alias, registry_path=registry_path)
    epochs = max(1, min(int(envelope.parameters.get("epochs", 20)), 200))
    learning_rate = float(envelope.parameters.get("learning_rate", 0.2))
    if learning_rate <= 0:
        raise AdvancedOperatorError("learning_rate must be positive")

    vocab = _build_vocab(row["text"] for row in train_rows)
    labels = sorted({row["label"] for row in train_rows})
    if len(labels) < 2:
        raise AdvancedOperatorError("train_dataset must contain at least two labels")

    baseline_label = Counter(row["label"] for row in train_rows).most_common(1)[0][0]
    baseline_holdout = _accuracy_constant(holdout_rows, baseline_label)
    weights = {label: defaultdict(float) for label in labels}
    bias = {label: 0.0 for label in labels}
    losses: list[float] = []
    for _ in range(epochs):
        total_loss = 0.0
        for row in train_rows:
            features = _features(row["text"], vocab)
            probs = _predict_proba(features, labels, weights, bias)
            total_loss += -math.log(max(probs[row["label"]], 1e-12))
            for label in labels:
                grad = probs[label] - (1.0 if label == row["label"] else 0.0)
                bias[label] -= learning_rate * grad
                for idx, value in features.items():
                    weights[label][idx] -= learning_rate * grad * value
        losses.append(total_loss / len(train_rows))

    train_acc = _accuracy(train_rows, vocab, labels, weights, bias)
    holdout_acc = _accuracy(holdout_rows, vocab, labels, weights, bias)
    dataset_payload = {
        "license": license_id,
        "train_dataset": train_rows,
        "holdout_dataset": holdout_rows,
    }
    dataset_hash = _sha256_text(_canonical_json(dataset_payload))
    version_id = f"{base_model_id}.sft-linear.{dataset_hash[:8]}.{envelope.run_id}"
    adapter = {
        "schema_version": "solar.sft_linear_adapter.v1",
        "version_id": version_id,
        "base_model_id": base_model_id,
        "labels": labels,
        "vocab": vocab,
        "weights": {label: dict(weights[label]) for label in labels},
        "bias": bias,
        "created_at": _now(),
    }
    metrics = {
        "epochs": epochs,
        "train_examples": len(train_rows),
        "holdout_examples": len(holdout_rows),
        "train_accuracy": train_acc,
        "holdout_accuracy": holdout_acc,
        "baseline_holdout_accuracy": baseline_holdout,
        "holdout_delta": holdout_acc - baseline_holdout,
        "final_loss": losses[-1],
    }
    run_dir = envelope.artifact_root / envelope.run_id
    model_dir = run_dir / "model_versions" / version_id
    adapter_path = model_dir / "adapter.json"
    manifest_path = model_dir / "manifest.json"
    graph_path = run_dir / "artifact_graph.json"
    _atomic_write_json(adapter_path, adapter)
    adapter_hash = _hash_file(adapter_path)
    manifest = {
        "schema_version": "solar.advanced_ai4rnd.training_manifest.v1",
        "run_id": envelope.run_id,
        "algorithm": envelope.algorithm,
        "version_id": version_id,
        "base_model_id": base_model_id,
        "dataset_hash": dataset_hash,
        "adapter_hash": adapter_hash,
        "parameters": dict(envelope.parameters),
        "metrics": metrics,
        "lineage": [
            {"from": f"dataset.{dataset_hash}", "to": version_id, "relation": "trained_adapter"},
            {"from": base_model_id, "to": version_id, "relation": "adapted_from"},
        ],
    }
    _atomic_write_json(manifest_path, manifest)
    artifact_graph = {
        "schema_version": "solar.advanced_ai4rnd.artifact_graph.v1",
        "created_at": _now(),
        "run_id": envelope.run_id,
        "nodes": {
            f"dataset.{dataset_hash}": {
                "kind": "dataset",
                "hash": dataset_hash,
                "license": license_id,
                "train_examples": len(train_rows),
                "holdout_examples": len(holdout_rows),
            },
            base_model_id: {
                "kind": "base_model",
                "source": "harness/config/model-registry.json",
            },
            version_id: {
                "kind": "model_version",
                "algorithm": envelope.algorithm,
                "artifact_hash": adapter_hash,
                "manifest": str(manifest_path),
            },
        },
        "edges": manifest["lineage"],
        "metrics": metrics,
    }
    _atomic_write_json(graph_path, artifact_graph)
    return {
        "schema_version": "solar.advanced_ai4rnd.operator_result.v1",
        "status": "passed",
        "task_graph_status": "passed",
        "result_state": "FULLY_IMPLEMENTED",
        "operator_kind": envelope.operator_kind,
        "algorithm": envelope.algorithm,
        "run_id": envelope.run_id,
        "sprint_id": envelope.sprint_id,
        "node_id": envelope.node_id,
        "metrics": metrics,
        "artifacts": {
            "adapter": str(adapter_path),
            "manifest": str(manifest_path),
            "artifact_graph": str(graph_path),
        },
        "output_hash": adapter_hash,
        "model_version_id": version_id,
        "dataset_hash": dataset_hash,
        "base_model_id": base_model_id,
    }


def _resolve_base_model(alias: str, *, registry_path: Path | None = None) -> str:
    if model_registry is None:
        raise AdvancedOperatorError("model_registry is unavailable")
    registry = model_registry.load_registry(registry_path or model_registry.REGISTRY_PATH)
    try:
        return str(model_registry.normalize(registry, alias))
    except SystemExit as exc:
        raise AdvancedOperatorError(str(exc)) from exc


def _validate_dataset(value: Any, key: str) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AdvancedOperatorError(f"{key} must be a list of examples")
    rows: list[dict[str, str]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise AdvancedOperatorError(f"{key}[{idx}] must be an object")
        text = str(item.get("text") or "").strip()
        label = str(item.get("label") or "").strip()
        if not text or not label:
            raise AdvancedOperatorError(f"{key}[{idx}] must include text and label")
        rows.append({"text": text, "label": label})
    if not rows:
        raise AdvancedOperatorError(f"{key} must not be empty")
    return rows


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _build_vocab(texts: Iterable[str]) -> dict[str, int]:
    tokens = sorted({token for text in texts for token in _tokenize(text)})
    if not tokens:
        raise AdvancedOperatorError("dataset text must contain at least one token")
    return {token: idx for idx, token in enumerate(tokens)}


def _features(text: str, vocab: Mapping[str, int]) -> dict[int, float]:
    counts = Counter(token for token in _tokenize(text) if token in vocab)
    total = sum(counts.values()) or 1
    return {int(vocab[token]): count / total for token, count in counts.items()}


def _predict_proba(
    features: Mapping[int, float],
    labels: Sequence[str],
    weights: Mapping[str, Mapping[int, float]],
    bias: Mapping[str, float],
) -> dict[str, float]:
    logits = {}
    for label in labels:
        logits[label] = float(bias[label]) + sum(weights[label].get(idx, 0.0) * value for idx, value in features.items())
    max_logit = max(logits.values())
    exp = {label: math.exp(value - max_logit) for label, value in logits.items()}
    total = sum(exp.values())
    return {label: value / total for label, value in exp.items()}


def _predict_label(
    text: str,
    vocab: Mapping[str, int],
    labels: Sequence[str],
    weights: Mapping[str, Mapping[int, float]],
    bias: Mapping[str, float],
) -> str:
    probs = _predict_proba(_features(text, vocab), labels, weights, bias)
    return max(labels, key=lambda label: (probs[label], label))


def _accuracy(
    rows: Sequence[Mapping[str, str]],
    vocab: Mapping[str, int],
    labels: Sequence[str],
    weights: Mapping[str, Mapping[int, float]],
    bias: Mapping[str, float],
) -> float:
    correct = 0
    for row in rows:
        if _predict_label(row["text"], vocab, labels, weights, bias) == row["label"]:
            correct += 1
    return correct / len(rows)


def _accuracy_constant(rows: Sequence[Mapping[str, str]], label: str) -> float:
    return sum(1 for row in rows if row["label"] == label) / len(rows)


def _record_task_graph_state(
    envelope: OperatorEnvelope,
    result: Mapping[str, Any],
    *,
    sprints_dir: Path | None,
) -> None:
    if task_state is None:
        return
    try:
        state = task_state.load_state(envelope.sprint_id, sprints_dir) or task_state.make_empty_state(envelope.sprint_id)
        note = str(result.get("reason") or result.get("status") or "")
        task_state.set_node_result(
            state,
            envelope.node_id,
            str(result.get("task_graph_status") or "failed"),
            note=note,
            assigned_to=PHYSICAL_OPERATOR_ID,
            dispatch_id=envelope.task_id,
        )
        node_result = state["node_results"][envelope.node_id]
        node_result["advanced_ai4rnd"] = {
            "operator_kind": envelope.operator_kind,
            "algorithm": envelope.algorithm,
            "status": result.get("status"),
            "result_state": result.get("result_state"),
            "inputs_hash": _sha256_text(_canonical_json(envelope.inputs)),
            "parameters": dict(envelope.parameters),
            "metrics": dict(result.get("metrics") or {}),
            "artifacts": dict(result.get("artifacts") or {}),
            "output_hash": result.get("output_hash"),
        }
        task_state.record_event(
            state,
            "advanced_ai4rnd_operator_completed",
            PHYSICAL_OPERATOR_ID,
            f"{envelope.algorithm}:{result.get('status')}",
        )
        task_state.save_state(envelope.sprint_id, state, sprints_dir)
    except Exception:
        return


def _record_evidence(
    envelope: OperatorEnvelope,
    result: Mapping[str, Any],
    *,
    evidence_dir: Path | None,
) -> None:
    if EvidenceLedger is None or build_scheduler_decision is None:
        return
    try:
        ledger = EvidenceLedger(ledger_dir=evidence_dir) if evidence_dir else EvidenceLedger()
        decision = build_scheduler_decision(
            selected_actor=PHYSICAL_OPERATOR_ID,
            logical_operator=f"{envelope.operator_kind}:{envelope.algorithm}",
            score_factors={
                "supported": 1.0 if result.get("status") == "passed" else 0.0,
                "output_hash_present": 1.0 if result.get("output_hash") else 0.0,
            },
            penalties={} if result.get("status") == "passed" else {"not_executable": 1.0},
            rejected=[],
        )
        ledger.write_run_entry(
            task_id=envelope.task_id,
            sprint_id=envelope.sprint_id,
            node_id=envelope.node_id,
            actor_id=PHYSICAL_OPERATOR_ID,
            logical_operator=f"{envelope.operator_kind}:{envelope.algorithm}",
            scheduler_decision=decision,
            dag_ref=f"{envelope.sprint_id}.task_graph.json",
            verification_results={
                "status": result.get("status"),
                "result_state": result.get("result_state"),
                "metrics": result.get("metrics") or {},
                "output_hash": result.get("output_hash"),
                "artifacts": result.get("artifacts") or {},
            },
        )
    except Exception:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an advanced AI4RnD optimizer/trainer envelope")
    parser.add_argument("--envelope", required=True, help="Path to envelope JSON, or - for stdin")
    parser.add_argument("--sprints-dir", help="Optional TaskGraph state directory")
    parser.add_argument("--evidence-dir", help="Optional evidence ledger directory")
    parser.add_argument("--registry", help="Optional model registry path")
    args = parser.parse_args(argv)
    payload = (
        json.load(sys.stdin)
        if args.envelope == "-"
        else json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    )
    result = execute_operator(
        payload,
        sprints_dir=Path(args.sprints_dir) if args.sprints_dir else None,
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
        registry_path=Path(args.registry) if args.registry else None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
