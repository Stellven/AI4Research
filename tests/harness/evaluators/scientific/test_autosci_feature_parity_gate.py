from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evaluators.scientific import autosci_feature_parity_gate

HARNESS = (Path(__file__).resolve().parents[4] / 'harness')
ROUTE_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"


def payload_with_items(items: list[dict]) -> dict:
    native_skills = [item["native_skill"] for item in items]
    proof_levels = ("E0", "E1", "E2", "E3", "E4", "E5")
    execution_policies = ("pure", "bounded_local", "approval_required", "provider_required")
    runtime_statuses = ("not_required", "pending", "supplied", "verified")
    requirement_statuses = ("ok", "pending", "supplied", "missing", "blocked")
    return {
        "schema": "autosci_feature_parity.v1",
        "task_id": "test-autosci-feature-parity",
        "sprint_id": "phase19-test",
        "node_id": "node-autosci-feature-parity",
        "status": "completed",
        "inputs": {
            "autosci_repo": "/tmp/AutoSci",
            "route_config": str(ROUTE_CONFIG),
            "requested_skill": "N/A",
        },
        "outputs": {
            "parity": {
                "config_version": "phase19.v1",
                "autosci_repo": "/tmp/AutoSci",
                "native_skill_count": len(native_skills),
                "configured_route_count": len(items),
                "routed_count": len([item for item in items if item["coverage_status"] != "missing"]),
                "missing_route_count": len([item for item in items if item["coverage_status"] == "missing"]),
                "full_count": len([item for item in items if item["coverage_status"] == "full"]),
                "partial_count": len([item for item in items if item["coverage_status"] == "partial"]),
                "gated_count": len([item for item in items if item["coverage_status"] == "gated"]),
                "blocked_count": len([item for item in items if item["coverage_status"] == "blocked"]),
                "semantic_full_count": len([item for item in items if item["semantic_parity"] == "full"]),
                "semantic_partial_count": len([item for item in items if item["semantic_parity"] == "partial"]),
                "semantic_missing_count": len([item for item in items if item["semantic_parity"] == "missing"]),
                "execution_policy_counts": {
                    value: len([item for item in items if item["execution_policy"] == value])
                    for value in execution_policies
                },
                "proof_level_counts": {
                    value: len([item for item in items if item["proof_level"] == value])
                    for value in proof_levels
                },
                "runtime_proof_status_counts": {
                    value: len([item for item in items if item["runtime_proof_status"] == value])
                    for value in runtime_statuses
                },
                "proof_requirement_status_counts": {
                    value: sum(
                        1
                        for item in items
                        for requirement in item["proof_requirements"]
                        if requirement["status"] == value
                    )
                    for value in requirement_statuses
                },
                "native_skills": native_skills,
                "items": items,
            }
        },
        "artifacts": [{"type": "route_config", "path": str(ROUTE_CONFIG)}],
        "provenance": {
            "operator_id": "AutoSciFeatureParityBridge",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": ["Gate test parity scope limitation."],
    }


def base_item(
    skill: str,
    *,
    coverage_status: str = "full",
    side_effect_policy: str = "none",
    semantic_parity: str | None = None,
    execution_policy: str | None = None,
    proof_level: str | None = None,
) -> dict:
    semantic = semantic_parity or ("full" if coverage_status == "full" else "missing" if coverage_status == "missing" else "partial")
    execution = execution_policy or (
        "pure"
        if side_effect_policy == "none"
        else "bounded_local"
        if side_effect_policy == "dry_run_only"
        else "approval_required"
        if side_effect_policy == "approval_required"
        else "provider_required"
    )
    proof = proof_level or ("E3" if coverage_status == "full" else "E0" if coverage_status == "missing" else "E2")
    runtime_status = "pending" if execution in {"approval_required", "provider_required"} else "not_required"
    proof_requirements = [
        {
            "category": "route_definition",
            "status": "ok" if coverage_status != "missing" else "missing",
            "description": "Solar route declaration exists.",
            "evidence_refs": [f"route:{skill}"],
        },
        {
            "category": "native_skill_presence",
            "status": "ok",
            "description": "Native AutoSci skill exists.",
            "evidence_refs": [f"native:{skill}"],
        },
        {
            "category": "primary_tool_abi",
            "status": "ok",
            "description": "Primary tool references resolve.",
            "evidence_refs": ["plugins/autosci/bin/autosci_bridge.py"],
        },
    ]
    if semantic != "full":
        proof_requirements.append(
            {
                "category": "semantic_equivalence_evidence",
                "status": "pending",
                "description": "Non-full semantic parity still needs proof.",
                "evidence_refs": [f"route:{skill}"],
            }
        )
    if runtime_status == "pending":
        proof_requirements.append(
            {
                "category": "external_runtime_evidence",
                "status": "pending",
                "description": "External runtime proof is still required.",
                "evidence_refs": [],
            }
        )
    if side_effect_policy == "approval_required":
        proof_requirements.append(
            {
                "category": "approval_boundary_evidence",
                "status": "pending",
                "description": "Approval boundary proof is still required.",
                "evidence_refs": [],
            }
        )
    return {
        "autosci_feature": f"/{skill}",
        "native_skill": skill,
        "feature_kind": "skill",
        "native_paths": [f"i18n/en/skills/{skill}/SKILL.md"],
        "solar_capability": "cap.research-literature-discover",
        "solar_logical_operator": "ScientificLiteratureDiscoverer",
        "solar_backend_action": "discover_literature",
        "coverage_status": coverage_status,
        "backend_mode": "solar_native" if coverage_status == "full" else "route_plan",
        "side_effect_policy": side_effect_policy,
        "semantic_parity": semantic,
        "execution_policy": execution,
        "proof_level": proof,
        "proof_refs": [f"route:{skill}", f"native:{skill}"],
        "remaining_requirements": [] if semantic == "full" else ["Complete route-specific parity proof."],
        "runtime_proof_refs": [],
        "runtime_proof_sources": [],
        "runtime_proof_status": runtime_status,
        "proof_requirements": proof_requirements,
        "evidence_schema": "literature_discovery.v1",
        "primary_tools": ["plugins/autosci/bin/autosci_bridge.py"],
        "required_capabilities": ["route coverage"],
        "limitations": ["Non-full route requires downstream evidence."] if coverage_status != "full" else ["N/A"],
        "evidence_ids": [f"route:{skill}", f"native:{skill}"],
    }


def mark_runtime_verified(item: dict, *, categories: list[str] | None = None) -> dict:
    proof_categories = categories or ["external_runtime_evidence", "approval_boundary_evidence"]
    skill = item["native_skill"]
    proof_id = f"runtime:{skill}:verified-test"
    item["runtime_proof_status"] = "verified"
    item["runtime_proof_refs"] = [proof_id]
    item["runtime_proof_sources"] = [
        {
            "proof_id": proof_id,
            "native_skill": skill,
            "status": "supplied",
            "manifest_path": "/tmp/runtime-proof.json",
            "collection_mode": "approved_side_effect",
            "production_ready": True,
            "provenance": {
                "source": "unit-test approved runtime proof",
                "captured_at": "2026-06-29T00:00:00Z",
                "artifact_kind": "autosci_runtime_proof_manifest.v1",
            },
            "categories": proof_categories,
            "evidence_refs": [proof_id],
            "evidence_ref_statuses": [
                {"ref": proof_id, "status": "external_ref", "kind": "external"}
            ],
            "block_reasons": [],
            "description": "Verified runtime proof for strict full-parity acceptance.",
        }
    ]
    for requirement in item["proof_requirements"]:
        if requirement["category"] in proof_categories:
            requirement["status"] = "supplied"
            requirement["evidence_refs"] = [proof_id]
    return item


def append_blocked_runtime_source(item: dict, *, categories: list[str], collection_mode: str) -> dict:
    skill = item["native_skill"]
    proof_id = f"runtime:{skill}:blocked-test"
    item["runtime_proof_sources"].append(
        {
            "proof_id": proof_id,
            "native_skill": skill,
            "status": "blocked",
            "manifest_path": "/tmp/blocked-proof.json",
            "collection_mode": collection_mode,
            "production_ready": False,
            "provenance": {
                "source": "unit-test blocked proof",
                "captured_at": "2026-06-30T00:00:00Z",
                "artifact_kind": "autosci_semantic_parity_audit.v1"
                if collection_mode == "semantic_audit"
                else "autosci_runtime_proof_manifest.v1",
            },
            "categories": categories,
            "evidence_refs": [proof_id],
            "evidence_ref_statuses": [
                {"ref": proof_id, "status": "external_ref", "kind": "external"}
            ],
            "block_reasons": ["audit semantic_parity must be full"],
            "description": "Blocked proof source for gate boundary testing.",
        }
    )
    return item


def test_autosci_feature_parity_gate_accepts_honest_mixed_route_inventory() -> None:
    payload = payload_with_items(
        [
            base_item("discover"),
            base_item("daily-arxiv", coverage_status="gated", side_effect_policy="approval_required"),
            base_item("novelty", coverage_status="partial", side_effect_policy="dry_run_only"),
        ]
    )

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []
    assert result.warnings


def test_autosci_feature_parity_gate_allows_blocked_partial_semantic_audit_source() -> None:
    item = base_item("ask", coverage_status="partial", side_effect_policy="none")
    append_blocked_runtime_source(
        item,
        categories=["semantic_equivalence_evidence"],
        collection_mode="semantic_audit",
    )
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_autosci_feature_parity_gate_rejects_blocked_nonsemantic_runtime_source() -> None:
    item = base_item("daily-arxiv", coverage_status="gated", side_effect_policy="approval_required")
    append_blocked_runtime_source(
        item,
        categories=["external_runtime_evidence"],
        collection_mode="live_provider",
    )
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert "blocked non-semantic proof is not accepted" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_strict_full_acceptance_rejects_partial_inventory() -> None:
    payload = payload_with_items(
        [
            base_item("discover"),
            base_item("novelty", coverage_status="partial", side_effect_policy="dry_run_only"),
        ]
    )

    result = autosci_feature_parity_gate.evaluate_full_parity_acceptance(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "novelty: full parity requires semantic_parity=full" in joined
    assert "novelty: full parity has unresolved proof requirements" in joined
    assert "novelty: full parity requires remaining_requirements to be empty" in joined
    assert "novelty: full parity requires coverage_status=full" in joined


def test_autosci_feature_parity_gate_strict_full_acceptance_allows_verified_gated_side_effect_route() -> None:
    full_discover = base_item("discover")
    gated_daily = base_item(
        "daily-arxiv",
        coverage_status="gated",
        side_effect_policy="approval_required",
        semantic_parity="full",
        proof_level="E3",
    )
    mark_runtime_verified(gated_daily)
    payload = payload_with_items([full_discover, gated_daily])

    result = autosci_feature_parity_gate.evaluate_full_parity_acceptance(payload)

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_autosci_feature_parity_gate_rejects_missing_route() -> None:
    missing = base_item("future-skill", coverage_status="missing", side_effect_policy="unavailable")
    missing["solar_capability"] = "N/A"
    missing["solar_logical_operator"] = "N/A"
    missing["solar_backend_action"] = "N/A"
    payload = payload_with_items([base_item("discover"), missing])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "failed"
    assert "all discovered AutoSci native skills must have a Solar route" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_full_route_with_approval_gate() -> None:
    payload = payload_with_items([base_item("poster", coverage_status="full", side_effect_policy="approval_required")])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "failed"
    assert "cannot claim full coverage" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_full_route_with_fixture_limitation() -> None:
    item = base_item("exp-design", coverage_status="full", side_effect_policy="none")
    item["limitations"] = ["Fixture experiment plan is bounded to local evidence."]
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert result.status == "failed"
    assert "full coverage cannot describe fixture" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_semantic_full_without_e3_proof() -> None:
    item = base_item("discover", semantic_parity="full", proof_level="E2")
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert "semantic_parity=full requires proof_level E3 or higher" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_bridge_primary_tool_action_drift() -> None:
    item = base_item("paper-plan", coverage_status="partial", side_effect_policy="dry_run_only")
    item["solar_backend_action"] = "plan_report"
    item["primary_tools"] = ["plugins/autosci/bin/autosci_bridge.py run --action write_report"]
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "primary_tools bridge action" in joined
    assert "solar_backend_action plan_report" in joined


def test_autosci_feature_parity_gate_rejects_pending_runtime_without_requirement() -> None:
    item = base_item("daily-arxiv", coverage_status="gated", side_effect_policy="approval_required")
    item["proof_requirements"] = [
        requirement for requirement in item["proof_requirements"] if requirement["category"] != "external_runtime_evidence"
    ]
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert "runtime_proof_status=pending requires external_runtime_evidence requirement" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_runtime_status_count_drift() -> None:
    item = base_item("daily-arxiv", coverage_status="gated", side_effect_policy="approval_required")
    payload = payload_with_items([item])
    payload["outputs"]["parity"]["runtime_proof_status_counts"]["pending"] = 0

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert "runtime_proof_status_counts.pending=0 does not match actual 1" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_runtime_source_skill_mismatch() -> None:
    item = base_item("daily-arxiv", coverage_status="gated", side_effect_policy="approval_required")
    item["runtime_proof_status"] = "supplied"
    item["runtime_proof_refs"] = ["runtime:wrong-skill:test"]
    item["runtime_proof_sources"] = [
        {
            "proof_id": "runtime:wrong-skill:test",
            "native_skill": "novelty",
            "status": "supplied",
            "manifest_path": "/tmp/runtime-proof.json",
            "categories": ["external_runtime_evidence"],
            "evidence_refs": ["runtime:wrong-skill:test"],
            "evidence_ref_statuses": [
                {"ref": "runtime:wrong-skill:test", "status": "external_ref", "kind": "external"}
            ],
            "description": "Wrong skill proof should be rejected.",
        }
    ]
    for requirement in item["proof_requirements"]:
        if requirement["category"] == "external_runtime_evidence":
            requirement["status"] = "supplied"
            requirement["evidence_refs"] = ["runtime:wrong-skill:test"]
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    assert "runtime_proof_sources[0].native_skill must match item native_skill" in " ".join(result.reasons)


def test_autosci_feature_parity_gate_rejects_unknown_runtime_source_category() -> None:
    item = base_item("daily-arxiv", coverage_status="gated", side_effect_policy="approval_required")
    item["runtime_proof_status"] = "supplied"
    item["runtime_proof_refs"] = ["runtime:daily-arxiv:unknown-category"]
    item["runtime_proof_sources"] = [
        {
            "proof_id": "runtime:daily-arxiv:unknown-category",
            "native_skill": "daily-arxiv",
            "status": "supplied",
            "manifest_path": "/tmp/runtime-proof.json",
            "categories": ["unknown_runtime_category"],
            "evidence_refs": ["runtime:daily-arxiv:unknown-category"],
            "evidence_ref_statuses": [
                {"ref": "runtime:daily-arxiv:unknown-category", "status": "external_ref", "kind": "external"}
            ],
            "description": "Unknown proof category should be rejected.",
        }
    ]
    payload = payload_with_items([item])

    result = autosci_feature_parity_gate.evaluate(payload)

    assert result.ok is False
    joined = " ".join(result.reasons)
    assert "runtime_proof_status=supplied requires at least one supplied proof requirement" in joined
    assert "unknown_runtime_category" in joined
