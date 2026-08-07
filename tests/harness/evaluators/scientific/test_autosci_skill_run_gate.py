from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evaluators.scientific import autosci_skill_run_gate


def payload(tmp_path: Path, *, status: str = "inconclusive", execution_status: str = "partial") -> dict:
    route_config = tmp_path / "feature_parity_routes.v1.json"
    binding_config = tmp_path / "feature_operator_bindings.v1.json"
    route_config.write_text("{}\n", encoding="utf-8")
    binding_config.write_text("{}\n", encoding="utf-8")
    side_effect_policy = "approval_required" if execution_status == "gated" else "dry_run_only"
    return {
        "schema": "autosci_skill_run.v1",
        "task_id": "test-autosci-skill-run",
        "sprint_id": "phase19-test",
        "node_id": "node-autosci-skill-run",
        "status": status,
        "inputs": {
            "skill": "review",
            "run_id": "test-autosci-skill-run",
            "work_dir": "artifacts/autosci/runs/test-autosci-skill-run",
            "route_config": str(route_config),
            "binding_config": str(binding_config),
        },
        "outputs": {
            "skill_run": {
                "selected_skill": "review",
                "autosci_command": "/review",
                "execution_status": execution_status,
                "side_effect_policy": side_effect_policy,
                "action_count": 0,
                "passed_count": 0,
                "schema_only_count": 0,
                "failed_count": 0,
                "actions": [],
                "route": {
                    "coverage_status": execution_status,
                    "backend_mode": "route_plan",
                    "evidence_schema": "artifact_review.v1",
                },
            }
        },
        "artifacts": [
            {"type": "route_config", "path": str(route_config)},
            {"type": "binding_config", "path": str(binding_config)},
        ],
        "provenance": {
            "operator_id": "AutoSciSkillShim",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": ["Partial/gated route evidence must not be treated as full parity."],
    }


def test_skill_run_gate_rejects_completed_partial_route(tmp_path: Path) -> None:
    result = autosci_skill_run_gate.evaluate(
        payload(tmp_path, status="completed", execution_status="partial"),
        path=tmp_path / "autosci_skill_run.json",
    )

    assert result.ok is False
    assert result.status == "failed"
    assert "top-level status inconclusive" in " ".join(result.reasons)


def test_skill_run_gate_rejects_completed_gated_route(tmp_path: Path) -> None:
    result = autosci_skill_run_gate.evaluate(
        payload(tmp_path, status="completed", execution_status="gated"),
        path=tmp_path / "autosci_skill_run.json",
    )

    assert result.ok is False
    assert result.status == "failed"
    assert "top-level status inconclusive" in " ".join(result.reasons)


def test_skill_run_gate_keeps_partial_route_inconclusive(tmp_path: Path) -> None:
    result = autosci_skill_run_gate.evaluate(
        payload(tmp_path, status="inconclusive", execution_status="partial"),
        path=tmp_path / "autosci_skill_run.json",
    )

    assert result.ok is False
    assert result.status == "inconclusive"
    assert result.reasons == []
    assert any("partial" in warning for warning in result.warnings)
