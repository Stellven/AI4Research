from __future__ import annotations

import inspect
import os
import sys


_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research import deepdive_requirement_compiler as compiler
from research import deepdive_brief_expander as expander


def test_generic_research_words_do_not_trigger_deepdive():
    assert not compiler.is_explicit_deepdive_request("帮我调研一下 agent memory 的论文")
    assert not compiler.is_explicit_deepdive_request("做一个研究综述，看看 benchmark comparison")
    assert not compiler.is_explicit_deepdive_request("分析这篇 paper 是否值得关注")


def test_explicit_profile_or_marker_triggers_deepdive():
    assert compiler.is_explicit_deepdive_request("分析 agent infra", profile="deepdive")
    assert compiler.is_explicit_deepdive_request("分析 agent infra", source_channel="deepdive")
    assert compiler.is_explicit_deepdive_request("做一个 DeepDive：agent infra 未来路线")
    assert compiler.is_explicit_deepdive_request("做一个深度研究：agent infra 未来路线")


def test_compile_deepdive_brief_uses_separate_schema_and_nodes():
    contract = compiler.compile_deepdive_brief(
        """
        DeepDive: Agent runtime 是否正在成为 AI infra 的核心层？
        为什么现在发生？
        哪些反证会推翻这个判断？
        """
    )
    validation = compiler.validate_deepdive_contract(contract)

    assert validation["ok"], validation
    assert contract["schema_version"] == compiler.SCHEMA_VERSION
    assert contract["schema_version"] != "solar.requirement_ir.v1"
    assert "requirement_ir" not in contract
    assert contract["runtime_owner"] == "DeepDive"
    assert contract["deepdive_dag"]["dag_variant"] == "deepdive_research"
    assert all(node["id"].startswith("D") for node in contract["deepdive_dag"]["nodes"])
    assert all(
        node["logical_operator"].startswith("DeepDive")
        for node in contract["deepdive_dag"]["nodes"]
    )
    assert all(item["mapped_nodes"] for item in contract["traceability"]["items"])


def test_compile_deepdive_insight_contract_extends_runtime_gates():
    contract = compiler.compile_deepdive_brief(
        "DeepDive: 通过洞察 CAIS 2026 学术会议，分析 Agent 技术挑战和 Solar 吸收路线"
    )
    validation = compiler.validate_deepdive_contract(contract)
    node_ids = {node["id"] for node in contract["deepdive_dag"]["nodes"]}
    operators = {node["logical_operator"] for node in contract["deepdive_dag"]["nodes"]}

    assert validation["ok"], validation
    assert contract["mode"] == "insight"
    assert contract["insight_profile"]["profile_id"] == "cais-agent-insight"
    assert contract["insight_profile"]["ok"] is True
    assert "DD_INSIGHT" in contract["deepdive_dag"]["required_gates"]
    assert "GenericSurveyTOCGate" in contract["output_contract"]["insight_gates"]
    assert "conference_signals" in contract["output_contract"]["signal_clusters"]
    assert {"D10", "D11", "D12", "D17", "D18"} <= node_ids
    assert "DeepDiveChiefInsightEditor" in operators
    assert "DeepDiveSignalExtractor" in operators
    assert "DeepDiveActionMapper" in operators
    assert "signal_map.json" in contract["output_contract"]["insight"]
    assert "action_mapping.json" in contract["output_contract"]["insight"]
    assert "conference_signal_map.json" not in contract["output_contract"]["insight"]
    assert "conference_signal_map.json" in contract["output_contract"]["profile_extensions"]
    assert "solar_absorption_map.json" in contract["output_contract"]["profile_extensions"]
    assert any("generic survey taxonomy" in item for item in contract["scope_boundaries"]["must_not_do"])


def test_compile_deepdive_insight_contract_locks_mirror_runtime_fields():
    contract = compiler.compile_deepdive_brief(
        "DeepDive: 通过洞察 CAIS 2026 学术会议，分析 Agent 技术挑战和 Solar 吸收路线"
    )
    nodes = {node["id"]: node for node in contract["deepdive_dag"]["nodes"]}

    for node_id in ("D10", "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18"):
        node = nodes[node_id]
        meta = compiler.INSIGHT_RUNTIME_NODE_METADATA[node_id]

        assert node["artifact_paths"] == meta["artifact_paths"]
        assert node["gates"] == list(meta["gates"])
        assert node["verification_gates"] == node["gates"]
        assert node["evaluator_sidecar"] == meta["evaluator_sidecar"]
        assert node["closeout_acceptance"] == meta["closeout_acceptance"]
        assert node["status_metadata"] == meta["status_metadata"]


def test_compile_generic_insight_contract_has_no_cais_or_solar_defaults():
    contract = compiler.compile_deepdive_brief(
        "DeepDive: insight 分析 AI coding agent 产品机会、技术路线和开源项目策略"
    )
    validation = compiler.validate_deepdive_contract(contract)
    operators = {node["logical_operator"] for node in contract["deepdive_dag"]["nodes"]}
    output_text = "\n".join(contract["output_contract"]["insight"])

    assert validation["ok"], validation
    assert contract["mode"] == "insight"
    assert contract["insight_profile"]["active"] is False
    assert "DeepDiveSignalExtractor" in operators
    assert "DeepDiveActionMapper" in operators
    assert "conference_signal" not in output_text
    assert "paper_to_solar" not in output_text
    assert "profile_extensions" not in contract["output_contract"]
    assert not any("Solar absorption" in item for item in contract["scope_boundaries"]["must_not_do"])


def test_deepdive_brief_expander_writes_separate_artifacts(tmp_path):
    payload = expander.expand_deepdive_brief("DeepDive: agent runtime 趋势是什么？", tmp_path)

    assert payload["schema_version"] == expander.SCHEMA_VERSION
    assert payload["operator"] == "DeepDiveBriefExpander"
    assert payload["normal_requirement_pipeline_import_allowed"] is False
    assert (tmp_path / "deepdive_brief_expansion.json").exists()
    assert (tmp_path / "deepdive_brief_expansion.md").exists()
    assert not (tmp_path / "raw_intent.json").exists()
    assert not (tmp_path / "requirement_ir.json").exists()


def test_deepdive_contract_records_expansion_without_normal_schema(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SOLAR_DEEPDIVE_BRIEF_EXPANDER_CMD",
        f"{sys.executable} -c \"print('## 扩展研究 brief\\\\n\\\\n为什么 Agent runtime 会成为基础设施？')\"",
    )
    expansion = expander.expand_deepdive_brief("DeepDive: Agent runtime", tmp_path)
    contract = compiler.compile_deepdive_brief("DeepDive: Agent runtime", expansion=expansion)
    validation = compiler.validate_deepdive_contract(contract)

    assert validation["ok"], validation
    assert contract["brief"].startswith("## 扩展研究 brief")
    assert contract["raw_brief"] == "DeepDive: Agent runtime"
    assert contract["brief_expansion"]["operator"] == "DeepDiveBriefExpander"
    assert contract["brief_expansion"]["normal_requirement_pipeline_import_allowed"] is False
    assert contract["schema_version"] != "solar.requirement_ir.v1"


def test_deepdive_compiler_has_no_runtime_import_from_pm_router():
    source = inspect.getsource(compiler)

    assert "codex_pm_router" not in source
    assert "from requirement_coverage" not in source
    assert "solar.requirement_ir.v1" not in [
        compiler.SCHEMA_VERSION,
        compiler.TRACE_SCHEMA_VERSION,
    ]


def test_operator_mapping_documents_copy_policy():
    mapping = compiler.OPERATOR_MAPPING

    assert mapping
    assert {item["deepdive_operator"] for item in mapping} >= {
        "DeepDiveBriefCapture",
        "DeepDiveResearchContract",
        "DeepDiveEvidenceDAG",
        "DeepDiveTraceabilityReport",
        "DeepDiveCloseoutDecision",
    }
    assert all(item["copy_policy"] for item in mapping)
    assert all("boundary" in item for item in mapping)
