#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import skill_capsule_bridge as bridge  # noqa: E402


def test_canonical_skill_id_normalizes_names() -> None:
    assert bridge.canonical_skill_id("ML Model Explanation") == "skill.ml-model-explanation"
    assert bridge.canonical_skill_id("nano-pdf") == "skill.nano-pdf"


def test_query_skill_candidates_prefers_exact_required_skill(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "load_skill_bridge_catalog",
        lambda include_all=True: [
            {
                "skill_id": "skill.nano-pdf",
                "name": "nano-pdf",
                "level": "effective",
                "level_rank": 4,
                "description": "Edit PDFs with natural-language instructions.",
                "execution_surface": "prompt_guided_cli",
                "aliases": ["skill.nano-pdf", "nano-pdf", "pdf", "edit-pdf"],
            },
            {
                "skill_id": "skill.kaizen",
                "name": "kaizen",
                "level": "effective",
                "level_rank": 4,
                "description": "Continuous improvement and refactoring guidance.",
                "execution_surface": "prompt_context_skill",
                "aliases": ["skill.kaizen", "kaizen", "refactor"],
            },
        ],
    )
    rows = bridge.query_skill_candidates(
        objective="Use nano-pdf to update the generated report PDF.",
        logical_operator="ImplementationWorker",
        task_type="implementation",
        required_skills=["nano-pdf"],
        limit=2,
    )
    assert rows[0]["skill_id"] == "skill.nano-pdf"
    assert rows[0]["match"]["exact_required"] == ["nano-pdf"]


def test_build_skill_bridge_payload_filters_unready_skills(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "load_skill_bridge_catalog",
        lambda include_all=True: [
            {
                "skill_id": "skill.discover-only",
                "name": "discover-only",
                "level": "discoverable",
                "level_rank": 1,
                "description": "Only discovered, not injectable.",
                "execution_surface": "discovered_only",
                "aliases": ["skill.discover-only", "discover-only"],
            },
            {
                "skill_id": "skill.content-research-writer",
                "name": "content-research-writer",
                "level": "injectable",
                "level_rank": 2,
                "description": "Research and citation oriented content writer.",
                "execution_surface": "prompt_context_skill",
                "aliases": ["skill.content-research-writer", "content-research-writer", "research", "citation"],
            },
        ],
    )
    payload = bridge.build_skill_bridge_payload(
        objective="Need citation-backed research writing help.",
        logical_operator="ResearchSynthesizer",
        task_type="research",
        required_skills=[],
    )
    assert payload["selected_skills"] == ["skill.content-research-writer"]
    assert payload["skill_bridge"]["mode"] == "auto_discovered_installed_skills"


def test_load_skill_bridge_catalog_dedupes_same_skill_id(monkeypatch, tmp_path) -> None:
    skill_a = tmp_path / "a" / "SKILL.md"
    skill_a.parent.mkdir(parents=True)
    skill_a.write_text("---\nname: nano-pdf\ndescription: short\n---\n", encoding="utf-8")
    skill_b = tmp_path / "b" / "SKILL.md"
    skill_b.parent.mkdir(parents=True)
    skill_b.write_text("---\nname: nano-pdf\ndescription: much longer description\n---\n", encoding="utf-8")
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "nano-pdf", "path": str(skill_a), "source": "codex-skills", "level": "injectable", "layers": {}},
                {"name": "nano-pdf", "path": str(skill_b), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert len(catalog) == 1
    assert catalog[0]["path"] == str(skill_b)


def test_load_skill_bridge_catalog_extracts_cli_hints_from_metadata(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "nano" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: nano-pdf
description: Edit PDFs with natural-language instructions using the nano-pdf CLI.
metadata:
  openclaw:
    requires:
      bins: ["nano-pdf"]
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "nano-pdf", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["cli_bins"] == ["nano-pdf"]
    assert catalog[0]["suggested_first_command"] == "nano-pdf --help"
    assert catalog[0]["suggested_verify_command"] == "nano-pdf --version"
    assert catalog[0]["cli_command_template"] == "nano-pdf <args>"
    assert catalog[0]["template_profile"] == "cli_tooling"
    assert catalog[0]["dispatch_strategy"] == "tool_first_cli_execution"
    assert catalog[0]["specialization_family"] == "pdf_cli_artifact"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-pdf-cli-pane-bridge"
    assert catalog[0]["delivery_expectation"] == "command_log_and_artifact_delta"
    assert "run_primary_command_path" in catalog[0]["workflow_phases"]


def test_load_skill_bridge_catalog_marks_methodology_skills(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "workflow" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: kaizen
description: A workflow guide and improvement methodology for iterative refactoring.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "kaizen", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["template_profile"] == "workflow_methodology"
    assert catalog[0]["dispatch_strategy"] == "workflow_first_guidance"
    assert catalog[0]["specialization_family"] == "workflow_generalist"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-workflow-pane-bridge"
    assert catalog[0]["delivery_expectation"] == "phase_checklist_and_decision_log"
    assert "apply_skill_workflow" in catalog[0]["workflow_phases"]
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "builder_idle"


def test_load_skill_bridge_catalog_routes_research_workflow_to_knowledge_idle(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "research" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: research-synth
description: A research workflow for evidence synthesis, citations, and knowledge analysis.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "research-synth", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "research_workflow"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-research-workflow-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "knowledge_idle"


def test_load_skill_bridge_catalog_routes_planning_workflow_to_planner_idle(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "planner" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: architect-planner
description: A planning and architecture workflow for roadmap and strategy decisions.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "architect-planner", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "planning_workflow"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-planning-workflow-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "planner_idle"


def test_load_skill_bridge_catalog_routes_github_review_cli(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "gh" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: gh-address-comments
description: Use gh CLI to address GitHub PR review comments and rerun verification.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "gh-address-comments", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "github_review_cli"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-github-review-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "builder_idle"
    assert catalog[0]["delivery_expectation"] == "review_comment_resolution_and_ci_status"


def test_load_skill_bridge_catalog_routes_eval_verification(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "evals" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: ai-evals
description: Run evaluations, compare results against acceptance criteria, and emit a verdict.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "ai-evals", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "evaluation_and_verification"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-eval-verification-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "evaluator_idle"
    assert catalog[0]["delivery_expectation"] == "verification_matrix_and_verdict"


def test_load_skill_bridge_catalog_routes_repo_refactor(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "refactor" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: agent-md-refactor
description: Refactor bloated instruction files and reduce technical debt with a staged cleanup plan.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "agent-md-refactor", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "repo_refactor"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-repo-refactor-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "builder_idle"


def test_load_skill_bridge_catalog_routes_frontend_accessibility(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "a11y" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: accessibility-auditor
description: Audit frontend accessibility, WCAG issues, and screen reader behavior.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "accessibility-auditor", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "frontend_accessibility"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-frontend-accessibility-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "evaluator_idle"


def test_load_skill_bridge_catalog_routes_api_backend_design(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "api" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: api-design
description: Design REST API endpoints, auth, pagination, and backend operability constraints.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "api-design", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "api_backend_design"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-api-backend-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "planner_idle"


def test_load_skill_bridge_catalog_routes_data_sheet_analysis(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "sheet" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: excel-analysis
description: Analyze spreadsheets, cohort metrics, and CSV datasets to extract findings and caveats.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "excel-analysis", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "data_sheet_analysis"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-data-sheet-analysis-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "knowledge_idle"


def test_load_skill_bridge_catalog_routes_infra_devops(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "ansible" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: ansible-automation
description: Automate infrastructure deployment, configuration management, and operability checks.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "ansible-automation", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "infra_devops_automation"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-infra-devops-pane-bridge"


def test_load_skill_bridge_catalog_routes_security_review(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "security" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: api-security-hardening
description: Review API hardening, RBAC, and residual security exposure.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "api-security-hardening", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "security_review_hardening"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-security-review-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "evaluator_idle"


def test_load_skill_bridge_catalog_routes_frontend_ui(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "ui" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: aesthetic
description: Improve frontend UI, component architecture, and visual polish.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "aesthetic", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "frontend_ui_engineering"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-frontend-ui-pane-bridge"


def test_load_skill_bridge_catalog_routes_agent_building(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "agent" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: agent-development
description: Create agents, define memory and tools, and design multi-agent system contracts.
---
""",
        encoding="utf-8",
    )
    bridge.load_skill_bridge_catalog.cache_clear()
    monkeypatch.setattr(
        bridge.solar_skills,
        "_readiness_payload",
        lambda include_all=True, write_scorecards=False: {
            "skills": [
                {"name": "agent-development", "path": str(skill), "source": "agents-skills", "level": "injectable", "layers": {}},
            ]
        },
    )
    catalog = bridge.load_skill_bridge_catalog()
    assert catalog[0]["specialization_family"] == "agent_building_systems"
    assert catalog[0]["recommended_operator_profile"] == "mini-skill-agent-building-pane-bridge"
    assert catalog[0]["recommended_runtime_preferences"]["pane_target_selector"] == "planner_idle"


def test_build_skill_bridge_payload_prefers_exact_required_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "query_skill_candidates",
        lambda **kwargs: [
            {
                "skill_id": "skill.nano-pdf",
                "level_rank": 4,
                "match": {"exact_required": ["nano-pdf"], "exact_signal": [], "fuzzy_hits": []},
            },
            {
                "skill_id": "skill.figma",
                "level_rank": 4,
                "match": {"exact_required": [], "exact_signal": ["artifact"], "fuzzy_hits": ["patch"]},
            },
        ],
    )
    payload = bridge.build_skill_bridge_payload(
        objective="Use nano-pdf to patch the generated PDF artifact.",
        logical_operator="UnknownOperator",
        task_type="implementation",
        required_skills=["nano-pdf"],
    )
    assert payload["selected_skills"] == ["skill.nano-pdf"]


def test_build_skill_bridge_payload_carries_template_profile_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "query_skill_candidates",
        lambda **kwargs: [
            {
                "skill_id": "skill.nano-pdf",
                "level_rank": 4,
                "template_profile": "cli_tooling",
                "dispatch_strategy": "tool_first_cli_execution",
                "specialization_family": "pdf_cli_artifact",
                "recommended_operator_profile": "mini-skill-pdf-cli-pane-bridge",
                "match": {"exact_required": ["nano-pdf"], "exact_signal": [], "fuzzy_hits": []},
            },
        ],
    )
    payload = bridge.build_skill_bridge_payload(
        objective="Use nano-pdf to patch the generated PDF artifact.",
        logical_operator="UnknownOperator",
        task_type="implementation",
        required_skills=["nano-pdf"],
    )
    assert payload["skill_bridge"]["template_profile"] == "cli_tooling"
    assert payload["skill_bridge"]["dispatch_strategy"] == "tool_first_cli_execution"
    assert payload["skill_bridge"]["specialization_family"] == "pdf_cli_artifact"
    assert payload["skill_bridge"]["recommended_operator_profile"] == "mini-skill-pdf-cli-pane-bridge"
    assert payload["skill_bridge"]["delivery_expectation"] == "command_log_and_artifact_delta"
