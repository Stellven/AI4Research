from __future__ import annotations

from research.evidence.review_proof import bind_reviewer_execution


def _proof(writer_provider: str) -> dict:
    return {
        "reviewer_separation": {
            "independence": {
                "status": "same_provider_limitation",
                "writer": {"provider": writer_provider, "model": "writer-model"},
                "reviewer": {"provider": "local_deterministic", "model": "local"},
                "fully_independent": False,
            }
        }
    }


def test_requested_but_unavailable_provider_is_not_independent() -> None:
    proof = bind_reviewer_execution(
        _proof("openai"),
        {
            "status": "unavailable",
            "invocation_mode": "provider",
            "provider": "openrouter",
            "model": "review-model",
        },
    )

    independence = proof["reviewer_separation"]["independence"]
    assert independence["status"] == "same_provider_limitation"
    assert independence["fully_independent"] is False
    assert independence["execution_bound"] is False


def test_completed_different_provider_is_execution_bound_independent() -> None:
    proof = bind_reviewer_execution(
        _proof("openai"),
        {
            "status": "completed",
            "invocation_mode": "provider",
            "provider": "openrouter",
            "model": "review-model",
        },
    )

    independence = proof["reviewer_separation"]["independence"]
    assert independence["status"] == "independent_provider"
    assert independence["fully_independent"] is True
    assert independence["execution_bound"] is True


def test_completed_provider_cannot_make_local_fixture_writer_independent() -> None:
    proof = bind_reviewer_execution(
        _proof("local_fixture"),
        {
            "status": "completed",
            "invocation_mode": "provider",
            "provider": "openrouter",
            "model": "review-model",
        },
    )

    independence = proof["reviewer_separation"]["independence"]
    assert independence["status"] == "same_provider_limitation"
    assert independence["fully_independent"] is False
    assert independence["execution_bound"] is True
