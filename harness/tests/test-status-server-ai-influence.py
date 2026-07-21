#!/usr/bin/env python3
"""Regression test for the AI Influence report center."""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_MODULE = ROOT / "lib" / "symphony" / "status-server.py"
AI_SCRIPT = ROOT / "scripts" / "ai_influence_daily.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    status = load_module("solar_status_server_ai_influence_test", STATUS_MODULE)
    ai = load_module("solar_ai_influence_daily_test", AI_SCRIPT)
    with tempfile.TemporaryDirectory(prefix="solar-ai-influence-ui-test-") as td:
        base = Path(td)
        harness = base / "harness"
        knowledge = base / "Knowledge"
        # Today-relative (UTC) digest date so it stays inside the default 30-day discovery window
        # (_ai_influence_period_cutoff). A hardcoded calendar date made this a time-bomb that aged
        # out once real time advanced past 30 days, dropping the digest and failing ok/count.
        recent = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1)).isoformat()
        run_dir = knowledge / "_raw" / "ai-influence-daily-digest" / recent
        write(run_dir / "digest.md", "# AI Influence Digest\n")
        write(run_dir / "digest.html", "<!doctype html><h1>AI Influence</h1>")
        write(
            run_dir / "digest.json",
            json.dumps(
                {
                    "date": recent,
                    "analysis": {
                        "analysis_status": "ok",
                        "model": "glm-5.1",
                        "items": [{"title": "item"}],
                        "trend_analysis": {"core_trends": [{"theme": "Agent 工作流"}]},
                    },
                    "stats": {"top_scored": 7},
                    "gmail": {"status": "sent"},
                    "wiki_dispatch": str(knowledge / "_raw" / "solar-harness" / ".dispatch" / "wiki-ingest-ai-influence-test.md"),
                },
                ensure_ascii=False,
            ),
        )

        status.HARNESS_DIR = harness
        status.REPORTS_DIR = harness / "reports"
        status.KNOWLEDGE_DIR = knowledge
        status.AI_INFLUENCE_RAW_DIR = run_dir.parent
        status.TECH_HOTSPOT_CONFIG = harness / "missing-tech-hotspot-config.yaml"
        status.HUGGINGFACE_PAPERS_RAW_DIR = knowledge / "_raw" / "huggingface-papers-trending"
        status.OPEN_ALLOWED_ROOTS = [harness, knowledge]

        payload = status._ai_influence_payload(limit=10)
        assert payload["ok"] is True
        assert payload["count"] == 1
        item = next(item for item in payload["items"] if item.get("kind") == "daily_digest")
        assert item["date"] == recent
        assert item["metrics"]["条目"] == 1
        assert item["metrics"]["趋势"] == 1
        assert item["primary"]["view_url"].startswith("/ai-influence/report?")
        html = status._ai_influence_html()
        assert "AI Influence 报告中心" in html
        assert "打开报告" in html

        hf_dir = knowledge / "_raw" / "tech-hotspot-radar" / "2026-06-01"
        write(hf_dir / "hf-paper-report.html", "<!doctype html><h1>HF Paper HTML</h1>")
        write(hf_dir / "hf-paper-report.md", "# HF Paper\n")
        write(
            hf_dir / "hf-paper-insight-pack.json",
            json.dumps(
                {
                    "date": "2026-06-01",
                    "report_variant": "premium_insight_report",
                    "premium_insight_count": 0,
                    "fallback_count": 24,
                    "report_context": {
                        "cadence": "weekly",
                        "week_id": "2026-W23",
                        "window_start": "2026-06-01",
                        "window_end": "2026-06-07",
                        "window_label": "2026-W23 · 2026-06-01 ~ 2026-06-07",
                    },
                    "collection_summary": {
                        "daily_unique_papers": 24,
                    },
                    "grouped_report_sections": [{}, {}, {}, {}, {}],
                    "papers": [{"paper_id": "p1"}, {"paper_id": "p2"}],
                },
                ensure_ascii=False,
            ),
        )
        hf_item = status._huggingface_papers_item(hf_dir)
        assert hf_item["status"] == "ok"
        assert hf_item["title"] == "Hugging Face 论文周报 — 2026-W23 · 2026-06-01 ~ 2026-06-07"
        assert hf_item["subtitle"] == "论文热点周报"
        assert hf_item["metrics"]["报告形态"] == "高级洞察报告"
        assert hf_item["metrics"]["报告周期"] == "2026-W23 · 2026-06-01 ~ 2026-06-07"
        assert hf_item["metrics"]["窗口去重"] == 24
        assert hf_item["metrics"]["分组章节"] == 5
        assert hf_item["primary"]["artifact"] == "report_html"
        assert any(a["artifact"] == "report_html" for a in hf_item["artifacts"])
        assert any(r["artifact"] == "report_html" for r in hf_item["resources"])

        import os

        old_vault = os.environ.get("OBSIDIAN_VAULT_PATH")
        os.environ["OBSIDIAN_VAULT_PATH"] = str(knowledge)
        try:
            dispatch = Path(ai.create_wiki_ingest_dispatch(run_dir, recent))
        finally:
            if old_vault is None:
                os.environ.pop("OBSIDIAN_VAULT_PATH", None)
            else:
                os.environ["OBSIDIAN_VAULT_PATH"] = old_vault
        text = dispatch.read_text(encoding="utf-8")
        assert dispatch.parent == knowledge / "_raw" / "solar-harness" / ".dispatch"
        assert "type: wiki-dispatch" in text
        assert "skill: wiki-ingest" in text
        assert "status: pending" in text
        assert f"source={run_dir / 'digest.md'}" in text

    print("PASS status-server AI Influence report center")


if __name__ == "__main__":
    main()
