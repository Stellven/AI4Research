from __future__ import annotations

from evaluators.scientific import literature_discovery_gate


def _payload(*, mode: str, channels: list[str], require_online: bool = False, min_channels: int = 1) -> dict:
    return {
        "schema": "literature_discovery.v1",
        "task_id": "task-literature-discovery",
        "sprint_id": "sprint-literature-discovery",
        "node_id": "literature_discover",
        "status": "completed",
        "inputs": {
            "query": "skill generation",
            "require_online_source_evidence": require_online,
            "min_online_source_channels": min_channels,
        },
        "outputs": {
            "query": "skill generation",
            "mode": mode,
            "limit": 3,
            "candidates": [
                {
                    "candidate_id": "s2:paper-001",
                    "title": "Skill Generation for Inference-Time Agents",
                    "source_channels": channels,
                    "ranking_score": 0.91,
                    "ranking_rationale": "source=search_s2; year=2026",
                    "dedup_status": "new",
                    "source_ref": "https://www.semanticscholar.org/paper/paper-001",
                }
            ],
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-26T00:00:00Z",
        },
        "limitations": ["Literature candidates require human review before ingest."],
    }


def test_literature_discovery_gate_accepts_required_online_channel() -> None:
    result = literature_discovery_gate.evaluate(
        _payload(mode="topic", channels=["search_s2"], require_online=True)
    )

    assert result.ok is True
    assert result.status == "passed"


def test_literature_discovery_gate_rejects_fixture_for_required_online_evidence() -> None:
    result = literature_discovery_gate.evaluate(
        _payload(mode="fixture", channels=["local_fixture"], require_online=True)
    )

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "online source evidence cannot use fixture discovery mode" in joined
    assert "online source evidence requires at least one non-fixture online source channel" in joined


def test_literature_discovery_gate_enforces_minimum_online_source_fan_in() -> None:
    result = literature_discovery_gate.evaluate(
        _payload(mode="topic", channels=["search_s2"], require_online=True, min_channels=2)
    )

    assert result.ok is False
    assert "requires at least 2 online source channel" in " ".join(result.reasons)
