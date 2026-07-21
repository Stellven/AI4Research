"""Dynamic bridge from installed skills to schedulable Solar-Harness hints.

This module does not try to auto-productize every discovered skill into a
first-class logical/physical operator. Instead, it turns certified installed
skills into runtime-selectable dispatch hints that can be attached to capsule
plans, instruction files, and worker-visible skill injection.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import solar_skills  # type: ignore
import yaml

LEVEL_RANK = {
    "broken": 0,
    "discoverable": 1,
    "injectable": 2,
    "executable": 3,
    "effective": 4,
}

SOURCE_RANK = {
    "agents-skills": 4,
    "solar-native": 3,
    "claude-skills": 2,
    "codex-skills": 1,
}

WORKFLOW_KEYWORDS = (
    "workflow",
    "methodology",
    "playbook",
    "checklist",
    "framework",
    "guide",
    "discipline",
    "process",
    "pattern",
)

KNOWLEDGE_KEYWORDS = (
    "research",
    "citation",
    "evidence",
    "paper",
    "knowledge",
    "analysis",
    "synthesis",
)

PLANNER_KEYWORDS = (
    "plan",
    "planner",
    "design",
    "architecture",
    "strategy",
    "roadmap",
)

SKILL_SPECIALIZATION_RULES = (
    {
        "family": "pdf_cli_artifact",
        "priority": 100,
        "skill_ids": {"skill.nano-pdf"},
        "alias_tokens": {"nano-pdf", "pdf", "edit-pdf"},
        "recommended_operator_profile": "mini-skill-pdf-cli-pane-bridge",
        "pane_target_selector": "builder_idle",
        "delivery_expectation": "command_log_and_artifact_delta",
        "workflow_phases": [
            "inspect_tool_contract",
            "run_primary_command_path",
            "verify_outputs_and_exit_signals",
            "preserve_citations_and_structure",
            "record_command_evidence",
        ],
    },
    {
        "family": "research_workflow",
        "priority": 40,
        "skill_ids": set(),
        "alias_tokens": {"research", "citation", "evidence", "synthesis", "paper"},
        "recommended_operator_profile": "mini-skill-research-workflow-pane-bridge",
        "pane_target_selector": "knowledge_idle",
        "delivery_expectation": "phase_checklist_and_decision_log",
        "workflow_phases": [
            "frame_objective_and_constraints",
            "collect_evidence_and_sources",
            "map_claims_to_citations",
            "summarize_decisions_and_evidence",
        ],
    },
    {
        "family": "planning_workflow",
        "priority": 30,
        "skill_ids": set(),
        "alias_tokens": {"plan", "planner", "architecture", "strategy", "roadmap", "tradeoff", "adr"},
        "recommended_operator_profile": "mini-skill-planning-workflow-pane-bridge",
        "pane_target_selector": "planner_idle",
        "delivery_expectation": "phase_checklist_and_decision_log",
        "workflow_phases": [
            "frame_objective_and_constraints",
            "enumerate_options_and_tradeoffs",
            "select_direction_and_rationale",
            "summarize_decisions_and_evidence",
        ],
    },
    {
        "family": "github_review_cli",
        "priority": 95,
        "skill_ids": {
            "skill.gh-address-comments",
            "skill.address-github-comments",
            "skill.gh-fix-ci",
            "skill.gh-issues",
        },
        "alias_tokens": set(),
        "recommended_operator_profile": "mini-skill-github-review-pane-bridge",
        "pane_target_selector": "builder_idle",
        "delivery_expectation": "review_comment_resolution_and_ci_status",
        "workflow_phases": [
            "inspect_review_context",
            "address_requested_changes",
            "run_verification_or_ci_checks",
            "summarize_resolution_log",
        ],
    },
    {
        "family": "browser_research_automation",
        "priority": 85,
        "skill_ids": {
            "skill.agent-browser",
            "skill.browser-automation",
            "skill.browser-debugging",
            "skill.browser",
        },
        "alias_tokens": set(),
        "recommended_operator_profile": "mini-skill-browser-research-pane-bridge",
        "pane_target_selector": "knowledge_idle",
        "delivery_expectation": "navigation_trace_and_source_capture",
        "workflow_phases": [
            "plan_navigation_targets",
            "capture_navigation_evidence",
            "extract_relevant_findings",
            "summarize_source_traceability",
        ],
    },
    {
        "family": "agent_orchestration",
        "priority": 90,
        "skill_ids": {
            "skill.agent",
            "skill.agents",
            "skill.autonomous-agents",
            "skill.agent-manager-skill",
            "skill.agent-management",
            "skill.agent-messaging",
            "skill.agent-organizer",
            "skill.agent-orchestrator",
        },
        "alias_tokens": set(),
        "recommended_operator_profile": "mini-skill-agent-orchestration-pane-bridge",
        "pane_target_selector": "planner_idle",
        "delivery_expectation": "orchestration_plan_and_execution_log",
        "workflow_phases": [
            "map_agents_and_roles",
            "stage_tmux_or_message_actions",
            "coordinate_execution_sequence",
            "summarize_orchestration_state",
        ],
    },
    {
        "family": "document_artifact_transform",
        "priority": 80,
        "skill_ids": {
            "skill.documents",
            "skill.markitdown",
            "skill.paper-2-web",
            "skill.pdf-processing",
            "skill.pdf-processing-pro",
        },
        "alias_tokens": set(),
        "recommended_operator_profile": "mini-skill-document-artifact-pane-bridge",
        "pane_target_selector": "builder_idle",
        "delivery_expectation": "artifact_transform_log_and_output_index",
        "workflow_phases": [
            "inspect_source_artifacts",
            "run_transform_or_conversion_path",
            "verify_output_fidelity",
            "summarize_artifact_changes",
        ],
    },
    {
        "family": "evaluation_and_verification",
        "priority": 85,
        "skill_ids": {
            "skill.ai-evals",
            "skill.evals",
            "skill.agent-evaluation",
            "skill.verification-before-completion",
        },
        "alias_tokens": set(),
        "recommended_operator_profile": "mini-skill-eval-verification-pane-bridge",
        "pane_target_selector": "evaluator_idle",
        "delivery_expectation": "verification_matrix_and_verdict",
        "workflow_phases": [
            "frame_verification_scope",
            "run_checks_or_evals",
            "compare_results_against_acceptance",
            "emit_verdict_and_residual_risk",
        ],
    },
    {
        "family": "repo_refactor",
        "priority": 75,
        "skill_ids": {
            "skill.agent-md-refactor",
            "skill.angular-migration",
        },
        "alias_tokens": {"refactor", "migration", "cleanup", "module", "technical debt"},
        "recommended_operator_profile": "mini-skill-repo-refactor-pane-bridge",
        "pane_target_selector": "builder_idle",
        "delivery_expectation": "refactor_plan_and_changed_surface_summary",
        "workflow_phases": [
            "map_current_structure_and_constraints",
            "stage_refactor_sequence",
            "apply_safe_changes_and_checks",
            "summarize_changed_surface_and_followups",
        ],
    },
    {
        "family": "frontend_accessibility",
        "priority": 88,
        "skill_ids": {
            "skill.accessibility",
            "skill.accessibility-auditor",
            "skill.accessibility-compliance",
            "skill.accessibility-tester",
            "skill.accessibility-testing",
        },
        "alias_tokens": {"accessibility", "wcag", "a11y", "screen reader", "keyboard navigation"},
        "recommended_operator_profile": "mini-skill-frontend-accessibility-pane-bridge",
        "pane_target_selector": "evaluator_idle",
        "delivery_expectation": "accessibility_issue_matrix_and_fix_plan",
        "workflow_phases": [
            "inspect_accessibility_scope",
            "identify_wcag_issues",
            "propose_or_apply_remediations",
            "summarize_issue_matrix_and_risk",
        ],
    },
    {
        "family": "api_backend_design",
        "priority": 55,
        "skill_ids": {
            "skill.api-authentication",
            "skill.api-contract-testing",
            "skill.api-design",
            "skill.api-design-principles",
            "skill.api-designer",
            "skill.api-documentation-generator",
            "skill.api-documenter",
            "skill.api-error-handling",
            "skill.api-filtering-sorting",
            "skill.api-gateway-configuration",
            "skill.api-pagination",
            "skill.api-rate-limiting",
            "skill.api-reference-documentation",
            "skill.api-response-optimization",
            "skill.api-security-best-practices",
            "skill.api-security-hardening",
            "skill.api-versioning-strategy",
            "skill.backend-dev-guidelines",
            "skill.backend-patterns",
        },
        "alias_tokens": {"api", "rest", "graphql", "backend", "auth", "pagination", "versioning", "gateway"},
        "recommended_operator_profile": "mini-skill-api-backend-pane-bridge",
        "pane_target_selector": "planner_idle",
        "delivery_expectation": "api_contract_and_backend_decision_log",
        "workflow_phases": [
            "frame_contract_and_constraints",
            "design_endpoints_models_and_policies",
            "validate_operability_and_security",
            "summarize_api_decisions_and_open_risks",
        ],
    },
    {
        "family": "data_sheet_analysis",
        "priority": 65,
        "skill_ids": {
            "skill.excel-analysis",
            "skill.cohort-analysis",
            "skill.exploratory-data-analysis",
            "skill.csv-data-wrangler",
            "skill.data-analyst",
            "skill.data-researcher",
            "skill.a-b-test-analysis",
            "skill.ab-test-setup",
        },
        "alias_tokens": {"excel", "spreadsheet", "sheet", "csv", "cohort", "funnel", "data analysis", "pivot table"},
        "recommended_operator_profile": "mini-skill-data-sheet-analysis-pane-bridge",
        "pane_target_selector": "knowledge_idle",
        "delivery_expectation": "analysis_findings_table_and_metric_notes",
        "workflow_phases": [
            "inspect_dataset_and_questions",
            "run_analysis_or_wrangling_path",
            "extract_metrics_patterns_and_anomalies",
            "summarize_findings_and_caveats",
        ],
    },
    {
        "family": "infra_devops_automation",
        "priority": 60,
        "skill_ids": {
            "skill.ansible-automation",
            "skill.airflow-dag-patterns",
            "skill.aws-ami-builder",
            "skill.aws-cloudfront-cdn",
            "skill.aws-ec2-setup",
            "skill.aws-lambda-functions",
            "skill.aws-rds-database",
            "skill.aws-s3-management",
            "skill.azure-app-service",
            "skill.azure-functions",
        },
        "alias_tokens": {"ansible", "terraform", "deploy", "deployment", "kubernetes", "docker", "devops", "autoscaling"},
        "recommended_operator_profile": "mini-skill-infra-devops-pane-bridge",
        "pane_target_selector": "builder_idle",
        "delivery_expectation": "infra_change_plan_and_operability_notes",
        "workflow_phases": [
            "inspect_infra_scope_and_constraints",
            "stage_deployment_or_automation_path",
            "validate_operability_and_rollout_risk",
            "summarize_infra_changes_and_followups",
        ],
    },
    {
        "family": "security_review_hardening",
        "priority": 92,
        "skill_ids": {
            "skill.access-control-rbac",
            "skill.ad-security-reviewer",
            "skill.api-security-best-practices",
            "skill.api-security-hardening",
            "skill.auth-implementation-patterns",
            "skill.attack-tree-construction",
        },
        "alias_tokens": {"security", "hardening", "vulnerability", "rbac", "auth", "authorization", "penetration", "compliance"},
        "recommended_operator_profile": "mini-skill-security-review-pane-bridge",
        "pane_target_selector": "evaluator_idle",
        "delivery_expectation": "risk_matrix_and_hardening_actions",
        "workflow_phases": [
            "frame_threat_surface_and_controls",
            "identify_gaps_or_attack_paths",
            "map_hardening_actions_and_priority",
            "summarize_risk_matrix_and_residual_exposure",
        ],
    },
    {
        "family": "frontend_ui_engineering",
        "priority": 70,
        "skill_ids": {
            "skill.aesthetic",
            "skill.3d-web-experience",
            "skill.angular-architect",
            "skill.angular-module-design",
        },
        "alias_tokens": {"frontend", "ui", "ux", "react", "angular", "vue", "design system", "component architecture"},
        "recommended_operator_profile": "mini-skill-frontend-ui-pane-bridge",
        "pane_target_selector": "builder_idle",
        "delivery_expectation": "ui_change_plan_and_component_notes",
        "workflow_phases": [
            "inspect_ui_scope_and_constraints",
            "map_components_and_interaction_changes",
            "apply_or_plan_ui_updates",
            "summarize_ui_decisions_and_followups",
        ],
    },
    {
        "family": "agent_building_systems",
        "priority": 78,
        "skill_ids": {
            "skill.agent-development",
            "skill.ai-agents-architect",
            "skill.autogpt-agents",
            "skill.context-engineering",
            "skill.context-manager",
            "skill.conversation-memory",
            "skill.crewai",
            "skill.crewai-multi-agent",
            "skill.parallel-agents",
            "skill.task-coordination-strategies",
        },
        "alias_tokens": {"agent development", "create agent", "agent architecture", "context engineering", "multi-agent", "memory system"},
        "recommended_operator_profile": "mini-skill-agent-building-pane-bridge",
        "pane_target_selector": "planner_idle",
        "delivery_expectation": "agent_design_and_system_contract",
        "workflow_phases": [
            "frame_agent_roles_memory_and_tools",
            "design_runtime_and_coordination_contract",
            "validate_failure_modes_and_observability",
            "summarize_agent_system_design_and_open_risks",
        ],
    },
)


def canonical_skill_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return f"skill.{slug}" if slug else "skill.unknown"


def _level_rank(level: str) -> int:
    return LEVEL_RANK.get(str(level or "").strip().lower(), 0)


def _normalize_text_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                tokens.update(_normalize_text_tokens(item))
            continue
        if isinstance(value, dict):
            for item in value.values():
                tokens.update(_normalize_text_tokens(item))
            continue
        text = str(value).strip().lower()
        if not text:
            continue
        tokens.add(text)
        for part in re.split(r"[^a-z0-9._/-]+", text):
            if part:
                tokens.add(part)
    return tokens


def _parse_frontmatter(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    try:
        payload = yaml.safe_load(block)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _derive_execution_surface(record: dict[str, Any], meta: dict[str, Any]) -> str:
    name = str(record.get("name") or "")
    path = Path(str(record.get("path") or ""))
    description = str(meta.get("description") or record.get("description") or "").lower()
    allowed_tools = str(meta.get("allowed-tools") or meta.get("allowed_tools") or "").lower()
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    openclaw = metadata.get("openclaw") if isinstance(metadata, dict) else {}
    requires = openclaw.get("requires") if isinstance(openclaw, dict) else {}
    bins = requires.get("bins") if isinstance(requires, dict) else []

    if bins or "cli" in description or "terminal" in description or "bash(" in allowed_tools:
        return "prompt_guided_cli"
    if path.parts and ".claude" in path.parts:
        return "claude_skill_prompt"
    if name:
        return "prompt_context_skill"
    return "discovered_only"


def _extract_cli_bins(meta: dict[str, Any], description: str, allowed_tools: str) -> list[str]:
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    openclaw = metadata.get("openclaw") if isinstance(metadata, dict) else {}
    requires = openclaw.get("requires") if isinstance(openclaw, dict) else {}
    bins = requires.get("bins") if isinstance(requires, dict) else []
    if bins is None:
        bins = []
    out = [str(item).strip() for item in bins if str(item).strip()]
    if out:
        return out
    for match in re.findall(r"\bBash\(([^)]+)\)", allowed_tools, flags=re.I):
        token = str(match).strip().rstrip("*").strip()
        if token and token not in out:
            out.append(token)
    if out:
        return out
    desc_match = re.search(r"\buse [`']?([a-z0-9._-]+)[`']?\b", description, flags=re.I)
    if desc_match:
        return [desc_match.group(1)]
    return []


def _derive_template_profile(
    record: dict[str, Any],
    meta: dict[str, Any],
    execution_surface: str,
    *,
    cli_bins: list[str],
) -> str:
    path = Path(str(record.get("path") or ""))
    description = str(meta.get("description") or record.get("description") or "").lower()
    if execution_surface == "prompt_guided_cli" or cli_bins:
        return "cli_tooling"
    if execution_surface in {"prompt_context_skill", "claude_skill_prompt"}:
        if any(keyword in description for keyword in WORKFLOW_KEYWORDS):
            return "workflow_methodology"
        if path.parts and ".claude" in path.parts:
            return "workflow_methodology"
    return "workflow_methodology" if execution_surface != "discovered_only" else "discovered_only"


def _derive_dispatch_strategy(template_profile: str, execution_surface: str) -> str:
    if template_profile == "cli_tooling" or execution_surface == "prompt_guided_cli":
        return "tool_first_cli_execution"
    if template_profile == "workflow_methodology":
        return "workflow_first_guidance"
    return "best_effort_skill_context"


def _derive_workflow_phases(template_profile: str) -> list[str]:
    if template_profile == "cli_tooling":
        return [
            "inspect_tool_contract",
            "run_primary_command_path",
            "verify_outputs_and_exit_signals",
            "record_command_evidence",
        ]
    if template_profile == "workflow_methodology":
        return [
            "frame_objective_and_constraints",
            "apply_skill_workflow",
            "validate_against_acceptance",
            "summarize_decisions_and_evidence",
        ]
    return ["execute_skill_guidance", "summarize_evidence"]


def _derive_delivery_expectation(template_profile: str) -> str:
    if template_profile == "cli_tooling":
        return "command_log_and_artifact_delta"
    if template_profile == "workflow_methodology":
        return "phase_checklist_and_decision_log"
    return "skill_guided_result_summary"


def _derive_pane_target_selector(
    template_profile: str,
    execution_surface: str,
    description: str,
) -> str:
    text = str(description or "").lower()
    if template_profile == "cli_tooling" or execution_surface == "prompt_guided_cli":
        return "builder_idle"
    if any(keyword in text for keyword in KNOWLEDGE_KEYWORDS):
        return "knowledge_idle"
    if any(keyword in text for keyword in PLANNER_KEYWORDS):
        return "planner_idle"
    return "builder_idle"


def _derive_recommended_operator_profile(template_profile: str) -> str:
    if template_profile == "cli_tooling":
        return "mini-skill-cli-pane-bridge"
    if template_profile == "workflow_methodology":
        return "mini-skill-workflow-pane-bridge"
    return "mini-skill-dispatch-pane-bridge"


def _specialization_override(
    skill_id: str,
    aliases: set[str],
    *,
    template_profile: str,
    execution_surface: str,
    description: str,
) -> dict[str, Any]:
    lowered_aliases = {str(item).strip().lower() for item in aliases if str(item).strip()}
    text_tokens = _normalize_text_tokens(description, lowered_aliases)
    default = {
        "family": "cli_generalist" if template_profile == "cli_tooling" else "workflow_generalist",
        "recommended_operator_profile": _derive_recommended_operator_profile(template_profile),
        "pane_target_selector": _derive_pane_target_selector(template_profile, execution_surface, description),
        "delivery_expectation": _derive_delivery_expectation(template_profile),
    }
    best_match: dict[str, Any] | None = None
    best_score: tuple[int, int, int] | None = None
    for rule in SKILL_SPECIALIZATION_RULES:
        rule_skill_ids = {str(item).strip().lower() for item in rule.get("skill_ids", set()) if str(item).strip()}
        rule_aliases = {str(item).strip().lower() for item in rule.get("alias_tokens", set()) if str(item).strip()}
        exact_skill_match = int(str(skill_id).strip().lower() in rule_skill_ids)
        alias_overlap = len(rule_aliases.intersection(text_tokens))
        if not exact_skill_match and not alias_overlap:
            continue
        priority = int(rule.get("priority") or 0)
        score = (exact_skill_match, priority, alias_overlap)
        if best_score is None or score > best_score:
            best_score = score
            best_match = rule
    if best_match is not None:
        merged = dict(default)
        merged.update({k: v for k, v in best_match.items() if k not in {"skill_ids", "alias_tokens", "priority"}})
        return merged
    return default


def _derive_skill_hints(record: dict[str, Any], meta: dict[str, Any], execution_surface: str) -> dict[str, Any]:
    description = str(meta.get("description") or record.get("description") or "")
    allowed_tools = str(meta.get("allowed-tools") or meta.get("allowed_tools") or "")
    cli_bins = _extract_cli_bins(meta, description, allowed_tools)
    template_profile = _derive_template_profile(record, meta, execution_surface, cli_bins=cli_bins)
    aliases = _skill_aliases(record, meta)
    specialization = _specialization_override(
        canonical_skill_id(str(meta.get("name") or record.get("name") or "")),
        aliases,
        template_profile=template_profile,
        execution_surface=execution_surface,
        description=description,
    )
    workflow_phases = [
        str(item).strip()
        for item in (specialization.get("workflow_phases") or _derive_workflow_phases(template_profile))
        if str(item).strip()
    ]
    delivery_expectation = str(specialization.get("delivery_expectation") or _derive_delivery_expectation(template_profile))
    pane_target_selector = str(specialization.get("pane_target_selector") or _derive_pane_target_selector(template_profile, execution_surface, description))
    recommended_operator_profile = str(specialization.get("recommended_operator_profile") or _derive_recommended_operator_profile(template_profile))
    hint = {
        "allowed_tools": allowed_tools,
        "cli_bins": cli_bins,
        "workflow_hint": description,
        "suggested_first_command": "",
        "suggested_verify_command": "",
        "cli_command_template": "",
        "template_profile": template_profile,
        "dispatch_strategy": _derive_dispatch_strategy(template_profile, execution_surface),
        "workflow_phases": workflow_phases,
        "delivery_expectation": delivery_expectation,
        "specialization_family": str(specialization.get("family") or ""),
        "recommended_operator_profile": recommended_operator_profile,
        "recommended_runtime_preferences": {
            "pane_target": "best_effort",
            "pane_target_selector": pane_target_selector,
            "execution_surface": execution_surface,
        },
    }
    if execution_surface == "prompt_guided_cli" and cli_bins:
        hint["suggested_first_command"] = f"{cli_bins[0]} --help"
        hint["suggested_verify_command"] = f"{cli_bins[0]} --version"
        hint["cli_command_template"] = f"{cli_bins[0]} <args>"
    return hint


def _skill_aliases(record: dict[str, Any], meta: dict[str, Any]) -> set[str]:
    name = str(record.get("name") or "")
    skill_id = canonical_skill_id(name)
    aliases = _normalize_text_tokens(
        skill_id,
        name,
        name.replace(" ", "-"),
        name.replace(" ", "_"),
        meta.get("description"),
        meta.get("tags"),
    )
    aliases.add(skill_id)
    aliases.add(skill_id.removeprefix("skill."))
    return aliases


@lru_cache(maxsize=1)
def load_skill_bridge_catalog(include_all: bool = True) -> list[dict[str, Any]]:
    payload = solar_skills._readiness_payload(include_all=include_all, write_scorecards=False)  # type: ignore[attr-defined]
    by_skill_id: dict[str, dict[str, Any]] = {}
    for record in payload.get("skills", []) or []:
        path_str = str(record.get("path") or "").strip()
        if not path_str:
            continue
        level = str(record.get("level") or "broken")
        path = Path(path_str)
        meta = _parse_frontmatter(path)
        name = str(meta.get("name") or record.get("name") or path.parent.name)
        skill_id = canonical_skill_id(name)
        aliases = _skill_aliases({"name": name, **record}, meta)
        execution_surface = _derive_execution_surface(record, meta)
        hints = _derive_skill_hints(record, meta, execution_surface)
        normalized = {
            "skill_id": skill_id,
            "name": name,
            "path": str(path),
            "source": str(record.get("source") or ""),
            "level": level,
            "level_rank": _level_rank(level),
            "layers": dict(record.get("layers") or {}),
            "description": str(meta.get("description") or record.get("description") or ""),
            "homepage": str(meta.get("homepage") or ""),
            "execution_surface": execution_surface,
            "allowed_tools": str(hints.get("allowed_tools") or ""),
            "cli_bins": list(hints.get("cli_bins") or []),
            "workflow_hint": str(hints.get("workflow_hint") or ""),
            "suggested_first_command": str(hints.get("suggested_first_command") or ""),
            "suggested_verify_command": str(hints.get("suggested_verify_command") or ""),
            "cli_command_template": str(hints.get("cli_command_template") or ""),
            "template_profile": str(hints.get("template_profile") or ""),
            "dispatch_strategy": str(hints.get("dispatch_strategy") or ""),
            "workflow_phases": list(hints.get("workflow_phases") or []),
            "delivery_expectation": str(hints.get("delivery_expectation") or ""),
            "specialization_family": str(hints.get("specialization_family") or ""),
            "recommended_operator_profile": str(hints.get("recommended_operator_profile") or ""),
            "recommended_runtime_preferences": dict(hints.get("recommended_runtime_preferences") or {}),
            "aliases": sorted(aliases),
        }
        existing = by_skill_id.get(skill_id)
        if existing is None:
            by_skill_id[skill_id] = normalized
            continue
        new_rank = (
            int(normalized.get("level_rank") or 0),
            SOURCE_RANK.get(str(normalized.get("source") or ""), 0),
            len(str(normalized.get("description") or "")),
        )
        old_rank = (
            int(existing.get("level_rank") or 0),
            SOURCE_RANK.get(str(existing.get("source") or ""), 0),
            len(str(existing.get("description") or "")),
        )
        if new_rank > old_rank:
            by_skill_id[skill_id] = normalized
    out = list(by_skill_id.values())
    out.sort(key=lambda item: (-int(item.get("level_rank") or 0), str(item.get("skill_id") or "")))
    return out


def resolve_skill_records(skill_ids: list[str]) -> list[dict[str, Any]]:
    wanted = {str(item or "").strip().lower() for item in skill_ids if str(item or "").strip()}
    if not wanted:
        return []
    matches: list[dict[str, Any]] = []
    for item in load_skill_bridge_catalog():
        aliases = {str(alias).lower() for alias in item.get("aliases") or []}
        if aliases & wanted:
            matches.append(dict(item))
    matches.sort(key=lambda item: (-int(item.get("level_rank") or 0), str(item.get("skill_id") or "")))
    return matches


def query_skill_candidates(
    *,
    objective: str = "",
    logical_operator: str = "",
    task_type: str = "",
    required_skills: list[str] | None = None,
    limit: int = 6,
    min_level: str = "injectable",
) -> list[dict[str, Any]]:
    req = {str(item or "").strip().lower() for item in (required_skills or []) if str(item or "").strip()}
    tokens = _normalize_text_tokens(objective, logical_operator, task_type, required_skills or [])
    floor = _level_rank(min_level)
    ranked: list[dict[str, Any]] = []
    for item in load_skill_bridge_catalog():
        if int(item.get("level_rank") or 0) < floor:
            continue
        aliases = {str(alias).lower() for alias in item.get("aliases") or []}
        exact_required = sorted(req & aliases)
        exact_signal = sorted(tokens & aliases)
        fuzzy_hits = [
            token for token in tokens
            if token
            and len(token) >= 4
            and any(token in alias or alias in token for alias in aliases)
        ]
        score = 0
        if exact_required:
            score += 120
        if exact_signal:
            score += 60 + (8 * len(exact_signal))
        if fuzzy_hits:
            score += 8 * len(set(fuzzy_hits))
        score += int(item.get("level_rank") or 0) * 5
        if str(item.get("execution_surface") or "").startswith("prompt_"):
            score += 2
        if not score:
            continue
        ranked.append(
            {
                **dict(item),
                "score": score,
                "match": {
                    "exact_required": exact_required,
                    "exact_signal": exact_signal,
                    "fuzzy_hits": sorted(set(fuzzy_hits)),
                },
            }
        )
    ranked.sort(key=lambda item: (-int(item.get("score") or 0), -int(item.get("level_rank") or 0), str(item.get("skill_id") or "")))
    return ranked[: max(int(limit or 0), 0)]


def build_skill_bridge_payload(
    *,
    objective: str = "",
    logical_operator: str = "",
    task_type: str = "",
    required_skills: list[str] | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    candidates = query_skill_candidates(
        objective=objective,
        logical_operator=logical_operator,
        task_type=task_type,
        required_skills=required_skills,
        limit=max(limit, 1),
    )
    required_set = {str(item or "").strip().lower() for item in (required_skills or []) if str(item or "").strip()}
    if required_set:
        exact_required = [
            item for item in candidates
            if set(str(x).lower() for x in ((item.get("match") or {}).get("exact_required") or []))
        ]
        if exact_required:
            candidates = exact_required
    if not candidates:
        return {}
    selected = [str(item.get("skill_id") or "") for item in candidates if str(item.get("skill_id") or "")]
    primary_profile = str(candidates[0].get("template_profile") or "")
    return {
        "selected_skills": selected,
        "skill_bridge": {
            "mode": "auto_discovered_installed_skills",
            "template_profile": primary_profile,
            "dispatch_strategy": str(candidates[0].get("dispatch_strategy") or _derive_dispatch_strategy(primary_profile, "")),
            "workflow_phases": list(candidates[0].get("workflow_phases") or _derive_workflow_phases(primary_profile)),
            "delivery_expectation": str(candidates[0].get("delivery_expectation") or _derive_delivery_expectation(primary_profile)),
            "specialization_family": str(candidates[0].get("specialization_family") or ""),
            "recommended_operator_profile": str(candidates[0].get("recommended_operator_profile") or _derive_recommended_operator_profile(primary_profile)),
            "recommended_runtime_preferences": dict(candidates[0].get("recommended_runtime_preferences") or {}),
            "selected": candidates,
            "selection_basis": {
                "required_skills": list(required_skills or []),
                "logical_operator": logical_operator,
                "task_type": task_type,
            },
        },
    }
