from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "scripts" / "tech_hotspot_radar.py"


def _load_namespace() -> dict:
    ns: dict = {"__file__": str(SCRIPT), "__name__": "tech_hotspot_radar_test"}
    code = compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")
    exec(code, ns)
    return ns


def test_browser_agent_chatgpt_cmd_falls_back_to_bundled_wrapper(monkeypatch):
    monkeypatch.delenv("TECH_HOTSPOT_BROWSER_CHATGPT_CMD", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_CHATGPT_CMD", raising=False)
    ns = _load_namespace()
    cmd = ns["browser_agent_chatgpt_cmd"]({})
    assert cmd, "expected bundled wrapper fallback command"
    assert cmd[-1].endswith("chatgpt_report_operator.py")


def test_browser_agent_chatgpt_cmd_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("TECH_HOTSPOT_BROWSER_CHATGPT_CMD", "python3 /tmp/custom-wrapper.py")
    ns = _load_namespace()
    cmd = ns["browser_agent_chatgpt_cmd"]({})
    assert cmd == ["python3", "/tmp/custom-wrapper.py"]


def test_browser_agent_notebooklm_cmd_falls_back_to_bundled_wrapper(monkeypatch, tmp_path):
    monkeypatch.delenv("TECH_HOTSPOT_BROWSER_NOTEBOOKLM_CMD", raising=False)
    monkeypatch.delenv("BROWSER_AGENT_NOTEBOOKLM_CMD", raising=False)
    fake_python = tmp_path / ".claude/mcp-servers/browser-use/.venv/bin/python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    ns = _load_namespace()
    cmd = ns["browser_agent_notebooklm_cmd"]({})
    assert cmd, "expected bundled wrapper fallback command"
    assert cmd[-1].endswith("browser_agent_notebooklm_wrapper.py")
    assert "browser-use/.venv/bin/python" in cmd[0]


def test_call_browser_agent_chatgpt_text_prefers_process_env_over_config(monkeypatch, tmp_path):
    wrapper = tmp_path / "fake_wrapper.py"
    wrapper.write_text(
        "import json, os\n"
        "print(json.dumps({\n"
        "  'profile_directory': os.environ.get('BROWSER_AGENT_PROFILE_DIRECTORY'),\n"
        "  'headless': os.environ.get('BROWSER_AGENT_HEADLESS'),\n"
        "  'account_email': os.environ.get('BROWSER_AGENT_TARGET_ACCOUNT_EMAIL'),\n"
        "  'pad': 'x' * 700\n"
        "}, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TECH_HOTSPOT_BROWSER_CHATGPT_CMD", f"{sys.executable} {wrapper}")
    monkeypatch.setenv("BROWSER_AGENT_PROFILE_DIRECTORY", "Default")
    monkeypatch.setenv("BROWSER_AGENT_HEADLESS", "true")
    monkeypatch.setenv("BROWSER_AGENT_TARGET_ACCOUNT_EMAIL", "browser-agent@example.com")
    ns = _load_namespace()
    result = ns["call_browser_agent_chatgpt_text"](
        "验证 env override",
        {
            "output": {"raw_dir": str(tmp_path)},
            "youtube": {
                "phase_report_reasoner": {
                    "profile_directory": "Profile 1",
                    "headless": False,
                    "target_account_email": "someone@example.com",
                }
            },
        },
        purpose="hf-headless-env-override",
        expected="json",
    )
    payload = json.loads(result["text"])
    assert payload["profile_directory"] == "Default"
    assert payload["headless"] == "true"
    assert payload["account_email"] == "browser-agent@example.com"


def test_hf_public_report_render_outputs_reader_facing_md_and_html():
    ns = _load_namespace()
    public_records = [
        {
            "paper_id": "2509.22186",
            "packet_id": "pkt-123",
            "title": "MinerU2.5",
            "summary": "这是一篇关于高分辨率文档解析工程化的论文。",
            "taxonomy": {
                "domain": "systems",
                "stack_layer": "inference",
                "research_route": "applied_research",
            },
            "scores": {
                "insight_report": 0.585,
                "experiment": 0.715,
                "open_project": 0.640,
                "deep_research_seed": 0.675,
            },
            "assets": {
                "linked_models": ["m1", "m2"],
                "linked_datasets": ["d1"],
                "linked_spaces": ["s1"],
                "total_assets": 4,
            },
            "github": {
                "full_name": "opendatalab/MinerU",
                "url": "https://github.com/opendatalab/MinerU",
            },
            "reasoning": {
                "mode": "premium_insight",
                "trend_type": "real_trend",
                "premium_insight_available": True,
                "evidence_ids": ["2509.22186", "pkt-123"],
            },
            "why_matters": "这条线直接影响知识库、文档解析和企业工作流自动化。",
            "recommended_action": "先做最小复现实验，再决定是否上主线观察。",
            "research_implication": "解耦式 VLM 可能成为文档理解的新默认架构。",
            "experiment_plan": ["对比现有 OCR pipeline", "测试长文档吞吐"],
            "open_source_opportunity": "围绕 PDF 解析做 benchmark harness。",
            "deep_research_question": "解耦式解析是否会成为文档 VLM 的主流范式？",
            "hypotheses": ["高分辨率解析会先在企业文档工作流落地"],
            "strategic_questions": ["是否值得持续跟踪 opendatalab 生态"],
            "evidence_gap": ["缺少跨行业基准对比"],
        }
    ]
    markdown = ns["_hf_render_public_report_markdown"](
        date_str="2026-06-01",
        report_variant="premium_insight_report",
        premium_count=1,
        fallback_count=0,
        public_records=public_records,
    )
    html = ns["_hf_render_public_report_html"](
        date_str="2026-06-01",
        report_variant="premium_insight_report",
        premium_count=1,
        fallback_count=0,
        public_records=public_records,
    )
    assert "## 一页判断" in markdown
    assert "| 指标 | 值 |" in markdown
    assert "#### 推荐动作" in markdown
    assert "#### 实验计划" in markdown
    assert "<!doctype html>" in html
    assert "hf-hero" in html
    assert "Top 论文洞察" in html
    assert "opendatalab/MinerU" in html


def test_hf_normalize_report_plan_assigns_unassigned_papers():
    ns = _load_namespace()
    public_records = [
        {"paper_id": "p1"},
        {"paper_id": "p2"},
        {"paper_id": "p3"},
    ]
    plan = ns["hf_normalize_report_plan"](
        {
            "headline": "",
            "executive_summary": "今天 HF 热点集中在两条可解释主线。",
            "sections": [
                {
                    "section_id": "agents",
                    "title": "Agent 框架化",
                    "trend_label": "Agent",
                    "thesis": "Agent 正在从 demo 进入工程化。",
                    "why_now": "今天这组论文共同体现了平台化趋势。",
                    "paper_ids": ["p1", "p2", "p2", "missing"],
                }
            ],
            "closing_watchpoints": ["关注 repo 跟进速度"],
        },
        public_records,
        date_str="2026-06-01",
    )
    assert plan["headline"] == "AI Influence HF Paper 高级洞察周报 — 2026-W23 · 2026-06-01 ~ 2026-06-07"
    assert len(plan["sections"]) == 2
    assert plan["sections"][0]["paper_ids"] == ["p1", "p2"]
    assert plan["sections"][1]["section_id"] == "other-signals"
    assert plan["sections"][1]["paper_ids"] == ["p3"]
    assert plan["closing_watchpoints"] == ["关注 repo 跟进速度"]


def test_hf_write_public_report_prefers_grouped_flow_outputs(tmp_path):
    ns = _load_namespace()
    candidates = [
        {
            "public": {
                "paper_id": "p1",
                "packet_id": "pkt-1",
                "title": "MinerU2.5",
                "summary": "高分辨率文档解析成为工程化入口。",
                "taxonomy": {"domain": "systems", "stack_layer": "inference", "research_route": "applied_research"},
                "scores": {"insight_report": 0.7, "experiment": 0.8},
                "assets": {"linked_models": [], "linked_datasets": [], "linked_spaces": [], "total_assets": 1},
                "github": {"full_name": "org/repo1", "url": "https://github.com/org/repo1"},
                "reasoning": {"mode": "fallback_report", "trend_type": "watchlist", "premium_insight_available": False},
                "why_matters": "文档智能会影响知识工作流入口。",
                "recommended_action": "跟踪解耦式架构的复现线索。",
            },
            "compiled": {"chapter": "公开摘要 A"},
        },
        {
            "public": {
                "paper_id": "p2",
                "packet_id": "pkt-2",
                "title": "Kronos",
                "summary": "通用时间序列基础模型开始争夺标准接口。",
                "taxonomy": {"domain": "time-series", "stack_layer": "foundation_model", "research_route": "model_system"},
                "scores": {"insight_report": 0.75, "experiment": 0.65},
                "assets": {"linked_models": [], "linked_datasets": [], "linked_spaces": [], "total_assets": 1},
                "github": {"full_name": "org/repo2", "url": "https://github.com/org/repo2"},
                "reasoning": {"mode": "premium_insight", "trend_type": "real_trend", "premium_insight_available": True},
                "why_matters": "基础模型接口标准化会影响后续生态。",
                "recommended_action": "观察是否快速形成 benchmark 竞争。",
            },
            "compiled": {"chapter": "公开摘要 B"},
        },
    ]
    ns["hf_paper_insight_db_path"] = lambda config: tmp_path / "dummy.sqlite"
    ns["hf_load_report_candidates"] = lambda store_path, limit, date_str, config, reasoning_mode: candidates
    ns["hf_call_grouped_report_flow"] = lambda public_records, config, date_str, report_context=None: {
        "ok": True,
        "model": "chatgpt-5.5",
        "plan": {
            "headline": "AI Influence HF Paper 高级洞察周报 — 2026-W23 · 2026-06-01 ~ 2026-06-07",
            "executive_summary": "今天 HF 热点可以拆成文档智能与基础模型接口两条主线。",
            "closing_watchpoints": ["继续跟踪开源复现速度"],
        },
        "sections": [
            {
                "section_id": "doc-intel",
                "title": "文档智能自动化",
                "trend_type": "real_trend",
                "section_summary": "文档理解开始从 OCR 升级为工作流级自动化入口。",
                "trend_description": "这部分论文说明高分辨率解析能力正在向企业工作流渗透。",
                "insight_analysis": "关键不只是识别精度，而是能否成为后续 agent 编排的前置层。",
                "planning_recommendations": ["做最小 PDF 解析基准", "跟踪开源 benchmark 形成速度"],
                "paper_commentary": [
                    {
                        "paper_id": "p1",
                        "title": "MinerU2.5",
                        "role": "文档智能入口样本",
                        "takeaway": "高分辨率解析与解耦式架构是关键看点。",
                        "evidence_ids": ["p1", "pkt-1"],
                    }
                ],
                "evidence_ids": ["p1", "pkt-1"],
            },
            {
                "section_id": "foundation-interfaces",
                "title": "基础模型接口化",
                "trend_type": "real_trend",
                "section_summary": "时间序列基础模型开始争夺统一生态接口。",
                "trend_description": "这部分论文说明基础模型竞争正在向行业标准位移。",
                "insight_analysis": "如果接口先形成，后续生态锁定会快于纯论文迭代。",
                "planning_recommendations": ["观察 benchmark 与 SDK 配套节奏"],
                "paper_commentary": [
                    {
                        "paper_id": "p2",
                        "title": "Kronos",
                        "role": "接口标准竞争样本",
                        "takeaway": "应关注其是否形成生态入口优势。",
                        "evidence_ids": ["p2", "pkt-2"],
                    }
                ],
                "evidence_ids": ["p2", "pkt-2"],
            },
        ],
    }
    result = ns["hf_write_public_report"](
        {"output": {"raw_dir": str(tmp_path)}},
        date_str="2026-06-01",
        limit=5,
        output_base=str(tmp_path),
        reasoning_mode="browser_agent",
    )
    assert result["grouped_report_ok"] is True
    assert result["report_variant"] == "premium_insight_report"
    assert Path(result["plan_json"]).exists()
    assert Path(result["sections_json"]).exists()
    markdown = Path(result["report_md"]).read_text(encoding="utf-8")
    html = Path(result["report_html"]).read_text(encoding="utf-8")
    pack = json.loads(Path(result["pack_json"]).read_text(encoding="utf-8"))
    assert "## 01. 文档智能自动化" in markdown
    assert "## 02. 基础模型接口化" in markdown
    assert "### 该部分论文分工" in markdown
    assert "后续观察点" in markdown
    assert "<!doctype html>" in html
    assert "文档智能自动化" in html
    assert "该部分论文分工" in html
    assert pack["grouped_report_ok"] is True
    assert pack["report_variant"] == "premium_insight_report"
    assert pack["grouped_report_plan"]["headline"] == "AI Influence HF Paper 高级洞察周报 — 2026-W23 · 2026-06-01 ~ 2026-06-07"
    assert pack["report_context"]["cadence"] == "weekly"
    assert pack["report_context"]["week_id"] == "2026-W23"
    assert pack["report_context"]["window_start"] == "2026-06-01"
    assert pack["report_context"]["window_end"] == "2026-06-07"
    assert len(pack["grouped_report_sections"]) == 2


def test_hf_report_context_weekly_uses_iso_week_not_rolling_window():
    ns = _load_namespace()
    context = ns["hf_report_context"]("2026-05-29", {"hf_paper_insight": {"reporting": {"cadence": "weekly"}}})
    assert context["week_id"] == "2026-W22"
    assert context["window_start"] == "2026-05-25"
    assert context["window_end"] == "2026-05-31"
    assert context["window_label"] == "2026-W22 · 2026-05-25 ~ 2026-05-31"


def test_hf_weekly_priority_score_prefers_persistent_high_rank_signals():
    ns = _load_namespace()
    end_date = ns["dt"].date(2026, 6, 1)
    strong = ns["hf_weekly_priority_score"](
        {
            "days_seen": 5,
            "best_daily_rank": 2,
            "best_weekly_rank": 3,
            "best_monthly_rank": 8,
            "last_daily_seen": "2026-06-01",
        },
        {
            "insight_report": 0.82,
            "experiment": 0.66,
            "deep_research_seed": 0.71,
            "research_signal": 0.64,
            "open_project": 0.58,
        },
        end_date=end_date,
        lookback_days=7,
    )
    weak = ns["hf_weekly_priority_score"](
        {
            "days_seen": 1,
            "best_daily_rank": 15,
            "best_weekly_rank": 0,
            "best_monthly_rank": 0,
            "last_daily_seen": "2026-05-27",
        },
        {
            "insight_report": 0.31,
            "experiment": 0.21,
            "deep_research_seed": 0.28,
            "research_signal": 0.22,
            "open_project": 0.18,
        },
        end_date=end_date,
        lookback_days=7,
    )
    assert strong > weak


def test_hf_candidate_reasoning_plan_defaults_weekly_to_grouped_sections():
    ns = _load_namespace()
    plan = ns["hf_candidate_reasoning_plan"](
        report_context={"cadence": "weekly"},
        paper_id="p-core",
        core_ids={"p-core", "p2"},
        requested_mode="browser_agent",
        config={},
    )
    assert plan["use_high_reasoning"] is False
    assert plan["fallback_reason"] == "weekly_grouped_core_pool"
    assert plan["strategy"] == "grouped_sections"

    support_plan = ns["hf_candidate_reasoning_plan"](
        report_context={"cadence": "weekly"},
        paper_id="p-support",
        core_ids={"p-core", "p2"},
        requested_mode="browser_agent",
        config={},
    )
    assert support_plan["use_high_reasoning"] is False
    assert support_plan["fallback_reason"] == "weekly_supporting_pool"
    assert support_plan["strategy"] == "grouped_sections"


def test_hf_candidate_reasoning_plan_allows_weekly_per_paper_override():
    ns = _load_namespace()
    config = {"hf_paper_insight": {"reporting": {"high_reasoning_strategy": "per_paper"}}}
    core_plan = ns["hf_candidate_reasoning_plan"](
        report_context={"cadence": "weekly"},
        paper_id="p-core",
        core_ids={"p-core", "p2"},
        requested_mode="browser_agent",
        config=config,
    )
    assert core_plan["use_high_reasoning"] is True
    assert core_plan["fallback_reason"] is None
    assert core_plan["strategy"] == "per_paper"

    support_plan = ns["hf_candidate_reasoning_plan"](
        report_context={"cadence": "weekly"},
        paper_id="p-support",
        core_ids={"p-core", "p2"},
        requested_mode="browser_agent",
        config=config,
    )
    assert support_plan["use_high_reasoning"] is False
    assert support_plan["fallback_reason"] == "weekly_supporting_pool"
    assert support_plan["strategy"] == "per_paper"


def test_hf_report_collection_summary_uses_weekly_source_tables(tmp_path):
    ns = _load_namespace()
    db_path = tmp_path / "tech-hotspot-radar.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE hf_daily_papers (
            paper_date TEXT NOT NULL,
            paper_id TEXT NOT NULL,
            rank INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE hf_paper_period_snapshots (
            paper_id TEXT NOT NULL,
            period TEXT NOT NULL,
            snapshot_at TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO hf_daily_papers (paper_date, paper_id, rank) VALUES (?, ?, ?)",
        [
            ("2026-05-26", "p1", 1),
            ("2026-05-26", "p2", 2),
            ("2026-05-27", "p1", 3),
            ("2026-05-28", "p3", 4),
        ],
    )
    conn.executemany(
        "INSERT INTO hf_paper_period_snapshots (paper_id, period, snapshot_at) VALUES (?, ?, ?)",
        [
            ("p1", "weekly", "2026-05-26T10:00:00Z"),
            ("p2", "weekly", "2026-05-27T10:00:00Z"),
            ("p2", "monthly", "2026-05-27T11:00:00Z"),
            ("p4", "monthly", "2026-06-01T12:00:00Z"),
        ],
    )
    conn.commit()
    conn.close()
    summary = ns["hf_report_collection_summary"](
        {"output": {"database": str(db_path)}},
        report_context={
            "cadence": "weekly",
            "week_id": "2026-W22",
            "window_start": "2026-05-25",
            "window_end": "2026-05-31",
            "window_label": "2026-W22 · 2026-05-25 ~ 2026-05-31",
        },
        public_records=[
            {"paper_id": "p1", "weekly_signal": {"is_core": True}},
            {"paper_id": "p2", "weekly_signal": {"is_core": False}},
        ],
    )
    assert summary["daily_rows"] == 4
    assert summary["daily_unique_papers"] == 3
    assert summary["weekly_snapshot_unique_papers"] == 2
    assert summary["monthly_snapshot_unique_papers"] == 1
    assert summary["selected_papers"] == 2
    assert summary["core_papers"] == 1


def test_hf_missing_value_handles_lists_without_typeerror():
    ns = _load_namespace()
    assert ns["_hf_missing_value"](None) is True
    assert ns["_hf_missing_value"]("") is True
    assert ns["_hf_missing_value"]("  ") is True
    assert ns["_hf_missing_value"]([]) is True
    assert ns["_hf_missing_value"]({}) is True
    assert ns["_hf_missing_value"](["section"]) is False
    assert ns["_hf_missing_value"]({"headline": "ok"}) is False


def test_hf_clean_public_text_scrubs_internal_ids():
    ns = _load_namespace()
    raw = "这是一条判断。依据：2605.30263, pkt-a3c9e8b0828b405c [evidence: 2605.30263, pkt-a3c9e8b0828b405c]"
    cleaned = ns["hf_clean_public_text"](raw)
    assert "2605.30263" not in cleaned
    assert "pkt-a3c9e8b0828b405c" not in cleaned
    assert "evidence" not in cleaned.lower()


def test_hf_clean_public_text_repairs_empty_evidence_sentences():
    ns = _load_namespace()
    raw = (
        "核心判断一：多模态模型正在补空间短板，证据来自 2605.30263、pkt-a3c9e8b0828b405c 及对应材料。"
        " 关注的是长程交互状态管理。"
        " 核心依据来自 与 。"
        " - 将 放入观察池。"
        " 【evidence_ids: 2605.30263, pkt-a3c9e8b0828b405c】"
    )
    cleaned = ns["hf_clean_public_text"](raw)
    assert "2605.30263" not in cleaned
    assert "pkt-a3c9e8b0828b405c" not in cleaned
    assert "evidence_ids" not in cleaned
    assert "证据来自" not in cleaned
    assert "核心依据来自" not in cleaned
    assert "该论文关注的是长程交互状态管理。" in cleaned
    assert "将该论文放入观察池。" in cleaned


def test_grouped_report_render_hides_internal_ids_and_labels():
    ns = _load_namespace()
    grouped_report = {
        "plan": {
            "headline": "HF 论文周报规划：测试标题",
            "executive_summary": "本期观察。依据：2605.30263, pkt-a3c9e8b0828b405c",
            "closing_watchpoints": ["跟踪 minWM。依据：2605.30263, pkt-a3c9e8b0828b405c"],
        },
        "sections": [
            {
                "title": "测试章节",
                "trend_type": "watchlist",
                "section_summary": "章节摘要。依据：2605.30263, pkt-a3c9e8b0828b405c",
                "trend_description": "趋势描述。依据：2605.30263, pkt-a3c9e8b0828b405c",
                "insight_analysis": "洞察分析。依据：2605.30263, pkt-a3c9e8b0828b405c",
                "planning_recommendations": ["做实验"],
                "paper_commentary": [
                    {
                        "paper_id": "2605.30263",
                        "title": "minWM",
                        "role": "主轴论文。依据：2605.30263",
                        "takeaway": "最值得看。依据：pkt-a3c9e8b0828b405c",
                        "evidence_ids": ["2605.30263", "pkt-a3c9e8b0828b405c"],
                    }
                ],
                "evidence_ids": ["2605.30263", "pkt-a3c9e8b0828b405c"],
            }
        ],
    }
    public_records = [{"title": "minWM"}]
    markdown = ns["_hf_render_grouped_report_markdown"](
        date_str="2026-06-01",
        report_variant="premium_insight_report",
        premium_count=1,
        fallback_count=0,
        public_records=public_records,
        grouped_report=grouped_report,
        report_context={"window_label": "2026-W23 · 2026-06-01 ~ 2026-06-07"},
    )
    assert "premium_insight_report" not in markdown
    assert "pkt-a3c9e8b0828b405c" not in markdown
    assert "2605.30263" not in markdown
    assert "正式洞察周报" in markdown


def test_grouped_report_render_repairs_empty_cleanup_shells():
    ns = _load_namespace()
    grouped_report = {
        "plan": {
            "headline": "HF 论文周报规划：测试标题",
            "executive_summary": "核心判断一：多模态模型正在补空间短板，证据来自 2605.30263、pkt-a3c9e8b0828b405c 及对应材料。",
            "closing_watchpoints": ["将 放入观察池。"],
        },
        "sections": [
            {
                "title": "测试章节",
                "trend_type": "watchlist",
                "section_summary": "章节摘要。",
                "trend_description": "这部分材料目前更适合作为观察项。 关注的是长程交互状态管理。核心依据来自 与 。",
                "insight_analysis": "该判断依据 与 。",
                "planning_recommendations": ["将 放入观察池。", "【evidence_ids: 2605.30263, pkt-a3c9e8b0828b405c】"],
                "paper_commentary": [],
            }
        ],
    }
    markdown = ns["_hf_render_grouped_report_markdown"](
        date_str="2026-06-01",
        report_variant="premium_insight_report",
        premium_count=1,
        fallback_count=0,
        public_records=[{"title": "minWM"}],
        grouped_report=grouped_report,
        report_context={"window_label": "2026-W23 · 2026-06-01 ~ 2026-06-07"},
    )
    assert "证据来自" not in markdown
    assert "核心依据来自" not in markdown
    assert "该判断依据" not in markdown
    assert "【evidence_ids" not in markdown
    assert "该论文关注的是长程交互状态管理。" in markdown
    assert "将该论文放入观察池。" in markdown


def test_hf_internal_report_tokens_ignores_normal_cli_and_debug_words():
    ns = _load_namespace()
    clean = "本周值得关注的是 terminal agent、CLI tooling 与 debug workflow 的工程趋势。"
    leaked = "本轮因 rate limit 与 materialize-hf-paper-insights 失败，请稍后重试。"
    assert ns["hf_internal_report_tokens"](clean) == []
    assert ns["hf_internal_report_tokens"](leaked) == ["rate_limit", "materialize_command"]


def test_ai_influence_html_render_uses_reader_facing_sources():
    ns = _load_namespace()
    html = ns["render_ai_influence_report_html_anything"](
        "测试报告标题\n证据边界\n这里只基于素材。\n一页结论\n这是结论。\n核心趋势\n1. 主趋势\n判断\n这是判断。",
        {
            "date": "2026-05-26",
            "videos": [
                {
                    "channel": "Google for Developers",
                    "title": "What's new in Google AI",
                    "published_at": "2026-05-23T00:45:21+00:00",
                    "duration_min": 18.2,
                    "summary_zh": "聚焦 Gemini 3.5、AI Studio 与开发者工作流。",
                    "url": "https://www.youtube.com/watch?v=SSe1VmVrtw0",
                    "video_ref": "V001",
                }
            ],
            "report_spec": {
                "title": "测试报告标题",
                "chapters": [
                    {"title": "Gemini 平台化", "material_video_refs": ["V001"]},
                ],
            },
        },
        {"headline": "测试报告标题"},
    )
    assert "本期素材" in html
    assert "章节与视频素材对应表" in html
    assert "V001" in html
    assert "ai-material-ref" in html
    assert "ai-material-chip" in html
    assert "Google for Developers" in html
    assert "What&#x27;s new in Google AI" in html
    assert "聚焦 Gemini 3.5、AI Studio 与开发者工作流。" in html
    assert "<table>" in html
    assert "<th>频道</th>" in html
    assert "<th>视频标题</th>" in html
    assert "<th>发布时间 / 时长</th>" in html
    assert 'href="https://www.youtube.com/watch?v=SSe1VmVrtw0"' in html
    assert 'target="_blank"' in html
    assert "html-anything profile=" not in html
    assert "Browser Agent + ChatGPT 5.5 Thinking high" not in html
    assert "证据边界" not in html
    assert "本报告只基于本次证据包写作，不补外部事实。" not in html
    assert '<section class="ai-report-section"' in html
    assert "<h2>摘要</h2>" in html
    assert "<h4>1. 主趋势</h4>" in html


def test_ai_influence_html_render_injects_notebooklm_figures():
    ns = _load_namespace()
    html = ns["render_ai_influence_report_html_anything"](
        "测试报告标题\n一页结论\n这是结论。\n核心趋势\n1. 主趋势\n判断\n这是判断。\n产品 / 研究 / 工程启示\n这里是落点。",
        {
            "date": "2026-05-26",
            "videos": [],
            "report_spec": {"title": "测试报告标题"},
            "notebooklm": {
                "infographics": [
                    {
                        "title": "平台关系图",
                        "placement_section": "正文",
                        "material_video_refs": ["V001", "V002"],
                        "prompt_text": "画出平台关系与层次",
                        "status": "ready",
                        "image_path": "notebooklm/figure-1.png",
                    }
                ]
            },
        },
        {"headline": "测试报告标题"},
    )
    assert "平台关系图" in html
    assert "notebooklm/figure-1.png" in html
    assert "素材：V001 / V002" in html
    assert "状态：ready" in html


def test_ai_influence_html_render_drops_internal_preamble():
    ns = _load_namespace()
    html = ns["render_ai_influence_report_html_anything"](
        "测试报告标题\n证据边界\n本报告只基于本次证据包写作，不补外部事实。\n需要先把材料质量说清楚：这里是内部前言。\n一页结论\n这是结论。\n核心趋势\n1. 主趋势\n判断\n这是判断。",
        {
            "date": "2026-05-26",
            "videos": [],
            "report_spec": {"title": "测试报告标题"},
        },
        {"headline": "测试报告标题"},
    )
    assert "证据边界" not in html
    assert "本报告只基于本次证据包写作，不补外部事实。" not in html
    assert "需要先把材料质量说清楚" not in html
    assert "<h2>摘要</h2>" in html


def test_ai_influence_reader_tone_polish_rewrites_internal_phrasing():
    ns = _load_namespace()
    polished = ns["_polish_ai_influence_reader_tone"](
        "由于 transcript 几乎没有有效语义，本报告不引用其具体观点，只把标题作为“行业正在讨论空间化 Agent UI”的主题证据。"
        "\n第一，证据中的 200 秒持续推理能力来自自动转写和语义整理，虽然方向可信，但精确表述仍需后续用原视频或官方材料确认。"
    )
    assert "transcript" not in polished
    assert "本报告不引用其具体观点" not in polished
    assert "方向参考" in polished
    assert "公开视频转写" in polished


def test_ai_influence_heading_system_is_editorialized():
    ns = _load_namespace()
    normalized = ns["_normalize_ai_influence_report_markdown"](
        "标题\n一页结论\n这是结论。\n核心趋势\n1. 中心判断：Google 正在变\n判断\n这是判断。\n证据来自哪些频道/视频\n这里是来源。\n为什么重要\n这里是影响。\n对产品/研究/工程/投资的启示\n这里是落点。\n反向证据或不确定性\n这里是待验证。",
        "标题",
    )
    assert "## 摘要" in normalized
    assert "## 正文" in normalized
    assert "### 1. 主线：Google 正在变" in normalized
    assert "#### 观察" in normalized
    assert "#### 素材来源" in normalized
    assert "#### 影响" in normalized
    assert "#### 落点" in normalized
    assert "#### 仍待验证" in normalized


def test_ai_influence_material_map_does_not_leak_planner_fields():
    ns = _load_namespace()
    html = ns["render_ai_influence_report_html_anything"](
        "# 测试报告\n\n## 一页结论\n本节素材：V001《测试视频》。\n\n## 核心趋势\n正文。\n\n## 关键视频证据\n- V001\n\n## 产品 / 研究 / 工程启示\n启示。\n\n## Open Questions\n- 待验证。\n\n## Provenance\n- final_reasoner: chatgpt-5.5\n- local_preprocess: ThunderOMLX/Qwen3.6 semantic packets\n- input_videos: 1\n",
        {
            "date": "2026-05-26",
            "videos": [
                {
                    "video_ref": "V001",
                    "video_id": "abc123",
                    "channel": "AI Engineer",
                    "title": "测试视频",
                    "published_at": "2026-05-23T00:00:00+00:00",
                    "duration_min": 42,
                    "summary_zh": "面向读者的摘要。",
                    "url": "https://www.youtube.com/watch?v=abc123",
                    "_internal_debug": "SHOULD_NOT_RENDER",
                }
            ],
            "report_spec": {
                "title": "测试报告",
                "internal_notes": "SHOULD_NOT_RENDER",
                "chapters": [
                    {
                        "title": "中心判断：Coding Agent 的竞争点正在转向工程运行面",
                        "purpose": "把素材组织成一个清晰判断：这是内部写作指令。",
                        "material_video_refs": ["V001"],
                        "debug_prompt": "SHOULD_NOT_RENDER",
                    }
                ],
            },
        },
        {"headline": "测试报告"},
    )
    assert "Coding Agent 的竞争点正在转向工程运行面" in html
    assert "中心判断：" not in html
    assert "把素材组织成" not in html
    assert "purpose" not in html
    assert "material_video_refs" not in html
    assert "internal_notes" not in html
    assert "SHOULD_NOT_RENDER" not in html


def test_plan_prompt_requires_figure_slots():
    ns = _load_namespace()
    prompt = ns["build_ai_influence_report_plan_prompt"](
        [{
            "video_ref": "V001",
            "channel": "Google for Developers",
            "title": "What's new in Google AI",
            "published_at": "2026-05-23T00:45:21+00:00",
            "duration_min": 18.2,
            "language": "en",
            "summary_zh": "摘要",
            "key_points": ["A"],
            "topic_tags": ["agent"],
            "why_it_matters": "重要",
            "transcript_chars": 12000,
        }],
        date_str="2026-05-26",
        days=7,
        model_name="chatgpt-5.5",
    )
    assert '"figure_slots"' in prompt
    assert "NotebookLM" in prompt
    assert "generation_text" in prompt


def test_grouping_prompt_uses_transcript_and_material_type_contract():
    ns = _load_namespace()
    prompt = ns["build_ai_influence_video_grouping_prompt"](
        [{
            "video_ref": "V001",
            "channel": "Google for Developers",
            "title": "Conference keynote about Gemini",
            "published_at": "2026-05-23T00:45:21+00:00",
            "duration_min": 32.0,
            "language": "en",
            "summary_zh": "发布会摘要",
            "key_points": ["Agent platform"],
            "topic_tags": ["agent"],
            "why_it_matters": "重要",
            "transcript_chars": 12000,
            "transcript_truncated_for_grouping": False,
            "transcript_excerpt": "This is a keynote transcript about Gemini agent platform primitives.",
        }],
        date_str="2026-05-26",
        days=7,
        model_name="chatgpt-5.5",
    )
    assert "语义分组" in prompt
    assert "重要展会" in prompt
    assert "大咖访谈" in prompt
    assert "tutorial_demo" in prompt
    assert "transcript_excerpt" in prompt
    assert "不要只按关键词或发布时间聚类" in prompt


def test_plan_prompt_consumes_video_groups_and_requires_hierarchy():
    ns = _load_namespace()
    prompt = ns["build_ai_influence_report_plan_prompt"](
        [{
            "video_ref": "V001",
            "channel": "Google for Developers",
            "title": "What's new in Google AI",
            "published_at": "2026-05-23T00:45:21+00:00",
            "duration_min": 18.2,
            "language": "en",
            "summary_zh": "摘要",
            "key_points": ["A"],
            "topic_tags": ["agent"],
            "why_it_matters": "重要",
            "transcript_chars": 12000,
        }],
        date_str="2026-05-26",
        days=7,
        model_name="chatgpt-5.5",
        video_group_plan={
            "video_groups": [
                {
                    "group_id": "google-io-keynotes",
                    "group_type": "conference",
                    "group_title": "Google I/O 相关发布",
                    "material_video_refs": ["V001"],
                }
            ]
        },
    )
    assert "前置语义分组 JSON" in prompt
    assert "google-io-keynotes" in prompt
    assert '"trends"' in prompt
    assert '"subsections"' in prompt
    assert "趋势 X → 章节 Y → 小结 Z" in prompt


def test_plan_material_refs_recurses_trends_chapters_subsections():
    ns = _load_namespace()
    refs = ns["_plan_material_refs"]({
        "material_video_refs": ["V001"],
        "trends": [
            {
                "material_video_refs": ["V002"],
                "chapters": [
                    {
                        "material_video_refs": ["V003"],
                        "subsections": [
                            {"material_video_refs": ["V004"], "supporting_video_refs": ["V005"]}
                        ],
                    }
                ],
            }
        ],
    })
    assert refs == ["V001", "V002", "V003", "V004", "V005"]


def test_planned_report_ir_builds_per_chapter_contract():
    ns = _load_namespace()
    evidence_pack = {
        "date": "2026-05-31",
        "lookback_days": 7,
        "report_spec": {
            "report_id": "agent-platform",
            "title": "Agent 平台化报告",
            "scope": "分析 agent runtime",
            "reader_value": "帮助判断趋势",
            "trends": [
                {
                    "trend_title": "Agent 工具层基础设施化",
                    "material_video_refs": ["V001"],
                    "chapters": [
                        {
                            "title": "工具接口协议化",
                            "purpose": "解释为什么重要",
                            "material_video_refs": ["V001"],
                        }
                    ],
                }
            ],
        },
        "videos": [{"video_ref": "V001", "title": "Agent video"}],
    }
    report_ir = ns["build_ai_influence_report_ir"](evidence_pack)
    assert report_ir["operator_contract"]["planner"].startswith("DeepResearchChatGPT")
    assert report_ir["operator_contract"]["chapter_writer"].startswith("tools/chatgpt_report_operator.py")
    assert report_ir["operator_contract"]["whole_report_writer"] == "disabled"
    assert any(ch["chapter_type"] == "core_trend" and ch["title"] == "工具接口协议化" for ch in report_ir["chapters"])


def test_chapter_prompt_requires_chapter_writer_only():
    ns = _load_namespace()
    report_ir = {
        "title": "Agent 平台化报告",
        "global_scope": "分析 agent runtime",
        "reader_value": "帮助判断趋势",
    }
    chapter_spec = {
        "chapter_id": "ch_01",
        "title": "工具接口协议化",
        "output_heading": "### 工具接口协议化",
        "chapter_type": "core_trend",
        "material_video_refs": ["V001"],
    }
    evidence = {
        "videos": [
            {
                "video_ref": "V001",
                "channel": "AI Engineer",
                "title": "Agent Runtime",
                "transcript_clean": "agent tools need stable protocol",
            }
        ]
    }
    prompt = ns["build_planned_report_chapter_prompt"](
        report_ir,
        chapter_spec,
        evidence,
        model_name="chatgpt-5.5",
    )
    assert "ChatGPT Report Chapter Writer" in prompt
    assert "只写当前章节" in prompt
    assert "不写整份报告" in prompt
    assert "### 工具接口协议化" in prompt
    assert "chapter_evidence_pack" in prompt


def test_build_planned_report_evidence_pack_skips_missing_status_transcript(tmp_path):
    ns = _load_namespace()
    conn = sqlite3.connect(":memory:")
    conn.executescript(ns["SCHEMA_SQL"])
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO youtube_channels(channel_id,channel_name,channel_url,category,enabled,imported_at) VALUES(?,?,?,?,?,?)",
        ("UCtest", "AI Engineer", "https://www.youtube.com/@aiDotEngineer", "AI / Tech", 1, "2026-05-26T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO youtube_videos(video_id,channel_id,title,channel_name,video_url,published_at,duration_seconds,fetched_at) VALUES(?,?,?,?,?,?,?,?)",
        ("bad001", "UCtest", "Prompt to Pipeline", "AI Engineer", "https://www.youtube.com/watch?v=bad001", "2026-05-23T00:00:00+00:00", 1200, "2026-05-26T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO youtube_transcripts(video_id,transcript_raw,transcript_clean,transcript_status,language,char_count) VALUES(?,?,?,?,?,?)",
        ("bad001", "我 我 我", "我 我 我\n研究\n研究\n机构\n" * 60, "missing", "mixed", 0),
    )
    pack = ns["build_planned_report_evidence_pack"](
        conn,
        [{
            "video_ref": "V001",
            "video_id": "bad001",
            "title": "Prompt to Pipeline",
            "channel": "AI Engineer",
            "url": "https://www.youtube.com/watch?v=bad001",
            "published_at": "2026-05-23T00:00:00+00:00",
        }],
        {"material_video_refs": ["V001"]},
        date_str="2026-05-26",
        days=7,
    )
    assert pack["videos"] == []
    assert pack["skipped_material_refs"] == ["V001"]


def test_notebooklm_bundle_and_request_are_built(tmp_path):
    ns = _load_namespace()
    evidence_pack = {
        "date": "2026-05-26",
        "report_spec": {
            "title": "测试报告",
            "figure_slots": [
                {
                    "figure_id": "agent-map",
                    "placement_section": "正文",
                    "placement_heading": "Gemini 平台化",
                    "title": "Agent 平台关系图",
                    "material_video_refs": ["V001"],
                    "generation_text": "画平台关系图",
                }
            ],
        },
        "videos": [
            {
                "video_ref": "V001",
                "title": "What's new in Google AI",
                "channel": "Google for Developers",
                "published_at": "2026-05-23T00:45:21+00:00",
                "url": "https://www.youtube.com/watch?v=SSe1VmVrtw0",
                "summary_zh": "摘要",
                "transcript_clean": "transcript body",
            }
        ],
    }
    request = ns["build_ai_influence_notebooklm_request"](
        evidence_pack,
        tmp_path / "report",
        notebook_name="AI Influence 2026-05",
    )
    assert request["notebook_name"] == "AI Influence 2026-05"
    assert request["mindmap"]["enabled"] is True
    assert request["infographics"][0]["figure_id"] == "agent-map"
    bundle_text = Path(request["source_files"][0]).read_text(encoding="utf-8")
    assert "Transcript 原文" in bundle_text
    assert "What's new in Google AI" in bundle_text


def test_attach_notebooklm_context_to_evidence_pack():
    ns = _load_namespace()
    pack = ns["attach_notebooklm_context_to_evidence_pack"](
        {"date": "2026-05-26", "videos": []},
        {
            "notebook_name": "AI Influence 2026-05",
            "notebook_url": "https://notebooklm.google.com/notebook/abc",
            "source_summary": "summary",
            "mindmap": {"status": "ready"},
            "infographics": [{"title": "图一"}],
        },
    )
    assert pack["notebooklm"]["notebook_name"] == "AI Influence 2026-05"
    assert pack["notebooklm"]["mindmap"]["status"] == "ready"
    assert pack["notebooklm"]["infographics"][0]["title"] == "图一"


def test_transcript_path_for_video_uses_week_bucket(tmp_path):
    ns = _load_namespace()
    db_path = tmp_path / "tech-hotspot-radar.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE youtube_videos (video_id TEXT PRIMARY KEY, published_at TEXT)")
    conn.execute(
        "INSERT INTO youtube_videos(video_id, published_at) VALUES (?, ?)",
        ("PvFMT58lgvk", "2026-05-07T19:36:01+00:00"),
    )
    conn.commit()
    conn.close()
    config = {
        "output": {
            "state_dir": str(tmp_path / "state"),
            "database": str(db_path),
        }
    }
    path = ns["transcript_path_for_video"]("PvFMT58lgvk", config)
    assert path.name == "PvFMT58lgvk.txt"
    assert path.parent.name == ns["transcript_week_key"]("2026-05-07T19:36:01+00:00")


def test_transcript_state_dirs_migrates_flat_cache_and_rewrites_sources(tmp_path):
    ns = _load_namespace()
    state_dir = tmp_path / "state"
    transcripts_dir = state_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    legacy = transcripts_dir / "PvFMT58lgvk.txt"
    legacy.write_text("hello\n", encoding="utf-8")
    result_dir = state_dir / "transcript-results" / "done"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_json = result_dir / "job.json"
    result_json.write_text(
        '{"source": "%s", "status": "completed"}\n' % str(legacy),
        encoding="utf-8",
    )
    db_path = tmp_path / "tech-hotspot-radar.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE youtube_videos (video_id TEXT PRIMARY KEY, published_at TEXT)")
    conn.execute(
        "INSERT INTO youtube_videos(video_id, published_at) VALUES (?, ?)",
        ("PvFMT58lgvk", "2026-05-07T19:36:01+00:00"),
    )
    conn.commit()
    conn.close()
    config = {
        "output": {
            "state_dir": str(state_dir),
            "database": str(db_path),
        }
    }
    ns["transcript_state_dirs"](config)
    migrated = transcripts_dir / ns["transcript_week_key"]("2026-05-07T19:36:01+00:00") / "PvFMT58lgvk.txt"
    assert migrated.exists()
    assert legacy.exists() is False
    payload = result_json.read_text(encoding="utf-8")
    assert str(migrated) in payload
    found = ns["find_transcript_file"]("PvFMT58lgvk", config)
    assert found == migrated


def test_ai_influence_validation_rejects_raw_video_id_leak(tmp_path):
    ns = _load_namespace()
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    complete_md = """# 测试报告

## 一页结论
本节素材：V001《测试视频》。这里不能出现 SSe1VmVrtw0。

## 核心趋势
### 趋势一
判断。

## 关键视频证据
- V001《测试视频》

## 产品 / 研究 / 工程启示
启示。

## Open Questions
- 待验证。

## Provenance
- final_reasoner: chatgpt-5.5
- local_preprocess: ThunderOMLX/Qwen3.6 semantic packets
- input_videos: 1
"""
    (report_dir / "report.md").write_text(complete_md, encoding="utf-8")
    (report_dir / "report.html").write_text(
        "章节与视频素材对应表 <span class='ai-material-ref'>V001</span> <span class='ai-material-chip'>测试视频</span>",
        encoding="utf-8",
    )
    (report_dir / "report-result.json").write_text('{"request_dir": ""}\n', encoding="utf-8")
    (report_dir / "evidence-pack.json").write_text(
        '{"videos":[{"video_ref":"V001","video_id":"SSe1VmVrtw0","title":"测试视频","channel":"Google for Developers","transcript_clean":"This is a clean English transcript about Gemini, agent workflows, developer tools, and platform strategy. It contains enough meaningful sentences for validation."}]}\n',
        encoding="utf-8",
    )
    (report_dir / "transcripts.txt").write_text("raw\n", encoding="utf-8")
    (report_dir / "transcripts-cleaned.txt").write_text("clean\n", encoding="utf-8")
    result = ns["validate_ai_influence_planned_report_dir"](report_dir)
    assert result["status"] == "error"
    assert "raw_video_id_leaked:SSe1VmVrtw0" in result["errors"]


def test_ai_influence_validation_accepts_hardened_report_with_project_archive(tmp_path):
    ns = _load_namespace()
    report_dir = tmp_path / "report"
    request_dir = tmp_path / "browser-request"
    report_dir.mkdir()
    request_dir.mkdir()
    (request_dir / "project-archive-result.json").write_text(
        '{"status":"ok","project_name":"杂项"}\n',
        encoding="utf-8",
    )
    complete_md = """# 测试报告

## 一页结论
本节素材：V001《测试视频》。这是结论。

## 核心趋势
### 趋势一
判断。

## 关键视频证据
- V001《测试视频》

## 产品 / 研究 / 工程启示
启示。

## Open Questions
- 待验证。

## Provenance
- final_reasoner: chatgpt-5.5
- local_preprocess: ThunderOMLX/Qwen3.6 semantic packets
- input_videos: 1
"""
    (report_dir / "report.md").write_text(complete_md, encoding="utf-8")
    (report_dir / "report.html").write_text(
        "章节与视频素材对应表 <span class='ai-material-ref'>V001</span> <span class='ai-material-chip'>测试视频</span>",
        encoding="utf-8",
    )
    (report_dir / "report-result.json").write_text(
        '{"request_dir": "%s"}\n' % str(request_dir),
        encoding="utf-8",
    )
    (report_dir / "evidence-pack.json").write_text(
        '{"videos":[{"video_ref":"V001","video_id":"SSe1VmVrtw0","title":"测试视频","channel":"Google for Developers","transcript_clean":"This is a clean English transcript about Gemini, agent workflows, developer tools, and platform strategy. It contains enough meaningful sentences for validation."}]}\n',
        encoding="utf-8",
    )
    (report_dir / "transcripts.txt").write_text("raw\n", encoding="utf-8")
    (report_dir / "transcripts-cleaned.txt").write_text("clean\n", encoding="utf-8")
    result = ns["validate_ai_influence_planned_report_dir"](
        report_dir,
        expected_chatgpt_project="杂项",
        require_project_archive=True,
    )
    assert result["status"] == "ok"
    assert result["errors"] == []


def test_ai_influence_validation_rejects_bad_transcript_in_evidence_pack(tmp_path):
    ns = _load_namespace()
    report_dir = tmp_path / "report"
    request_dir = tmp_path / "browser-request"
    report_dir.mkdir()
    request_dir.mkdir()
    (request_dir / "project-archive-result.json").write_text(
        '{"status":"ok","project_name":"杂项"}\n',
        encoding="utf-8",
    )
    complete_md = """# 测试报告

## 一页结论
本节素材：V001《测试视频》。这是结论。

## 核心趋势
### 趋势一
判断。

## 关键视频证据
- V001《测试视频》

## 产品 / 研究 / 工程启示
启示。

## Open Questions
- 待验证。

## Provenance
- final_reasoner: chatgpt-5.5
- local_preprocess: ThunderOMLX/Qwen3.6 semantic packets
- input_videos: 1
"""
    (report_dir / "report.md").write_text(complete_md, encoding="utf-8")
    (report_dir / "report.html").write_text(
        "章节与视频素材对应表 <span class='ai-material-ref'>V001</span> <span class='ai-material-chip'>测试视频</span>",
        encoding="utf-8",
    )
    (report_dir / "report-result.json").write_text(
        '{"request_dir": "%s"}\n' % str(request_dir),
        encoding="utf-8",
    )
    bad = "我叫Page\n研究\n研究\n机构\n互相\n针钛 针钛\n" * 80
    (report_dir / "evidence-pack.json").write_text(
        '{"videos":[{"video_ref":"V001","video_id":"ns9f1fjLD7Y","title":"Prompt to Pipeline","channel":"AI Engineer","transcript_clean":%s}]}\n'
        % __import__("json").dumps(bad, ensure_ascii=False),
        encoding="utf-8",
    )
    (report_dir / "transcripts.txt").write_text("raw\n", encoding="utf-8")
    (report_dir / "transcripts-cleaned.txt").write_text("clean\n", encoding="utf-8")
    result = ns["validate_ai_influence_planned_report_dir"](
        report_dir,
        expected_chatgpt_project="杂项",
        require_project_archive=True,
    )
    assert result["status"] == "error"
    assert any("bad_transcript_in_evidence_pack" in err for err in result["errors"])


def test_cleanup_transcript_cache_removes_nested_week_files(tmp_path):
    ns = _load_namespace()
    state_dir = tmp_path / "state"
    week_dir = state_dir / "transcripts" / "2026-W19"
    week_dir.mkdir(parents=True, exist_ok=True)
    old_txt = week_dir / "old.txt"
    old_txt.write_text("stale\n", encoding="utf-8")
    stale_ts = 1_700_000_000
    os.utime(old_txt, (stale_ts, stale_ts))
    config = {
        "output": {
            "state_dir": str(state_dir),
            "database": str(tmp_path / "missing.sqlite"),
            "retention_days": 1,
        }
    }
    removed = ns["cleanup_transcript_cache"](config)
    assert removed == 1
    assert old_txt.exists() is False
