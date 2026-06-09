#!/usr/bin/env python3
from __future__ import annotations

from harness.lib import graph_scheduler as mod


def test_spec_write_alias_matches_architecture_writing() -> None:
    worker = {
        "skills": ["architecture-writing", "technical-writing", "markdown"],
        "capabilities": ["documentation"],
    }
    assert mod._skills_match(worker, ["spec.write"]) is True


def test_provider_contract_alias_matches_api_design_family() -> None:
    worker = {
        "skills": ["architecture", "api-design", "schema"],
        "capabilities": ["rules.catalog", "agent.inventory"],
    }
    assert mod._skills_match(worker, ["provider.contract"]) is True


def test_browser_automation_hyphen_alias_matches_browser_dot_skill() -> None:
    worker = {
        "skills": ["browser.automation", "browser.qa"],
        "capabilities": ["browser.mcp"],
    }
    assert mod._skills_match(worker, ["browser-automation"]) is True


def test_backend_development_alias_matches_builder_impl_family() -> None:
    worker = {
        "skills": ["code_impl", "python", "integration"],
        "capabilities": ["subprocess"],
    }
    assert mod._skills_match(worker, ["backend-development"]) is True


def test_planner_alias_matches_planning_worker_skill() -> None:
    worker = {
        "skills": ["planning", "workflow.planning", "markdown"],
        "capabilities": ["harness.dag"],
    }
    assert mod._skills_match(worker, ["planner"]) is True


def test_assign_workers_prefers_planner_role_before_builder_fallback() -> None:
    node = {
        "id": "N1",
        "required_skills": ["architecture-writing"],
        "required_capabilities": ["documentation"],
        "capsule_plan_ir": {"role": "planner"},
        "physical_plan_ir": {"role": "planner"},
    }
    workers = [
        {
            "pane": "solar-harness-lab:0.0",
            "role": "builder",
            "skills": ["architecture-writing", "markdown"],
            "capabilities": ["documentation"],
            "models": ["sonnet"],
        },
        {
            "pane": "solar-harness:0.1",
            "role": "planner",
            "skills": ["architecture-writing", "markdown"],
            "capabilities": ["documentation"],
            "models": ["sonnet"],
        },
    ]
    result = mod.assign_workers([node], workers)
    assert result["assigned"][0]["pane"] == "solar-harness:0.1"
    assert result["assigned"][0]["dispatch_role"] == "planner"
    assert result["assigned"][0]["worker_role"] == "planner"


def test_assign_workers_builder_node_does_not_match_planner_only_pane() -> None:
    node = {
        "id": "N1",
        "required_skills": ["architecture-writing"],
        "required_capabilities": ["documentation"],
        "capsule_plan_ir": {"role": "builder"},
        "physical_plan_ir": {"role": "builder"},
    }
    workers = [
        {
            "pane": "solar-harness:0.1",
            "role": "planner",
            "skills": ["architecture-writing", "markdown"],
            "capabilities": ["documentation"],
            "models": ["sonnet"],
        },
    ]
    result = mod.assign_workers([node], workers)
    assert result["assigned"] == []
    assert result["queued"][0]["reason"] == "no_matching_worker"
    assert result["queued"][0]["details"]["required_role"] == "builder"
