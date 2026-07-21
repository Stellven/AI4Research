#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import skill_dispatch_operator as sdo  # noqa: E402


def test_build_request_prefers_skill_surface(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sdo,
        "resolve_skill_records",
        lambda selected: [
            {
                "skill_id": "skill.nano-pdf",
                "level": "injectable",
                "execution_surface": "prompt_guided_cli",
                "path": "/tmp/nano-pdf/SKILL.md",
                "description": "PDF CLI",
            }
        ],
    )
    monkeypatch.setattr(
        sdo,
        "_discover_tmux_panes",
        lambda: [
            {
                "session": "solar-harness-lab",
                "window": "0",
                "pane": "1",
                "target": "solar-harness-lab:0.1",
                "title": "Builder 1 | Sonnet",
                "command": "claude",
            }
        ],
    )
    request = sdo.build_request(
        {
            "task_id": "T1",
            "objective": "Use nano-pdf to rewrite the generated PDF.",
            "selected_skills": ["skill.nano-pdf"],
        },
        task_dir=tmp_path,
    )
    assert request["execution_surface"] == "prompt_guided_cli"
    assert request["pane_target"] == "solar-harness-lab:0.1"


def test_validate_request_rejects_missing_skills():
    try:
        sdo._validate_request({"objective": "x", "selected_skills": [], "execution_surface": "prompt_context_skill"})
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "selected_skills required" in str(exc)


def test_run_request_writes_prompt_and_result(monkeypatch, tmp_path):
    calls = []

    class FakeHand:
        def provision(self, *, capabilities=None, location=None):
            calls.append(("provision", list(capabilities or []), location))
            return type("Ref", (), {"location": location, "hand_id": "pane-1"})()

        def execute(self, hand_ref, command_name, input_data, *, idempotency_key, timeout_seconds=None):
            calls.append(("execute", command_name, input_data.get("command")))
            return type(
                "Result",
                (),
                {
                    "status": sdo.ResultStatus.OK,
                    "output": {"pane": hand_ref.location, "command_sent": input_data.get("command")},
                    "error": "",
                },
            )()

    monkeypatch.setattr(sdo, "PaneHand", lambda: FakeHand())
    request = {
        "task_id": "T2",
        "objective": "Use selected skills to complete the task.",
        "selected_skills": ["skill.nano-pdf"],
        "skill_records": [
            {
                "skill_id": "skill.nano-pdf",
                "level": "injectable",
                "execution_surface": "prompt_guided_cli",
                "template_profile": "cli_tooling",
                "specialization_family": "pdf_cli_artifact",
                "dispatch_strategy": "tool_first_cli_execution",
                "suggested_first_command": "nano-pdf --help",
                "suggested_verify_command": "nano-pdf --version",
                "cli_command_template": "nano-pdf <args>",
                "workflow_phases": [
                    "inspect_tool_contract",
                    "run_primary_command_path",
                    "verify_outputs_and_exit_signals",
                    "record_command_evidence",
                ],
                "delivery_expectation": "command_log_and_artifact_delta",
                "path": "/tmp/nano-pdf/SKILL.md",
                "description": "PDF CLI",
            }
        ],
        "execution_surface": "prompt_guided_cli",
        "pane_target": "solar-harness-lab:0.1",
        "pane_resolution": {"strategy": "explicit_full_target"},
        "result_path": str(tmp_path / "closeout.md"),
        "required_skills": ["nano-pdf"],
        "required_capabilities": ["documentation"],
        "acceptance": ["Produce an updated PDF."],
        "resolved_capability_capsule": {"verification_hooks": {"self_check": ["check.skill_dispatch_result_written"]}},
    }
    result = sdo.run_request(request, task_dir=tmp_path)
    assert result["ok"] is True
    assert (tmp_path / "skill-dispatch-pane-prompt.md").exists()
    assert (tmp_path / "skill-dispatch-bridge-contract.json").exists()
    assert (tmp_path / "skill-dispatch-selection-proof.json").exists()
    assert (tmp_path / "skill-dispatch-result.json").exists()
    contract = json.loads((tmp_path / "skill-dispatch-bridge-contract.json").read_text(encoding="utf-8"))
    assert contract["specialization_family"] == "pdf_cli_artifact"
    assert contract["command_protocol"]["mode"] == "cli_tooling"
    assert contract["command_protocol"]["command_template"] == "nano-pdf <args>"
    assert contract["workflow_contract"]["delivery_expectation"] == "command_log_and_artifact_delta"
    prompt_body = (tmp_path / "skill-dispatch-pane-prompt.md").read_text(encoding="utf-8")
    assert "## CLI Execution Discipline" in prompt_body
    assert "## Specialization Discipline" in prompt_body
    assert "Preserve citations, links, and visible structure" in prompt_body
    assert "Delivery Expectation: `command_log_and_artifact_delta`" in prompt_body
    assert "inspect_tool_contract" in prompt_body
    assert calls[0][0] == "provision"
    assert calls[1][0] == "execute"
    assert "Read" in calls[1][2]
    assert "Preserve citations, links, and visible document structure" in calls[1][2]
    assert "Start with `nano-pdf --help`" in calls[1][2]
    assert "Use `nano-pdf --version` as a lightweight verification check" in calls[1][2]
    assert "Prefer the command shape `nano-pdf <args>`" in calls[1][2]


def test_build_prompt_markdown_for_workflow_profile(tmp_path):
    request = {
        "task_id": "T4",
        "objective": "Use the methodology skill to review and refine the plan.",
        "selected_skills": ["skill.kaizen"],
        "skill_records": [
            {
                "skill_id": "skill.kaizen",
                "level": "injectable",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "planning_workflow",
                "dispatch_strategy": "workflow_first_guidance",
                "workflow_phases": [
                    "frame_objective_and_constraints",
                    "apply_skill_workflow",
                    "validate_against_acceptance",
                    "summarize_decisions_and_evidence",
                ],
                "delivery_expectation": "phase_checklist_and_decision_log",
                "path": "/tmp/kaizen/SKILL.md",
                "description": "A workflow guide for iterative improvement.",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
        "resolved_capability_capsule": {},
    }
    body = sdo._build_prompt_markdown(request, tmp_path / "prompt.md")
    assert "Template Profile: `workflow_methodology`" in body
    assert "Specialization Family: `planning_workflow`" in body
    assert "Delivery Expectation: `phase_checklist_and_decision_log`" in body
    assert "## Workflow Discipline" in body
    assert "## Specialization Discipline" in body
    assert "Surface options, tradeoffs, and decision rationale" in body
    assert "frame_objective_and_constraints" in body
    assert "generic completion style" in body


def test_workflow_contract_helpers_for_methodology_profile():
    request = {
        "selected_skills": ["skill.kaizen"],
        "skill_records": [
            {
                "skill_id": "skill.kaizen",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "workflow_phases": [
                    "frame_objective_and_constraints",
                    "apply_skill_workflow",
                ],
                "delivery_expectation": "phase_checklist_and_decision_log",
            }
        ],
        "execution_surface": "prompt_context_skill",
    }
    protocol = sdo._command_protocol(request)
    contract = sdo._workflow_contract(request)
    assert protocol["mode"] == "workflow_methodology"
    assert contract["phases"] == ["frame_objective_and_constraints", "apply_skill_workflow"]
    assert contract["delivery_expectation"] == "phase_checklist_and_decision_log"


def test_build_pane_command_for_workflow_profile(tmp_path):
    request = {
        "selected_skills": ["skill.kaizen"],
        "skill_records": [
            {
                "skill_id": "skill.kaizen",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "planning_workflow",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
    }
    command = sdo._build_pane_command(request, tmp_path / "prompt.md")
    assert "methodology-oriented installed skills" in command
    assert "Surface options, tradeoffs, and a decision log" in command
    assert "Follow the workflow explicitly" in command
    assert "frame_objective_and_constraints" in command
    assert "delivery_expectation=phase_checklist_and_decision_log" in command


def test_build_pane_command_for_github_review_family(tmp_path):
    request = {
        "selected_skills": ["skill.gh-address-comments"],
        "skill_records": [
            {
                "skill_id": "skill.gh-address-comments",
                "execution_surface": "prompt_guided_cli",
                "template_profile": "cli_tooling",
                "specialization_family": "github_review_cli",
                "suggested_first_command": "gh pr view",
                "suggested_verify_command": "gh pr checks",
                "cli_command_template": "gh <subcommand>",
            }
        ],
        "execution_surface": "prompt_guided_cli",
        "result_path": str(tmp_path / "closeout.md"),
    }
    command = sdo._build_pane_command(request, tmp_path / "prompt.md")
    assert "review-comment to fix mapping" in command
    assert "gh pr view" in command
    assert "gh pr checks" in command


def test_build_prompt_markdown_for_eval_family(tmp_path):
    request = {
        "task_id": "T5",
        "objective": "Run verification and produce a verdict.",
        "selected_skills": ["skill.ai-evals"],
        "skill_records": [
            {
                "skill_id": "skill.ai-evals",
                "level": "injectable",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "evaluation_and_verification",
                "dispatch_strategy": "workflow_first_guidance",
                "workflow_phases": [
                    "frame_verification_scope",
                    "run_checks_or_evals",
                    "compare_results_against_acceptance",
                    "emit_verdict_and_residual_risk",
                ],
                "delivery_expectation": "verification_matrix_and_verdict",
                "path": "/tmp/ai-evals/SKILL.md",
                "description": "Evaluation workflow",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
        "resolved_capability_capsule": {},
    }
    body = sdo._build_prompt_markdown(request, tmp_path / "prompt.md")
    assert "Specialization Family: `evaluation_and_verification`" in body
    assert "## Specialization Discipline" in body
    assert "verification matrix" in body


def test_resolve_pane_target_supports_evaluator_idle(monkeypatch):
    monkeypatch.setattr(
        sdo,
        "_discover_tmux_panes",
        lambda: [
            {"session": "solar-harness", "window": "0", "pane": "1", "target": "solar-harness:0.1", "title": "Builder 1", "command": "claude"},
            {"session": "solar-harness", "window": "0", "pane": "2", "target": "solar-harness:0.2", "title": "Evaluator | Opus", "command": "claude"},
        ],
    )
    target, meta = sdo._resolve_pane_target({"pane_target_selector": "evaluator_idle", "pane_target": "best_effort"})
    assert target == "solar-harness:0.2"
    assert meta["selector"] == "evaluator_idle"


def test_build_prompt_markdown_for_api_backend_family(tmp_path):
    request = {
        "task_id": "T6",
        "objective": "Design API contract and backend decisions.",
        "selected_skills": ["skill.api-design"],
        "skill_records": [
            {
                "skill_id": "skill.api-design",
                "level": "injectable",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "api_backend_design",
                "dispatch_strategy": "workflow_first_guidance",
                "workflow_phases": [
                    "frame_contract_and_constraints",
                    "design_endpoints_models_and_policies",
                    "validate_operability_and_security",
                    "summarize_api_decisions_and_open_risks",
                ],
                "delivery_expectation": "api_contract_and_backend_decision_log",
                "path": "/tmp/api-design/SKILL.md",
                "description": "API design workflow",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
        "resolved_capability_capsule": {},
    }
    body = sdo._build_prompt_markdown(request, tmp_path / "prompt.md")
    assert "Specialization Family: `api_backend_design`" in body
    assert "## Specialization Discipline" in body
    assert "contract, security, pagination" in body


def test_build_prompt_markdown_for_frontend_accessibility_family(tmp_path):
    request = {
        "task_id": "T7",
        "objective": "Audit accessibility issues and produce remediation plan.",
        "selected_skills": ["skill.accessibility-auditor"],
        "skill_records": [
            {
                "skill_id": "skill.accessibility-auditor",
                "level": "injectable",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "frontend_accessibility",
                "dispatch_strategy": "workflow_first_guidance",
                "workflow_phases": [
                    "inspect_accessibility_scope",
                    "identify_wcag_issues",
                    "propose_or_apply_remediations",
                    "summarize_issue_matrix_and_risk",
                ],
                "delivery_expectation": "accessibility_issue_matrix_and_fix_plan",
                "path": "/tmp/accessibility-auditor/SKILL.md",
                "description": "Accessibility workflow",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
        "resolved_capability_capsule": {},
    }
    body = sdo._build_prompt_markdown(request, tmp_path / "prompt.md")
    assert "Specialization Family: `frontend_accessibility`" in body
    assert "issue matrix" in body


def test_build_prompt_markdown_for_security_review_family(tmp_path):
    request = {
        "task_id": "T8",
        "objective": "Review hardening gaps and produce residual risk summary.",
        "selected_skills": ["skill.api-security-hardening"],
        "skill_records": [
            {
                "skill_id": "skill.api-security-hardening",
                "level": "injectable",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "security_review_hardening",
                "dispatch_strategy": "workflow_first_guidance",
                "workflow_phases": [
                    "frame_threat_surface_and_controls",
                    "identify_gaps_or_attack_paths",
                    "map_hardening_actions_and_priority",
                    "summarize_risk_matrix_and_residual_exposure",
                ],
                "delivery_expectation": "risk_matrix_and_hardening_actions",
                "path": "/tmp/api-security-hardening/SKILL.md",
                "description": "Security review workflow",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
        "resolved_capability_capsule": {},
    }
    body = sdo._build_prompt_markdown(request, tmp_path / "prompt.md")
    assert "Specialization Family: `security_review_hardening`" in body
    assert "risk-oriented structure" in body


def test_build_prompt_markdown_for_agent_building_family(tmp_path):
    request = {
        "task_id": "T9",
        "objective": "Design agent roles, memory, and context contract.",
        "selected_skills": ["skill.agent-development"],
        "skill_records": [
            {
                "skill_id": "skill.agent-development",
                "level": "injectable",
                "execution_surface": "prompt_context_skill",
                "template_profile": "workflow_methodology",
                "specialization_family": "agent_building_systems",
                "dispatch_strategy": "workflow_first_guidance",
                "workflow_phases": [
                    "frame_agent_roles_memory_and_tools",
                    "design_runtime_and_coordination_contract",
                    "validate_failure_modes_and_observability",
                    "summarize_agent_system_design_and_open_risks",
                ],
                "delivery_expectation": "agent_design_and_system_contract",
                "path": "/tmp/agent-development/SKILL.md",
                "description": "Agent building workflow",
            }
        ],
        "execution_surface": "prompt_context_skill",
        "result_path": str(tmp_path / "closeout.md"),
        "resolved_capability_capsule": {},
    }
    body = sdo._build_prompt_markdown(request, tmp_path / "prompt.md")
    assert "Specialization Family: `agent_building_systems`" in body
    assert "agent roles, memory, tools" in body


def test_main_applies_success_cooldown(monkeypatch, tmp_path):
    envelope = {
        "task_id": "T3",
        "operator_id": "mini-skill-dispatch-pane-bridge",
        "objective": "Use installed skills.",
        "selected_skills": ["skill.nano-pdf"],
    }
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
    monkeypatch.setenv("SOLAR_OPERATOR_ENVELOPE_JSON", str(envelope_path))
    monkeypatch.setenv("TASK_DIR", str(tmp_path / "task"))
    monkeypatch.setattr(sdo.ofc, "ensure_operator_available", lambda operator_id, allow_unregistered=True: None)
    monkeypatch.setattr(
        sdo,
        "build_request",
        lambda envelope, task_dir=None: {
            "task_id": "T3",
            "objective": "Use installed skills.",
            "selected_skills": ["skill.nano-pdf"],
            "execution_surface": "prompt_context_skill",
            "pane_target": "0",
            "pane_resolution": {"strategy": "explicit_legacy_target"},
            "result_path": "",
        },
    )
    monkeypatch.setattr(sdo, "run_request", lambda request, task_dir: {"ok": True})
    calls = []
    monkeypatch.setattr(
        sdo.ofc,
        "apply_success_cooldown",
        lambda operator_id, *, success_cooldown_seconds: calls.append((operator_id, success_cooldown_seconds)) or {},
    )
    assert sdo.main() == 0
    assert calls == [("mini-skill-dispatch-pane-bridge", 120)]
