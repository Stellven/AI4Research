#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import capsule_execution_gate as gate  # noqa: E402


def _manifest() -> dict:
    return {
        "capability_capsule_id": "cap.example",
        "contract": {
            "inputs": {"required": [{"name": "repo_path", "type": "path"}]},
            "preconditions": [{"check": "input_present", "field": "repo_path"}],
        },
        "verification": {
            "self_check": [{"kind": "artifact_present", "path": "proof.json"}],
        },
        "bindings": {"secret_refs": []},
        "effects": {"risk": []},
    }


def test_missing_required_input_blocks(tmp_path):
    decision = gate.run_gate({"task_id": "t1"}, _manifest(), tmp_path)
    assert decision.ok is False
    assert any("repo_path" in item for item in decision.blocks)


def test_cooldown_blocks_when_active(tmp_path):
    cooldown_path = tmp_path / "cooldown.json"
    gate._write_json(  # type: ignore[attr-defined]
        cooldown_path,
        {"cap.example": {"last_run_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}},
    )
    decision = gate.run_gate(
        {"task_id": "t1", "repo_path": "/tmp/repo", "cooldown_s": 60},
        _manifest(),
        tmp_path,
        cooldown_path=cooldown_path,
    )
    assert any("cooldown active" in item for item in decision.blocks)


def test_idempotency_dedup_second_dispatch_blocked(tmp_path):
    dedup = tmp_path / "dedup.json"
    first = gate.run_gate({"task_id": "t1", "repo_path": "/tmp/repo"}, _manifest(), tmp_path, dedup_path=dedup)
    second = gate.run_gate({"task_id": "t1", "repo_path": "/tmp/repo"}, _manifest(), tmp_path, dedup_path=dedup)
    assert first.ok is True
    assert second.ok is False
    assert any("duplicate active dispatch" in item for item in second.blocks)


def test_proof_obligation_artifact_missing_warns(tmp_path):
    decision = gate.run_gate({"task_id": "t1", "repo_path": "/tmp/repo"}, _manifest(), tmp_path)
    assert any("missing proof artifact" in item for item in decision.warnings)


def test_guard_sensitive_action_raises(tmp_path):
    manifest = _manifest()
    manifest["bindings"] = {"secret_refs": ["secret.api_key"]}
    decision = gate.run_gate({"task_id": "t1", "repo_path": "/tmp/repo"}, manifest, tmp_path)
    assert any("allow_sensitive=true" in item for item in decision.blocks)
