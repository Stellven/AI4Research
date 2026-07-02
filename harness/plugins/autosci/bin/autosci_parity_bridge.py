#!/usr/bin/env python3
"""AutoSci native-skill parity inventory for Solar-native routes."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_HARNESS = Path(__file__).resolve().parents[3]
REPO_ROOT = REPO_HARNESS.parent
OUTPUT_HARNESS = Path(
    os.environ.get("SOLAR_AUTOSCI_OUTPUT_HARNESS")
    or os.environ.get("HARNESS_DIR", REPO_HARNESS)
).resolve()
CONFIG_PATH = REPO_HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
DEFAULT_AUTOSCI_REPO = REPO_ROOT.parent / "AutoSci"
SCHEMA = "autosci_feature_parity.v1"
SEMANTIC_AUDIT_SCHEMA = "autosci_semantic_parity_audit.v1"
SEMANTIC_PARITY_VALUES = {"full", "partial", "missing"}
EXECUTION_POLICY_VALUES = {"pure", "bounded_local", "approval_required", "provider_required"}
PROOF_LEVELS = ("E0", "E1", "E2", "E3", "E4", "E5")
RUNTIME_PROOF_STATUS_VALUES = ("not_required", "pending", "supplied", "verified")
PROOF_REQUIREMENT_STATUS_VALUES = ("ok", "pending", "supplied", "missing", "blocked")
RUNTIME_VERIFICATION_REQUIREMENT_CATEGORIES = {
    "approval_boundary_evidence",
    "external_runtime_evidence",
    "provider_source_evidence",
    "review_llm_or_model_evidence",
    "side_effect_execution_evidence",
    "wiki_mutation_evidence",
}
RUNTIME_PROOF_COLLECTION_MODES = {
    "approved_side_effect",
    "live_provider",
    "manual_review",
    "native_autosci_replay",
    "production_dispatch",
    "semantic_audit",
}
PATH_LIKE_SUFFIXES = (".json", ".jsonl", ".md", ".txt", ".pdf", ".tex", ".log", ".csv", ".tsv", ".yaml", ".yml")
EXTERNAL_REF_PREFIXES = ("runtime:", "route:", "native:", "doi:", "s2:", "arxiv:", "http://", "https://")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def resolve_output(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "artifacts":
        return OUTPUT_HARNESS / path
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate
    repo_candidate = REPO_ROOT / path
    if repo_candidate.exists():
        return repo_candidate
    if path.parts and path.parts[0] == REPO_HARNESS.name:
        return REPO_ROOT / path
    return OUTPUT_HARNESS / path


def default_output(skill: str | None = None) -> Path:
    name = f"autosci_feature_parity.{skill}.json" if skill else "autosci_feature_parity.json"
    return OUTPUT_HARNESS / "artifacts" / "autosci" / "phase19" / name


def discover_native_skills(autosci_repo: Path) -> tuple[list[str], list[str]]:
    skills_root = autosci_repo / "i18n" / "en" / "skills"
    if not skills_root.exists():
        return [], [f"AutoSci skills root not found: {skills_root}"]
    skills = sorted(path.parent.name for path in skills_root.glob("*/SKILL.md"))
    if not skills:
        return [], [f"AutoSci skills root contains no SKILL.md files: {skills_root}"]
    return skills, []


def route_items(
    routes: list[dict[str, Any]],
    native_skills: list[str],
    *,
    runtime_proofs_by_skill: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    native_set = set(native_skills)
    runtime_proofs_by_skill = runtime_proofs_by_skill or {}
    items: list[dict[str, Any]] = []
    for route in sorted(routes, key=lambda item: str(item.get("native_skill") or "")):
        skill = str(route.get("native_skill") or "")
        item = dict(route)
        runtime_proof_sources = runtime_proofs_by_skill.get(skill, [])
        supplied_runtime_proofs = [
            proof for proof in runtime_proof_sources if str(proof.get("status") or "") == "supplied"
        ]
        semantic_audit_verified, semantic_audit_refs, semantic_audit_reasons = semantic_audit_full_verified(
            skill,
            runtime_proof_sources,
        )
        tool_status = primary_tool_statuses(item.get("primary_tools") or [])
        missing_tools = [entry for entry in tool_status if entry["status"] == "missing"]
        item["autosci_feature"] = route.get("autosci_command") or f"/{skill}"
        item["evidence_ids"] = [
            f"route:{skill}",
            f"native:{skill}" if skill in native_set else f"config-only:{skill}",
        ]
        item["tool_abi_status"] = "missing" if missing_tools else "ok"
        item["primary_tool_statuses"] = tool_status
        item["missing_primary_tools"] = missing_tools
        item["semantic_parity"] = "full" if semantic_audit_verified else semantic_parity(route)
        item["semantic_audit_status"] = "verified" if semantic_audit_verified else (
            "not_supplied" if not semantic_audit_reasons else "inconclusive"
        )
        item["semantic_audit_refs"] = semantic_audit_refs
        if semantic_audit_reasons:
            item["semantic_audit_reasons"] = semantic_audit_reasons
        item["execution_policy"] = execution_policy(route)
        item["proof_level"] = proof_level(route, missing_tools=missing_tools)
        if semantic_audit_verified and PROOF_LEVELS.index(item["proof_level"]) < PROOF_LEVELS.index("E3"):
            item["proof_level"] = "E3"
        item["proof_refs"] = non_empty_string_list(route.get("proof_refs")) or list(item["evidence_ids"])
        item["remaining_requirements"] = (
            non_empty_string_list(route.get("remaining_requirements"))
            or default_remaining_requirements(item)
        )
        runtime_refs = _unique_strings([
            *non_empty_string_list(route.get("runtime_proof_refs")),
            *runtime_proof_refs(supplied_runtime_proofs),
        ])
        supplied_categories = runtime_proof_categories(supplied_runtime_proofs)
        item["runtime_proof_refs"] = runtime_refs
        item["runtime_proof_sources"] = runtime_proof_sources
        item["proof_requirements"] = proof_requirements(
            item,
            route,
            skill_in_native=skill in native_set,
            missing_tools=missing_tools,
            runtime_refs=runtime_refs,
            supplied_categories=supplied_categories,
        )
        item["runtime_proof_status"] = runtime_proof_status_from_requirements(
            item,
            runtime_refs=runtime_refs,
            requirements=item["proof_requirements"],
        )
        item["coverage_status"] = coverage_status_from_verified_requirements(
            item,
            requirements=item["proof_requirements"],
        )
        item["proof_level"] = proof_level_from_verified_requirements(
            item,
            requirements=item["proof_requirements"],
        )
        items.append(item)
    return items


def non_empty_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def semantic_parity(route: dict[str, Any]) -> str:
    configured = str(route.get("semantic_parity") or "").strip()
    if configured in SEMANTIC_PARITY_VALUES:
        return configured
    coverage = str(route.get("coverage_status") or "").strip()
    if coverage == "full":
        return "full"
    if coverage == "missing":
        return "missing"
    return "partial"


def execution_policy(route: dict[str, Any]) -> str:
    configured = str(route.get("execution_policy") or "").strip()
    if configured in EXECUTION_POLICY_VALUES:
        return configured
    side_effect_policy = str(route.get("side_effect_policy") or "").strip()
    backend_mode = str(route.get("backend_mode") or "").strip()
    if side_effect_policy == "none":
        return "pure"
    if side_effect_policy == "dry_run_only":
        return "bounded_local"
    if side_effect_policy == "approval_required":
        return "approval_required"
    if backend_mode in {"external_optional", "side_effect_gated"}:
        return "provider_required"
    return "provider_required"


def proof_level(route: dict[str, Any], *, missing_tools: list[dict[str, Any]]) -> str:
    configured = str(route.get("proof_level") or "").strip()
    if configured in PROOF_LEVELS:
        return configured
    coverage = str(route.get("coverage_status") or "").strip()
    if coverage == "missing" or missing_tools:
        return "E0"
    if coverage == "full":
        return "E3"
    return "E2"


def default_remaining_requirements(item: dict[str, Any]) -> list[str]:
    semantic = str(item.get("semantic_parity") or "")
    limits = non_empty_string_list(item.get("limitations"))
    if semantic == "full":
        return []
    return limits or ["Complete and audit the remaining native AutoSci parity requirements for this route."]


def runtime_proof_required(item: dict[str, Any]) -> bool:
    backend_mode = str(item.get("backend_mode") or "")
    side_effect_policy = str(item.get("side_effect_policy") or "")
    execution = str(item.get("execution_policy") or "")
    text = route_text(item)
    return (
        backend_mode in {"external_optional", "side_effect_gated"}
        or side_effect_policy == "approval_required"
        or execution in {"approval_required", "provider_required"}
        or any(marker in text for marker in ("provider", "runtime evidence", "live ", "external", "remote", "api"))
    )


def runtime_proof_status(item: dict[str, Any], *, runtime_refs: list[str]) -> str:
    if not runtime_proof_required(item):
        return "not_required"
    if runtime_refs:
        return "supplied"
    return "pending"


def runtime_proof_status_from_requirements(
    item: dict[str, Any],
    *,
    runtime_refs: list[str],
    requirements: list[dict[str, Any]],
) -> str:
    base = runtime_proof_status(item, runtime_refs=runtime_refs)
    if base != "supplied":
        return base
    unresolved = [
        requirement
        for requirement in requirements
        if str(requirement.get("category") or "") in RUNTIME_VERIFICATION_REQUIREMENT_CATEGORIES
        if str(requirement.get("status") or "") not in {"ok", "supplied"}
    ]
    return "verified" if not unresolved else "supplied"


def requirements_all_satisfied(requirements: list[dict[str, Any]]) -> bool:
    if not requirements:
        return False
    return all(str(requirement.get("status") or "") in {"ok", "supplied"} for requirement in requirements)


def coverage_status_from_verified_requirements(
    item: dict[str, Any],
    *,
    requirements: list[dict[str, Any]],
) -> str:
    configured = str(item.get("coverage_status") or "").strip()
    if configured in {"missing", "blocked"}:
        return configured
    if str(item.get("tool_abi_status") or "") != "ok":
        return configured or "partial"
    if str(item.get("semantic_parity") or "") != "full":
        return configured or "partial"
    if not requirements_all_satisfied(requirements):
        return configured or "partial"
    runtime_status = str(item.get("runtime_proof_status") or "")
    if runtime_status not in {"verified", "not_required"}:
        return configured or "partial"
    if str(item.get("side_effect_policy") or "") == "approval_required" or str(item.get("backend_mode") or "") == "side_effect_gated":
        return "gated"
    return "full"


def proof_level_from_verified_requirements(
    item: dict[str, Any],
    *,
    requirements: list[dict[str, Any]],
) -> str:
    current = str(item.get("proof_level") or "")
    if current not in PROOF_LEVELS:
        current = "E0"
    if str(item.get("native_skill") or "") != "research":
        return current
    if PROOF_LEVELS.index(current) >= PROOF_LEVELS.index("E4"):
        return current
    if str(item.get("semantic_parity") or "") != "full":
        return current
    if str(item.get("runtime_proof_status") or "") not in {"verified", "not_required"}:
        return current
    if str(item.get("coverage_status") or "") not in {"full", "gated"}:
        return current
    if not requirements_all_satisfied(requirements):
        return current
    return "E4"


def runtime_proof_refs(proofs: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for proof in proofs:
        refs.append(str(proof.get("proof_id") or ""))
        refs.extend(non_empty_string_list(proof.get("evidence_refs")))
    return _unique_strings(refs)


def is_path_like_ref(ref: str) -> bool:
    text = ref.strip()
    if not text or text.startswith(EXTERNAL_REF_PREFIXES):
        return False
    if text.startswith(("/", "./", "../", "~")):
        return True
    if "/" in text:
        return True
    return text.lower().endswith(PATH_LIKE_SUFFIXES)


def evidence_ref_status(ref: str) -> dict[str, str]:
    text = str(ref or "").strip()
    if not text:
        return {"ref": text, "status": "missing", "kind": "empty"}
    if not is_path_like_ref(text):
        return {"ref": text, "status": "external_ref", "kind": "external"}
    path = resolve_output(text).expanduser()
    return {
        "ref": text,
        "status": "ok" if path.exists() else "missing",
        "kind": "local_path",
        "path": str(path),
    }


def runtime_proof_categories(proofs: list[dict[str, Any]]) -> set[str]:
    categories: set[str] = set()
    for proof in proofs:
        for category in non_empty_string_list(proof.get("categories")):
            categories.add(category)
    return categories


def semantic_audit_checks_pass(checks: Any) -> bool:
    if not isinstance(checks, list) or not checks:
        return False
    for check in checks:
        if not isinstance(check, dict):
            return False
        if str(check.get("status") or "").strip().lower() not in {"ok", "pass", "passed"}:
            return False
    return True


def resolve_audit_ref(ref: str, *, audit_path: Path) -> Path | None:
    text = str(ref or "").strip()
    if not text or text.startswith(EXTERNAL_REF_PREFIXES):
        return None
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    candidates = [
        resolve_output(text),
        audit_path.parent / path,
        REPO_ROOT / path,
        Path.cwd() / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def semantic_audit_validation_errors(payload: dict[str, Any], *, audit_path: Path, skill: str) -> list[str]:
    errors: list[str] = []
    if str(payload.get("schema") or "") != SEMANTIC_AUDIT_SCHEMA:
        errors.append(f"audit schema must be {SEMANTIC_AUDIT_SCHEMA}")
    if str(payload.get("status") or "") != "completed":
        errors.append("audit status must be completed")
    audit_skill = str(payload.get("native_skill") or "").strip()
    if not audit_skill:
        errors.append("audit native_skill is required")
    elif audit_skill != skill:
        errors.append(f"audit native_skill must match {skill}")
    if str(payload.get("semantic_parity") or "") != "full":
        errors.append("audit semantic_parity must be full")
    if not str(payload.get("auditor") or "").strip():
        errors.append("audit auditor is required")
    native_refs = non_empty_string_list(payload.get("native_evidence_refs"))
    solar_refs = non_empty_string_list(payload.get("solar_evidence_refs"))
    if not native_refs:
        errors.append("audit native_evidence_refs are required")
    if not solar_refs:
        errors.append("audit solar_evidence_refs are required")
    if not semantic_audit_checks_pass(payload.get("acceptance_checks")):
        errors.append("audit acceptance_checks must all pass")
    for ref in [*native_refs, *solar_refs]:
        resolved = resolve_audit_ref(ref, audit_path=audit_path)
        if resolved is not None and not resolved.exists():
            errors.append(f"audit evidence ref does not exist: {ref}")
    return errors


def semantic_audit_full_verified(skill: str, proofs: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
    reasons: list[str] = []
    for proof in proofs:
        categories = set(non_empty_string_list(proof.get("categories")))
        if "semantic_equivalence_evidence" not in categories:
            continue
        proof_id = str(proof.get("proof_id") or "semantic-proof")
        if str(proof.get("status") or "") != "supplied":
            block_reasons = non_empty_string_list(proof.get("block_reasons"))
            reasons.extend(
                [f"{proof_id}: {reason}" for reason in block_reasons]
                or [f"{proof_id}: proof status is {proof.get('status') or 'not_supplied'}"]
            )
            continue
        if str(proof.get("collection_mode") or "") != "semantic_audit":
            reasons.append(f"{proof_id}: collection_mode is not semantic_audit")
            continue
        provenance = proof.get("provenance") if isinstance(proof.get("provenance"), dict) else {}
        if str(provenance.get("artifact_kind") or "") != SEMANTIC_AUDIT_SCHEMA:
            reasons.append(f"{proof_id}: provenance artifact_kind is not {SEMANTIC_AUDIT_SCHEMA}")
            continue
        audit_ref_errors: list[str] = []
        for ref in non_empty_string_list(proof.get("evidence_refs")):
            if not is_path_like_ref(ref):
                continue
            path = resolve_output(ref).expanduser()
            if not path.exists() or not path.is_file() or path.suffix.lower() != ".json":
                continue
            try:
                payload = load_json(path)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                audit_ref_errors.append(f"{proof_id}: invalid audit JSON {ref}: {exc}")
                continue
            errors = semantic_audit_validation_errors(payload, audit_path=path, skill=skill)
            if errors:
                audit_ref_errors.extend(f"{proof_id}: {error}" for error in errors)
                continue
            return True, [ref], []
        reasons.extend(audit_ref_errors or [f"{proof_id}: no verified semantic parity audit JSON was found"])
    return False, [], _unique_strings(reasons)


def runtime_proof_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def runtime_proof_provenance(value: Any) -> tuple[dict[str, str], list[str]]:
    if not isinstance(value, dict):
        return {}, ["provenance must be an object"]
    provenance = {
        "source": str(value.get("source") or value.get("provider") or value.get("tool") or "").strip(),
        "captured_at": str(value.get("captured_at") or value.get("collected_at") or value.get("timestamp") or "").strip(),
        "artifact_kind": str(value.get("artifact_kind") or value.get("kind") or "").strip(),
    }
    command = str(value.get("command") or value.get("route_invocation") or "").strip()
    if command:
        provenance["command"] = command
    missing = [field for field in ("source", "captured_at", "artifact_kind") if not provenance.get(field)]
    return provenance, [f"provenance.{field} is required" for field in missing]


def route_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("native_skill", "backend_mode", "side_effect_policy", "solar_backend_action"):
        parts.append(str(item.get(field) or ""))
    for field in ("limitations", "required_capabilities", "primary_tools"):
        value = item.get(field)
        if isinstance(value, list):
            parts.extend(str(entry or "") for entry in value)
    return " ".join(parts).lower()


def proof_requirement(
    *,
    category: str,
    status: str,
    description: str,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "status": status,
        "description": description,
        "evidence_refs": non_empty_string_list(evidence_refs or []),
    }


def proof_requirements(
    item: dict[str, Any],
    route: dict[str, Any],
    *,
    skill_in_native: bool,
    missing_tools: list[dict[str, Any]],
    runtime_refs: list[str],
    supplied_categories: set[str] | None = None,
) -> list[dict[str, Any]]:
    supplied_categories = supplied_categories or set()
    skill = str(item.get("native_skill") or "")
    tool_refs = [
        str(entry.get("ref") or entry.get("path") or "")
        for entry in item.get("primary_tool_statuses", [])
        if isinstance(entry, dict)
    ]
    requirements = [
        proof_requirement(
            category="route_definition",
            status="ok",
            description="Solar route declaration exists in feature_parity_routes.v1.json.",
            evidence_refs=[f"route:{skill}"],
        ),
        proof_requirement(
            category="native_skill_presence",
            status="ok" if skill_in_native else "missing",
            description="Discovered AutoSci native skill file exists under i18n/en/skills.",
            evidence_refs=[f"native:{skill}" if skill_in_native else f"config-only:{skill}"],
        ),
        proof_requirement(
            category="primary_tool_abi",
            status="missing" if missing_tools else "ok",
            description="Primary Solar tool/config references resolve locally or are declared external.",
            evidence_refs=tool_refs,
        ),
    ]
    semantic = str(item.get("semantic_parity") or "")
    semantic_supplied = "semantic_equivalence_evidence" in supplied_categories
    if semantic != "full" or semantic_supplied:
        requirements.append(
            proof_requirement(
                category="semantic_equivalence_evidence",
                status="supplied" if semantic_supplied else "pending",
                description="Route still needs audited native AutoSci semantic equivalence proof before semantic full parity.",
                evidence_refs=runtime_refs if semantic_supplied else non_empty_string_list(item.get("proof_refs")),
            )
        )
    external_runtime_required = runtime_proof_required(item)
    external_runtime_supplied = "external_runtime_evidence" in supplied_categories
    if external_runtime_required or external_runtime_supplied:
        requirements.append(
            proof_requirement(
                category="external_runtime_evidence",
                status="supplied" if external_runtime_supplied else "pending",
                description=(
                    "Route supplied external runtime evidence for model/review execution."
                    if external_runtime_supplied and not external_runtime_required
                    else "Route needs approved provider/runtime execution evidence before external behavior can be considered complete."
                ),
                evidence_refs=runtime_refs,
            )
        )
    side_effect_policy = str(item.get("side_effect_policy") or "")
    backend_mode = str(item.get("backend_mode") or "")
    approval_supplied = "approval_boundary_evidence" in supplied_categories
    if side_effect_policy == "approval_required" or approval_supplied:
        requirements.append(
            proof_requirement(
                category="approval_boundary_evidence",
                status="supplied" if approval_supplied else "pending",
                description="Side-effecting route requires durable approval, allowlist, before/after, and result evidence.",
                evidence_refs=runtime_refs,
            )
        )
    side_effect_supplied = "side_effect_execution_evidence" in supplied_categories
    if backend_mode == "side_effect_gated" or side_effect_supplied:
        requirements.append(
            proof_requirement(
                category="side_effect_execution_evidence",
                status="supplied" if side_effect_supplied else "pending",
                description="Gated side-effect route needs approved execution or provider delivery proof.",
                evidence_refs=runtime_refs,
            )
        )
    text = route_text({**item, **route})
    if "review llm" in text or "model" in text or "llm" in text:
        requirements.append(
            proof_requirement(
                category="review_llm_or_model_evidence",
                status="supplied" if "review_llm_or_model_evidence" in supplied_categories else "pending",
                description="Model/Review LLM-dependent route needs persisted request/response or supplied review evidence.",
                evidence_refs=runtime_refs,
            )
        )
    source_markers = ("source", "provider", "semantic scholar", "arxiv", "deepxiv", "web search", "online", "feed")
    if any(marker in text for marker in source_markers):
        requirements.append(
            proof_requirement(
                category="provider_source_evidence",
                status="supplied" if "provider_source_evidence" in supplied_categories else "pending",
                description="Source-dependent route needs non-fixture provider/source-channel evidence.",
                evidence_refs=runtime_refs,
            )
        )
    if "wiki" in text and ("write" in text or "mutation" in text or "set-meta" in text or "add-edge" in text):
        requirements.append(
            proof_requirement(
                category="wiki_mutation_evidence",
                status="supplied" if "wiki_mutation_evidence" in supplied_categories else "pending",
                description="Wiki-mutating route needs approved before/after mutation and rebuild evidence.",
                evidence_refs=runtime_refs,
            )
        )
    return requirements


def load_runtime_proof_manifests(paths: list[str]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]], list[str]]:
    proofs_by_skill: dict[str, list[dict[str, Any]]] = {}
    artifacts: list[dict[str, str]] = []
    warnings: list[str] = []
    for raw_path in paths:
        path = resolve_output(raw_path)
        artifacts.append({"type": "runtime_proof_manifest", "path": str(path)})
        if not path.exists():
            warnings.append(f"Runtime proof manifest not found: {path}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            warnings.append(f"Runtime proof manifest is not valid JSON: {path}: {exc}")
            continue
        proofs_raw = payload.get("proofs") if isinstance(payload, dict) else None
        if isinstance(payload, dict) and isinstance(proofs_raw, list):
            proofs_iter = proofs_raw
        elif isinstance(payload, dict):
            proofs_iter = [payload]
        else:
            warnings.append(f"Runtime proof manifest must be a JSON object or contain proofs list: {path}")
            continue
        for index, proof_raw in enumerate(proofs_iter):
            if not isinstance(proof_raw, dict):
                warnings.append(f"Runtime proof manifest entry {path}#{index} is not an object")
                continue
            skill = str(proof_raw.get("native_skill") or proof_raw.get("skill") or "").strip()
            if not skill:
                warnings.append(f"Runtime proof manifest entry {path}#{index} has no native_skill")
                continue
            proof_id = str(proof_raw.get("proof_id") or proof_raw.get("id") or f"{path.name}#{index}").strip()
            evidence_refs = non_empty_string_list(proof_raw.get("evidence_refs"))
            evidence_statuses = [evidence_ref_status(ref) for ref in evidence_refs]
            missing_refs = [
                status
                for status in evidence_statuses
                if status.get("kind") == "local_path" and status.get("status") != "ok"
            ]
            collection_mode = str(proof_raw.get("collection_mode") or "").strip()
            production_ready = runtime_proof_bool(proof_raw.get("production_ready"))
            provenance, provenance_errors = runtime_proof_provenance(proof_raw.get("provenance"))
            block_reasons: list[str] = []
            if not evidence_refs:
                block_reasons.append("evidence_refs must include at least one runtime artifact")
            if missing_refs:
                block_reasons.append("one or more local evidence_refs are missing")
            if not collection_mode:
                block_reasons.append("collection_mode is required")
            elif collection_mode not in RUNTIME_PROOF_COLLECTION_MODES:
                block_reasons.append(
                    "collection_mode must be one of "
                    + ", ".join(sorted(RUNTIME_PROOF_COLLECTION_MODES))
                )
            if not production_ready:
                block_reasons.append("production_ready must be true for supplied runtime proof")
            block_reasons.extend(provenance_errors)
            normalized = {
                "proof_id": proof_id,
                "native_skill": skill,
                "status": "blocked" if block_reasons else "supplied",
                "manifest_path": str(path),
                "categories": non_empty_string_list(proof_raw.get("categories")) or ["external_runtime_evidence"],
                "collection_mode": collection_mode,
                "production_ready": production_ready,
                "provenance": provenance,
                "block_reasons": block_reasons,
                "evidence_refs": evidence_refs,
                "evidence_ref_statuses": evidence_statuses,
                "description": str(proof_raw.get("description") or "Runtime proof was supplied via manifest.").strip(),
            }
            proofs_by_skill.setdefault(skill, []).append(normalized)
    return proofs_by_skill, artifacts, warnings


def _looks_like_runtime_proof_manifest(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if str(payload.get("schema") or "") == "autosci_runtime_proof_manifest.v1":
        return True
    return isinstance(payload.get("proofs"), list)


def discover_runtime_proof_manifests(dirs: list[str]) -> tuple[list[str], list[dict[str, str]], list[str]]:
    manifests: list[str] = []
    artifacts: list[dict[str, str]] = []
    warnings: list[str] = []
    for raw_dir in dirs:
        path = resolve_output(raw_dir)
        artifacts.append({"type": "runtime_proof_dir", "path": str(path)})
        if not path.exists():
            warnings.append(f"Runtime proof directory not found: {path}")
            continue
        if not path.is_dir():
            warnings.append(f"Runtime proof directory is not a directory: {path}")
            continue
        for candidate in sorted(path.rglob("*.json")):
            if _looks_like_runtime_proof_manifest(candidate):
                manifests.append(str(candidate))
    return _unique_strings(manifests), artifacts, warnings


def local_evidence_ref(path: Path) -> str:
    resolved = path.expanduser().resolve()
    for root in (OUTPUT_HARNESS, REPO_ROOT, Path.cwd()):
        try:
            return str(resolved.relative_to(root.resolve()))
        except ValueError:
            continue
    return str(resolved)


def semantic_audit_timestamp(payload: dict[str, Any]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    for value in (payload.get("audited_at"), payload.get("generated_at"), provenance.get("timestamp")):
        text = str(value or "").strip()
        if text:
            return text
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def semantic_audit_evidence_refs(payload: dict[str, Any], *, audit_path: Path) -> list[str]:
    refs = [local_evidence_ref(audit_path)]
    for raw_ref in [
        *non_empty_string_list(payload.get("native_evidence_refs")),
        *non_empty_string_list(payload.get("solar_evidence_refs")),
    ]:
        resolved = resolve_audit_ref(raw_ref, audit_path=audit_path)
        refs.append(str(raw_ref) if resolved is None else local_evidence_ref(resolved))
    return _unique_strings(refs)


def _looks_like_semantic_audit(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and str(payload.get("schema") or "") == SEMANTIC_AUDIT_SCHEMA


def discover_semantic_audits(dirs: list[str]) -> tuple[list[str], list[dict[str, str]], list[str]]:
    audits: list[str] = []
    artifacts: list[dict[str, str]] = []
    warnings: list[str] = []
    for raw_dir in dirs:
        path = resolve_output(raw_dir)
        artifacts.append({"type": "semantic_audit_dir", "path": str(path)})
        if not path.exists():
            warnings.append(f"Semantic audit directory not found: {path}")
            continue
        if not path.is_dir():
            warnings.append(f"Semantic audit path is not a directory: {path}")
            continue
        for candidate in sorted(path.rglob("*.json")):
            if _looks_like_semantic_audit(candidate):
                audits.append(str(candidate))
    return _unique_strings(audits), artifacts, warnings


def load_semantic_audit_proofs(paths: list[str]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]], list[str]]:
    proofs_by_skill: dict[str, list[dict[str, Any]]] = {}
    artifacts: list[dict[str, str]] = []
    warnings: list[str] = []
    for raw_path in paths:
        path = resolve_output(raw_path)
        artifacts.append({"type": "semantic_parity_audit", "path": str(path)})
        if not path.exists():
            warnings.append(f"Semantic audit not found: {path}")
            continue
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            warnings.append(f"Semantic audit is not valid JSON: {path}: {exc}")
            continue
        skill = str(payload.get("native_skill") or "").strip()
        if not skill:
            warnings.append(f"Semantic audit has no native_skill: {path}")
            continue
        evidence_refs = semantic_audit_evidence_refs(payload, audit_path=path)
        block_reasons = semantic_audit_validation_errors(payload, audit_path=path, skill=skill)
        captured_at = semantic_audit_timestamp(payload)
        proof = {
            "proof_id": f"runtime:{skill}:semantic-audit:{path.stem}",
            "native_skill": skill,
            "status": "blocked" if block_reasons else "supplied",
            "manifest_path": str(path),
            "categories": ["semantic_equivalence_evidence"],
            "collection_mode": "semantic_audit",
            "production_ready": not block_reasons,
            "provenance": {
                "source": str(payload.get("auditor") or "semantic_parity_audit").strip(),
                "captured_at": captured_at,
                "artifact_kind": SEMANTIC_AUDIT_SCHEMA,
                "command": "autosci_parity_bridge.py semantic-audit ingestion",
            },
            "block_reasons": block_reasons,
            "evidence_refs": evidence_refs,
            "evidence_ref_statuses": [evidence_ref_status(ref) for ref in evidence_refs],
            "description": "Semantic parity audit supplied directly to the parity inventory.",
        }
        proofs_by_skill.setdefault(skill, []).append(proof)
    return proofs_by_skill, artifacts, warnings


def merge_runtime_proofs(
    *sources: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        for skill, proofs in source.items():
            merged.setdefault(skill, []).extend(proofs)
    return merged


def primary_tool_statuses(primary_tools: list[Any]) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for raw in primary_tools:
        ref = str(raw or "").strip()
        token = ref.split()[0] if ref else ""
        if not token or token == "N/A":
            continue
        candidates = local_tool_candidates(token)
        if not candidates:
            statuses.append({"ref": ref, "token": token, "status": "external"})
            continue
        existing = next((path for path in candidates if path.exists()), None)
        statuses.append(
            {
                "ref": ref,
                "token": token,
                "status": "ok" if existing else "missing",
                "path": str(existing or candidates[0]),
            }
        )
    return statuses


def local_tool_candidates(token: str) -> list[Path]:
    if token.startswith("tools/"):
        return [REPO_ROOT / token]
    if token.startswith("plugins/"):
        return [REPO_HARNESS / token]
    if token.startswith("harness/"):
        return [REPO_ROOT / token]
    if token.startswith("config/"):
        return [REPO_HARNESS / "plugins" / "autosci" / token, REPO_ROOT / token]
    if token == ".env.example":
        return [REPO_HARNESS / "plugins" / "autosci" / "config" / token, REPO_ROOT / token]
    if token.endswith((".py", ".md", ".json", ".yml", ".yaml")):
        return [REPO_ROOT / token, REPO_HARNESS / token]
    return []


def add_missing_items(items: list[dict[str, Any]], native_skills: list[str]) -> list[dict[str, Any]]:
    routed = {str(item.get("native_skill") or "") for item in items}
    missing = sorted(set(native_skills) - routed)
    for skill in missing:
        items.append(
            {
                "autosci_feature": f"/{skill}",
                "native_skill": skill,
                "feature_kind": "skill",
                "native_paths": [f"i18n/en/skills/{skill}/SKILL.md"],
                "solar_capability": "N/A",
                "solar_logical_operator": "N/A",
                "solar_backend_action": "N/A",
                "coverage_status": "missing",
                "backend_mode": "route_plan",
                "side_effect_policy": "unavailable",
                "semantic_parity": "missing",
                "execution_policy": "provider_required",
                "proof_level": "E0",
                "proof_refs": [f"missing:{skill}"],
                "remaining_requirements": ["Configure a Solar route for this discovered AutoSci native skill."],
                "runtime_proof_refs": [],
                "runtime_proof_sources": [],
                "runtime_proof_status": "pending",
                "proof_requirements": [
                    proof_requirement(
                        category="route_definition",
                        status="missing",
                        description="No Solar route declaration exists for this discovered native skill.",
                        evidence_refs=[f"missing:{skill}"],
                    ),
                    proof_requirement(
                        category="native_skill_presence",
                        status="ok",
                        description="Discovered AutoSci native skill file exists under i18n/en/skills.",
                        evidence_refs=[f"native:{skill}"],
                    ),
                    proof_requirement(
                        category="semantic_equivalence_evidence",
                        status="pending",
                        description="No Solar semantic equivalence proof exists until a route is configured.",
                        evidence_refs=[],
                    ),
                ],
                "evidence_schema": SCHEMA,
                "primary_tools": ["N/A"],
                "required_capabilities": ["Solar route definition"],
                "limitations": ["No Solar route is configured for this discovered AutoSci native skill."],
                "evidence_ids": [f"missing:{skill}"],
            }
        )
    return sorted(items, key=lambda item: str(item.get("native_skill") or ""))


def count(items: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("coverage_status") == status)


def count_field(items: list[dict[str, Any]], field: str, value: str) -> int:
    return sum(1 for item in items if item.get(field) == value)


def value_counts(items: list[dict[str, Any]], field: str, values: tuple[str, ...] | set[str]) -> dict[str, int]:
    return {value: count_field(items, field, value) for value in values}


def proof_requirement_status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
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


def build_evidence(
    *,
    autosci_repo: Path,
    requested_skill: str | None = None,
    runtime_proof_manifests: list[str] | None = None,
    runtime_proof_dirs: list[str] | None = None,
    semantic_audits: list[str] | None = None,
    semantic_audit_dirs: list[str] | None = None,
) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    routes = config.get("routes")
    if not isinstance(routes, list):
        raise ValueError(f"{CONFIG_PATH} routes must be a list")

    native_skills, discovery_warnings = discover_native_skills(autosci_repo)
    discovered_runtime_manifests, runtime_dir_artifacts, runtime_dir_warnings = discover_runtime_proof_manifests(
        runtime_proof_dirs or []
    )
    runtime_manifest_paths = _unique_strings([*(runtime_proof_manifests or []), *discovered_runtime_manifests])
    runtime_proofs, runtime_manifest_artifacts, runtime_manifest_warnings = load_runtime_proof_manifests(
        runtime_manifest_paths
    )
    discovered_semantic_audits, semantic_audit_dir_artifacts, semantic_audit_dir_warnings = discover_semantic_audits(
        semantic_audit_dirs or []
    )
    semantic_audit_paths = _unique_strings([*(semantic_audits or []), *discovered_semantic_audits])
    semantic_proofs, semantic_audit_artifacts, semantic_audit_warnings = load_semantic_audit_proofs(
        semantic_audit_paths
    )
    runtime_proofs = merge_runtime_proofs(runtime_proofs, semantic_proofs)
    configured_items = route_items(
        [route for route in routes if isinstance(route, dict)],
        native_skills,
        runtime_proofs_by_skill=runtime_proofs,
    )
    if requested_skill:
        configured_items = [
            item for item in configured_items if item.get("native_skill") == requested_skill
        ]
        native_skills = [skill for skill in native_skills if skill == requested_skill]
        if not configured_items:
            native_skills = sorted(set(native_skills + [requested_skill]))
    items = add_missing_items(configured_items, native_skills)

    missing_count = count(items, "missing")
    status = "completed"
    if discovery_warnings or runtime_manifest_warnings or semantic_audit_dir_warnings or semantic_audit_warnings:
        status = "inconclusive"
    if missing_count:
        status = "failed"

    limitations = [
        "Phase 19 parity evidence verifies Solar-native route coverage, not live execution of external services.",
        "Side effects such as secrets, remote execution, SMTP, browser rendering, GitHub Actions, and destructive reset remain approval-gated.",
        "Local primary tool/config references are checked for ABI existence; external executables/providers are represented as external requirements.",
    ]
    limitations.extend(discovery_warnings)
    limitations.extend(runtime_dir_warnings)
    limitations.extend(runtime_manifest_warnings)
    limitations.extend(semantic_audit_dir_warnings)
    limitations.extend(semantic_audit_warnings)
    return {
        "schema": SCHEMA,
        "task_id": "phase19-autosci-feature-parity",
        "sprint_id": "phase19",
        "node_id": "autosci-feature-parity-inventory" if not requested_skill else f"autosci-feature-parity-{requested_skill}",
        "status": status,
        "inputs": {
            "autosci_repo": str(autosci_repo),
            "route_config": str(CONFIG_PATH),
            "requested_skill": requested_skill or "N/A",
            "runtime_proof_manifests": runtime_proof_manifests or [],
            "runtime_proof_dirs": runtime_proof_dirs or [],
            "runtime_proof_manifest_paths": runtime_manifest_paths,
            "semantic_audits": semantic_audits or [],
            "semantic_audit_dirs": semantic_audit_dirs or [],
            "semantic_audit_paths": semantic_audit_paths,
        },
        "outputs": {
            "parity": {
                "config_version": str(config.get("version") or "unknown"),
                "autosci_repo": str(autosci_repo),
                "native_skill_count": len(native_skills),
                "configured_route_count": len(items),
                "routed_count": len(items) - missing_count,
                "missing_route_count": missing_count,
                "full_count": count(items, "full"),
                "partial_count": count(items, "partial"),
                "gated_count": count(items, "gated"),
                "blocked_count": count(items, "blocked"),
                "semantic_full_count": count_field(items, "semantic_parity", "full"),
                "semantic_partial_count": count_field(items, "semantic_parity", "partial"),
                "semantic_missing_count": count_field(items, "semantic_parity", "missing"),
                "execution_policy_counts": value_counts(items, "execution_policy", EXECUTION_POLICY_VALUES),
                "proof_level_counts": value_counts(items, "proof_level", PROOF_LEVELS),
                "runtime_proof_status_counts": value_counts(items, "runtime_proof_status", RUNTIME_PROOF_STATUS_VALUES),
                "proof_requirement_status_counts": proof_requirement_status_counts(items),
                "native_skills": native_skills,
                "items": items,
            }
        },
        "artifacts": [
            {
                "type": "route_config",
                "path": str(CONFIG_PATH),
            },
            *runtime_manifest_artifacts,
            *runtime_dir_artifacts,
            *semantic_audit_artifacts,
            *semantic_audit_dir_artifacts,
        ],
        "provenance": {
            "operator_id": "AutoSciFeatureParityBridge",
            "implementation_package": "harness.plugins.autosci",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        "limitations": limitations,
    }


def write_evidence(payload: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_inventory(args: argparse.Namespace) -> int:
    autosci_repo = Path(args.autosci_repo).expanduser().resolve()
    payload = build_evidence(
        autosci_repo=autosci_repo,
        runtime_proof_manifests=list(args.runtime_proof_manifest or []),
        runtime_proof_dirs=list(args.runtime_proof_dir or []),
        semantic_audits=list(args.semantic_audit or []),
        semantic_audit_dirs=list(args.semantic_audit_dir or []),
    )
    out_path = resolve_output(args.out) if args.out else default_output()
    write_evidence(payload, out_path)
    parity = payload["outputs"]["parity"]
    print(
        json.dumps(
            {
                "ok": payload["status"] == "completed",
                "schema": SCHEMA,
                "evidence_path": str(out_path),
                "native_skill_count": parity["native_skill_count"],
                "routed_count": parity["routed_count"],
                "missing_route_count": parity["missing_route_count"],
                "full_count": parity["full_count"],
                "partial_count": parity["partial_count"],
                "gated_count": parity["gated_count"],
                "semantic_full_count": parity["semantic_full_count"],
                "semantic_partial_count": parity["semantic_partial_count"],
                "semantic_missing_count": parity["semantic_missing_count"],
                "runtime_proof_status_counts": parity["runtime_proof_status_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "completed" else 2


def run_route(args: argparse.Namespace) -> int:
    autosci_repo = Path(args.autosci_repo).expanduser().resolve()
    payload = build_evidence(
        autosci_repo=autosci_repo,
        requested_skill=args.skill,
        runtime_proof_manifests=list(args.runtime_proof_manifest or []),
        runtime_proof_dirs=list(args.runtime_proof_dir or []),
        semantic_audits=list(args.semantic_audit or []),
        semantic_audit_dirs=list(args.semantic_audit_dir or []),
    )
    out_path = resolve_output(args.out) if args.out else default_output(args.skill)
    write_evidence(payload, out_path)
    parity = payload["outputs"]["parity"]
    print(
        json.dumps(
            {
                "ok": payload["status"] == "completed",
                "schema": SCHEMA,
                "evidence_path": str(out_path),
                "skill": args.skill,
                "routed_count": parity["routed_count"],
                "missing_route_count": parity["missing_route_count"],
                "semantic_full_count": parity["semantic_full_count"],
                "semantic_partial_count": parity["semantic_partial_count"],
                "semantic_missing_count": parity["semantic_missing_count"],
                "runtime_proof_status_counts": parity["runtime_proof_status_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "completed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--autosci-repo",
        default=os.environ.get("AUTOSCI_REPO", str(DEFAULT_AUTOSCI_REPO)),
        help="Path to the AutoSci checkout. Defaults to AUTOSCI_REPO or a sibling checkout.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="Write full native-skill route parity evidence")
    inventory.add_argument("--out", help="Output JSON path, relative to HARNESS_DIR when not absolute")
    inventory.add_argument(
        "--runtime-proof-manifest",
        action="append",
        default=[],
        help="Explicit autosci_runtime_proof_manifest.v1 JSON file to attach as supplied runtime proof.",
    )
    inventory.add_argument(
        "--runtime-proof-dir",
        action="append",
        default=[],
        help="Directory recursively scanned for autosci_runtime_proof_manifest.v1 JSON files.",
    )
    inventory.add_argument(
        "--semantic-audit",
        action="append",
        default=[],
        help="Explicit autosci_semantic_parity_audit.v1 JSON file to attach as semantic equivalence proof.",
    )
    inventory.add_argument(
        "--semantic-audit-dir",
        action="append",
        default=[],
        help="Directory recursively scanned for autosci_semantic_parity_audit.v1 JSON files.",
    )
    inventory.set_defaults(func=run_inventory)

    route = subparsers.add_parser("route", help="Write parity evidence for one native AutoSci skill")
    route.add_argument("--skill", required=True, help="Native AutoSci skill name, for example daily-arxiv")
    route.add_argument("--out", help="Output JSON path, relative to HARNESS_DIR when not absolute")
    route.add_argument(
        "--runtime-proof-manifest",
        action="append",
        default=[],
        help="Explicit autosci_runtime_proof_manifest.v1 JSON file to attach as supplied runtime proof.",
    )
    route.add_argument(
        "--runtime-proof-dir",
        action="append",
        default=[],
        help="Directory recursively scanned for autosci_runtime_proof_manifest.v1 JSON files.",
    )
    route.add_argument(
        "--semantic-audit",
        action="append",
        default=[],
        help="Explicit autosci_semantic_parity_audit.v1 JSON file to attach as semantic equivalence proof.",
    )
    route.add_argument(
        "--semantic-audit-dir",
        action="append",
        default=[],
        help="Directory recursively scanned for autosci_semantic_parity_audit.v1 JSON files.",
    )
    route.set_defaults(func=run_route)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
