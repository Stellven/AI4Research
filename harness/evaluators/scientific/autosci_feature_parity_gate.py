#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluators.scientific.common import (  # noqa: E402
    GateResult,
    check_artifact_paths,
    finish,
    has_any_evidence_ids,
    limitations,
    load_json,
    outputs,
    require_non_empty_list,
    require_non_empty_string,
    validate_schema,
)

SCHEMA = "autosci_feature_parity.v1"
SEMANTIC_PARITY_VALUES = {"full", "partial", "missing"}
EXECUTION_POLICY_VALUES = {"pure", "bounded_local", "approval_required", "provider_required"}
PROOF_LEVELS = ("E0", "E1", "E2", "E3", "E4", "E5")
PROOF_LEVEL_RANK = {value: index for index, value in enumerate(PROOF_LEVELS)}
RUNTIME_PROOF_STATUS_VALUES = {"not_required", "pending", "supplied", "verified"}
PROOF_REQUIREMENT_STATUS_VALUES = {"ok", "pending", "supplied", "missing", "blocked"}
RUNTIME_PROOF_COLLECTION_MODES = {
    "approved_side_effect",
    "live_provider",
    "manual_review",
    "native_autosci_replay",
    "production_dispatch",
    "semantic_audit",
}
FULL_PARITY_RUNTIME_OK = {"not_required", "verified"}
FULL_PARITY_UNRESOLVED_REQUIREMENT_STATUSES = {"pending", "missing", "blocked"}


def _count(items: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("coverage_status") == status)


def _bridge_actions(primary_tools: Any) -> list[str]:
    if not isinstance(primary_tools, list):
        return []
    actions: list[str] = []
    for raw in primary_tools:
        text = str(raw or "")
        if "autosci_bridge.py" not in text or "--action" not in text:
            continue
        try:
            tokens = shlex.split(text)
        except ValueError:
            tokens = text.split()
        for index, token in enumerate(tokens):
            if token == "--action" and index + 1 < len(tokens):
                actions.append(tokens[index + 1])
            elif token.startswith("--action="):
                actions.append(token.split("=", 1)[1])
    return actions


def _proof_requirement_status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {value: 0 for value in PROOF_REQUIREMENT_STATUS_VALUES}
    for item in items:
        requirements = item.get("proof_requirements")
        if not isinstance(requirements, list):
            continue
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            status = str(requirement.get("status") or "")
            if status in counts:
                counts[status] += 1
    return counts


def evaluate(payload: dict[str, Any], path: str | Path | None = None):
    reasons, warnings = validate_schema(payload, SCHEMA)
    parity = outputs(payload).get("parity")
    if not isinstance(parity, dict):
        reasons.append("outputs.parity must be an object")
        return finish(payload, reasons, warnings, path=path)

    items_raw = require_non_empty_list(parity.get("items"), "outputs.parity.items", reasons)
    items: list[dict[str, Any]] = []
    for index, item in enumerate(items_raw):
        if not isinstance(item, dict):
            reasons.append(f"items[{index}] must be an object")
            continue
        items.append(item)

    native_skills_raw = require_non_empty_list(parity.get("native_skills"), "outputs.parity.native_skills", reasons)
    native_skills = [str(skill) for skill in native_skills_raw if isinstance(skill, str) and skill.strip()]
    item_skills: set[str] = set()
    for index, item in enumerate(items):
        skill = require_non_empty_string(item.get("native_skill"), f"items[{index}].native_skill", reasons)
        if skill in item_skills:
            reasons.append(f"items[{index}].native_skill duplicates route for {skill}")
        if skill:
            item_skills.add(skill)
        for field in (
            "autosci_feature",
            "feature_kind",
            "solar_capability",
            "solar_logical_operator",
            "solar_backend_action",
            "coverage_status",
            "backend_mode",
            "side_effect_policy",
            "semantic_parity",
            "execution_policy",
            "proof_level",
            "evidence_schema",
        ):
            require_non_empty_string(item.get(field), f"items[{index}].{field}", reasons)
        proof_refs = require_non_empty_list(item.get("proof_refs"), f"items[{index}].proof_refs", reasons)
        runtime_proof_status = require_non_empty_string(
            item.get("runtime_proof_status"),
            f"items[{index}].runtime_proof_status",
            reasons,
        )
        runtime_proof_refs = item.get("runtime_proof_refs")
        if not isinstance(runtime_proof_refs, list):
            reasons.append(f"items[{index}].runtime_proof_refs must be a list")
            runtime_proof_refs = []
        runtime_proof_sources = item.get("runtime_proof_sources")
        if not isinstance(runtime_proof_sources, list):
            reasons.append(f"items[{index}].runtime_proof_sources must be a list")
            runtime_proof_sources = []
        runtime_source_categories: set[str] = set()
        for source_index, source in enumerate(runtime_proof_sources):
            if not isinstance(source, dict):
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}] must be an object")
                continue
            require_non_empty_string(
                source.get("proof_id"),
                f"items[{index}].runtime_proof_sources[{source_index}].proof_id",
                reasons,
            )
            source_skill = require_non_empty_string(
                source.get("native_skill"),
                f"items[{index}].runtime_proof_sources[{source_index}].native_skill",
                reasons,
            )
            source_status = require_non_empty_string(
                source.get("status"),
                f"items[{index}].runtime_proof_sources[{source_index}].status",
                reasons,
            )
            require_non_empty_string(
                source.get("manifest_path"),
                f"items[{index}].runtime_proof_sources[{source_index}].manifest_path",
                reasons,
            )
            require_non_empty_string(
                source.get("description"),
                f"items[{index}].runtime_proof_sources[{source_index}].description",
                reasons,
            )
            collection_mode = require_non_empty_string(
                source.get("collection_mode"),
                f"items[{index}].runtime_proof_sources[{source_index}].collection_mode",
                reasons,
            )
            if collection_mode and collection_mode not in RUNTIME_PROOF_COLLECTION_MODES:
                reasons.append(
                    f"items[{index}].runtime_proof_sources[{source_index}].collection_mode must be one of "
                    f"{', '.join(sorted(RUNTIME_PROOF_COLLECTION_MODES))}"
                )
            production_ready = source.get("production_ready")
            if not isinstance(production_ready, bool):
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}].production_ready must be boolean")
            elif source_status == "supplied" and production_ready is not True:
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}] supplied proof requires production_ready=true")
            provenance = source.get("provenance")
            if not isinstance(provenance, dict):
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}].provenance must be an object")
            else:
                for provenance_field in ("source", "captured_at", "artifact_kind"):
                    require_non_empty_string(
                        provenance.get(provenance_field),
                        f"items[{index}].runtime_proof_sources[{source_index}].provenance.{provenance_field}",
                        reasons,
                    )
            block_reasons = source.get("block_reasons")
            if not isinstance(block_reasons, list):
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}].block_reasons must be a list")
            elif source_status == "blocked" and not block_reasons:
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}] blocked proof requires block_reasons")
            elif source_status == "supplied" and block_reasons:
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}] supplied proof must not include block_reasons")
            source_categories: set[str] = set()
            require_non_empty_list(
                source.get("categories"),
                f"items[{index}].runtime_proof_sources[{source_index}].categories",
                reasons,
            )
            if isinstance(source.get("categories"), list):
                source_categories = {
                    str(category)
                    for category in source.get("categories")
                    if str(category or "").strip()
                }
                runtime_source_categories.update(source_categories)
            require_non_empty_list(
                source.get("evidence_refs"),
                f"items[{index}].runtime_proof_sources[{source_index}].evidence_refs",
                reasons,
            )
            evidence_ref_statuses = require_non_empty_list(
                source.get("evidence_ref_statuses"),
                f"items[{index}].runtime_proof_sources[{source_index}].evidence_ref_statuses",
                reasons,
            )
            unresolved_refs = []
            for ref_index, ref_status in enumerate(evidence_ref_statuses):
                if not isinstance(ref_status, dict):
                    reasons.append(
                        f"items[{index}].runtime_proof_sources[{source_index}].evidence_ref_statuses[{ref_index}] must be an object"
                    )
                    continue
                ref_kind = require_non_empty_string(
                    ref_status.get("kind"),
                    f"items[{index}].runtime_proof_sources[{source_index}].evidence_ref_statuses[{ref_index}].kind",
                    reasons,
                )
                ref_state = require_non_empty_string(
                    ref_status.get("status"),
                    f"items[{index}].runtime_proof_sources[{source_index}].evidence_ref_statuses[{ref_index}].status",
                    reasons,
                )
                require_non_empty_string(
                    ref_status.get("ref"),
                    f"items[{index}].runtime_proof_sources[{source_index}].evidence_ref_statuses[{ref_index}].ref",
                    reasons,
                )
                if ref_kind == "local_path" and ref_state != "ok":
                    unresolved_refs.append(str(ref_status.get("ref") or ref_index))
            if source_skill and skill and source_skill != skill:
                reasons.append(
                    f"items[{index}].runtime_proof_sources[{source_index}].native_skill must match item native_skill"
                )
            if source_status and source_status not in {"supplied", "blocked"}:
                reasons.append(f"items[{index}].runtime_proof_sources[{source_index}].status must be supplied or blocked")
            if source_status == "supplied" and unresolved_refs:
                reasons.append(
                    f"items[{index}].runtime_proof_sources[{source_index}] supplied proof has unresolved local refs: "
                    f"{', '.join(unresolved_refs)}"
                )
            if source_status == "blocked":
                is_semantic_audit_block = (
                    collection_mode == "semantic_audit"
                    and source_categories == {"semantic_equivalence_evidence"}
                    and not unresolved_refs
                )
                if not is_semantic_audit_block:
                    if unresolved_refs:
                        reasons.append(
                            f"items[{index}].runtime_proof_sources[{source_index}] blocked proof has unresolved local refs: "
                            f"{', '.join(unresolved_refs)}"
                        )
                    else:
                        reasons.append(
                            f"items[{index}].runtime_proof_sources[{source_index}] blocked non-semantic proof is not accepted"
                        )
        proof_requirements_raw = require_non_empty_list(
            item.get("proof_requirements"),
            f"items[{index}].proof_requirements",
            reasons,
        )
        proof_requirement_categories: set[str] = set()
        proof_requirement_statuses: list[str] = []
        for req_index, requirement in enumerate(proof_requirements_raw):
            if not isinstance(requirement, dict):
                reasons.append(f"items[{index}].proof_requirements[{req_index}] must be an object")
                continue
            category = require_non_empty_string(
                requirement.get("category"),
                f"items[{index}].proof_requirements[{req_index}].category",
                reasons,
            )
            status = require_non_empty_string(
                requirement.get("status"),
                f"items[{index}].proof_requirements[{req_index}].status",
                reasons,
            )
            require_non_empty_string(
                requirement.get("description"),
                f"items[{index}].proof_requirements[{req_index}].description",
                reasons,
            )
            evidence_refs = requirement.get("evidence_refs")
            if not isinstance(evidence_refs, list):
                reasons.append(f"items[{index}].proof_requirements[{req_index}].evidence_refs must be a list")
            if category:
                proof_requirement_categories.add(category)
            if status:
                proof_requirement_statuses.append(status)
                if status not in PROOF_REQUIREMENT_STATUS_VALUES:
                    reasons.append(
                        f"items[{index}].proof_requirements[{req_index}].status must be one of "
                        f"{', '.join(sorted(PROOF_REQUIREMENT_STATUS_VALUES))}"
                    )
        remaining_requirements = item.get("remaining_requirements")
        if not isinstance(remaining_requirements, list):
            reasons.append(f"items[{index}].remaining_requirements must be a list")
        require_non_empty_list(item.get("native_paths"), f"items[{index}].native_paths", reasons)
        require_non_empty_list(item.get("primary_tools"), f"items[{index}].primary_tools", reasons)
        require_non_empty_list(item.get("required_capabilities"), f"items[{index}].required_capabilities", reasons)
        item_limits = require_non_empty_list(item.get("limitations"), f"items[{index}].limitations", reasons)
        bridge_actions = _bridge_actions(item.get("primary_tools"))
        backend_action = str(item.get("solar_backend_action") or "")
        if bridge_actions and backend_action not in bridge_actions:
            reasons.append(
                f"items[{index}].primary_tools bridge action(s) {', '.join(bridge_actions)} "
                f"must include solar_backend_action {backend_action}"
            )
        if not has_any_evidence_ids(item.get("evidence_ids")):
            reasons.append(f"items[{index}].evidence_ids must contain at least one id")
        tool_abi_status = str(item.get("tool_abi_status") or "")
        missing_primary_tools = item.get("missing_primary_tools")
        if tool_abi_status:
            if tool_abi_status not in {"ok", "missing"}:
                reasons.append(f"items[{index}].tool_abi_status must be ok or missing")
            if tool_abi_status == "missing":
                reasons.append(f"items[{index}] has missing primary tool/config references")
        if isinstance(missing_primary_tools, list) and missing_primary_tools:
            missing_refs = ", ".join(str(entry.get("ref") or entry) for entry in missing_primary_tools if isinstance(entry, dict))
            reasons.append(f"items[{index}].missing_primary_tools must be empty: {missing_refs}")

        coverage = item.get("coverage_status")
        side_effect_policy = item.get("side_effect_policy")
        semantic = str(item.get("semantic_parity") or "")
        execution = str(item.get("execution_policy") or "")
        proof = str(item.get("proof_level") or "")
        if semantic and semantic not in SEMANTIC_PARITY_VALUES:
            reasons.append(f"items[{index}].semantic_parity must be full, partial, or missing")
        if execution and execution not in EXECUTION_POLICY_VALUES:
            reasons.append(
                f"items[{index}].execution_policy must be pure, bounded_local, approval_required, or provider_required"
            )
        if proof and proof not in PROOF_LEVEL_RANK:
            reasons.append(f"items[{index}].proof_level must be one of {', '.join(PROOF_LEVELS)}")
        if runtime_proof_status and runtime_proof_status not in RUNTIME_PROOF_STATUS_VALUES:
            reasons.append(
                f"items[{index}].runtime_proof_status must be one of {', '.join(sorted(RUNTIME_PROOF_STATUS_VALUES))}"
            )
        if runtime_proof_status in {"supplied", "verified"} and not runtime_proof_refs:
            reasons.append(f"items[{index}].runtime_proof_status={runtime_proof_status} requires runtime_proof_refs")
        if runtime_proof_status == "supplied" and "supplied" not in proof_requirement_statuses:
            reasons.append(f"items[{index}].runtime_proof_status=supplied requires at least one supplied proof requirement")
        if runtime_proof_status == "pending" and "external_runtime_evidence" not in proof_requirement_categories:
            reasons.append(f"items[{index}].runtime_proof_status=pending requires external_runtime_evidence requirement")
        unknown_source_categories = sorted(runtime_source_categories - proof_requirement_categories)
        if unknown_source_categories:
            reasons.append(
                f"items[{index}].runtime_proof_sources categories are not declared proof requirements: "
                f"{', '.join(unknown_source_categories)}"
            )
        if proof_refs and semantic == "full" and PROOF_LEVEL_RANK.get(proof, -1) < PROOF_LEVEL_RANK["E3"]:
            reasons.append(f"items[{index}] semantic_parity=full requires proof_level E3 or higher")
        if semantic == "full" and str(item.get("native_skill") or "") == "research" and PROOF_LEVEL_RANK.get(proof, -1) < PROOF_LEVEL_RANK["E4"]:
            reasons.append("research semantic_parity=full requires recoverable lifecycle proof_level E4 or higher")
        if semantic == "missing" and coverage != "missing":
            reasons.append(f"items[{index}] semantic_parity=missing requires coverage_status=missing")
        if semantic in {"partial", "missing"} and isinstance(remaining_requirements, list) and not remaining_requirements:
            reasons.append(f"items[{index}].remaining_requirements must explain non-full semantic parity")
        if semantic in {"partial", "missing"} and not any(
            status in {"pending", "missing", "blocked"} for status in proof_requirement_statuses
        ):
            reasons.append(f"items[{index}].proof_requirements must include unresolved proof for non-full semantic parity")
        if execution in {"approval_required", "provider_required"} and "external_runtime_evidence" not in proof_requirement_categories:
            reasons.append(f"items[{index}].execution_policy={execution} requires external_runtime_evidence requirement")
        if side_effect_policy == "approval_required" and "approval_boundary_evidence" not in proof_requirement_categories:
            reasons.append(f"items[{index}] approval_required side effects require approval_boundary_evidence requirement")
        if coverage == "full" and side_effect_policy not in {"none", "dry_run_only"}:
            reasons.append(
                f"items[{index}] cannot claim full coverage while side_effect_policy={side_effect_policy}"
            )
        if coverage == "full":
            limitation_text = " ".join(str(item).lower() for item in item_limits)
            overclaim_markers = (
                "fixture",
                "smoke only",
                "smoke evidence only",
                "not yet implemented",
                "not fully implemented",
                "local surrogate",
            )
            if any(marker in limitation_text for marker in overclaim_markers):
                reasons.append(f"items[{index}] full coverage cannot describe fixture/smoke-only or unimplemented behavior")
        if coverage in {"partial", "gated", "blocked", "missing"} and not item_limits:
            reasons.append(f"items[{index}] must explain limitations for {coverage} coverage")
        if coverage == "gated" and side_effect_policy != "approval_required":
            reasons.append(f"items[{index}] gated coverage requires approval_required side effect policy")
        if coverage == "missing" and side_effect_policy != "unavailable":
            reasons.append(f"items[{index}] missing coverage requires unavailable side effect policy")

    missing_native = sorted(set(native_skills) - item_skills)
    extra_routes = sorted(item_skills - set(native_skills))
    if missing_native:
        reasons.append(f"native skills without route: {', '.join(missing_native)}")
    if extra_routes:
        warnings.append(f"routes without discovered native skill: {', '.join(extra_routes)}")

    expected_native_count = int(parity.get("native_skill_count") or 0)
    if expected_native_count != len(native_skills):
        reasons.append(
            f"native_skill_count={expected_native_count} does not match native_skills length={len(native_skills)}"
        )
    expected_configured_count = int(parity.get("configured_route_count") or 0)
    if expected_configured_count != len(items):
        reasons.append(
            f"configured_route_count={expected_configured_count} does not match items length={len(items)}"
        )
    routed_count = int(parity.get("routed_count") or 0)
    missing_route_count = int(parity.get("missing_route_count") or 0)
    actual_missing = _count(items, "missing") + len(missing_native)
    actual_routed = len(items) - _count(items, "missing")
    if routed_count != actual_routed:
        reasons.append(f"routed_count={routed_count} does not match actual routed count={actual_routed}")
    if missing_route_count != actual_missing:
        reasons.append(
            f"missing_route_count={missing_route_count} does not match actual missing count={actual_missing}"
        )
    if missing_route_count:
        reasons.append("all discovered AutoSci native skills must have a Solar route")

    count_fields = {
        "full_count": _count(items, "full"),
        "partial_count": _count(items, "partial"),
        "gated_count": _count(items, "gated"),
        "blocked_count": _count(items, "blocked"),
    }
    for field, actual in count_fields.items():
        expected = int(parity.get(field) or 0)
        if expected != actual:
            reasons.append(f"{field}={expected} does not match actual {actual}")
    semantic_count_fields = {
        "semantic_full_count": sum(1 for item in items if item.get("semantic_parity") == "full"),
        "semantic_partial_count": sum(1 for item in items if item.get("semantic_parity") == "partial"),
        "semantic_missing_count": sum(1 for item in items if item.get("semantic_parity") == "missing"),
    }
    for field, actual in semantic_count_fields.items():
        expected = int(parity.get(field) or 0)
        if expected != actual:
            reasons.append(f"{field}={expected} does not match actual {actual}")
    execution_policy_counts = parity.get("execution_policy_counts")
    if not isinstance(execution_policy_counts, dict):
        reasons.append("outputs.parity.execution_policy_counts must be an object")
    else:
        for value in EXECUTION_POLICY_VALUES:
            expected = int(execution_policy_counts.get(value) or 0)
            actual = sum(1 for item in items if item.get("execution_policy") == value)
            if expected != actual:
                reasons.append(f"execution_policy_counts.{value}={expected} does not match actual {actual}")
    proof_level_counts = parity.get("proof_level_counts")
    if not isinstance(proof_level_counts, dict):
        reasons.append("outputs.parity.proof_level_counts must be an object")
    else:
        for value in PROOF_LEVELS:
            expected = int(proof_level_counts.get(value) or 0)
            actual = sum(1 for item in items if item.get("proof_level") == value)
            if expected != actual:
                reasons.append(f"proof_level_counts.{value}={expected} does not match actual {actual}")
    runtime_proof_status_counts = parity.get("runtime_proof_status_counts")
    if not isinstance(runtime_proof_status_counts, dict):
        reasons.append("outputs.parity.runtime_proof_status_counts must be an object")
    else:
        for value in RUNTIME_PROOF_STATUS_VALUES:
            expected = int(runtime_proof_status_counts.get(value) or 0)
            actual = sum(1 for item in items if item.get("runtime_proof_status") == value)
            if expected != actual:
                reasons.append(f"runtime_proof_status_counts.{value}={expected} does not match actual {actual}")
    proof_requirement_status_counts = parity.get("proof_requirement_status_counts")
    if not isinstance(proof_requirement_status_counts, dict):
        reasons.append("outputs.parity.proof_requirement_status_counts must be an object")
    else:
        actual_counts = _proof_requirement_status_counts(items)
        for value in PROOF_REQUIREMENT_STATUS_VALUES:
            expected = int(proof_requirement_status_counts.get(value) or 0)
            actual = actual_counts.get(value, 0)
            if expected != actual:
                reasons.append(f"proof_requirement_status_counts.{value}={expected} does not match actual {actual}")
    if count_fields["partial_count"] or count_fields["gated_count"] or count_fields["blocked_count"]:
        warnings.append("parity inventory includes non-full routes; downstream execution must respect limitations")
    if semantic_count_fields["semantic_partial_count"] or semantic_count_fields["semantic_missing_count"]:
        warnings.append("semantic parity includes non-full routes; proof levels and remaining requirements are authoritative")

    if not limitations(payload):
        reasons.append("top-level limitations must describe parity scope")
    check_artifact_paths(payload, path, reasons)
    return finish(payload, reasons, warnings, path=path)


def full_parity_acceptance_reasons(payload: dict[str, Any]) -> list[str]:
    parity = outputs(payload).get("parity")
    if not isinstance(parity, dict):
        return ["outputs.parity must be an object before full parity acceptance can be evaluated"]
    items = parity.get("items")
    if not isinstance(items, list) or not items:
        return ["outputs.parity.items must be non-empty before full parity acceptance can be evaluated"]

    reasons: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            reasons.append(f"items[{index}] must be an object before full parity acceptance can be evaluated")
            continue
        skill = str(item.get("native_skill") or f"items[{index}]")
        semantic = str(item.get("semantic_parity") or "")
        coverage = str(item.get("coverage_status") or "")
        side_effect_policy = str(item.get("side_effect_policy") or "")
        runtime_status = str(item.get("runtime_proof_status") or "")
        proof = str(item.get("proof_level") or "")

        if semantic != "full":
            reasons.append(f"{skill}: full parity requires semantic_parity=full")
        required_proof_level = "E4" if skill == "research" else "E3"
        if PROOF_LEVEL_RANK.get(proof, -1) < PROOF_LEVEL_RANK[required_proof_level]:
            reasons.append(f"{skill}: full parity requires proof_level {required_proof_level} or higher")
        if runtime_status not in FULL_PARITY_RUNTIME_OK:
            reasons.append(f"{skill}: full parity requires runtime_proof_status verified or not_required")

        requirements = item.get("proof_requirements")
        if not isinstance(requirements, list) or not requirements:
            reasons.append(f"{skill}: full parity requires non-empty proof_requirements")
        else:
            unresolved = [
                f"{str(requirement.get('category') or 'unknown')}:{str(requirement.get('status') or 'unknown')}"
                for requirement in requirements
                if isinstance(requirement, dict)
                and str(requirement.get("status") or "") in FULL_PARITY_UNRESOLVED_REQUIREMENT_STATUSES
            ]
            if unresolved:
                reasons.append(f"{skill}: full parity has unresolved proof requirements: {', '.join(unresolved)}")

        remaining = [
            str(requirement).strip()
            for requirement in item.get("remaining_requirements", [])
            if str(requirement or "").strip() and str(requirement or "").strip() != "N/A"
        ]
        if remaining:
            reasons.append(f"{skill}: full parity requires remaining_requirements to be empty")

        if side_effect_policy == "approval_required":
            if coverage != "gated":
                reasons.append(f"{skill}: approval-required full parity must remain coverage_status=gated")
        elif coverage != "full":
            reasons.append(f"{skill}: full parity requires coverage_status=full")

    return reasons


def evaluate_full_parity_acceptance(payload: dict[str, Any], path: str | Path | None = None) -> GateResult:
    base = evaluate(payload, path)
    if not base.ok:
        return base
    reasons = full_parity_acceptance_reasons(payload)
    warnings = list(base.warnings)
    if reasons:
        warnings.append("strict full parity acceptance failed; ordinary parity honesty/schema gate may still pass")
    return finish(payload, reasons, warnings, path=path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument(
        "--require-full-parity",
        action="store_true",
        help="Fail unless every route satisfies strict final full-parity acceptance.",
    )
    args = parser.parse_args(argv)
    try:
        payload = load_json(args.path)
        evaluator = evaluate_full_parity_acceptance if args.require_full_parity else evaluate
        result = evaluator(payload, args.path)
    except Exception as exc:  # noqa: BLE001 - gate CLI should return structured failure.
        result = GateResult(
            ok=False,
            status="failed",
            reasons=[f"{type(exc).__name__}: {exc}"],
            schema=SCHEMA,
            path=args.path,
        )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.status == "passed":
        return 0
    if result.status == "inconclusive":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
