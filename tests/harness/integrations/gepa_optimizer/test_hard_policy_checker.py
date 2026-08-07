from __future__ import annotations

from integrations.gepa_optimizer.hard_policy_checker import check_candidate


def test_hard_policy_checker_rejects_relaxed_safety():
    result = check_candidate(
        {
            "candidate_type": "capsule",
            "target_id": "cap.example",
            "payload": {
                "safety": {
                    "secrets_access": "allowed",
                    "git_push": True,
                }
            },
            "mutable_sections": ["instructions"],
            "frozen_sections": ["safety"],
        }
    )
    assert result["ok"] is False
    assert result["decision"] == "hard_reject"
    assert any("secrets_access" in violation for violation in result["violations"])


def test_hard_policy_checker_detects_frozen_section_changes():
    result = check_candidate(
        {
            "candidate_type": "capsule",
            "target_id": "cap.example",
            "payload": {
                "safety": {
                    "destructive_shell": "allowed",
                }
            },
            "mutable_sections": ["instructions"],
            "frozen_sections": ["safety"],
            "frozen_values": {
                "safety": {
                    "destructive_shell": "denied",
                }
            },
        }
    )
    assert result["ok"] is False
    assert "safety.destructive_shell" in result["frozen_section_diff"]


def test_hard_policy_checker_allows_denied_only_payload():
    result = check_candidate(
        {
            "candidate_type": "capsule",
            "target_id": "cap.example",
            "payload": {
                "safety": {
                    "secrets_access": "denied",
                    "git_push": False,
                }
            },
            "mutable_sections": ["instructions"],
            "frozen_sections": ["safety"],
        }
    )
    assert result["ok"] is True
    assert result["decision"] == "allow"
