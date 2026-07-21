#!/usr/bin/env python3
"""Deterministic AutoSci route parity inventory for pre-unification work."""
from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_DIR.parent
DEFAULT_NATIVE_REPO = REPO_ROOT.parent / "AutoSci"

ROUTE_CONFIG = HARNESS_DIR / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
OPERATOR_BINDINGS = HARNESS_DIR / "plugins" / "autosci" / "config" / "feature_operator_bindings.v1.json"
PLUGIN_MANIFEST = HARNESS_DIR / "plugins" / "autosci" / "manifest.yaml"
LOGICAL_OPERATORS = HARNESS_DIR / "config" / "logical-operators.json"
PHYSICAL_OPERATORS = HARNESS_DIR / "config" / "physical-operators.json"
CAPABILITY_REGISTRY = HARNESS_DIR / "config" / "capability-capsules.registry.yaml"
SCHEMAS_DIR = HARNESS_DIR / "schemas" / "evidence"
GATES_DIR = HARNESS_DIR / "evaluators" / "scientific"
AUTOSCI_BRIDGE = HARNESS_DIR / "plugins" / "autosci" / "bin" / "autosci_bridge.py"

GATE_BY_SCHEMA = {
    "artifact_review.v1": "artifact_review_gate.py",
    "autosci_skill_run.v1": "autosci_skill_run_gate.py",
    "claim_verdict.v1": "claim_verdict_gate.py",
    "code_evidence_map.v1": "code_evidence_gate.py",
    "experiment_plan.v1": "experiment_plan_gate.py",
    "experiment_result.v1": "experiment_result_gate.py",
    "experiment_status.v1": "experiment_status_gate.py",
    "idea_candidate.v1": "idea_gate.py",
    "idea_evaluation.v1": "idea_gate.py",
    "literature_discovery.v1": "literature_discovery_gate.py",
    "publication_bundle.v1": "publication_gate.py",
    "research_claims.v1": "claims_gate.py",
    "research_graph_update.v1": "graph_update_gate.py",
    "research_memory_update.v1": "memory_update_gate.py",
    "research_method.v1": "method_gate.py",
    "research_paper.v1": "paper_gate.py",
    "scientific_lifecycle.v1": "lifecycle_gate.py",
    "scientific_report.v1": "report_gate.py",
    "workflow_evolution.v1": "workflow_evolution_gate.py",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def discover_native_skills(native_repo: Path) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    roots = [
        native_repo / "i18n" / "en" / "skills",
        native_repo / ".claude" / "skills",
    ]
    skills: set[str] = set()
    for root in roots:
        if not root.exists():
            warnings.append(f"native skills root missing: {root}")
            continue
        skills.update(path.parent.name for path in root.glob("*/SKILL.md"))
    return sorted(skills), warnings


def load_capability_registry(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(
        re.findall(
            r"^\s*-?\s*capability_capsule_id:\s*([^\s]+)\s*$",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def load_manifest_capabilities(path: Path) -> set[str]:
    if not path.exists():
        return set()
    capabilities: set[str] = set()
    in_capabilities = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "capabilities:":
            in_capabilities = True
            continue
        if in_capabilities and line and not line.startswith((" ", "\t")):
            break
        if in_capabilities:
            match = re.match(r"^\s*-\s*['\"]?([^'\"\s]+)['\"]?\s*$", line)
            if match:
                capabilities.add(match.group(1))
    return capabilities


def load_bridge_actions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ACTIONS" for target in node.targets):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "ACTIONS":
            value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Dict):
            return set()
        actions: set[str] = set()
        for key in value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                actions.add(key.value)
        return actions
    return set()


def gate_for_schema(schema: str) -> str:
    configured = GATE_BY_SCHEMA.get(schema)
    if configured:
        return configured
    stem = schema.replace(".v1", "").replace("-", "_")
    return f"{stem}_gate.py"


def logical_binding_actor_ids(logical_payload: dict[str, Any], logical_operator: str) -> list[str]:
    bindings = logical_payload.get("bindings")
    if not isinstance(bindings, dict):
        return []
    binding = bindings.get(logical_operator)
    if not isinstance(binding, dict):
        return []
    candidates = binding.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [
        str(candidate.get("actor_id") or "")
        for candidate in candidates
        if isinstance(candidate, dict) and str(candidate.get("actor_id") or "").strip()
    ]


def coverage_count(routes: list[dict[str, Any]], status: str) -> int:
    return sum(1 for route in routes if route.get("coverage_status") == status)


def status_for_route(route: dict[str, Any], *, live_markers: tuple[str, ...]) -> bool:
    fields = [
        str(route.get("native_skill") or ""),
        str(route.get("autosci_command") or ""),
        str(route.get("solar_backend_action") or ""),
        str(route.get("backend_mode") or ""),
        str(route.get("side_effect_policy") or ""),
        " ".join(str(item) for item in route.get("required_capabilities") or []),
        " ".join(str(item) for item in route.get("limitations") or []),
    ]
    text = " ".join(fields).lower()
    return any(marker in text for marker in live_markers)


def build_inventory(native_repo: Path) -> dict[str, Any]:
    route_config = load_json(ROUTE_CONFIG)
    routes = [route for route in route_config.get("routes", []) if isinstance(route, dict)]
    routes_by_skill = {str(route.get("native_skill") or ""): route for route in routes}
    native_skills, native_warnings = discover_native_skills(native_repo)
    native_skill_set = set(native_skills)
    configured_skill_set = set(routes_by_skill)

    operator_bindings_payload = load_json(OPERATOR_BINDINGS) if OPERATOR_BINDINGS.exists() else {"bindings": []}
    feature_bindings = {
        str(binding.get("native_skill") or ""): binding
        for binding in operator_bindings_payload.get("bindings", [])
        if isinstance(binding, dict)
    }
    logical_payload = load_json(LOGICAL_OPERATORS)
    logical_operator_ids = set(logical_payload.get("logical_operators", {}))
    physical_payload = load_json(PHYSICAL_OPERATORS)
    physical_operator_ids = set(physical_payload.get("operators", {}))
    registry_capabilities = load_capability_registry(CAPABILITY_REGISTRY)
    manifest_capabilities = load_manifest_capabilities(PLUGIN_MANIFEST)
    bridge_actions = load_bridge_actions(AUTOSCI_BRIDGE)

    route_capabilities = {str(route.get("solar_capability") or "") for route in routes if route.get("solar_capability")}
    manifest_registry_drift = {
        "manifest_capabilities_missing_from_registry": sorted(manifest_capabilities - registry_capabilities),
        "route_capabilities_missing_from_manifest": sorted(route_capabilities - manifest_capabilities),
        "route_capabilities_missing_from_registry": sorted(route_capabilities - registry_capabilities),
    }

    route_capabilities_missing_from_registry: list[dict[str, str]] = []
    route_logical_operators_missing: list[dict[str, str]] = []
    route_physical_operator_binding_missing: list[dict[str, Any]] = []
    route_evidence_schemas_missing: list[dict[str, str]] = []
    route_backend_actions_missing: list[dict[str, str]] = []
    route_gate_missing: list[dict[str, str]] = []
    native_command_parity_by_command: dict[str, dict[str, Any]] = {}

    for skill in sorted(native_skill_set | configured_skill_set):
        route = routes_by_skill.get(skill, {})
        command = str(route.get("autosci_command") or f"/{skill}")
        capability = str(route.get("solar_capability") or "")
        logical_operator = str(route.get("solar_logical_operator") or "")
        backend_action = str(route.get("solar_backend_action") or "")
        evidence_schema = str(route.get("evidence_schema") or "")
        feature_binding = feature_bindings.get(skill, {})
        feature_physical_operator = str(feature_binding.get("physical_operator") or "")
        actor_ids = logical_binding_actor_ids(logical_payload, logical_operator)
        gate_file = gate_for_schema(evidence_schema) if evidence_schema else ""

        capability_registered = bool(capability and capability in registry_capabilities)
        logical_registered = bool(logical_operator and logical_operator in logical_operator_ids)
        feature_physical_registered = bool(feature_physical_operator)
        actor_binding_registered = bool(actor_ids and all(actor_id in physical_operator_ids for actor_id in actor_ids))
        schema_registered = bool(evidence_schema and (SCHEMAS_DIR / f"{evidence_schema}.schema.json").exists())
        gate_registered = bool(gate_file and (GATES_DIR / gate_file).exists())
        backend_registered = bool(backend_action and backend_action in bridge_actions)

        if route and not capability_registered:
            route_capabilities_missing_from_registry.append({"native_skill": skill, "solar_capability": capability or "N/A"})
        if route and not logical_registered:
            route_logical_operators_missing.append({"native_skill": skill, "solar_logical_operator": logical_operator or "N/A"})
        if route and (not feature_physical_registered or not actor_binding_registered):
            route_physical_operator_binding_missing.append(
                {
                    "native_skill": skill,
                    "feature_physical_operator": feature_physical_operator or "N/A",
                    "logical_actor_ids": actor_ids,
                    "actor_binding_registered": actor_binding_registered,
                }
            )
        if route and not schema_registered:
            route_evidence_schemas_missing.append({"native_skill": skill, "evidence_schema": evidence_schema or "N/A"})
        if route and not backend_registered:
            route_backend_actions_missing.append({"native_skill": skill, "solar_backend_action": backend_action or "N/A"})
        if route and not gate_registered:
            route_gate_missing.append({"native_skill": skill, "gate": gate_file or "N/A", "evidence_schema": evidence_schema or "N/A"})

        native_command_parity_by_command[command] = {
            "native_skill": skill,
            "native_skill_present": skill in native_skill_set,
            "route_present": bool(route),
            "coverage_status": str(route.get("coverage_status") or "missing"),
            "semantic_parity": str(route.get("semantic_parity") or ("missing" if not route else "partial")),
            "evidence_schema": evidence_schema or "N/A",
            "gate": gate_file or "N/A",
            "backend_action": backend_action or "N/A",
            "capability_registered": capability_registered,
            "logical_operator_registered": logical_registered,
            "physical_operator_binding_registered": feature_physical_registered and actor_binding_registered,
            "backend_action_registered": backend_registered,
            "evidence_schema_registered": schema_registered,
            "gate_registered": gate_registered,
            "limitations": route.get("limitations") or [],
        }

    missing_native_skills = sorted(native_skill_set - configured_skill_set)

    def proof_status(name: str, skills: list[str], reason: str) -> dict[str, Any]:
        statuses = [
            native_command_parity_by_command.get(str(routes_by_skill.get(skill, {}).get("autosci_command") or f"/{skill}"), {})
            for skill in skills
        ]
        route_statuses = sorted({str(item.get("coverage_status") or "missing") for item in statuses if item})
        if route_statuses and set(route_statuses) <= {"full"}:
            status = "verified"
        elif route_statuses:
            status = "pending"
        else:
            status = "missing"
        return {
            "name": name,
            "status": status,
            "routes": skills,
            "route_statuses": route_statuses,
            "reason": reason if status != "verified" else "All tracked routes are full.",
        }

    provider_routes = [
        str(route.get("native_skill") or "")
        for route in routes
        if status_for_route(route, live_markers=("provider", "live ", "api", "semantic scholar", "arxiv", "deepxiv", "review llm", "model"))
    ]

    return {
        "schema": "autosci_parity_inventory.v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inputs": {
            "native_repo": str(native_repo),
            "route_config": str(ROUTE_CONFIG),
            "operator_bindings": str(OPERATOR_BINDINGS),
            "logical_operators": str(LOGICAL_OPERATORS),
            "physical_operators": str(PHYSICAL_OPERATORS),
            "capability_registry": str(CAPABILITY_REGISTRY),
            "plugin_manifest": str(PLUGIN_MANIFEST),
        },
        "route_count": len(routes),
        "full_count": coverage_count(routes, "full"),
        "partial_count": coverage_count(routes, "partial"),
        "gated_count": coverage_count(routes, "gated"),
        "missing_route_count": len(missing_native_skills),
        "missing_native_skills": missing_native_skills,
        "native_skill_count": len(native_skills),
        "manifest_registry_drift": manifest_registry_drift,
        "route_capabilities_missing_from_registry": route_capabilities_missing_from_registry,
        "route_logical_operators_missing": route_logical_operators_missing,
        "route_physical_operator_binding_missing": route_physical_operator_binding_missing,
        "route_evidence_schemas_missing": route_evidence_schemas_missing,
        "route_backend_actions_missing": route_backend_actions_missing,
        "route_gate_missing": route_gate_missing,
        "native_command_parity_by_command": native_command_parity_by_command,
        "provider_live_proof_status": proof_status(
            "provider_live_proof_status",
            sorted(set(provider_routes)),
            "Provider/live routes require env-gated runtime proof manifests; route config alone is not live proof.",
        ),
        "remote_experiment_proof_status": proof_status(
            "remote_experiment_proof_status",
            ["exp-run", "exp-status"],
            "Remote experiment parity requires remote config, approval, execution, and collection evidence.",
        ),
        "paper_compile_proof_status": proof_status(
            "paper_compile_proof_status",
            ["paper-compile"],
            "Paper compile parity requires approved TeX runtime evidence and submission checks.",
        ),
        "review_llm_proof_status": proof_status(
            "review_llm_proof_status",
            ["review", "ideate", "novelty", "paper-draft", "rebuttal"],
            "Review LLM parity requires persisted model/review evidence; local surrogate output is not final acceptance.",
        ),
        "warnings": native_warnings,
    }


def write_inventory(payload: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-repo", default=str(DEFAULT_NATIVE_REPO), help="Read-only native AutoSci checkout")
    parser.add_argument("--out", required=True, help="Output JSON path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    native_repo = Path(args.native_repo).expanduser().resolve()
    out = Path(args.out).expanduser()
    payload = build_inventory(native_repo)
    write_inventory(payload, out)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out),
                "route_count": payload["route_count"],
                "missing_route_count": payload["missing_route_count"],
                "full_count": payload["full_count"],
                "partial_count": payload["partial_count"],
                "gated_count": payload["gated_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
