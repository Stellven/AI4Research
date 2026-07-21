#!/usr/bin/env python3
"""Generic command backend adapter for installed-skill pane dispatch."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from hands_runtime import PaneHand, ResultStatus  # noqa: E402
import operator_flow_control as ofc  # noqa: E402
from skill_capsule_bridge import resolve_skill_records  # noqa: E402

DEFAULT_OPERATOR_ID = "mini-skill-dispatch-pane-bridge"
DEFAULT_PANE_TARGET = "best_effort"
DEFAULT_PANE_SELECTOR = "builder_idle"
DEFAULT_EXECUTION_SURFACE = "prompt_context_skill"
DEFAULT_PANE_SESSIONS = (
    "solar-harness-lab",
    "solar-harness-multi-task",
    "solar-harness",
    "solar",
)
ALLOWED_EXECUTION_SURFACES = {"prompt_context_skill", "prompt_guided_cli"}


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _task_dir() -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def _operator_id(envelope: dict[str, Any]) -> str:
    value = str(envelope.get("operator_id") or "").strip()
    return value or DEFAULT_OPERATOR_ID


def _runtime_preferences(envelope: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    resolved = envelope.get("resolved_capability_capsule")
    if isinstance(resolved, dict) and isinstance(resolved.get("runtime_preferences"), dict):
        merged.update(deepcopy(resolved["runtime_preferences"]))
    if isinstance(envelope.get("runtime_preferences"), dict):
        merged.update(deepcopy(envelope["runtime_preferences"]))
    return merged


def _discover_tmux_panes() -> list[dict[str, str]]:
    try:
        proc = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{session_name}\t#{window_index}\t#{pane_index}\t#{pane_title}\t#{pane_current_command}",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    panes: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        session, window, pane, title, command = (line.split("\t", 4) + ["", "", "", "", ""])[:5]
        panes.append(
            {
                "session": session.strip(),
                "window": window.strip(),
                "pane": pane.strip(),
                "target": f"{session.strip()}:{window.strip()}.{pane.strip()}",
                "title": title.strip(),
                "command": command.strip(),
            }
        )
    return panes


def _pane_score(row: dict[str, str]) -> tuple[int, int, int]:
    session = row.get("session", "")
    title = row.get("title", "").lower()
    command = row.get("command", "").lower()
    session_rank = DEFAULT_PANE_SESSIONS.index(session) if session in DEFAULT_PANE_SESSIONS else len(DEFAULT_PANE_SESSIONS)
    title_bonus = 0
    if any(token in title for token in ("builder", "lab-builder", "planner", "evaluator", "knowledge", "opus", "sonnet", "qwen")):
        title_bonus = -1
    command_bonus = 0 if command in {"claude", "codex", "zsh", "bash"} else 1
    return (session_rank, title_bonus, command_bonus)


def _resolve_pane_target(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requested = str(request.get("pane_target") or "").strip()
    if requested and ":" in requested:
        return requested, {"strategy": "explicit_full_target", "requested": requested}
    if requested and requested not in {"auto", "builder_idle", "best_effort", "knowledge_idle", "planner_idle", "evaluator_idle"}:
        return requested, {"strategy": "explicit_legacy_target", "requested": requested}
    selector = str(request.get("pane_target_selector") or requested or DEFAULT_PANE_SELECTOR).strip() or DEFAULT_PANE_SELECTOR
    panes = _discover_tmux_panes()
    if not panes:
        fallback = requested if requested and requested not in {"auto", "builder_idle", "best_effort", "knowledge_idle"} else "0"
        return fallback, {"strategy": "no_tmux_inventory_fallback", "requested": requested, "selector": selector}
    filtered = [row for row in panes if row.get("session") in DEFAULT_PANE_SESSIONS]
    if selector == "builder_idle":
        filtered = [row for row in filtered if "builder" in row.get("title", "").lower()] or filtered
    elif selector == "planner_idle":
        filtered = [row for row in filtered if any(token in row.get("title", "").lower() for token in ("planner", "architect", "pm"))] or filtered
    elif selector == "knowledge_idle":
        filtered = [row for row in filtered if any(token in row.get("title", "").lower() for token in ("knowledge", "qwen", "builder"))] or filtered
    elif selector == "evaluator_idle":
        filtered = [row for row in filtered if any(token in row.get("title", "").lower() for token in ("evaluator", "verifier", "critic", "review"))] or filtered
    if not filtered:
        filtered = panes
    chosen = sorted(filtered, key=_pane_score)[0]
    return chosen["target"], {
        "strategy": "tmux_inventory_selector",
        "selector": selector,
        "requested": requested,
        "resolved": chosen["target"],
        "title": chosen.get("title", ""),
        "command": chosen.get("command", ""),
    }


def _coerce_selected_skills(envelope: dict[str, Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    values = [
        envelope.get("selected_skills"),
        (envelope.get("capsule_plan") or {}).get("selected_skills") if isinstance(envelope.get("capsule_plan"), dict) else [],
        (envelope.get("resolved_capability_capsule") or {}).get("selected_skills") if isinstance(envelope.get("resolved_capability_capsule"), dict) else [],
    ]
    for value in values:
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = [str(item) for item in value]
        else:
            items = []
        for item in items:
            cleaned = str(item or "").strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(cleaned)
    return merged


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    runtime_preferences = _runtime_preferences(envelope)
    selected_skills = _coerce_selected_skills(envelope)
    skill_records = resolve_skill_records(selected_skills)
    execution_surface = str(
        runtime_preferences.get("execution_surface")
        or (skill_records[0].get("execution_surface") if skill_records else DEFAULT_EXECUTION_SURFACE)
        or DEFAULT_EXECUTION_SURFACE
    ).strip() or DEFAULT_EXECUTION_SURFACE
    request = {
        "operator_id": _operator_id(envelope),
        "task_id": str(envelope.get("task_id") or ""),
        "node_id": str(envelope.get("node_id") or ""),
        "sprint_id": str(envelope.get("sprint_id") or ""),
        "objective": str(envelope.get("objective") or ""),
        "task_type": str(envelope.get("task_type") or ""),
        "logical_operator": str(envelope.get("logical_operator") or ""),
        "selected_skills": selected_skills,
        "skill_records": skill_records,
        "execution_surface": execution_surface,
        "pane_target": str(runtime_preferences.get("pane_target") or envelope.get("pane_target") or DEFAULT_PANE_TARGET),
        "pane_target_selector": str(runtime_preferences.get("pane_target_selector") or envelope.get("pane_target_selector") or DEFAULT_PANE_SELECTOR),
        "result_path": str(envelope.get("result_path") or ""),
        "required_capabilities": list((envelope.get("task_graph_node") or {}).get("required_capabilities") or []),
        "required_skills": list((envelope.get("task_graph_node") or {}).get("required_skills") or []),
        "acceptance": list((envelope.get("task_graph_node") or {}).get("acceptance") or []),
        "capsule_plan": dict(envelope.get("capsule_plan") or {}),
        "resolved_capability_capsule": dict(envelope.get("resolved_capability_capsule") or {}),
    }
    pane_target, pane_meta = _resolve_pane_target(request)
    request["pane_target"] = pane_target
    request["pane_resolution"] = pane_meta
    if task_dir is not None:
        request["output_dir"] = str(task_dir.resolve())
    return request


def _validate_request(request: dict[str, Any]) -> None:
    if not request.get("selected_skills"):
        raise RuntimeError("selected_skills required for generic skill dispatch")
    surface = str(request.get("execution_surface") or "").strip()
    if surface not in ALLOWED_EXECUTION_SURFACES:
        raise RuntimeError(f"unsupported execution_surface: {surface}")
    if not str(request.get("objective") or "").strip():
        raise RuntimeError("objective required for generic skill dispatch")


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    operator_id = _operator_id(envelope)
    flow_control: dict[str, Any] = {}
    try:
        import operator_runtime  # type: ignore

        config = operator_runtime.get_operator_config(operator_id) or {}
        if isinstance(config.get("flow_control"), dict):
            flow_control = dict(config["flow_control"])
    except Exception:
        flow_control = {}
    return {
        "operator_id": operator_id,
        "success_cooldown_seconds": ofc.int_value(
            envelope.get("skill_dispatch_success_cooldown_seconds")
            or os.environ.get("SOLAR_SKILL_DISPATCH_SUCCESS_COOLDOWN_SECONDS")
            or flow_control.get("success_cooldown_seconds"),
            120,
        ),
        "rate_limit_cooldown_seconds": ofc.int_value(
            envelope.get("skill_dispatch_rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_SKILL_DISPATCH_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            900,
        ),
        "auth_cooldown_seconds": ofc.int_value(
            envelope.get("skill_dispatch_auth_cooldown_seconds")
            or os.environ.get("SOLAR_SKILL_DISPATCH_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _bullet_lines(values: list[str]) -> str:
    rows = [str(item).strip() for item in values if str(item).strip()]
    return "\n".join(f"- {item}" for item in rows) if rows else "- N/A"


def _primary_skill_record(request: dict[str, Any]) -> dict[str, Any]:
    for row in request.get("skill_records") or []:
        if isinstance(row, dict):
            return row
    return {}


def _primary_template_profile(request: dict[str, Any]) -> str:
    row = _primary_skill_record(request)
    profile = str(row.get("template_profile") or "").strip()
    if profile:
        return profile
    return "cli_tooling" if str(request.get("execution_surface") or "") == "prompt_guided_cli" else "workflow_methodology"


def _dispatch_strategy(request: dict[str, Any]) -> str:
    row = _primary_skill_record(request)
    strategy = str(row.get("dispatch_strategy") or "").strip()
    if strategy:
        return strategy
    profile = _primary_template_profile(request)
    return "tool_first_cli_execution" if profile == "cli_tooling" else "workflow_first_guidance"


def _workflow_phases(request: dict[str, Any]) -> list[str]:
    row = _primary_skill_record(request)
    phases = [str(item).strip() for item in (row.get("workflow_phases") or []) if str(item).strip()]
    if phases:
        return phases
    if _primary_template_profile(request) == "cli_tooling":
        return [
            "inspect_tool_contract",
            "run_primary_command_path",
            "verify_outputs_and_exit_signals",
            "record_command_evidence",
        ]
    return [
        "frame_objective_and_constraints",
        "apply_skill_workflow",
        "validate_against_acceptance",
        "summarize_decisions_and_evidence",
    ]


def _delivery_expectation(request: dict[str, Any]) -> str:
    row = _primary_skill_record(request)
    value = str(row.get("delivery_expectation") or "").strip()
    if value:
        return value
    return "command_log_and_artifact_delta" if _primary_template_profile(request) == "cli_tooling" else "phase_checklist_and_decision_log"


def _command_protocol(request: dict[str, Any]) -> dict[str, Any]:
    row = _primary_skill_record(request)
    profile = _primary_template_profile(request)
    return {
        "mode": profile,
        "first_command": str(row.get("suggested_first_command") or "").strip(),
        "verify_command": str(row.get("suggested_verify_command") or "").strip(),
        "command_template": str(row.get("cli_command_template") or "").strip(),
        "record_exact_commands": profile == "cli_tooling",
    }


def _workflow_contract(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "phases": _workflow_phases(request),
        "delivery_expectation": _delivery_expectation(request),
    }


def _specialization_family(request: dict[str, Any]) -> str:
    row = _primary_skill_record(request)
    value = str(row.get("specialization_family") or "").strip()
    if value:
        return value
    return "cli_generalist" if _primary_template_profile(request) == "cli_tooling" else "workflow_generalist"


def _specialization_guidance(request: dict[str, Any]) -> list[str]:
    family = _specialization_family(request)
    if family == "pdf_cli_artifact":
        return [
            "- Preserve citations, links, and visible structure unless the objective explicitly says otherwise.",
            "- Treat the artifact delta as the primary deliverable and call out any irreversible edit risk.",
        ]
    if family == "github_review_cli":
        return [
            "- Keep a comment-to-fix mapping so every requested change is either resolved or explicitly deferred.",
            "- Include CI/check status or the reason it could not be verified before closeout.",
        ]
    if family == "browser_research_automation":
        return [
            "- Capture the navigation path and source provenance for every important finding.",
            "- Prefer reproducible page interactions and evidence snapshots over vague browsing summaries.",
        ]
    if family == "agent_orchestration":
        return [
            "- Make agent roles, pane targets, and sequencing explicit before triggering actions.",
            "- Treat orchestration state and delegation outcomes as first-class evidence.",
        ]
    if family == "document_artifact_transform":
        return [
            "- Keep source-to-output mapping clear so transformed artifacts can be audited and replayed.",
            "- Call out fidelity loss, formatting drift, or conversion caveats explicitly.",
        ]
    if family == "evaluation_and_verification":
        return [
            "- Produce a clear verification matrix with pass/fail signals tied back to acceptance criteria.",
            "- End with a verdict plus any residual risk, not just raw check outputs.",
        ]
    if family == "repo_refactor":
        return [
            "- Make the refactor sequence explicit and keep the changed surface bounded and reviewable.",
            "- Call out follow-up debt, migration risk, and any intentionally deferred cleanup.",
        ]
    if family == "frontend_accessibility":
        return [
            "- Tie findings or fixes back to concrete accessibility issues, not generic UX preferences.",
            "- End with an issue matrix or remediation list that a builder/evaluator can act on directly.",
        ]
    if family == "api_backend_design":
        return [
            "- Keep contract, security, pagination, and operability decisions explicit rather than implicit.",
            "- Produce a decision log that downstream implementation can follow without reinterpretation.",
        ]
    if family == "data_sheet_analysis":
        return [
            "- Keep the analysis question, metric definitions, and caveats explicit throughout the closeout.",
            "- Prefer findings tables and metric notes over loose narrative summaries.",
        ]
    if family == "infra_devops_automation":
        return [
            "- Keep deployment, rollout, rollback, and operability notes explicit rather than implied.",
            "- Call out runtime risk, prerequisites, and post-change validation steps in the closeout.",
        ]
    if family == "security_review_hardening":
        return [
            "- Use a risk-oriented structure with findings, severity/priority, and concrete hardening actions.",
            "- End with residual exposure, not just a list of checks or vulnerabilities.",
        ]
    if family == "frontend_ui_engineering":
        return [
            "- Keep component boundaries, interaction changes, and visual intent explicit and reviewable.",
            "- Distinguish between implemented changes, proposed changes, and follow-up polish.",
        ]
    if family == "agent_building_systems":
        return [
            "- Make agent roles, memory, tools, context boundaries, and orchestration contracts explicit.",
            "- Include failure modes, observability, and delegation boundaries in the design closeout.",
        ]
    if family == "research_workflow":
        return [
            "- Maintain explicit citation discipline and keep evidence-to-claim mapping tight.",
            "- Prefer a short evidence matrix or source-backed findings over generic narrative summaries.",
        ]
    if family == "planning_workflow":
        return [
            "- Surface options, tradeoffs, and decision rationale rather than jumping straight to one answer.",
            "- Keep the closeout in a plan/decision-log shape so downstream DAG review can reuse it directly.",
        ]
    return []


def _build_prompt_markdown(request: dict[str, Any], prompt_path: Path) -> str:
    selected_skills = [str(item) for item in request.get("selected_skills") or []]
    skill_rows = []
    for row in request.get("skill_records") or []:
        if not isinstance(row, dict):
            continue
        cli_bins = ", ".join(str(item) for item in (row.get("cli_bins") or []) if str(item).strip()) or "N/A"
        first_cmd = str(row.get("suggested_first_command") or "N/A")
        verify_cmd = str(row.get("suggested_verify_command") or "N/A")
        cli_template = str(row.get("cli_command_template") or "N/A")
        template_profile = str(row.get("template_profile") or "N/A")
        skill_rows.append(
            f"- `{row.get('skill_id')}` level={row.get('level')} surface={row.get('execution_surface')} "
            f"profile={template_profile} path={row.get('path')} cli_bins={cli_bins} first_cmd={first_cmd} "
            f"verify_cmd={verify_cmd} cli_template={cli_template} desc={row.get('description') or 'N/A'}"
        )
    capsule = request.get("resolved_capability_capsule") if isinstance(request.get("resolved_capability_capsule"), dict) else {}
    verification = capsule.get("verification_hooks") if isinstance(capsule.get("verification_hooks"), dict) else {}
    template_profile = _primary_template_profile(request)
    dispatch_strategy = _dispatch_strategy(request)
    workflow_phases = _workflow_phases(request)
    delivery_expectation = _delivery_expectation(request)
    lines = [
        "# Skill Dispatch Task",
        "",
        f"- Task ID: `{request.get('task_id') or 'N/A'}`",
        f"- Sprint: `{request.get('sprint_id') or 'N/A'}`",
        f"- Node: `{request.get('node_id') or 'N/A'}`",
        f"- Logical Operator: `{request.get('logical_operator') or 'N/A'}`",
        f"- Task Type: `{request.get('task_type') or 'N/A'}`",
        f"- Execution Surface: `{request.get('execution_surface') or 'N/A'}`",
        f"- Template Profile: `{template_profile}`",
        f"- Specialization Family: `{_specialization_family(request)}`",
        f"- Dispatch Strategy: `{dispatch_strategy}`",
        f"- Delivery Expectation: `{delivery_expectation}`",
        "",
        "## Objective",
        "",
        str(request.get("objective") or "N/A"),
        "",
        "## Selected Skills",
        "",
        _bullet_lines(selected_skills),
        "",
        "## Resolved Skill Records",
        "",
        "\n".join(skill_rows) if skill_rows else "- N/A",
        "",
        "## Required Skills",
        "",
        _bullet_lines(list(request.get("required_skills") or [])),
        "",
        "## Required Capabilities",
        "",
        _bullet_lines(list(request.get("required_capabilities") or [])),
        "",
        "## Acceptance",
        "",
        _bullet_lines(list(request.get("acceptance") or [])),
        "",
        "## Verification Hooks",
        "",
        _bullet_lines(list(verification.get("self_check") or [])),
        "",
        "## Workflow Phases",
        "",
        _bullet_lines(workflow_phases),
        "",
        "## Output Contract",
        "",
        f"- Write your main closeout to: `{request.get('result_path') or 'N/A'}`",
        f"- Operator artifacts live next to: `{prompt_path.parent}`",
        f"- Delivery expectation: `{delivery_expectation}`",
        "",
        "## Rules",
        "",
        "- Use the selected installed skills as the primary methodology/tooling layer.",
        "- Keep evidence concise and concrete.",
    ]
    specialization_rules = _specialization_guidance(request)
    if specialization_rules:
        lines.extend(
            [
                "",
                "## Specialization Discipline",
                "",
                *specialization_rules,
            ]
        )
    if template_profile == "cli_tooling":
        lines.extend(
            [
                "",
                "## CLI Execution Discipline",
                "",
                "- Prefer the declared CLI/tooling path before improvising a generic workflow.",
                "- Record exact commands, flags, and any file outputs you touched.",
                "- Start with the suggested first command when it helps establish the tool contract.",
                "- Run a lightweight verification command when available and include the outcome in your closeout.",
                "- If the CLI path is blocked, state the blocker explicitly before falling back.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Workflow Discipline",
                "",
                "- Follow the selected skill workflow or checklist explicitly rather than using a generic completion style.",
                "- Map the objective into clear phases, decision points, and deliverables.",
                "- Mirror the workflow phases above in your working notes or final closeout.",
                "- Use normal tools as needed, but keep the skill's method as the primary control surface.",
                "- If the workflow conflicts with local constraints, state the tradeoff and continue with the closest safe adaptation.",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _build_pane_command(request: dict[str, Any], prompt_path: Path) -> str:
    surface = str(request.get("execution_surface") or DEFAULT_EXECUTION_SURFACE)
    result_path = str(request.get("result_path") or "N/A")
    skills = ", ".join(str(item) for item in (request.get("selected_skills") or []))
    template_profile = _primary_template_profile(request)
    row = _primary_skill_record(request)
    first_cmd = str(row.get("suggested_first_command") or "").strip()
    verify_cmd = str(row.get("suggested_verify_command") or "").strip()
    cli_template = str(row.get("cli_command_template") or "").strip()
    delivery_expectation = _delivery_expectation(request)
    if template_profile == "cli_tooling":
        family_clause = ""
        if _specialization_family(request) == "pdf_cli_artifact":
            family_clause = " Preserve citations, links, and visible document structure unless the task explicitly changes them."
        elif _specialization_family(request) == "github_review_cli":
            family_clause = " Keep a precise review-comment to fix mapping and report CI/check status."
        elif _specialization_family(request) == "document_artifact_transform":
            family_clause = " Preserve source-to-output traceability and call out any fidelity drift."
        elif _specialization_family(request) == "repo_refactor":
            family_clause = " Keep the changed surface bounded, sequence the refactor explicitly, and call out deferred cleanup."
        start_clause = f" Start with `{first_cmd}` if it fits." if first_cmd else ""
        verify_clause = f" Use `{verify_cmd}` as a lightweight verification check when useful." if verify_cmd else ""
        template_clause = f" Prefer the command shape `{cli_template}`." if cli_template else ""
        return (
            f"Read {prompt_path} and execute the task using the CLI-oriented installed skills [{skills}] "
            f"with execution_surface={surface}.{family_clause}{start_clause}{verify_clause}{template_clause} "
            f"Record exact commands and write the main result to {result_path} with delivery_expectation={delivery_expectation}. Keep going until complete."
        )
    phases = ", ".join(_workflow_phases(request))
    family_clause = ""
    if _specialization_family(request) == "research_workflow":
        family_clause = " Keep findings citation-backed and preserve source-to-claim traceability."
    elif _specialization_family(request) == "planning_workflow":
        family_clause = " Surface options, tradeoffs, and a decision log rather than only a final recommendation."
    elif _specialization_family(request) == "browser_research_automation":
        family_clause = " Capture navigation evidence and preserve source provenance for key findings."
    elif _specialization_family(request) == "agent_orchestration":
        family_clause = " Make roles, pane targets, delegation steps, and orchestration state explicit."
    elif _specialization_family(request) == "evaluation_and_verification":
        family_clause = " End with a verification matrix, a verdict, and any residual risk."
    elif _specialization_family(request) == "frontend_accessibility":
        family_clause = " Tie findings back to concrete WCAG or accessibility issues and produce an issue matrix or fix plan."
    elif _specialization_family(request) == "api_backend_design":
        family_clause = " Keep contract, security, and operability decisions explicit and end with a backend decision log."
    elif _specialization_family(request) == "data_sheet_analysis":
        family_clause = " Keep metric definitions, findings tables, and caveats explicit in the analysis output."
    elif _specialization_family(request) == "infra_devops_automation":
        family_clause = " Keep rollout, rollback, prerequisites, and operability validation explicit."
    elif _specialization_family(request) == "security_review_hardening":
        family_clause = " Use a risk matrix shape and end with hardening actions plus residual exposure."
    elif _specialization_family(request) == "frontend_ui_engineering":
        family_clause = " Keep component changes, interaction intent, and follow-up polish explicit."
    elif _specialization_family(request) == "agent_building_systems":
        family_clause = " Make agent roles, memory, tools, and failure modes explicit in the system design."
    return (
        f"Read {prompt_path} and execute the task using the methodology-oriented installed skills [{skills}] "
        f"with execution_surface={surface}.{family_clause} Follow the workflow explicitly using phases [{phases}] and write the main result to {result_path} "
        f"with delivery_expectation={delivery_expectation}. Keep going until complete."
    )


def run_request(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    _validate_request(request)
    task_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = task_dir / "skill-dispatch-pane-prompt.md"
    prompt_body = _build_prompt_markdown(request, prompt_path)
    prompt_path.write_text(prompt_body, encoding="utf-8")
    pane_command = _build_pane_command(request, prompt_path)
    request["pane_command"] = pane_command

    contract_path = task_dir / "skill-dispatch-bridge-contract.json"
    command_protocol = _command_protocol(request)
    workflow_contract = _workflow_contract(request)
    _write_json(
        contract_path,
        {
            "task_id": str(request.get("task_id") or ""),
            "selected_skills": list(request.get("selected_skills") or []),
            "execution_surface": str(request.get("execution_surface") or ""),
            "template_profile": _primary_template_profile(request),
            "specialization_family": _specialization_family(request),
            "dispatch_strategy": _dispatch_strategy(request),
            "command_protocol": command_protocol,
            "workflow_contract": workflow_contract,
            "pane_target": str(request.get("pane_target") or ""),
            "prompt_path": str(prompt_path),
            "result_path": str(request.get("result_path") or ""),
        },
    )
    proof_path = task_dir / "skill-dispatch-selection-proof.json"
    _write_json(
        proof_path,
        {
            "selected_skills": list(request.get("selected_skills") or []),
            "skill_records": list(request.get("skill_records") or []),
            "execution_surface": str(request.get("execution_surface") or ""),
            "template_profile": _primary_template_profile(request),
            "specialization_family": _specialization_family(request),
            "dispatch_strategy": _dispatch_strategy(request),
            "command_protocol": command_protocol,
            "workflow_contract": workflow_contract,
            "pane_resolution": dict(request.get("pane_resolution") or {}),
        },
    )

    hand = PaneHand()
    hand_ref = hand.provision(
        capabilities=list(request.get("selected_skills") or []) + ["tmux.send-keys"],
        location=str(request.get("pane_target") or "0"),
    )
    result = hand.execute(
        hand_ref,
        "skill_dispatch",
        {"command": pane_command},
        idempotency_key=str(request.get("task_id") or "skill-dispatch"),
    )
    payload = {
        "ok": result.status == ResultStatus.OK,
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "pane_target": str(request.get("pane_target") or ""),
        "selected_skills": list(request.get("selected_skills") or []),
        "execution_surface": str(request.get("execution_surface") or ""),
        "template_profile": _primary_template_profile(request),
        "specialization_family": _specialization_family(request),
        "dispatch_strategy": _dispatch_strategy(request),
        "command_protocol": command_protocol,
        "workflow_contract": workflow_contract,
        "prompt_path": str(prompt_path),
        "result_path": str(request.get("result_path") or ""),
        "pane_command": pane_command,
        "bridge_contract_path": str(contract_path),
        "selection_proof_path": str(proof_path),
        "pane_resolution": dict(request.get("pane_resolution") or {}),
        "hand_output": result.output,
        "error": result.error,
    }
    result_path = task_dir / "skill-dispatch-result.json"
    _write_json(result_path, payload)
    payload["result_artifact_path"] = str(result_path)
    return payload


def main() -> int:
    envelope = _load_envelope()
    task_dir = _task_dir()
    settings = _rate_control_settings(envelope)
    operator_id = settings["operator_id"]
    try:
        ofc.ensure_operator_available(operator_id, allow_unregistered=True)
        request = build_request(envelope, task_dir=task_dir)
        payload = run_request(request, task_dir=task_dir)
        if payload.get("ok"):
            ofc.apply_success_cooldown(
                operator_id,
                success_cooldown_seconds=int(settings["success_cooldown_seconds"]),
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        failure_text = str(payload.get("error") or payload.get("status") or "")
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=failure_text,
            rate_limit_cooldown_seconds=int(settings["rate_limit_cooldown_seconds"]),
            auth_cooldown_seconds=int(settings["auth_cooldown_seconds"]),
            defer_on_cooldown=True,
            defer_on_auth=True,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:
        failure_text = str(exc)
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=failure_text,
            rate_limit_cooldown_seconds=int(settings["rate_limit_cooldown_seconds"]),
            auth_cooldown_seconds=int(settings["auth_cooldown_seconds"]),
            defer_on_cooldown=True,
            defer_on_auth=True,
        )
        print(json.dumps({"ok": False, "error": failure_text, "operator_id": operator_id}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
