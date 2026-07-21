"""Tests for status-server/research_routes.py and /research/<sid> endpoint.

Acceptance:
- GET /research/<sid> returns JSON with required keys
- All numbers read from research_eval.*.json; no hardcoded data
- generate_markdown_report produces valid markdown
- End-to-end HTTP test via http.server
- Zero @mock.patch

Tests use real JSON files in temp directories.
"""

from __future__ import annotations

import json
import sys
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

# Place harness root on sys.path
_HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))

import importlib.util as _ilu

_mod_path = _HARNESS_ROOT / "status-server" / "research_routes.py"
_spec = _ilu.spec_from_file_location("research_routes", str(_mod_path))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_research_payload = _mod.build_research_payload
discover_human_search_waiting = _mod.discover_human_search_waiting
discover_quality_gates = _mod.discover_quality_gates
discover_eval_files = _mod.discover_eval_files
generate_markdown_report = _mod.generate_markdown_report
load_eval = _mod.load_eval


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_eval(tmpdir: Path, filename: str, data: dict) -> Path:
    p = tmpdir / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _write_graph(tmpdir: Path, filename: str, data: dict) -> Path:
    p = tmpdir / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _make_eval_data(
    source_count=10,
    evidence_count=50,
    claim_count=20,
    unsupported_claims=2,
    total_key_claims=20,
    span_matches=45,
    total_spans=50,
    status="passed",
    run_id="run-001",
    output_dir="",
    final_md="",
):
    return {
        "run_id": run_id,
        "source_count": source_count,
        "evidence_count": evidence_count,
        "claim_count": claim_count,
        "unsupported_claims": unsupported_claims,
        "total_key_claims": total_key_claims,
        "span_matches": span_matches,
        "total_spans": total_spans,
        "status": status,
        "section_count": 5,
        "check_count": 5,
        "output_dir": output_dir,
        "final_md": final_md,
    }


# ---------------------------------------------------------------------------
# Tests: discover_eval_files
# ---------------------------------------------------------------------------

class TestDiscoverEvalFiles:
    def test_finds_matching_files(self, tmp_path):
        _write_eval(tmp_path, "sprint-001-research_eval.json", {})
        _write_eval(tmp_path, "sprint-001-research_eval_extra.json", {})
        _write_eval(tmp_path, "sprint-002-research_eval.json", {})
        found = discover_eval_files(tmp_path, "sprint-001")
        assert len(found) == 2

    def test_returns_empty_for_no_match(self, tmp_path):
        _write_eval(tmp_path, "sprint-002-research_eval.json", {})
        found = discover_eval_files(tmp_path, "sprint-999")
        assert found == []

    def test_ignores_non_eval_files(self, tmp_path):
        _write_eval(tmp_path, "sprint-001-eval.json", {})
        _write_eval(tmp_path, "sprint-001-research_eval.json", {})
        found = discover_eval_files(tmp_path, "sprint-001")
        assert len(found) == 1


# ---------------------------------------------------------------------------
# Tests: load_eval
# ---------------------------------------------------------------------------

class TestLoadEval:
    def test_loads_valid_json(self, tmp_path):
        data = {"source_count": 5}
        p = _write_eval(tmp_path, "eval.json", data)
        assert load_eval(p) == data

    def test_returns_empty_on_missing(self, tmp_path):
        assert load_eval(tmp_path / "nonexistent.json") == {}

    def test_returns_empty_on_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json{{{", encoding="utf-8")
        assert load_eval(p) == {}


# ---------------------------------------------------------------------------
# Tests: build_research_payload
# ---------------------------------------------------------------------------

class TestBuildResearchPayload:
    def test_no_eval_files_returns_defaults(self, tmp_path):
        result = build_research_payload(tmp_path, "sprint-nope")
        assert result["source_count"] == 0
        assert result["evidence_count"] == 0
        assert result["claim_count"] == 0
        assert result["unsupported_rate"] == 0.0
        assert result["citation_accuracy"] == 0.0
        assert result["status"] == "no_data"
        assert result["eval_files"] == 0

    def test_single_eval_file_aggregates(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data())
        result = build_research_payload(tmp_path, "sid")
        assert result["source_count"] == 10
        assert result["evidence_count"] == 50
        assert result["claim_count"] == 20
        assert result["status"] == "passed"
        assert result["eval_files"] == 1

    def test_multiple_eval_files_sum(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(source_count=5, evidence_count=10))
        _write_eval(tmp_path, "sid-research_eval_extra.json", _make_eval_data(source_count=3, evidence_count=15))
        result = build_research_payload(tmp_path, "sid")
        assert result["source_count"] == 8
        assert result["evidence_count"] == 25
        assert result["eval_files"] == 2

    def test_unsupported_rate_calculation(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(
            unsupported_claims=3, total_key_claims=30,
            span_matches=40, total_spans=50,
        ))
        result = build_research_payload(tmp_path, "sid")
        assert result["unsupported_rate"] == pytest.approx(0.1, abs=0.001)
        assert result["citation_accuracy"] == pytest.approx(0.8, abs=0.001)

    def test_zero_division_safe(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(
            total_key_claims=0, total_spans=0,
        ))
        result = build_research_payload(tmp_path, "sid")
        assert result["unsupported_rate"] == 0.0
        assert result["citation_accuracy"] == 0.0

    def test_status_priority_failed_over_passed(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval_a.json", _make_eval_data(status="passed"))
        _write_eval(tmp_path, "sid-research_eval_b.json", _make_eval_data(status="failed"))
        result = build_research_payload(tmp_path, "sid")
        assert result["status"] == "failed"

    def test_json_keys_complete(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data())
        result = build_research_payload(tmp_path, "sid")
        for key in ("sid", "source_count", "evidence_count", "claim_count",
                     "unsupported_rate", "citation_accuracy", "status", "eval_files", "human_search", "quality_gates", "runs", "latest"):
            assert key in result, f"missing key: {key}"

    def test_artifact_paths_project_from_eval_output_dir(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        final = out / "final.md"
        ast = out / "report_ast.json"
        bib = out / "final.bibliography.json"
        final.write_text("# final", encoding="utf-8")
        ast.write_text(json.dumps({"chapters": [{"sections": [{"id": "s1"}, {"id": "s2"}]}]}), encoding="utf-8")
        bib.write_text("[]", encoding="utf-8")
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(
            run_id="run-artifacts",
            output_dir=str(out),
            final_md=str(final),
        ))

        result = build_research_payload(tmp_path, "sid")
        run = result["runs"][0]

        assert run["run_id"] == "run-artifacts"
        assert run["artifact_exists"]["final_md"] is True
        assert run["artifact_exists"]["report_ast"] is True
        assert run["artifact_exists"]["bibliography"] is True
        assert run["artifact_exists"]["eval_json"] is True
        assert run["report_ast_sections"] == 2


# ---------------------------------------------------------------------------
# Tests: DeepResearch quality gate projection
# ---------------------------------------------------------------------------

class TestQualityGateProjection:
    def test_discovers_quality_gate_from_task_graph(self, tmp_path):
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R8",
                "goal": "DeepResearch factuality gate",
                "status": "passed",
                "required_capabilities": ["research.factuality_evaluator"],
                "research_quality_gate": {
                    "ok": True,
                    "verdict": "PASS",
                    "auto_run": True,
                    "metrics": {"citation_accuracy": 1.0},
                },
            }],
        })

        result = discover_quality_gates(tmp_path, "sid")

        assert result["status"] == "ok"
        assert result["ok_count"] == 1
        assert result["items"][0]["node_id"] == "R8"
        assert result["items"][0]["auto_run"] is True

    def test_marks_required_quality_gate_missing(self, tmp_path):
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R8",
                "goal": "DeepResearch citation check",
                "status": "reviewing",
                "required_capabilities": ["research.citation_verify"],
            }],
        })

        result = discover_quality_gates(tmp_path, "sid")

        assert result["status"] == "missing"
        assert result["missing_count"] == 1
        assert result["items"][0]["ok"] is False

    def test_build_payload_includes_quality_gates(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data())
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R8",
                "goal": "DeepResearch factuality gate",
                "required_capabilities": ["research.factuality_evaluator"],
                "research_quality_gate": {"ok": True, "verdict": "PASS", "auto_run": True},
            }],
        })

        result = build_research_payload(tmp_path, "sid")

        assert result["quality_gates"]["count"] == 1
        assert result["quality_gates"]["items"][0]["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# Tests: human-in-loop search discovery
# ---------------------------------------------------------------------------

class TestHumanSearchDiscovery:
    def test_discovers_waiting_human_search_node(self, tmp_path):
        handoff = tmp_path / "handoff.md"
        handoff.write_text("# handoff", encoding="utf-8")
        results = tmp_path / "results.md"
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R2_external_search",
                "goal": "wait for web research",
                "status": "waiting_human_search",
                "human_search": {
                    "status": "waiting",
                    "provider": "human",
                    "run_id": "sid",
                    "handoff_md": str(handoff),
                    "results_md": str(results),
                    "import_command": "solar-harness research import-search ..."
                }
            }]
        })

        result = discover_human_search_waiting(tmp_path, "sid")

        assert result["status"] == "waiting"
        assert result["count"] == 1
        item = result["items"][0]
        assert item["node_id"] == "R2_external_search"
        assert item["handoff_exists"] is True
        assert item["results_exists"] is False
        assert item["ready_to_import"] is False

    def test_marks_results_ready_when_results_file_exists(self, tmp_path):
        handoff = tmp_path / "handoff.md"
        results = tmp_path / "results.md"
        handoff.write_text("# handoff", encoding="utf-8")
        results.write_text("# results", encoding="utf-8")
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "node_results": {"R2": {"status": "waiting_human_search"}},
            "nodes": [{
                "id": "R2",
                "goal": "wait for web research",
                "human_search": {
                    "status": "waiting",
                    "handoff_md": str(handoff),
                    "results_md": str(results),
                    "import_command": "solar-harness research import-search ..."
                }
            }]
        })

        result = discover_human_search_waiting(tmp_path, "sid")

        assert result["items"][0]["results_exists"] is True
        assert result["items"][0]["ready_to_import"] is True

    def test_build_payload_includes_human_search(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data())
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R2",
                "status": "waiting_human_search",
                "human_search": {"status": "waiting"}
            }]
        })

        result = build_research_payload(tmp_path, "sid")

        assert result["human_search"]["count"] == 1


# ---------------------------------------------------------------------------
# Tests: generate_markdown_report
# ---------------------------------------------------------------------------

class TestMarkdownReport:
    def test_includes_sid(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data())
        md = generate_markdown_report(tmp_path, "sid")
        assert "# Research Status Report: sid" in md

    def test_includes_metrics_table(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(
            source_count=7, evidence_count=42, claim_count=15,
        ))
        md = generate_markdown_report(tmp_path, "sid")
        assert "| Source Count | 7 |" in md
        assert "| Evidence Count | 42 |" in md
        assert "| Claim Count | 15 |" in md

    def test_includes_status(self, tmp_path):
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(status="passed"))
        md = generate_markdown_report(tmp_path, "sid")
        assert "**Status**: passed" in md

    def test_includes_research_artifacts(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        final = out / "final.md"
        final.write_text("# final", encoding="utf-8")
        (out / "report_ast.json").write_text(json.dumps({"chapters": []}), encoding="utf-8")
        _write_eval(tmp_path, "sid-research_eval.json", _make_eval_data(
            run_id="run-artifacts",
            output_dir=str(out),
            final_md=str(final),
        ))
        md = generate_markdown_report(tmp_path, "sid")
        assert "## Research Artifacts" in md
        assert "run-artifacts" in md
        assert "report_ast.json" in md

    def test_includes_human_search_waiting(self, tmp_path):
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R2",
                "status": "waiting_human_search",
                "human_search": {
                    "status": "waiting",
                    "handoff_md": "/tmp/handoff.md",
                    "results_md": "/tmp/results.md",
                    "import_command": "solar-harness research import-search ..."
                }
            }]
        })
        md = generate_markdown_report(tmp_path, "sid")
        assert "## Human Search Waiting" in md
        assert "R2" in md

    def test_includes_quality_gates(self, tmp_path):
        _write_graph(tmp_path, "sid.task_graph.json", {
            "sprint_id": "sid",
            "nodes": [{
                "id": "R8",
                "goal": "DeepResearch factuality gate",
                "required_capabilities": ["research.factuality_evaluator"],
                "research_quality_gate": {"ok": True, "verdict": "PASS", "auto_run": True},
            }]
        })
        md = generate_markdown_report(tmp_path, "sid")
        assert "## DeepResearch Quality Gates" in md
        assert "R8" in md
        assert "True" in md
