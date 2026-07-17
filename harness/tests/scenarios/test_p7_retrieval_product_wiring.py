"""Research retrieval must route through the normal governed Codex product path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_HARNESS = Path(__file__).resolve().parents[2]
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import capability_capsules as cc  # noqa: E402
import graph_scheduler as gs  # noqa: E402
import plan_validator as pv  # noqa: E402
from multi_task_runner import operator_supports_task_type  # noqa: E402


def test_research_scout_binds_generic_retrieval_capsule():
    plan = cc.default_capability_plan_for_logical_operator(
        "ResearchScout",
        request_type="research",
        node={"type": "research", "goal": "Gather current web sources"},
        registry_path=_HARNESS / "config" / "capability-capsules.registry.yaml",
    )
    assert plan["capability_capsule_id"] == "cap.research-retrieval"
    assert plan["dispatch_task_type"] == "knowledge-extraction"


def test_research_synthesizer_keeps_synthesis_capsule():
    plan = cc.default_capability_plan_for_logical_operator(
        "ResearchSynthesizer",
        request_type="research",
        node={"type": "research", "goal": "Synthesize claims from evidence"},
        registry_path=_HARNESS / "config" / "capability-capsules.registry.yaml",
    )
    assert plan["capability_capsule_id"] == "cap.requirement-research-synthesizer"
    assert plan["dispatch_task_type"] == "research"
    assert plan["selected_skills"] == []
    assert plan["required_resource_capsules"] == []
    assert plan["operator_constraints"]["default_operator_profile"] == "mini-codex-gpt55-medium-builder-1"


def test_draft_understand_anything_capsule_is_not_advertised_on_product_route():
    plan = cc.default_capability_plan_for_logical_operator(
        "ResearchScout",
        request_type="research",
        node={"type": "research", "goal": "Build a codebase knowledge graph and onboarding map"},
        registry_path=_HARNESS / "config" / "capability-capsules.registry.yaml",
    )
    assert plan == {}


def test_research_nodes_with_outputs_are_builder_work():
    node = {
        "logical_operator": "ResearchScout",
        "write_scope": ["workspace/research/source-pack/sources.jsonl"],
    }
    assert gs.node_dispatch_role(node) == "builder"
    assert gs.node_dispatch_role({"logical_operator": "ResearchScout", "write_scope": []}) == "planner"


def test_enabled_codex_research_builder_admits_retrieval_and_synthesis():
    operators = json.loads((_HARNESS / "config" / "physical-operators.json").read_text(encoding="utf-8"))["operators"]
    research_builder = operators["mini-codex-gpt55-medium-builder-1"]
    spark_builder = operators["mini-codex-gpt53-spark-builder-1"]

    assert research_builder["enabled"] is True
    assert operator_supports_task_type(research_builder, "knowledge-extraction") is True
    assert operator_supports_task_type(research_builder, "research") is True
    assert operator_supports_task_type(spark_builder, "knowledge-extraction") is False


def test_planner_policy_teaches_shape_free_evidence_and_source_vocabulary(monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    block = pv.planner_compile_policy_block(config_dir=_HARNESS / "config")

    assert "Rule of evidence" in block
    assert "cap.research-retrieval" in block
    assert "sources.jsonl" in block
    assert "claims.jsonl" in block
    assert "official_doc" in block
    assert "no required research DAG" in block
    assert "compile-grounded" in block
    assert "synthesis_plan.json" in block
    assert "solar.grounded_synthesis_plan.v2" in block
    assert "exact quote" in block
    assert "contradicts" in block


def test_synthesis_capsule_describes_the_grounded_report_bundle():
    manifest = yaml.safe_load(
        (_HARNESS / "config" / "capability-capsules" / "cap.requirement-research-synthesizer.yaml").read_text(
            encoding="utf-8"
        )
    )
    inputs = {item["name"] for item in manifest["contract"]["inputs"]["required"]}
    outputs = {item["name"] for item in manifest["contract"]["outputs"]["required"]}

    assert cc.validate_capability_capsule(manifest) == []
    assert {"research_question", "source_packs", "synthesis_plan"}.issubset(inputs)
    assert {
        "claims_jsonl",
        "evidence_gaps_json",
        "report_ast_json",
        "final_md",
        "research_eval_json",
    }.issubset(outputs)
    assert manifest["version"] == "0.3.0"
    assert "report-writing" in manifest["applicability"]["task_types"]
    assert manifest["bindings"]["skills"]["required"] == []
    assert "mini-codex-gpt55-medium-builder-1" in manifest["operator_compatibility"]["preferred"]
