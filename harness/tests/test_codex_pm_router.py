#!/usr/bin/env python3
"""Tests for codex_pm_router capability plan emission."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "tools" / "codex_pm_router.py"


def _load_router():
    for module_name in ("codex_pm_router", "capability_capsules", "requirement_coverage", "apo_plan_compiler"):
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location("codex_pm_router", ROUTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_pm_intake_emits_capsule_plan_for_standard_request():
    router = _load_router()
    payload = router.build_pm_intake(
        "Build a requirement compiler that produces PRD, contracts, and task graphs.",
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    assert by_id["S1"]["capability_capsule_id"] == "cap.requirement-compiler-planner"
    assert by_id["S2"]["capability_capsule_id"] == "cap.requirement-compiler-implementation"
    assert by_id["S4"]["capability_capsule_id"] == "cap.requirement-compiler-verification"
    assert by_id["S2"]["capsule_plan"]["required_resource_capsules"] == ["resource.repo-workspace"]
    validation = router.validate_compiled_package(payload)
    assert validation["ok"] is True
    assert validation["errors"] == []


def test_standard_compiled_prd_passes_existing_schema_validator(tmp_path):
    router = _load_router()
    payload = router.build_pm_intake(
        "Build a requirement compiler that produces PRD, contracts, and task graphs.",
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    prd_path = tmp_path / "compiled.prd.md"
    prd_path.write_text(payload["compiled_artifacts"]["prd_markdown"], encoding="utf-8")
    result = subprocess.run(
        ["bash", str(ROOT / "schemas" / "validate.sh"), "prd", str(prd_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_parallel_delivery_still_enforces_ready_width_gate():
    router = _load_router()
    payload = router.build_pm_intake(
        "Fix the reliability bug and produce a hotfix rollout plan.",
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    assert payload["dag_variant"] == "parallel_delivery"
    assert router.validate_compiled_package(payload)["ok"] is True

    graph = payload["compiled_artifacts"]["task_dag"]
    graph["nodes"][1]["depends_on"] = ["S1"]
    graph["nodes"][2]["depends_on"] = ["S1"]

    validation = router.validate_compiled_package(payload)
    assert validation["ok"] is False
    assert any(error.startswith("task_graph_ready_width_below_min:") for error in validation["errors"])


def test_build_pm_intake_emits_capsule_plan_for_research_request():
    router = _load_router()
    payload = router.build_pm_intake(
        "Read these papers and synthesize research implications for the planner.",
        papers=["paper-a"],
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    assert by_id["R1"]["capability_capsule_id"] == "cap.requirement-research-scout"
    assert by_id["R4"]["capability_capsule_id"] == "cap.requirement-research-synthesizer"
    assert by_id["R5"]["capability_capsule_id"] == "cap.requirement-compiler-verification"


def test_browser_agent_operator_request_is_standard_implementation_not_research():
    router = _load_router()
    text = """
    增加 Browser Agent 物理执行算子，用 browser 自动化调用 ChatGPT Deep Research
    和 Gemini Deep Research。需要接入 operator runtime、registry、schema、
    logical_operator、async submit/poll/collect、quota fallback 和 bridge observability。
    """
    payload = router.build_pm_intake(text, sprint_id="sprint-test", target_system="solar-harness")
    assert payload["classification"] == router.FULL_SPEC
    assert payload["dag_variant"] == "standard"
    node_ids = [node["id"] for node in payload["compiled_artifacts"]["task_dag"]["nodes"]]
    assert node_ids[:4] == ["S1", "S2", "S3", "S4"]


def test_convergence_request_uses_parallel_spec_dag():
    router = _load_router()
    payload = router.build_pm_intake(
        "把 GitHub Hotspot Radar 收口成统一 convergence package，补 architecture、contract、traceability 和 rollout。",
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    assert payload["classification"] == router.FULL_SPEC
    assert payload["dag_variant"] == "parallel_spec"
    assert payload["compiled_artifacts"]["task_dag"]["dag_variant"] == "parallel_spec"
    assert by_id["S2"]["depends_on"] == ["S1"]
    assert by_id["S3"]["depends_on"] == ["S1"]
    assert by_id["S4"]["depends_on"] == ["S1"]
    assert by_id["S5"]["depends_on"] == ["S2", "S3", "S4"]
    assert by_id["S1"]["gate"] == "G_PLAN"
    assert by_id["S2"]["gate"] == "G_IMPL"
    assert by_id["S3"]["gate"] == "G_IMPL"
    assert by_id["S4"]["gate"] == "G_VERIFY"
    assert by_id["S5"]["gate"] == "G_REVIEW"


def test_productization_request_uses_parallel_spec_dag():
    router = _load_router()
    payload = router.build_pm_intake(
        "继续做 skill-to-capsule operator 产品化，输出蓝图、追踪矩阵和最终收口。",
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    assert payload["dag_variant"] == "parallel_spec"
    assert by_id["S4"]["logical_operator"] == "ArtifactCurator"
    assert by_id["S5"]["logical_operator"] == "Verifier"


def test_plain_paper_research_request_still_uses_research_dag():
    router = _load_router()
    payload = router.build_pm_intake(
        "调研这些论文并输出证据链和技术洞察。",
        papers=["paper-a"],
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    assert payload["classification"] == router.RESEARCH
    assert payload["dag_variant"] == "research"


def test_code_understanding_request_rewrites_standard_graph_goals():
    router = _load_router()
    payload = router.build_pm_intake(
        "为这个仓库生成 knowledge graph、architecture map 和 onboarding artifacts。",
        repo_context=["~/Solar"],
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    assert payload["dag_variant"] == "standard"
    assert by_id["S1"]["type"] == "code-understanding"
    assert "knowledge-graph" in by_id["S1"]["signals"]
    assert "knowledge graph" in by_id["S2"]["goal"].lower()
    assert by_id["S2"]["outputs"] == ["knowledge-graph.json", "meta.json", "chunk-manifest.json", "resume-state.json"]
    assert by_id["S1"]["gate"] == "G_PLAN"
    assert by_id["S2"]["gate"] == "G_IMPL"
    assert by_id["S3"]["gate"] == "G_VERIFY"
    assert by_id["S4"]["gate"] == "G_REVIEW"
    assert by_id["S5"]["gate"] == "G_REVIEW"


def test_code_understanding_request_rewrites_research_graph_goals():
    router = _load_router()
    payload = router.build_pm_intake(
        "结合仓库和这些论文，输出代码库理解、architecture map、onboarding 和 knowledge graph。",
        papers=["paper-a"],
        repo_context=["~/Solar"],
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    nodes = payload["compiled_artifacts"]["task_dag"]["nodes"]
    by_id = {node["id"]: node for node in nodes}
    assert payload["dag_variant"] == "research"
    assert "knowledge graph" in by_id["R1"]["goal"].lower()
    assert "architecture map" in by_id["R2"]["goal"].lower()
    assert "onboarding" in by_id["R4"]["goal"].lower()
    assert by_id["R1"]["gate"] == "G_SOURCE"
    assert by_id["R2"]["gate"] == "G_EVIDENCE"
    assert by_id["R3"]["gate"] == "G_EVIDENCE"
    assert by_id["R4"]["gate"] == "G_SYNTHESIS"
    assert by_id["R5"]["gate"] == "G_REVIEW"
    assert by_id["R6"]["gate"] == "G_REVIEW"


def test_solar_handoff_view_uses_sprint_root_artifacts_for_sprint_packages():
    router = _load_router()
    payload = router.build_pm_intake(
        "为 GitHub Hotspot Radar 收口 requirement package 和 handoff。",
        sprint_id="sprint-test",
        target_system="solar-harness",
    )
    handoff_view = payload["requirement_ir"]["handoff_view"]
    assert handoff_view["codex"]["artifacts"] == [
        "sprint-test.requirement_ir.json",
        "sprint-test.prd.md",
        "sprint-test.Contracts.yaml",
        "sprint-test.task_graph.json",
    ]
    assert handoff_view["solar_harness"]["artifacts"] == [
        "sprint-test.requirement_ir.json",
        "sprint-test.prd.md",
        "sprint-test.Contracts.yaml",
        "sprint-test.task_graph.json",
        "sprint-test.handoff.md",
    ]
    solar_handoff = payload["compiled_artifacts"]["handoff_markdown"]["solar_harness"]
    assert "sprint-test.requirement_ir.json" in solar_handoff
    assert ".pm/requirement_ir.json" not in solar_handoff


def test_build_pm_intake_sanitizes_rawintent_consumer_payload():
    router = _load_router()
    consumer_text = """# RawIntent Consumer Request - codex bridge consumer smoke

## Source

- intent_id: intent-20260525-153733-d0bbf8d0af
- channel: codex_bridge
- actor: codex
- device: mac_mini
- thread_ref: N/A

## Rewritten Objective

让 Codex bridge 捕获 RawIntent 并自动编译成 sprint package。

## Problem

--- 
title: codex bridge consumer smoke
---
Codex bridge should capture RawIntent and auto consume into sprint package.

## Constraints

- All execution must enter Solar-Harness through RawIntent.

## Acceptance

- RawIntent, rewritten_intent, requirement_ir, and requirement_trace artifacts are persisted.

## Raw User Intent

[entrypoint_metadata]
sprint_id: N/A
node_id: N/A
role: pm

[raw_request]
Codex bridge should capture RawIntent and auto consume into sprint package.
"""
    payload = router.build_pm_intake(consumer_text, sprint_id="sprint-test", target_system="solar-harness")
    requirement_ir = payload["requirement_ir"]
    prd = payload["compiled_artifacts"]["prd_markdown"]
    assert "## Source" not in requirement_ir["normalized_goal"]
    assert "thread_ref:" not in requirement_ir["normalized_goal"]
    assert requirement_ir["normalized_goal"] == "让 Codex bridge 捕获 RawIntent 并自动编译成 sprint package。"
    assert requirement_ir["problem_statement"] == "Codex bridge should capture RawIntent and auto consume into sprint package."
    assert "RawIntent Consumer Request" not in prd


def test_validate_compiled_package_rejects_raw_metadata_pollution():
    router = _load_router()
    payload = router.build_pm_intake("正常需求：补齐 requirement compiler 的 closeout gate。", sprint_id="sprint-test")
    payload["requirement_ir"]["normalized_goal"] = "# RawIntent Consumer Request - ## Source intent_id: test"
    result = router.validate_compiled_package(payload)
    assert result["ok"] is False
    assert "raw_metadata_pollution_detected" in result["errors"]


def test_codex_pm_router_cli_defaults_to_rawintent(tmp_path):
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(ROOT)
    env["HARNESS_DIR"] = str(ROOT)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROUTER_PATH),
            "--text",
            "把 codex_pm_router 入口接到 RawIntent 主链。",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "rawintent"
    results = payload["consumer"]["results"]
    assert results and results[0]["status"] == "consumed"
