#!/usr/bin/env python3
"""skill_to_capsule_compiler.py — plugin/skill manifest to capability capsule drafts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from skill_operator_registry import SkillOperatorBinding, register_binding

HARNESS_DIR = Path(__file__).resolve().parent.parent
PLUGINS_DIR = HARNESS_DIR / "plugins"
CAPSULES_DIR = HARNESS_DIR / "config" / "capability-capsules"
REGISTRY_PATH = HARNESS_DIR / "config" / "capability-capsules.registry.yaml"

UNDERSTAND_ANYTHING_CAPABILITY_MAP: dict[str, dict[str, Any]] = {
    "understand-anything.knowledge_graph": {
        "capsule_id": "cap.understand-anything-knowledge-graph-builder",
        "logical_operator": "KnowledgeGraphBuilder",
        "command": "/understand-knowledge",
        "artifact": ".understand-anything/knowledge-graph.json",
        "task_types": ["knowledge-extraction", "code-understanding"],
        "positive_signals": ["understand-anything", "knowledge graph", "repo map", "architecture map"],
    },
    "understand-anything.domain_analysis": {
        "capsule_id": "cap.understand-anything-domain-analysis-builder",
        "logical_operator": "DomainAnalysisBuilder",
        "command": "/understand-domain",
        "artifact": ".understand-anything/domain-analysis.json",
        "task_types": ["knowledge-extraction", "analysis"],
        "positive_signals": ["domain analysis", "codebase understanding", "understand-anything"],
    },
    "understand-anything.tour": {
        "capsule_id": "cap.understand-anything-tour-builder",
        "logical_operator": "RepositoryTourBuilder",
        "command": "/understand-onboard",
        "artifact": ".understand-anything/onboarding-tour.md",
        "task_types": ["onboarding", "code-understanding"],
        "positive_signals": ["onboarding", "tour", "architecture walkthrough"],
    },
    "understand-anything.chat": {
        "capsule_id": "cap.understand-anything-chat-builder",
        "logical_operator": "CodebaseChatBuilder",
        "command": "/understand-chat",
        "artifact": ".understand-anything/chat-session.json",
        "task_types": ["code-understanding", "assistant"],
        "positive_signals": ["chat", "codebase q&a", "understand-anything"],
    },
}


@dataclass
class PluginManifest:
    plugin_id: str
    name: str
    path: Path
    description: str
    commands: list[str]
    capabilities: list[str]
    write_scope: list[str]
    read_scope: list[str]


@dataclass
class NormalizedCapability:
    plugin_id: str
    capability_id: str
    capsule_id: str
    logical_operator: str
    command: str
    artifact_path: str
    task_types: list[str]
    positive_signals: list[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def discover_plugins(harness_dir: Path | None = None, plugin_id: str | None = None) -> list[PluginManifest]:
    root = Path(harness_dir or HARNESS_DIR) / "plugins"
    manifests: list[PluginManifest] = []
    for manifest_path in sorted(root.glob("*/manifest.yaml")):
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            continue
        current_plugin_id = str(payload.get("id") or manifest_path.parent.name)
        if plugin_id and current_plugin_id != plugin_id:
            continue
        manifests.append(
            PluginManifest(
                plugin_id=current_plugin_id,
                name=str(payload.get("name") or current_plugin_id),
                path=manifest_path,
                description=str(payload.get("description") or ""),
                commands=[str(item) for item in payload.get("commands", []) or []],
                capabilities=[str(item) for item in payload.get("capabilities", []) or []],
                write_scope=[str(item) for item in payload.get("write_scope", []) or []],
                read_scope=[str(item) for item in payload.get("read_scope", []) or []],
            )
        )
    return manifests


def derive_physical_operator(capability_id: str) -> str:
    if str(capability_id).startswith("understand-anything."):
        return "mini-understand-anything-pane-bridge"
    return "mini-claude-sonnet-builder"


def derive_actor(capability_id: str) -> str:
    if str(capability_id).startswith("understand-anything."):
        return "codex"
    return "codex"


def normalize_capabilities(manifest: PluginManifest) -> list[NormalizedCapability]:
    normalized: list[NormalizedCapability] = []
    for capability_id in manifest.capabilities:
        mapping = UNDERSTAND_ANYTHING_CAPABILITY_MAP.get(capability_id)
        if mapping is None:
            continue
        normalized.append(
            NormalizedCapability(
                plugin_id=manifest.plugin_id,
                capability_id=capability_id,
                capsule_id=str(mapping["capsule_id"]),
                logical_operator=str(mapping["logical_operator"]),
                command=str(mapping["command"]),
                artifact_path=str(mapping["artifact"]),
                task_types=list(mapping["task_types"]),
                positive_signals=list(mapping["positive_signals"]),
            )
        )
    return normalized


def compile_capsule_draft(plugin_id: str, capability: NormalizedCapability) -> dict[str, Any]:
    operator_id = derive_physical_operator(capability.capability_id)
    return {
        "capability_capsule_id": capability.capsule_id,
        "version": "0.1.0",
        "capsule_kind": "capability",
        "metadata": {
            "name": capability.logical_operator,
            "description": f"Auto-compiled capability capsule for {plugin_id}:{capability.capability_id}.",
        },
        "applicability": {
            "task_types": list(capability.task_types),
            "positive_signals": list(capability.positive_signals),
            "negative_signals": ["browser", "finance"],
        },
        "contract": {
            "inputs": {
                "required": [{"name": "repo_path", "type": "path"}],
                "optional": [{"name": "language", "type": "string"}],
            },
            "outputs": {
                "required": [{"name": "knowledge_graph_path", "type": "path"}],
                "optional": [{"name": "actual_backend_used", "type": "string"}],
            },
            "preconditions": [
                {"check": "task_type_in", "values": list(capability.task_types)},
                {"check": "input_present", "field": "repo_path"},
            ],
            "postconditions": [{"check": "output_present", "field": "knowledge_graph_path"}],
            "invariants": [
                "Deterministic scan/parse stages remain separate from the semantic analysis stage.",
                "semantic_backend must remain ThunderOMLX for semantic analysis.",
            ],
        },
        "composition": {
            "consumes": [{"type": "artifact.repo_workspace"}],
            "produces": [{"type": "artifact.knowledge_graph"}],
            "compatible_with": ["resource.repo-workspace"],
            "incompatible_with": [],
            "requires_after": [],
        },
        "effects": {
            "read": ["workspace.repo"],
            "write": ["artifacts.knowledge_graph", "artifacts.operator_bridge_contract"],
            "execute": ["tmux_send_keys", capability.command],
            "network": [],
            "cost": ["local_runtime", "thunderomlx_local"],
            "risk": ["pane_target_mismatch"],
        },
        "bindings": {
            "skills": {"required": [f"skill.{plugin_id}"], "optional": []},
            "mcp_capabilities": {},
            "data_refs": ["data.repo_path"],
            "secret_refs": [],
            "required_guard_capsules": [],
            "required_resource_capsules": ["resource.repo-workspace"],
        },
        "runtime_preferences": {
            "execution_surface": "deterministic_scan_and_thunderomlx_semantic",
            "skill_command_template": f"{capability.command} {{repo_path}}",
            "pane_target": "best_effort",
            "semantic_backend": "ThunderOMLX",
            "semantic_phase_enforced": True,
            "success_artifact": capability.artifact_path,
        },
        "verification": {
            "self_check": [
                {"kind": "artifact_present", "path": capability.artifact_path},
                {"kind": "pattern_match", "pattern": r"actual_backend_used=ThunderOMLX"},
            ],
            "external_verifier": {"required": False},
            "pass_conditions": [
                {"kind": "artifact_present", "path": capability.artifact_path},
                {"kind": "pattern_match", "pattern": r"actual_backend_used=ThunderOMLX"},
            ],
        },
        "operator_compatibility": {
            "preferred": [operator_id],
            "forbidden": [],
        },
        "provenance": {
            "owner": "opensolar",
            "created_at": _now_iso(),
            "compiler": "skill_to_capsule_compiler",
        },
    }


def _registry_entry_for(capsule: NormalizedCapability) -> dict[str, Any]:
    return {
        "capability_capsule_id": capsule.capsule_id,
        "version": "0.1.0",
        "capsule_kind": "capability",
        "status": "draft",
        "schema_ref": "draft/capability-capsule.v1.draft.json",
        "manifest_path": f"capability-capsules/{capsule.capsule_id}.yaml",
        "tags": ["knowledge", "understand-anything", capsule.logical_operator.lower()],
        "owner": "opensolar",
        "default_operator_profile": derive_physical_operator(capsule.capability_id),
    }


def _write_registry_entry(registry_path: Path, entries: list[dict[str, Any]]) -> None:
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    payload.setdefault("version", 1)
    payload.setdefault("capsules", {})
    payload["capsules"].setdefault("capability", [])
    existing = [item for item in payload["capsules"]["capability"] if isinstance(item, dict)]
    by_id = {str(item.get("capability_capsule_id")): item for item in existing}
    for entry in entries:
        by_id[str(entry["capability_capsule_id"])] = entry
    payload["capsules"]["capability"] = sorted(
        by_id.values(),
        key=lambda item: str(item.get("capability_capsule_id", "")),
    )
    registry_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def batch_compile(
    *,
    dry_run: bool = True,
    plugin_id: str | None = None,
    harness_dir: Path | None = None,
) -> dict[str, Any]:
    harness_root = Path(harness_dir or HARNESS_DIR)
    generated: list[dict[str, Any]] = []
    skipped: list[str] = []
    errors: list[str] = []
    registry_entries: list[dict[str, Any]] = []
    for plugin in discover_plugins(harness_root, plugin_id=plugin_id):
        capabilities = normalize_capabilities(plugin)
        if not capabilities:
            skipped.append(plugin.plugin_id)
            continue
        for capability in capabilities:
            draft = compile_capsule_draft(plugin.plugin_id, capability)
            generated.append(
                {
                    "plugin_id": plugin.plugin_id,
                    "capability_id": capability.capability_id,
                    "capsule_id": capability.capsule_id,
                    "logical_operator": capability.logical_operator,
                    "manifest": draft,
                }
            )
            registry_entries.append(_registry_entry_for(capability))
            if not dry_run:
                manifest_path = harness_root / "config" / "capability-capsules" / f"{capability.capsule_id}.yaml"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True), encoding="utf-8")
                register_binding(
                    SkillOperatorBinding(
                        skill_id=capability.capability_id,
                        logical_operator=capability.logical_operator,
                        physical_operator=derive_physical_operator(capability.capability_id),
                        capsule_id=capability.capsule_id,
                        actor=derive_actor(capability.capability_id),
                        semantic_backend="ThunderOMLX",
                    ),
                    path=harness_root / "config" / "skill-operator-bindings.yaml",
                )
    if not dry_run and registry_entries:
        _write_registry_entry(harness_root / "config" / "capability-capsules.registry.yaml", registry_entries)
    return {
        "ok": not errors,
        "dry_run": dry_run,
        "capsule_count": len(generated),
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
        "generated_at": _now_iso(),
    }


def compile_report_jsonable(report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    payload["generated"] = [
        {key: value for key, value in item.items() if key != "manifest"}
        | {"manifest": item["manifest"]}
        for item in report.get("generated", [])
    ]
    return payload
