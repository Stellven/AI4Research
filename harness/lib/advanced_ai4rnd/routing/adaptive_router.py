"""Deterministic adaptive model routing with cost and policy evidence.

The implementation is intentionally small and CPU-only.  It is not a live
provider dispatcher; it is the auditable decision/update layer used by repair
tests and future production wiring.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


class PolicyViolation(ValueError):
    """Raised when policy leaves no legal route."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class RoutingCandidate:
    model_id: str
    capabilities: tuple[str, ...]
    quality_prior: float
    cost_per_1k_tokens: float
    latency_ms: int
    policy_tags: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RoutingCandidate":
        return cls(
            model_id=str(payload["model_id"]),
            capabilities=tuple(str(item) for item in payload.get("capabilities", ())),
            quality_prior=float(payload.get("quality_prior", 0.5)),
            cost_per_1k_tokens=float(payload.get("cost_per_1k_tokens", 0.0)),
            latency_ms=int(payload.get("latency_ms", 0)),
            policy_tags=tuple(str(item) for item in payload.get("policy_tags", ())),
        )


@dataclasses.dataclass(frozen=True)
class RoutingTask:
    task_id: str
    prompt: str
    required_capability: str
    estimated_tokens: int
    difficulty: str = "standard"
    priority: str = "balanced"


@dataclasses.dataclass(frozen=True)
class RoutingPolicy:
    max_cost_usd: float
    min_quality: float
    allowed_models: tuple[str, ...] = ()
    blocked_models: tuple[str, ...] = ()
    blocked_tags: tuple[str, ...] = ()
    require_capability_match: bool = True


@dataclasses.dataclass(frozen=True)
class RoutingDecision:
    decision_id: str
    selected_model: str
    probabilities: dict[str, float]
    scorecard: list[dict[str, Any]]
    evidence: dict[str, Any]


class AdaptiveRouter:
    """Stateful Bayesian/bandit route scorer with deterministic selection."""

    schema_version = "solar.advanced_ai4rnd.adaptive_router.v1"

    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)
        loaded = _load_json(self.state_path)
        self.state: dict[str, Any] = loaded or {
            "schema_version": self.schema_version,
            "models": {},
            "events": [],
        }
        self.state.setdefault("models", {})
        self.state.setdefault("events", [])

    def save(self) -> None:
        _atomic_write_json(self.state_path, self.state)

    def route(
        self,
        task: RoutingTask,
        candidates: Sequence[RoutingCandidate | Mapping[str, Any]],
        policy: RoutingPolicy,
    ) -> RoutingDecision:
        normalized = [
            item if isinstance(item, RoutingCandidate) else RoutingCandidate.from_mapping(item)
            for item in candidates
        ]
        if not normalized:
            raise PolicyViolation("no routing candidates supplied")
        for candidate in normalized:
            self._ensure_model(candidate)

        scored = [self._score_candidate(task, candidate, policy) for candidate in normalized]
        allowed = [item for item in scored if item["allowed"]]
        if not allowed:
            blocked = {
                "schema_version": "solar.advanced_ai4rnd.policy_violation.v1",
                "task": dataclasses.asdict(task),
                "policy": dataclasses.asdict(policy),
                "scorecard": scored,
                "blocked_at": _now(),
            }
            raise PolicyViolation(json.dumps(blocked, sort_keys=True))

        probabilities = self._softmax_probabilities(allowed)
        selected_model = max(
            allowed,
            key=lambda item: (probabilities[item["model_id"]], item["score"], -item["estimated_cost_usd"], item["model_id"]),
        )["model_id"]
        evidence = {
            "schema_version": "solar.advanced_ai4rnd.routing_decision_evidence.v1",
            "decision_time": _now(),
            "task": dataclasses.asdict(task),
            "policy": dataclasses.asdict(policy),
            "quality_constraint": {"minimum": policy.min_quality},
            "cost_constraint": {"maximum_usd": policy.max_cost_usd},
            "history_feedback": {
                item["model_id"]: self.state["models"][item["model_id"]]["stats"] for item in scored
            },
            "probabilities": probabilities,
            "selected_model": selected_model,
            "state_digest_before": _digest(self.state),
        }
        decision_id = _digest({"task": dataclasses.asdict(task), "evidence": evidence})[:16]
        event = {
            "event_type": "route_decision",
            "decision_id": decision_id,
            "selected_model": selected_model,
            "task_id": task.task_id,
            "created_at": evidence["decision_time"],
            "usage_estimate": self._usage_estimate(task, selected_model, normalized),
            "provenance": evidence,
        }
        self.state["events"].append(event)
        self.save()
        return RoutingDecision(
            decision_id=decision_id,
            selected_model=selected_model,
            probabilities=probabilities,
            scorecard=scored,
            evidence=evidence,
        )

    def update_feedback(
        self,
        *,
        model_id: str,
        reward: float,
        observed_quality: float,
        observed_cost_usd: float,
        decision_id: str,
        notes: str = "",
    ) -> dict[str, Any]:
        if model_id not in self.state["models"]:
            raise KeyError(f"unknown model_id: {model_id}")
        reward = min(1.0, max(0.0, float(reward)))
        quality = min(1.0, max(0.0, float(observed_quality)))
        cost = max(0.0, float(observed_cost_usd))
        stats = self.state["models"][model_id]["stats"]
        before = dict(stats)
        stats["observations"] += 1
        stats["reward_sum"] += reward
        stats["quality_sum"] += quality
        stats["cost_sum_usd"] += cost
        stats["alpha"] += reward
        stats["beta"] += 1.0 - reward
        stats["posterior_mean"] = stats["alpha"] / (stats["alpha"] + stats["beta"])
        event = {
            "event_type": "route_feedback_update",
            "decision_id": decision_id,
            "model_id": model_id,
            "created_at": _now(),
            "before": before,
            "after": dict(stats),
            "observed": {
                "reward": reward,
                "quality": quality,
                "cost_usd": cost,
                "notes": notes,
            },
        }
        self.state["events"].append(event)
        self.save()
        return event

    def _ensure_model(self, candidate: RoutingCandidate) -> None:
        models = self.state["models"]
        if candidate.model_id in models:
            return
        alpha = max(0.1, candidate.quality_prior * 4.0)
        beta = max(0.1, (1.0 - candidate.quality_prior) * 4.0)
        models[candidate.model_id] = {
            "candidate": dataclasses.asdict(candidate),
            "stats": {
                "observations": 0,
                "alpha": alpha,
                "beta": beta,
                "posterior_mean": alpha / (alpha + beta),
                "reward_sum": 0.0,
                "quality_sum": 0.0,
                "cost_sum_usd": 0.0,
            },
        }

    def _score_candidate(
        self,
        task: RoutingTask,
        candidate: RoutingCandidate,
        policy: RoutingPolicy,
    ) -> dict[str, Any]:
        stats = self.state["models"][candidate.model_id]["stats"]
        estimated_cost = candidate.cost_per_1k_tokens * (max(1, task.estimated_tokens) / 1000.0)
        reasons: list[str] = []
        if policy.allowed_models and candidate.model_id not in policy.allowed_models:
            reasons.append("model_not_in_allowed_models")
        if candidate.model_id in policy.blocked_models:
            reasons.append("model_blocked")
        if set(candidate.policy_tags) & set(policy.blocked_tags):
            reasons.append("blocked_policy_tag")
        if policy.require_capability_match and task.required_capability not in candidate.capabilities:
            reasons.append("missing_required_capability")
        if estimated_cost > policy.max_cost_usd:
            reasons.append("cost_limit_exceeded")
        if stats["posterior_mean"] < policy.min_quality:
            reasons.append("quality_floor_not_met")

        capability_bonus = 0.18 if task.required_capability in candidate.capabilities else -0.35
        difficulty_bonus = 0.08 if task.difficulty == "hard" and "reasoning" in candidate.capabilities else 0.0
        cost_weight = 1.4 if task.priority == "low_cost" else 0.45
        latency_weight = 0.00008 if task.priority == "low_latency" else 0.00003
        feedback_bonus = 0.04 * min(5, stats["observations"])
        score = (
            float(stats["posterior_mean"])
            + capability_bonus
            + difficulty_bonus
            + feedback_bonus
            - cost_weight * estimated_cost
            - latency_weight * candidate.latency_ms
        )
        return {
            "model_id": candidate.model_id,
            "allowed": not reasons,
            "block_reasons": reasons,
            "score": round(score, 6),
            "posterior_quality": round(float(stats["posterior_mean"]), 6),
            "estimated_cost_usd": round(estimated_cost, 8),
            "latency_ms": candidate.latency_ms,
            "quality_constraint": policy.min_quality,
            "cost_constraint_usd": policy.max_cost_usd,
            "observations": int(stats["observations"]),
        }

    @staticmethod
    def _softmax_probabilities(scorecard: Sequence[Mapping[str, Any]]) -> dict[str, float]:
        values = [float(item["score"]) for item in scorecard]
        peak = max(values)
        weights = [math.exp((value - peak) * 4.0) for value in values]
        total = sum(weights)
        return {
            str(item["model_id"]): round(weight / total, 6)
            for item, weight in zip(scorecard, weights)
        }

    @staticmethod
    def _usage_estimate(
        task: RoutingTask,
        model_id: str,
        candidates: Sequence[RoutingCandidate],
    ) -> dict[str, Any]:
        candidate = next(item for item in candidates if item.model_id == model_id)
        cost = candidate.cost_per_1k_tokens * (max(1, task.estimated_tokens) / 1000.0)
        return {
            "model_id": model_id,
            "estimated_input_tokens": task.estimated_tokens,
            "estimated_output_tokens": max(64, task.estimated_tokens // 4),
            "estimated_cost_usd": round(cost, 8),
            "cost_per_1k_tokens": candidate.cost_per_1k_tokens,
            "latency_ms": candidate.latency_ms,
        }
