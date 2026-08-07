"""Unified optimizer interface and CPU reference execution engine."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .metadata import CAPABILITY_METADATA

ALGORITHMS = tuple(CAPABILITY_METADATA)


class OptimizationError(RuntimeError):
    """Raised when an optimizer request is invalid or cannot be resumed."""


@dataclass(frozen=True)
class OptimizationProblem:
    dataset: list[dict[str, str]]
    labels: list[str]
    initial_candidate: dict[str, Any]
    max_steps: int
    objective_name: str
    complexity_weight: float
    success_min_delta: float


def run_reference_optimizer(
    algorithm: str,
    problem: Mapping[str, Any],
    *,
    run_dir: str | Path,
    seed: int = 0,
    run_id: str | None = None,
    max_steps: int | None = None,
    resume_from: str | Path | None = None,
    interrupt_after_steps: int | None = None,
    fail_once_steps: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Run one reference optimizer with observable trace and checkpoints."""
    name = _normalize_algorithm(algorithm)
    optimizer = _build_optimizer(name)
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)

    if resume_from is None:
        parsed = _parse_problem(problem, max_steps=max_steps)
        state = _new_state(name, parsed, seed=seed, run_id=run_id)
        _append_trace(
            state,
            "input",
            {
                "dataset_hash": _hash_data(parsed.dataset),
                "labels": parsed.labels,
                "objective": parsed.objective_name,
                "max_steps": parsed.max_steps,
            },
        )
        state["current_evaluation"] = evaluate_candidate(parsed, state["current_candidate"])
        state["baseline_evaluation"] = copy.deepcopy(state["current_evaluation"])
        state["best_evaluation"] = copy.deepcopy(state["current_evaluation"])
        _append_trace(state, "evaluation", {"phase": "baseline", **state["current_evaluation"]})
    else:
        checkpoint = load_checkpoint(resume_from)
        if checkpoint["algorithm"] != name:
            raise OptimizationError(
                f"checkpoint algorithm {checkpoint['algorithm']!r} does not match requested {name!r}"
            )
        parsed = _parse_problem(checkpoint["problem"], max_steps=max_steps)
        state = checkpoint
        state["resumed_from"] = str(resume_from)
        _append_trace(state, "resume", {"checkpoint": str(resume_from), "step": state["step"]})

    fail_steps = {int(step) for step in (fail_once_steps or [])}
    while state["step"] < parsed.max_steps:
        if _is_solved(parsed, state):
            break
        next_step = int(state["step"]) + 1
        seen = set(state.setdefault("failed_once_steps_seen", []))
        if next_step in fail_steps and next_step not in seen:
            seen.add(next_step)
            state["failed_once_steps_seen"] = sorted(seen)
            _append_trace(
                state,
                "recoverable_failure",
                {"step": next_step, "reason": "requested fail-once injection before candidate update"},
            )
            checkpoint_path = _write_checkpoint(root, state)
            return _result(parsed, state, root, status="recoverable_failed", checkpoint_path=checkpoint_path)

        previous = copy.deepcopy(state["current_candidate"])
        candidate, update = optimizer.propose(parsed, state)
        candidate["generation"] = next_step
        candidate["candidate_id"] = _candidate_id(name, candidate, next_step)
        evaluation = evaluate_candidate(parsed, candidate)

        state["step"] = next_step
        state["current_candidate"] = candidate
        state["current_evaluation"] = evaluation
        _append_trace(state, "candidate", {"step": next_step, "candidate": _public_candidate(candidate)})
        _append_trace(
            state,
            "update",
            {
                "step": next_step,
                "mechanism": update["mechanism"],
                "details": update,
                "changed": _candidate_changed(previous, candidate),
            },
        )
        _append_trace(state, "evaluation", {"step": next_step, **evaluation})
        if evaluation["objective"] > state["best_evaluation"]["objective"]:
            state["best_candidate"] = copy.deepcopy(candidate)
            state["best_evaluation"] = copy.deepcopy(evaluation)
            _append_trace(
                state,
                "selection",
                {
                    "step": next_step,
                    "selected": candidate["candidate_id"],
                    "objective": evaluation["objective"],
                },
            )

        checkpoint_path = _write_checkpoint(root, state)
        if interrupt_after_steps is not None and state["step"] >= int(interrupt_after_steps):
            _append_trace(state, "termination", {"reason": "interrupted", "step": state["step"]})
            checkpoint_path = _write_checkpoint(root, state)
            return _result(parsed, state, root, status="interrupted", checkpoint_path=checkpoint_path)

    reason = "solved" if _is_solved(parsed, state) else "budget_exhausted"
    _append_trace(state, "termination", {"reason": reason, "step": state["step"]})
    checkpoint_path = _write_checkpoint(root, state)
    delta = state["best_evaluation"]["objective"] - state["baseline_evaluation"]["objective"]
    status = "passed" if delta > parsed.success_min_delta else "completed_no_improvement"
    return _result(parsed, state, root, status=status, checkpoint_path=checkpoint_path)


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OptimizationError(f"checkpoint not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OptimizationError(f"checkpoint is not valid JSON: {path}") from exc


def dependency_gate(algorithm: str, *, mode: str = "reference") -> dict[str, Any]:
    """Return an explicit dependency gate for reference or production mode."""
    name = _normalize_algorithm(algorithm)
    meta = CAPABILITY_METADATA[name]
    dependency = meta.get("optional_dependency")
    if mode == "reference":
        return {
            "algorithm": name,
            "mode": mode,
            "gate": "open",
            "reason": "reference path uses only the Python standard library",
            "optional_dependency": dependency,
        }
    if mode != "production":
        raise OptimizationError("mode must be 'reference' or 'production'")
    if dependency is None:
        return {
            "algorithm": name,
            "mode": mode,
            "gate": "open",
            "reason": "no third-party package is declared for production handoff",
            "optional_dependency": None,
        }
    available = importlib.util.find_spec(str(dependency)) is not None
    return {
        "algorithm": name,
        "mode": mode,
        "gate": "open" if available else "blocked",
        "reason": (
            f"optional dependency {dependency!r} is importable"
            if available
            else f"optional dependency {dependency!r} is not installed"
        ),
        "optional_dependency": dependency,
    }


def evaluate_candidate(problem: OptimizationProblem, candidate: Mapping[str, Any]) -> dict[str, Any]:
    rules = _compiled_rules(candidate)
    labels = problem.labels
    predictions: list[dict[str, Any]] = []
    correct = 0
    for index, row in enumerate(problem.dataset):
        tokens = _apply_graph(_tokens(row["text"]), candidate.get("graph", []))
        scores = {label: float(candidate.get("bias", {}).get(label, 0.0)) for label in labels}
        for label in labels:
            for token, weight in rules.get(label, {}).items():
                if token in tokens:
                    scores[label] += float(weight)
        predicted = max(labels, key=lambda label: (scores[label], -labels.index(label)))
        is_correct = predicted == row["label"]
        correct += 1 if is_correct else 0
        predictions.append(
            {
                "index": index,
                "text_hash": _hash_text(row["text"])[:12],
                "label": row["label"],
                "predicted": predicted,
                "correct": is_correct,
                "scores": scores,
                "tokens": sorted(tokens),
            }
        )
    accuracy = correct / len(problem.dataset)
    complexity = _complexity(candidate)
    objective = accuracy - problem.complexity_weight * complexity
    return {
        "objective": round(objective, 6),
        "accuracy": round(accuracy, 6),
        "complexity": complexity,
        "complexity_penalty": round(problem.complexity_weight * complexity, 6),
        "predictions": predictions,
    }


def failed_predictions(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [item for item in evaluation["predictions"] if not item["correct"]]


def best_discriminating_token(
    problem: OptimizationProblem,
    *,
    label: str,
    text: str,
    avoid_labels: Sequence[str] = (),
) -> str:
    tokens = _tokens(text)
    label_docs = [_tokens(row["text"]) for row in problem.dataset if row["label"] == label]
    other_docs = [
        _tokens(row["text"])
        for row in problem.dataset
        if row["label"] != label or row["label"] in set(avoid_labels)
    ]
    scored: list[tuple[int, int, str]] = []
    for token in tokens:
        if len(token) < 3:
            continue
        positive = sum(1 for doc in label_docs if token in doc)
        negative = sum(1 for doc in other_docs if token in doc)
        scored.append((positive - negative, positive, token))
    if not scored:
        raise OptimizationError(f"no usable token found for label {label!r}")
    scored.sort(reverse=True)
    return scored[0][2]


def add_keyword(candidate: dict[str, Any], label: str, token: str, weight: float = 1.0) -> None:
    rules = candidate.setdefault("keyword_rules", {})
    label_rules = rules.setdefault(label, {})
    label_rules[token] = round(float(label_rules.get(token, 0.0)) + weight, 6)


def clone_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(candidate))


class ReferenceOptimizer:
    mechanism = "reference"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        raise NotImplementedError

    def failed_or_hardest(self, problem: OptimizationProblem, state: Mapping[str, Any]) -> dict[str, Any]:
        failures = failed_predictions(state["current_evaluation"])
        if failures:
            return failures[0]
        predictions = state["current_evaluation"]["predictions"]
        return min(predictions, key=lambda item: item["scores"][item["label"]])


def _parse_problem(payload: Mapping[str, Any], *, max_steps: int | None) -> OptimizationProblem:
    if not isinstance(payload, Mapping):
        raise OptimizationError("problem must be an object")
    raw_dataset = payload.get("dataset")
    if not isinstance(raw_dataset, list) or len(raw_dataset) < 2:
        raise OptimizationError("problem.dataset must contain at least two examples")
    dataset: list[dict[str, str]] = []
    for index, row in enumerate(raw_dataset):
        if not isinstance(row, Mapping):
            raise OptimizationError(f"dataset row {index} must be an object")
        text = str(row.get("text") or "").strip()
        label = str(row.get("label") or "").strip()
        if not text or not label:
            raise OptimizationError(f"dataset row {index} requires non-empty text and label")
        dataset.append({"text": text, "label": label})
    labels = sorted({row["label"] for row in dataset})
    if len(labels) < 2:
        raise OptimizationError("dataset must contain at least two labels")
    counts = {label: sum(1 for row in dataset if row["label"] == label) for label in labels}
    if min(counts.values()) < 1:
        raise OptimizationError("each label must have at least one example")

    steps = int(max_steps if max_steps is not None else payload.get("max_steps", 4))
    if steps < 1:
        raise OptimizationError("max_steps must be at least 1")
    candidate = clone_candidate(payload.get("initial_candidate") or _default_candidate(labels))
    candidate.setdefault("keyword_rules", {})
    candidate.setdefault("bias", {labels[0]: 0.1})
    candidate.setdefault("graph", [])
    candidate.setdefault("policy", {})
    candidate.setdefault("demos", [])
    candidate.setdefault("agents", [])
    return OptimizationProblem(
        dataset=dataset,
        labels=labels,
        initial_candidate=candidate,
        max_steps=steps,
        objective_name=str(payload.get("objective") or "accuracy_minus_complexity"),
        complexity_weight=float(payload.get("complexity_weight", 0.002)),
        success_min_delta=float(payload.get("success_min_delta", 0.0)),
    )


def _default_candidate(labels: Sequence[str]) -> dict[str, Any]:
    return {
        "candidate_id": "initial",
        "generation": 0,
        "keyword_rules": {},
        "bias": {labels[0]: 0.1},
        "instruction": "Predict the label from the text.",
        "graph": [],
        "policy": {"tie_break": labels[0]},
        "demos": [],
        "agents": [],
    }


def _new_state(
    algorithm: str,
    problem: OptimizationProblem,
    *,
    seed: int,
    run_id: str | None,
) -> dict[str, Any]:
    rid = run_id or f"{algorithm}-{_hash_data({'dataset': problem.dataset, 'seed': seed})[:12]}"
    candidate = clone_candidate(problem.initial_candidate)
    candidate["candidate_id"] = _candidate_id(algorithm, candidate, 0)
    candidate["algorithm"] = algorithm
    return {
        "schema_version": "solar.advanced_ai4rnd.optimization_checkpoint.v1",
        "algorithm": algorithm,
        "run_id": rid,
        "seed": int(seed),
        "step": 0,
        "problem": {
            "dataset": problem.dataset,
            "initial_candidate": problem.initial_candidate,
            "max_steps": problem.max_steps,
            "objective": problem.objective_name,
            "complexity_weight": problem.complexity_weight,
            "success_min_delta": problem.success_min_delta,
        },
        "current_candidate": candidate,
        "best_candidate": copy.deepcopy(candidate),
        "current_evaluation": {},
        "baseline_evaluation": {},
        "best_evaluation": {},
        "trace": [],
        "failed_once_steps_seen": [],
    }


def _result(
    problem: OptimizationProblem,
    state: dict[str, Any],
    root: Path,
    *,
    status: str,
    checkpoint_path: Path,
) -> dict[str, Any]:
    trace_path = root / "trace.json"
    result_path = root / "result.json"
    graph_path = root / "optimizer_graph.json"
    policy_path = root / "policy.json"
    dataset_path = root / "dataset.json"
    evaluation_path = root / "evaluation.json"

    baseline = state["baseline_evaluation"]
    best = state["best_evaluation"]
    delta = round(best["objective"] - baseline["objective"], 6)
    result_state = "PASS" if status == "passed" else "NOT_SUCCESS"
    if status in {"interrupted", "recoverable_failed"}:
        result_state = "INCOMPLETE_RECOVERABLE"
    payload = {
        "schema_version": "solar.advanced_ai4rnd.optimization_result.v1",
        "algorithm": state["algorithm"],
        "run_id": state["run_id"],
        "status": status,
        "result_state": result_state,
        "seed": state["seed"],
        "steps_completed": state["step"],
        "baseline_objective": baseline["objective"],
        "best_objective": best["objective"],
        "objective_delta": delta,
        "baseline_accuracy": baseline["accuracy"],
        "best_accuracy": best["accuracy"],
        "improved": delta > problem.success_min_delta,
        "best_candidate": _public_candidate(state["best_candidate"]),
        "artifacts": {
            "checkpoint": str(checkpoint_path),
            "dataset": str(dataset_path),
            "evaluation": str(evaluation_path),
            "optimizer_graph": str(graph_path),
            "policy": str(policy_path),
            "result": str(result_path),
            "trace": str(trace_path),
        },
        "dependency_gate": dependency_gate(state["algorithm"], mode="reference"),
        "capability_metadata": CAPABILITY_METADATA[state["algorithm"]],
    }
    graph = _optimizer_graph(state, payload)
    _atomic_write_json(dataset_path, {"schema_version": "solar.advanced_ai4rnd.dataset.v1", "rows": problem.dataset})
    _atomic_write_json(evaluation_path, {"baseline": baseline, "best": best, "delta": delta})
    _atomic_write_json(policy_path, _public_candidate(state["best_candidate"]))
    _atomic_write_json(graph_path, graph)
    _atomic_write_json(trace_path, state["trace"])
    _atomic_write_json(result_path, payload)
    payload["output_hash"] = _hash_file(result_path)
    _atomic_write_json(result_path, payload)
    return payload


def _optimizer_graph(state: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [
        {"id": "input.dataset", "kind": "dataset", "hash": _hash_data(state["problem"]["dataset"])},
        {"id": "candidate.initial", "kind": "candidate", "objective": result["baseline_objective"]},
        {"id": "candidate.best", "kind": "policy", "objective": result["best_objective"]},
        {"id": "evaluation.best", "kind": "evaluation", "accuracy": result["best_accuracy"]},
    ]
    for event in state["trace"]:
        if event["event"] == "update":
            nodes.append(
                {
                    "id": f"update.{event['step']}",
                    "kind": "algorithm_update",
                    "mechanism": event["mechanism"],
                }
            )
    return {
        "schema_version": "solar.advanced_ai4rnd.optimizer_graph.v1",
        "algorithm": state["algorithm"],
        "run_id": state["run_id"],
        "nodes": nodes,
        "edges": [
            {"from": "input.dataset", "to": "candidate.initial", "relation": "evaluates"},
            {"from": "candidate.initial", "to": "candidate.best", "relation": "optimized_into"},
            {"from": "candidate.best", "to": "evaluation.best", "relation": "scored_by"},
        ],
    }


def _write_checkpoint(root: Path, state: Mapping[str, Any]) -> Path:
    path = root / "checkpoint.json"
    _atomic_write_json(path, state)
    return path


def _append_trace(state: dict[str, Any], event: str, payload: Mapping[str, Any]) -> None:
    item = {"index": len(state["trace"]), "event": event, **dict(payload)}
    if "step" not in item:
        item["step"] = state.get("step", 0)
    state["trace"].append(item)


def _is_solved(problem: OptimizationProblem, state: Mapping[str, Any]) -> bool:
    evaluation = state.get("current_evaluation") or {}
    return bool(evaluation) and evaluation.get("accuracy") == 1.0


def _compiled_rules(candidate: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    rules = copy.deepcopy(candidate.get("keyword_rules") or {})
    for agent in candidate.get("agents") or []:
        for label, label_rules in (agent.get("keyword_rules") or {}).items():
            merged = rules.setdefault(label, {})
            for token, weight in label_rules.items():
                merged[token] = float(merged.get(token, 0.0)) + float(weight)
    return rules


def _apply_graph(tokens: set[str], graph: Any) -> set[str]:
    out = set(tokens)
    if not isinstance(graph, list):
        return out
    for node in graph:
        if not isinstance(node, Mapping):
            continue
        if node.get("kind") == "inject_label_token":
            terms = set(str(term).lower() for term in node.get("match_terms", []))
            if terms and terms.issubset(out):
                out.add(str(node.get("token")))
        elif node.get("kind") == "alias":
            source = str(node.get("source") or "").lower()
            target = str(node.get("target") or "").lower()
            if source in out and target:
                out.add(target)
    return out


def _complexity(candidate: Mapping[str, Any]) -> float:
    rules = _compiled_rules(candidate)
    keywords = sum(len(label_rules) for label_rules in rules.values())
    graph_nodes = len(candidate.get("graph") or [])
    demos = len(candidate.get("demos") or [])
    agents = len(candidate.get("agents") or [])
    tree_nodes = len((candidate.get("tree") or {}).get("nodes", []))
    return float(keywords + graph_nodes + 0.5 * demos + agents + 0.25 * tree_nodes)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_:-]+", text.lower()))


def _candidate_id(algorithm: str, candidate: Mapping[str, Any], generation: int) -> str:
    public = _public_candidate(candidate)
    return f"{algorithm}.{generation}.{_hash_data(public)[:10]}"


def _public_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in candidate.items()
        if key not in {"internal_notes"}
    }


def _candidate_changed(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    old = _public_candidate(previous)
    new = _public_candidate(current)
    old.pop("candidate_id", None)
    new.pop("candidate_id", None)
    old.pop("generation", None)
    new.pop("generation", None)
    return old != new


def _stable_random(seed: int, algorithm: str, step: int) -> random.Random:
    raw = f"{seed}:{algorithm}:{step}"
    return random.Random(int(_hash_text(raw)[:12], 16))


def _normalize_algorithm(algorithm: str) -> str:
    name = str(algorithm).strip().lower()
    if name not in CAPABILITY_METADATA:
        raise OptimizationError(f"unsupported algorithm {algorithm!r}; expected one of {sorted(ALGORITHMS)}")
    return name


def _build_optimizer(name: str) -> ReferenceOptimizer:
    from .algorithms import AFlowOptimizer, ADASOptimizer, CEGISOptimizer, MCTSOptimizer, MIPROv2Optimizer, TextGradOptimizer

    mapping: dict[str, type[ReferenceOptimizer]] = {
        "miprov2": MIPROv2Optimizer,
        "textgrad": TextGradOptimizer,
        "aflow": AFlowOptimizer,
        "mcts": MCTSOptimizer,
        "adas": ADASOptimizer,
        "cegis": CEGISOptimizer,
    }
    return mapping[name]()


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_data(data: Any) -> str:
    return _hash_text(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _softmax(values: Sequence[float]) -> list[float]:
    peak = max(values)
    exps = [math.exp(value - peak) for value in values]
    total = sum(exps)
    return [value / total for value in exps]
