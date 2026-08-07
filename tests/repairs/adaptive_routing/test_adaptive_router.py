from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "harness" / "lib"))

from advanced_ai4rnd.routing import (  # noqa: E402
    AdaptiveRouter,
    PolicyViolation,
    RoutingCandidate,
    RoutingPolicy,
    RoutingTask,
)


def _candidates() -> list[RoutingCandidate]:
    return [
        RoutingCandidate(
            model_id="accurate-reasoner",
            capabilities=("reasoning", "summarization"),
            quality_prior=0.88,
            cost_per_1k_tokens=0.08,
            latency_ms=900,
            policy_tags=("premium",),
        ),
        RoutingCandidate(
            model_id="balanced-local",
            capabilities=("reasoning", "summarization"),
            quality_prior=0.78,
            cost_per_1k_tokens=0.02,
            latency_ms=400,
            policy_tags=("local",),
        ),
        RoutingCandidate(
            model_id="cheap-summarizer",
            capabilities=("summarization",),
            quality_prior=0.65,
            cost_per_1k_tokens=0.005,
            latency_ms=120,
            policy_tags=("local", "low_cost"),
        ),
    ]


def test_routing_consumes_task_cost_history_feedback_and_policy(tmp_path: Path) -> None:
    router = AdaptiveRouter(tmp_path / "router-state.json")
    policy = RoutingPolicy(max_cost_usd=0.50, min_quality=0.50)
    hard_task = RoutingTask(
        task_id="hard-reasoning",
        prompt="Choose the strongest model for a multi-step policy proof.",
        required_capability="reasoning",
        estimated_tokens=1000,
        difficulty="hard",
        priority="quality",
    )

    first = router.route(hard_task, _candidates(), policy)
    assert first.selected_model == "accurate-reasoner"
    assert set(first.probabilities) == {"accurate-reasoner", "balanced-local"}
    assert first.evidence["task"]["prompt"].startswith("Choose the strongest")
    assert first.evidence["cost_constraint"]["maximum_usd"] == 0.50
    assert first.evidence["quality_constraint"]["minimum"] == 0.50
    assert first.evidence["history_feedback"]["accurate-reasoner"]["observations"] == 0
    assert first.scorecard[0]["estimated_cost_usd"] > first.scorecard[1]["estimated_cost_usd"]

    router.update_feedback(
        model_id="accurate-reasoner",
        reward=0.0,
        observed_quality=0.2,
        observed_cost_usd=0.08,
        decision_id=first.decision_id,
        notes="held-out fixture found a bad answer",
    )
    second = router.route(hard_task, _candidates(), policy)

    assert second.probabilities != first.probabilities
    assert second.evidence["history_feedback"]["accurate-reasoner"]["observations"] == 1
    assert second.selected_model == "balanced-local"

    restarted = AdaptiveRouter(tmp_path / "router-state.json")
    third = restarted.route(hard_task, _candidates(), policy)
    assert third.selected_model == "balanced-local"
    assert third.evidence["history_feedback"]["accurate-reasoner"]["observations"] == 1


def test_input_and_cost_policy_change_routing_decision(tmp_path: Path) -> None:
    router = AdaptiveRouter(tmp_path / "router-state.json")
    low_cost_policy = RoutingPolicy(max_cost_usd=0.015, min_quality=0.50)
    task = RoutingTask(
        task_id="cheap-summary",
        prompt="Summarize an internal trace under a tight budget.",
        required_capability="summarization",
        estimated_tokens=1000,
        priority="low_cost",
    )

    decision = router.route(task, _candidates(), low_cost_policy)
    assert decision.selected_model == "cheap-summarizer"
    blocked = {item["model_id"]: item["block_reasons"] for item in decision.scorecard if not item["allowed"]}
    assert "cost_limit_exceeded" in blocked["accurate-reasoner"]
    assert "cost_limit_exceeded" in blocked["balanced-local"]
    assert decision.evidence["policy"]["max_cost_usd"] == 0.015


def test_policy_violation_is_blocked_and_auditable(tmp_path: Path) -> None:
    router = AdaptiveRouter(tmp_path / "router-state.json")
    task = RoutingTask(
        task_id="blocked-live",
        prompt="Use a live premium model even though policy forbids it.",
        required_capability="reasoning",
        estimated_tokens=500,
    )
    policy = RoutingPolicy(
        max_cost_usd=0.0001,
        min_quality=0.90,
        blocked_tags=("premium", "local"),
    )

    with pytest.raises(PolicyViolation) as exc:
        router.route(task, _candidates(), policy)

    payload = json.loads(str(exc.value))
    assert payload["schema_version"] == "solar.advanced_ai4rnd.policy_violation.v1"
    assert {reason for item in payload["scorecard"] for reason in item["block_reasons"]} >= {
        "cost_limit_exceeded",
        "quality_floor_not_met",
        "blocked_policy_tag",
    }
