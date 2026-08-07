from __future__ import annotations

import json
from pathlib import Path

from integrations.gepa_optimizer.backend import GEPAOptimizerBackend


def test_backend_returns_gepa_unavailable_for_safe_candidate(tmp_path):
    backend = GEPAOptimizerBackend(run_root=tmp_path)
    result = backend.optimize_skill(
        "skill.flashmlx-performance-debug",
        "suite.flashmlx-smoke",
        candidate={
            "candidate_type": "skill",
            "target_id": "skill.flashmlx-performance-debug",
            "payload": {"skill_md": "hello", "safety_notes": {"secrets_access": "denied"}},
            "mutable_sections": ["instructions"],
            "frozen_sections": ["safety_notes"],
        },
    )
    assert result["status"] == "gepa_unavailable"
    assert result["publish_decision"] == "hold"
    summary = json.loads((Path(result["run_dir"]) / "summary.json").read_text())
    assert summary["backend_status"] == "gepa_unavailable"


def test_backend_rejects_policy_relaxation(tmp_path):
    backend = GEPAOptimizerBackend(run_root=tmp_path)
    result = backend.optimize_capsule(
        "cap.flashmlx-performance-debugger",
        "suite.flashmlx-smoke",
        candidate={
            "candidate_type": "capsule",
            "target_id": "cap.flashmlx-performance-debugger",
            "payload": {"safety": {"git_push": True}},
            "mutable_sections": ["instructions"],
            "frozen_sections": ["safety"],
        },
    )
    assert result["status"] == "hard_reject"
    assert result["publish_decision"] == "reject"
    assert result["policy_check"]["decision"] == "hard_reject"
