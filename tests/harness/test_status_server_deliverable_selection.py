#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "harness" / "lib" / "symphony" / "status-server.py"


def _load_status_server():
    spec = importlib.util.spec_from_file_location("status_server_deliverable_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_nested_governed_final_report_outranks_pm_transcript(tmp_path, monkeypatch) -> None:
    mod = _load_status_server()
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    reports = harness / "reports"
    sid = "sprint-nested-final-report"
    workdir = sprints / sid / "workdir"
    final_report = workdir / "workspace" / "research" / "report" / "final.md"
    final_report.parent.mkdir(parents=True)
    final_report.write_text("# Evidence-backed result\n\n" + ("grounded evidence\n" * 200), encoding="utf-8")
    sprints.mkdir(parents=True, exist_ok=True)
    (sprints / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "status": "passed",
                "phase": "finalized",
                "created_at": "2026-08-17T20:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "nodes": [
                    {
                        "id": "R2",
                        "task_type": "report-writing",
                        "write_scope": ["workspace/research/report/"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (sprints / f"{sid}.N0.pm-result.md").write_text(
        "# Planner transcript\n\n" + ("internal planning log\n" * 1000),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "HARNESS_DIR", harness)
    monkeypatch.setattr(mod, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)

    rows = mod._discover_sprint_deliverables(sid)
    selected = [row for row in rows if row.get("result")]

    assert len(selected) == 1
    assert selected[0]["name"] == "final.md"
    assert selected[0]["source"] == "output"
    assert selected[0]["producer_task_type"] == "report-writing"
    assert selected[0]["supporting"] is False


def test_native_direct_response_report_is_dashboard_result_without_graph(tmp_path, monkeypatch) -> None:
    mod = _load_status_server()
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    reports = harness / "reports"
    sid = "sprint-native-direct-answer"
    sprints.mkdir(parents=True)
    (sprints / f"{sid}.status.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "status": "passed",
                "phase": "direct_response_complete",
                "execution_mode": "direct_response",
            }
        ),
        encoding="utf-8",
    )
    (sprints / f"{sid}.direct-response-report.md").write_text(
        "# Answer\n\nPhotosynthesis converts light energy into stored chemical energy.\n",
        encoding="utf-8",
    )
    (sprints / f"{sid}.elastic-planner.pm-result.md").write_text(
        "internal closeout transcript\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "HARNESS_DIR", harness)
    monkeypatch.setattr(mod, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)

    rows = mod._discover_sprint_deliverables(sid)
    selected = [row for row in rows if row.get("result")]

    assert len(selected) == 1
    assert selected[0]["name"] == f"{sid}.direct-response-report.md"


def test_final_report_outranks_larger_research_context_html(tmp_path, monkeypatch) -> None:
    """Research source captures are evidence, not the user-facing report."""
    mod = _load_status_server()
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    reports = harness / "reports"
    sid = "sprint-research-context-result"
    workdir = sprints / sid / "workdir"
    context = workdir / "workspace" / "research" / "source-pack-context" / "raw" / "ctx.html"
    final_report = workdir / "workspace" / "research" / "report" / "final.md"
    context.parent.mkdir(parents=True)
    final_report.parent.mkdir(parents=True)
    context.write_text("<html>" + ("source capture" * 1000) + "</html>", encoding="utf-8")
    final_report.write_text("# 中文技术趋势报告\n\n结论。\n", encoding="utf-8")
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "nodes": [
                    {
                        "id": "R2",
                        "task_type": "research",
                        "write_scope": ["workspace/research/source-pack-context/"],
                    },
                    {
                        "id": "R4",
                        "task_type": "research",
                        "depends_on": ["R2"],
                        "write_scope": ["workspace/research/report/"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "HARNESS_DIR", harness)
    monkeypatch.setattr(mod, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)

    rows = mod._discover_sprint_deliverables(sid)
    selected = [row for row in rows if row.get("result")]
    context_row = next(row for row in rows if row["name"] == "ctx.html")

    assert context.stat().st_size > final_report.stat().st_size
    assert len(selected) == 1
    assert selected[0]["name"] == "final.md"
    assert context_row["supporting"] is True


def test_final_report_outranks_larger_nested_report_extract(tmp_path, monkeypatch) -> None:
    mod = _load_status_server()
    harness = tmp_path / "harness"
    sprints = harness / "sprints"
    reports = harness / "reports"
    sid = "sprint-report-extract-result"
    workdir = sprints / sid / "workdir"
    extract = workdir / "workspace" / "research" / "report" / "extracts" / "source.md"
    final_report = workdir / "workspace" / "research" / "report" / "final.md"
    extract.parent.mkdir(parents=True)
    final_report.parent.mkdir(parents=True, exist_ok=True)
    extract.write_text("# Source capture\n\n" + ("raw text\n" * 1000), encoding="utf-8")
    final_report.write_text("# 中文技术趋势报告\n\n结论。\n", encoding="utf-8")
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "nodes": [
                    {
                        "id": "R4",
                        "task_type": "research",
                        "write_scope": ["workspace/research/report/"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "HARNESS_DIR", harness)
    monkeypatch.setattr(mod, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(mod, "REPORTS_DIR", reports)

    rows = mod._discover_sprint_deliverables(sid)
    selected = [row for row in rows if row.get("result")]
    extract_row = next(row for row in rows if row["name"] == "source.md")

    assert extract.stat().st_size > final_report.stat().st_size
    assert len(selected) == 1
    assert selected[0]["name"] == "final.md"
    assert extract_row["supporting"] is True
