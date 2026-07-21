from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SCRIPTS = ROOT / "scripts"
for item in (str(TOOLS), str(SCRIPTS), str(ROOT / "lib")):
    if item not in sys.path:
        sys.path.insert(0, item)

from report_evidence import (  # noqa: E402
    append_chapter_event,
    build_chapter_evidence_pack,
    public_text_has_forbidden_fields,
    rebuild_chapter_state,
    run_chapter_writer,
)
from report_ir import compile_report_ir, create_chapter_jobs  # noqa: E402
from report_synthesis import synthesize_report  # noqa: E402


def _sample_catalog() -> list[dict]:
    return [
        {"video_ref": "V001", "video_id": "raw-1", "title": "Agent runtime"},
        {"video_ref": "V002", "video_id": "raw-2", "title": "Model routing"},
        {"video_ref": "V003", "video_id": "raw-3", "title": "Support"},
        {"video_ref": "V004", "video_id": "raw-4", "title": "Bad"},
    ]


def _sample_plan() -> dict:
    return {
        "schema_version": "legacy",
        "reports": [
            {
                "report_id": "ai-runtime",
                "title": "AI Runtime",
                "chapters": [
                    {"chapter_id": "ch_01", "title": "Runtime Shift", "material_video_refs": ["V001", "V002", "V003", "V004"]},
                    {"chapter_id": "ch_02", "title": "Implications", "priority": "P0", "deep_writer_required": True, "expected_words": 700, "material_video_refs": ["V001"]},
                ],
            }
        ],
    }


def _sample_evidence() -> dict:
    return {
        "videos": [
            {"video_ref": "V001", "video_id": "raw-1", "quality_tier": "T1", "transcript_status": "fetched", "transcript_segments": [{"text": "a"}, {"text": "b"}]},
            {"video_ref": "V002", "video_id": "raw-2", "quality_tier": "T0", "transcript_status": "fetched", "transcript_segments": [{"text": "c"}, {"text": "d"}]},
            {"video_ref": "V003", "video_id": "raw-3", "quality_tier": "T2", "transcript_status": "fetched", "transcript_segments": [{"text": "e"}]},
            {"video_ref": "V004", "video_id": "raw-4", "quality_tier": "T3", "transcript_status": "failed", "transcript_segments": [{"text": "x"}]},
        ]
    }


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("tech_hotspot_radar_test_module", ROOT / "scripts" / "tech_hotspot_radar.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compile_report_ir_compat_defaults_and_jobs() -> None:
    report_ir = compile_report_ir(_sample_plan(), _sample_catalog(), {"video_groups": []}, {})

    assert report_ir["report_id"] == "ai-runtime"
    assert report_ir["quality_targets"]["min_videos"] == 2
    assert report_ir["chapters"][0]["priority"] == "P1"
    assert report_ir["chapters"][0]["deep_writer_required"] is False
    assert report_ir["chapters"][0]["legacy_imported"] is True
    assert report_ir["chapters"][1]["priority"] == "P0"

    jobs = create_chapter_jobs(report_ir)
    assert [job["status"] for job in jobs] == ["queued", "queued"]
    assert jobs[0]["chapter_id"] == "ch_01"


def test_compile_report_ir_trends_catalog_dict_and_quality_override() -> None:
    plan = {
        "reports": [
            {
                "title": "Nested Trend Report",
                "trends": [
                    {
                        "title": "Trend A",
                        "selected_video_refs": ["V001", "V002"],
                        "chapters": [
                            {"title": "Nested A1", "purpose": "explain"},
                        ],
                    },
                    {"trend_title": "Trend B", "supporting_video_refs": ["V003"]},
                ],
            }
        ]
    }
    catalog = {"videos": [{"ref": "V001"}, {"ref": "V002"}, {"ref": "V003"}]}
    report_ir = compile_report_ir(plan, catalog, {"groups": [{"id": "g1"}]}, {"quality_targets": {"min_videos": 3}})

    assert report_ir["report_id"] == "nested-trend-report"
    assert report_ir["quality_targets"]["min_videos"] == 3
    assert [chapter["title"] for chapter in report_ir["chapters"]] == ["Nested A1", "Trend B"]
    assert report_ir["chapters"][0]["selected_video_refs"] == ["V001", "V002"]
    assert report_ir["video_groups"] == {"groups": [{"id": "g1"}]}


def test_chapter_evidence_filters_tiers_and_marks_weak() -> None:
    report_ir = compile_report_ir(_sample_plan(), _sample_catalog(), {}, {})
    chapter = report_ir["chapters"][0]
    pack = build_chapter_evidence_pack(_sample_evidence(), chapter, report_ir["quality_targets"])

    assert [v["video_ref"] for v in pack["core_evidence"]] == ["V001", "V002"]
    assert [v["video_ref"] for v in pack["support_evidence"]] == ["V003"]
    assert pack["support_evidence"][0]["support_only"] is True
    assert [v["video_ref"] for v in pack["excluded_evidence"]] == ["V004"]
    assert pack["weak"] is False
    assert "video_id" not in json.dumps(pack, ensure_ascii=False)
    assert "transcript_status" not in json.dumps(pack, ensure_ascii=False)

    weak = build_chapter_evidence_pack(_sample_evidence(), {"chapter_id": "ch_x", "chapter_type": "core_trend", "material_video_refs": ["V001"]}, report_ir["quality_targets"])
    assert weak["weak"] is True
    assert set(weak["weak_reasons"]) == {"selected_videos_below_min", "transcript_segments_below_min"}


def test_writer_state_synthesis_and_atomic_concurrent_outputs(tmp_path: Path) -> None:
    report_ir = compile_report_ir(_sample_plan(), _sample_catalog(), {}, {})
    jobs = create_chapter_jobs(report_ir)
    events = tmp_path / "report" / "events.jsonl"

    def writer(chapter_spec: dict, evidence_pack: dict, model_name: str) -> dict:
        return {
            "markdown": f"## {chapter_spec['title']}\n\nvisible text video_id raw-secret chapter_id raw-chapter transcript_status fetched",
            "model": model_name,
            "backend": "test",
        }

    def run_one(job: dict) -> str:
        chapter = next(ch for ch in report_ir["chapters"] if ch["chapter_id"] == job["chapter_id"])
        append_chapter_event(events, chapter_id=job["chapter_id"], from_status="queued", to_status="writing", reason="test")
        pack = build_chapter_evidence_pack(_sample_evidence(), chapter, report_ir["quality_targets"])
        result = run_chapter_writer(tmp_path / "report", job, chapter, pack, writer_callable=writer)
        append_chapter_event(events, chapter_id=job["chapter_id"], from_status="writing", to_status="verifying", reason="test")
        append_chapter_event(events, chapter_id=job["chapter_id"], from_status="verifying", to_status="passed", reason="test")
        return result["markdown"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        markdowns = list(pool.map(run_one, jobs))

    assert rebuild_chapter_state(events) == {"ch_01": "passed", "ch_02": "passed"}
    assert all(not public_text_has_forbidden_fields(markdown) for markdown in markdowns)
    assert (tmp_path / "report" / "chapters" / "ch_01.draft.md").exists()
    assert (tmp_path / "report" / "chapters" / "ch_02.draft.md").exists()
    synthesis = synthesize_report(report_ir, tmp_path / "report")
    assert "```synthesis_manifest" in synthesis["markdown"]
    assert "Executive Summary" in synthesis["markdown"]
    assert not public_text_has_forbidden_fields(synthesis["markdown"])


def test_cli_default_pipeline_and_legacy_branch(monkeypatch, tmp_path: Path) -> None:
    mod = _load_cli_module()
    out_dir = tmp_path / "out" / "ai-influence-planned" / "2026-06-01"
    out_dir.mkdir(parents=True)
    (out_dir / "report-plan.json").write_text(json.dumps(_sample_plan(), ensure_ascii=False), encoding="utf-8")
    (out_dir / "video-catalog.json").write_text(json.dumps(_sample_catalog(), ensure_ascii=False), encoding="utf-8")
    (out_dir / "video-groups.json").write_text("{}", encoding="utf-8")

    class Conn:
        row_factory = None

        def close(self) -> None:
            pass

    monkeypatch.setattr(mod, "resolve_config", lambda args: Path("unused.yaml"))
    monkeypatch.setattr(mod, "load_config", lambda path: {"output": {"raw_dir": str(tmp_path / "out")}, "youtube": {"ai_influence_report_flow": {"report_writer": {"model": "test-model"}}}})
    monkeypatch.setattr(mod, "resolve_db", lambda args, config: tmp_path / "db.sqlite")
    monkeypatch.setattr(mod, "ensure_db", lambda path: Conn())
    monkeypatch.setattr(mod, "begin_run", lambda *a, **k: 1)
    monkeypatch.setattr(mod, "finish_run", lambda *a, **k: None)
    monkeypatch.setattr(mod, "record_model_ledgers", lambda *a, **k: None)
    monkeypatch.setattr(mod, "render_ai_influence_report_html_anything", lambda markdown, evidence, report: f"<html>{markdown}</html>")
    monkeypatch.setattr(mod, "build_planned_report_evidence_pack", lambda *a, **k: {**_sample_evidence(), "skipped_material_refs": []})
    monkeypatch.setenv("SOLAR_REPORT_CHAPTER_WRITER_MOCK", "1")
    monkeypatch.setattr(mod, "call_ai_influence_chapter_writer_with_repair", lambda *a, **k: {"markdown": "## Mock Chapter\n\nSome mock text with length more than 120 characters to satisfy the character count validation requirement in the cli logic.", "model": "test-model"})

    args = argparse.Namespace(
        date="2026-06-01",
        days=7,
        plan_file=None,
        report_id=None,
        output_base=str(tmp_path / "out"),
        model="test-model",
        send=False,
        legacy=False,
        skip_notebooklm=True,
        notebook_name=None,
        continue_on_error=False,
    )
    assert mod.cmd_run_ai_influence_planned_reports(args) == 0
    report_dir = out_dir / "reports" / "ai-runtime"
    assert (report_dir / "report-ir.json").exists()
    assert (report_dir / "events.jsonl").exists()
    assert mod.runtime_rebuild_chapter_state(report_dir / "events.jsonl") == {"ch_01": "passed", "ch_02": "passed"}
    assert (report_dir / "synthesis" / "report.synthesized.md").exists()

    monkeypatch.setattr(mod, "_cmd_run_ai_influence_planned_reports_legacy", lambda legacy_args: 7)
    args.legacy = True
    assert mod.cmd_run_ai_influence_planned_reports(args) == 7
