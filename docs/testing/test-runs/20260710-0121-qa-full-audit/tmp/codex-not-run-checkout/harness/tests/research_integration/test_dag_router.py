"""Tests for graph_scheduler_research.py: template loading, research node
dispatch, and R7 per-section write_scope isolation.

Acceptance:
- load_deepresearch_template() loads and substitutes placeholders
- R7 fan-out expands into per-section nodes with isolated write_scope
- validate_write_scope_isolation detects overlapping scopes
- dispatch_research_node routes R-prefixed nodes correctly
- Two builders cannot write the same file (scope isolation)
- Non-research nodes pass through unchanged
- pytest exits 0 with >= 10 assertions
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import json
import pytest

from graph_scheduler_research import (
    dispatch_research_node,
    load_deepresearch_template,
    validate_write_scope_isolation,
)


_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "sprints"
    / "sprint-20260513-solar-deepresearch-product-line-s02-architecture"
    ".deepresearch.dag-template.json"
)


@pytest.fixture
def template_path():
    if not _TEMPLATE_PATH.exists():
        pytest.skip("dag-template.json not found")
    return _TEMPLATE_PATH


@pytest.fixture
def sample_report_ast():
    return {
        "chapters": [
            {
                "chapter_id": "ch01",
                "sections": [
                    {"section_id": "sec01", "title": "Introduction"},
                    {"section_id": "sec02", "title": "Background"},
                ],
            },
            {
                "chapter_id": "ch02",
                "sections": [
                    {"section_id": "sec03", "title": "Methods"},
                ],
            },
        ]
    }


class TestLoadTemplate:
    def test_loads_template_without_report_ast(self, template_path):
        graph = load_deepresearch_template(
            "sprint-test-001",
            template_path=str(template_path),
        )
        assert graph["sprint_id"] == "sprint-test-001"
        assert len(graph["nodes"]) == 12
        assert graph["schema_version"] == "solar.task_graph.v1"

    def test_substitutes_research_sid_in_write_scope(self, template_path):
        graph = load_deepresearch_template(
            "sprint-test-001",
            template_path=str(template_path),
        )
        for node in graph["nodes"]:
            for ws in node.get("write_scope", []):
                assert "<research-sid>" not in ws
                if "sprint-test-001" in ws:
                    assert "sprint-test-001" in ws

    def test_preserves_non_research_nodes(self, template_path):
        graph = load_deepresearch_template(
            "sprint-test-001",
            template_path=str(template_path),
        )
        node_ids = [n["id"] for n in graph["nodes"]]
        assert "R0_scope_rewrite" in node_ids
        assert "R11_final_export" in node_ids


class TestFanOutExpansion:
    def test_r7_expands_to_per_section_nodes(self, template_path, sample_report_ast):
        graph = load_deepresearch_template(
            "sprint-test-001",
            report_ast=sample_report_ast,
            template_path=str(template_path),
        )
        node_ids = [n["id"] for n in graph["nodes"]]
        assert "R7_section_writing_batch_sec01" in node_ids
        assert "R7_section_writing_batch_sec02" in node_ids
        assert "R7_section_writing_batch_sec03" in node_ids
        assert "R7_section_writing_batch" not in node_ids

    def test_r8_expands_to_per_section_nodes(self, template_path, sample_report_ast):
        graph = load_deepresearch_template(
            "sprint-test-001",
            report_ast=sample_report_ast,
            template_path=str(template_path),
        )
        node_ids = [n["id"] for n in graph["nodes"]]
        assert "R8_section_fact_check_sec01" in node_ids
        assert "R8_section_fact_check_sec02" in node_ids
        assert "R8_section_fact_check_sec03" in node_ids

    def test_r8_section_depends_on_r7_section(self, template_path, sample_report_ast):
        graph = load_deepresearch_template(
            "sprint-test-001",
            report_ast=sample_report_ast,
            template_path=str(template_path),
        )
        node_map = {n["id"]: n for n in graph["nodes"]}
        r8_sec01 = node_map["R8_section_fact_check_sec01"]
        assert "R7_section_writing_batch_sec01" in r8_sec01["depends_on"]

    def test_write_scope_has_section_specific_paths(self, template_path, sample_report_ast):
        graph = load_deepresearch_template(
            "sprint-test-001",
            report_ast=sample_report_ast,
            template_path=str(template_path),
        )
        node_map = {n["id"]: n for n in graph["nodes"]}
        r7_sec01 = node_map["R7_section_writing_batch_sec01"]
        write_scopes = r7_sec01["write_scope"]
        assert any("sec01" in ws for ws in write_scopes)
        assert any("ch01" in ws for ws in write_scopes)


class TestWriteScopeIsolation:
    def test_no_overlap_passes(self, template_path, sample_report_ast):
        graph = load_deepresearch_template(
            "sprint-test-001",
            report_ast=sample_report_ast,
            template_path=str(template_path),
        )
        result = validate_write_scope_isolation(graph)
        assert result["ok"] is True
        assert result["conflicts"] == []

    def test_two_builders_cannot_write_same_file(self):
        graph = {
            "nodes": [
                {
                    "id": "R7_section_writing_batch_sec01",
                    "write_scope": [
                        "/data/sprint-test-001.sections/ch01/sec01.draft.md",
                    ],
                },
                {
                    "id": "R7_section_writing_batch_sec01_dup",
                    "write_scope": [
                        "/data/sprint-test-001.sections/ch01/sec01.draft.md",
                    ],
                },
            ]
        }
        result = validate_write_scope_isolation(graph)
        assert result["ok"] is False
        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["conflict_path"] == "/data/sprint-test-001.sections/ch01/sec01.draft.md"

    def test_different_sections_no_conflict(self):
        graph = {
            "nodes": [
                {
                    "id": "R7_section_writing_batch_sec01",
                    "write_scope": ["/data/sprint-test-001.sections/ch01/sec01.draft.md"],
                },
                {
                    "id": "R7_section_writing_batch_sec02",
                    "write_scope": ["/data/sprint-test-001.sections/ch01/sec02.draft.md"],
                },
            ]
        }
        result = validate_write_scope_isolation(graph)
        assert result["ok"] is True


class TestDispatchResearchNode:
    def test_rejects_non_research_node(self):
        graph = {"nodes": [{"id": "N1_implement", "write_scope": []}]}
        result = dispatch_research_node(graph, "N1_implement", [])
        assert result["ok"] is False
        assert result["reason"] == "not_research_node"

    def test_rejects_unknown_node(self):
        graph = {"nodes": []}
        result = dispatch_research_node(graph, "R99_nonexistent", [])
        assert result["ok"] is False
        assert result["reason"] == "unknown_node"

    def test_assigns_research_node_to_worker(self):
        graph = {
            "nodes": [
                {
                    "id": "R0_scope_rewrite",
                    "write_scope": ["/data/scope.json"],
                    "depends_on": [],
                    "required_capabilities": ["research.scope_rewrite"],
                },
            ]
        }
        workers = [
            {
                "pane": "solar-harness-lab:0.0",
                "models": ["claude-sonnet"],
                "skills": ["bash"],
                "capabilities": ["research.scope_rewrite", "workflow.planning"],
                "busy": False,
            }
        ]
        result = dispatch_research_node(graph, "R0_scope_rewrite", workers)
        assert result["ok"] is True
        assert len(result["assigned"]) == 1
        assert result["assigned"][0]["research_node"] is True
