from __future__ import annotations

import pytest

from integrations.gepa_optimizer.candidate_schema import (
    CandidateSchemaError,
    CandidateType,
    OptimizationCandidate,
    normalize_candidate,
)


def test_normalize_candidate_from_dict():
    candidate = normalize_candidate(
        {
            "candidate_type": "skill",
            "target_id": "skill.flashmlx-performance-debug",
            "payload": {"skill_md": "hello"},
            "mutable_sections": ["instructions", "examples"],
            "frozen_sections": ["safety_notes"],
            "lineage": ["seed-1"],
        }
    )
    assert candidate.candidate_type is CandidateType.SKILL
    assert candidate.target_id == "skill.flashmlx-performance-debug"
    assert candidate.mutable_sections == ("instructions", "examples")
    assert candidate.frozen_sections == ("safety_notes",)


def test_candidate_rejects_overlap():
    with pytest.raises(CandidateSchemaError):
        OptimizationCandidate.from_dict(
            {
                "candidate_type": "capsule",
                "target_id": "cap.example",
                "payload": {"capsule_yaml": "..."},
                "mutable_sections": ["instructions", "safety"],
                "frozen_sections": ["safety"],
            }
        )


def test_candidate_canonical_json_is_stable():
    candidate = OptimizationCandidate.from_dict(
        {
            "candidate_type": "routing_policy",
            "target_id": "routing.default.v1",
            "payload": {"b": 2, "a": 1},
            "mutable_sections": ["rules"],
            "frozen_sections": ["hard_verifier_requirements"],
        }
    )
    assert candidate.canonical_json() == candidate.canonical_json()
