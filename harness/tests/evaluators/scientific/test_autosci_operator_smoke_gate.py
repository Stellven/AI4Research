from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evaluators.scientific import autosci_operator_smoke_gate

HARNESS = Path(__file__).resolve().parents[3]
ROUTE_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
BINDING_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_operator_bindings.v1.json"


def item(skill: str, status: str, *, side_effect_policy: str = "none") -> dict:
    return {
        "native_skill": skill,
        "autosci_feature": f"/{skill}",
        "solar_backend_action": "ingest_paper",
        "physical_operator": "AutoSciBridgePaperIngestor" if status != "unbound" else "N/A",
        "side_effect_policy": side_effect_policy,
        "execution_status": status,
        "smoke_steps": ["ingest_paper"] if status in {"completed", "partial", "gated"} else [],
        "evidence_paths": [str(ROUTE_CONFIG)] if status in {"completed", "partial", "gated"} else [],
        "gate_statuses": ["passed"] if status in {"completed", "partial", "gated"} else [],
        "evidence_ids": [f"route:{skill}", f"operator:{skill}"],
        "limitations": ["Approval required."] if status == "gated" else ["Fixture scope."],
    }


def payload(items: list[dict]) -> dict:
    core_actions = [
        {
            "action": "ingest_paper",
            "status": "passed",
            "schema": "research_paper.v1",
            "evidence_path": str(ROUTE_CONFIG),
            "gate_status": "passed",
            "evidence_ids": ["paper-skillgen"],
            "reasons": [],
            "warnings": [],
        }
    ]
    return {
        "schema": "autosci_operator_smoke.v1",
        "task_id": "test-autosci-operator-smoke",
        "sprint_id": "phase19-test",
        "node_id": "node-autosci-operator-smoke",
        "status": "completed",
        "inputs": {
            "paper_path": "plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md",
            "route_config": str(ROUTE_CONFIG),
            "binding_config": str(BINDING_CONFIG),
            "work_dir": "artifacts/autosci/operator-smoke/test",
        },
        "outputs": {
            "smoke": {
                "paper_path": "plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md",
                "route_count": len(items),
                "bound_count": len([entry for entry in items if entry["execution_status"] != "unbound"]),
                "completed_count": len([entry for entry in items if entry["execution_status"] == "completed"]),
                "partial_count": len([entry for entry in items if entry["execution_status"] == "partial"]),
                "gated_count": len([entry for entry in items if entry["execution_status"] == "gated"]),
                "failed_count": len([entry for entry in items if entry["execution_status"] == "failed"]),
                "unbound_count": len([entry for entry in items if entry["execution_status"] == "unbound"]),
                "core_action_count": len(core_actions),
                "core_actions": core_actions,
                "items": items,
            }
        },
        "artifacts": [
            {"type": "route_config", "path": str(ROUTE_CONFIG)},
            {"type": "binding_config", "path": str(BINDING_CONFIG)},
        ],
        "provenance": {
            "operator_id": "AutoSciSkillgenOperatorSmoke",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": ["Gate test fixture scope."],
    }


def test_operator_smoke_gate_accepts_completed_partial_and_gated_items() -> None:
    result = autosci_operator_smoke_gate.evaluate(
        payload(
            [
                item("ingest", "completed"),
                item("review", "partial", side_effect_policy="dry_run_only"),
                item("poster", "gated", side_effect_policy="approval_required"),
            ]
        )
    )

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []
    assert result.warnings


def test_operator_smoke_gate_rejects_unbound_item() -> None:
    result = autosci_operator_smoke_gate.evaluate(payload([item("future-skill", "unbound", side_effect_policy="unavailable")]))

    assert result.ok is False
    assert result.status == "failed"
    assert "unbound" in " ".join(result.reasons)
