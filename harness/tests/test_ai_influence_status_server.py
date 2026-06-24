from __future__ import annotations

import datetime
import importlib.util
import json
import sqlite3
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATUS_SERVER = _REPO_ROOT / "harness/lib/symphony/status-server.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_test", str(_STATUS_SERVER))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ai_influence_payload_discovers_all_report_kinds(tmp_path, monkeypatch):
    mod = _load_module()
    legacy_root = tmp_path / "legacy-ai-influence"
    hotspot_root = tmp_path / "tech-hotspot-radar"
    # Today-relative dates so the fixture stays inside the default 30-day discovery window
    # (_ai_influence_period_cutoff defaults to "30d"). Hardcoded calendar dates made this a
    # time-bomb: the older report silently aged past the cutoff once real time advanced, dropping
    # its kind from discovery and failing the count assertion on a date unrelated to any code change.
    recent = datetime.date.today().isoformat()
    older = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    legacy_run = legacy_root / recent
    planned_report = hotspot_root / "ai-influence-planned" / recent / "reports" / "planned-one"
    unified_run = hotspot_root / recent
    phase_run = hotspot_root / "phase-2" / older

    for path in [legacy_run, planned_report, unified_run, phase_run]:
        path.mkdir(parents=True, exist_ok=True)

    (legacy_run / "digest.md").write_text("# digest\n", encoding="utf-8")
    (legacy_run / "digest.html").write_text("<html>digest</html>", encoding="utf-8")
    (legacy_run / "digest.json").write_text(json.dumps({"date": recent, "stats": {"top_scored": 3}, "items": [1, 2]}, ensure_ascii=False), encoding="utf-8")

    (planned_report / "report.html").write_text("<html>planned</html>", encoding="utf-8")
    (planned_report / "report.md").write_text("# planned\n", encoding="utf-8")
    (planned_report / "report-result.json").write_text(json.dumps({"headline": "专题报告 A", "_model": "chatgpt-5.5", "_reasoning_effort": "high"}, ensure_ascii=False), encoding="utf-8")
    (planned_report / "evidence-pack.json").write_text(json.dumps({"videos": [{"title": "v1"}, {"title": "v2"}]}, ensure_ascii=False), encoding="utf-8")

    (unified_run / "report.html").write_text("<html>unified</html>", encoding="utf-8")
    (unified_run / "unified-overview.md").write_text("# unified\n", encoding="utf-8")
    (unified_run / f"youtube-transcripts-{recent}.txt").write_text("tx", encoding="utf-8")

    (phase_run / "report.html").write_text("<html>phase</html>", encoding="utf-8")
    (phase_run / "phase-report.md").write_text("# phase\n", encoding="utf-8")
    (phase_run / "phase-report.json").write_text(json.dumps({"headline": "Phase 2 报告", "_input_video_count": 5, "_model": "chatgpt-5.5"}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(mod, "AI_INFLUENCE_RAW_DIR", legacy_root)
    monkeypatch.setattr(mod, "HUGGINGFACE_PAPERS_RAW_DIR", tmp_path / "huggingface-papers")
    monkeypatch.setattr(mod, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(mod, "_tech_hotspot_raw_dir", lambda: hotspot_root)

    payload = mod._ai_influence_payload(limit=20)

    assert payload["count"] == 4
    labels = {item["module_label"] for item in payload["items"]}
    assert {"日度洞察", "大咖访谈及大展洞察报告", "统一日报", "Phase 2"} <= labels
    assert payload["module_counts"]["大咖访谈及大展洞察报告"] == 1
    assert "raw_dir" not in payload
    assert "legacy_raw_dir" not in payload
    assert all("report_dir" not in item for item in payload["items"])


def test_save_ai_influence_mail_config(tmp_path, monkeypatch):
    mod = _load_module()
    config_path = tmp_path / "ai-influence-mail-config.json"
    monkeypatch.setattr(mod, "AI_INFLUENCE_MAIL_CONFIG", config_path)

    result = mod._save_ai_influence_mail_config({"to": "a@example.com,b@example.com"})

    assert result["ok"] is True
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["to"] == "a@example.com,b@example.com"
    assert "updated_at" in saved


def test_ai_influence_html_splits_reports_and_resources_tabs(tmp_path, monkeypatch):
    mod = _load_module()
    legacy_root = tmp_path / "legacy-ai-influence"
    hotspot_root = tmp_path / "tech-hotspot-radar"
    planned_report = hotspot_root / "ai-influence-planned" / "2026-05-26" / "reports" / "planned-one"
    planned_report.mkdir(parents=True, exist_ok=True)

    (planned_report / "report.html").write_text("<html>planned</html>", encoding="utf-8")
    (planned_report / "report.md").write_text("# planned\n", encoding="utf-8")
    (planned_report / "transcripts.txt").write_text("transcript body", encoding="utf-8")
    (planned_report / "report-result.json").write_text(
        json.dumps(
            {
                "headline": "专题报告 A",
                "_model": "chatgpt-5.5",
                "_reasoning_effort": "high",
                "topic_tags": ["Gemini", "Agent"],
                "evidence_manifest": {
                    "videos": [
                        {
                            "channel": "Google",
                            "title": "What's new in Google AI",
                            "published_at": "2026-05-22T20:45:00Z",
                            "summary": "Gemini 平台更新摘要",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (planned_report / "evidence-pack.json").write_text(
        json.dumps({"videos": [{"title": "What's new in Google AI"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "AI_INFLUENCE_RAW_DIR", legacy_root)
    monkeypatch.setattr(mod, "HUGGINGFACE_PAPERS_RAW_DIR", tmp_path / "huggingface-papers")
    monkeypatch.setattr(mod, "_tech_hotspot_raw_dir", lambda: hotspot_root)

    html = mod._ai_influence_html(period="30d")

    assert "报告汇总" in html
    assert "素材资源" in html
    assert "id=\"tab-reports\"" in html
    assert "id=\"tab-resources\"" in html
    assert "2 份专题报告" not in html
    assert "1 份专题报告" in html
    assert "全部主题" in html
    assert "全部技术" in html
    assert "全部频道 / 账号" in html
    assert "素材 / 下载" in html
    assert "transcripts.txt" in html
    assert "/ai-influence/transcript?id=" in html
    assert str(planned_report) not in html
    assert "/file/view?path=" not in html
    assert "排序方式" in html
    assert "只看未发送" in html
    assert "按频道折叠" in html
    assert "全部报告" in html
    assert "active-chips" in html
    assert "active-chips" in html
    assert "group-send-btn" in html
    assert "/ai-influence/youtube-videos" in html


def test_ai_influence_html_has_month_tab_and_module_tab(tmp_path, monkeypatch):
    mod = _load_module()
    hotspot_root = tmp_path / "tech-hotspot-radar"
    planned_root = hotspot_root / "ai-influence-planned"

    def _build_planned_report(report_day: str, idx: int, headline: str) -> None:
        planned_report = planned_root / report_day / "reports" / f"planned-{idx}"
        planned_report.mkdir(parents=True, exist_ok=True)
        (planned_report / "report.html").write_text("<html>planned</html>", encoding="utf-8")
        (planned_report / "report.md").write_text(f"# planned {idx}\n", encoding="utf-8")
        (planned_report / "report-result.json").write_text(
            json.dumps(
                {"headline": headline, "_model": "chatgpt-5.5", "_reasoning_effort": "high"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (planned_report / "evidence-pack.json").write_text(json.dumps({"videos": []}, ensure_ascii=False), encoding="utf-8")

    _build_planned_report("2026-05-10", 1, "五月报告")
    _build_planned_report("2026-04-11", 2, "四月报告")

    monkeypatch.setattr(mod, "AI_INFLUENCE_RAW_DIR", tmp_path / "legacy-ai-influence")
    monkeypatch.setattr(mod, "HUGGINGFACE_PAPERS_RAW_DIR", tmp_path / "huggingface-papers")
    monkeypatch.setattr(mod, "_tech_hotspot_raw_dir", lambda: hotspot_root)

    html = mod._ai_influence_html(period="all")

    assert "月份" in html
    assert "全部月份" in html
    assert "2026-05" in html
    assert "2026-04" in html
    assert 'class="module-tabs"' in html
    assert 'data-month="2026-05"' in html


def test_ai_influence_payload_month_filter(tmp_path, monkeypatch):
    mod = _load_module()
    hotspot_root = tmp_path / "tech-hotspot-radar"
    planned_root = hotspot_root / "ai-influence-planned"

    def _build_planned_report(report_day: str, idx: int, headline: str) -> None:
        planned_report = planned_root / report_day / "reports" / f"planned-{idx}"
        planned_report.mkdir(parents=True, exist_ok=True)
        (planned_report / "report.html").write_text("<html>planned</html>", encoding="utf-8")
        (planned_report / "report.md").write_text(f"# planned {idx}\n", encoding="utf-8")
        (planned_report / "report-result.json").write_text(
            json.dumps(
                {"headline": headline, "_model": "chatgpt-5.5", "_reasoning_effort": "high"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (planned_report / "evidence-pack.json").write_text(json.dumps({"videos": []}, ensure_ascii=False), encoding="utf-8")

    _build_planned_report("2026-05-10", 1, "五月报告")
    _build_planned_report("2026-04-11", 2, "四月报告")

    monkeypatch.setattr(mod, "AI_INFLUENCE_RAW_DIR", tmp_path / "legacy-ai-influence")
    monkeypatch.setattr(mod, "HUGGINGFACE_PAPERS_RAW_DIR", tmp_path / "huggingface-papers")
    monkeypatch.setattr(mod, "_tech_hotspot_raw_dir", lambda: hotspot_root)

    all_payload = mod._ai_influence_payload(period="all")
    month_payload = mod._ai_influence_payload(period="all", month="2026-05")

    assert all_payload["count"] == 2
    assert month_payload["count"] == 1
    assert month_payload["filters_applied"]["month"] == "2026-05"
    assert "2026-05" in month_payload["filter_options"]["months"]
    assert month_payload["items"][0]["month"] == "2026-05"


def test_ai_influence_youtube_video_library_payload_and_archive(tmp_path, monkeypatch):
    mod = _load_module()
    db_path = tmp_path / "tech-hotspot-radar.sqlite"
    archive_path = tmp_path / "youtube-video-archive.json"
    youtube_config_path = tmp_path / "youtube-influence-digest.yaml"
    youtube_config_path.write_text(
        """
channels:
  - name: AI Engineer
    url: https://www.youtube.com/@aiDotEngineer
    category: AI / Tech
    priority: tier1
""".strip(),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE youtube_videos (
              video_id TEXT PRIMARY KEY,
              channel_name TEXT,
              video_url TEXT,
              title TEXT,
              description TEXT,
              published_at TEXT,
              duration_seconds REAL,
              thumbnail_url TEXT,
              view_count INTEGER,
              like_count INTEGER,
              comment_count INTEGER,
              tags TEXT
            );
            CREATE TABLE youtube_transcripts (
              video_id TEXT PRIMARY KEY,
              quality_tier TEXT,
              quality_score REAL,
              source TEXT,
              transcript_status TEXT,
              transcript_clean TEXT,
              transcript_raw TEXT
            );
            CREATE TABLE evidence_atoms (
              evidence_id TEXT,
              source TEXT,
              source_id TEXT,
              source_table TEXT,
              atom_type TEXT,
              content TEXT,
              metadata_json TEXT,
              importance_score REAL,
              novelty_score REAL,
              technical_depth REAL,
              source_weight REAL,
              created_at TEXT,
              model_used TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO youtube_videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "abc123",
                "AI Engineer",
                "https://www.youtube.com/watch?v=abc123",
                "Agent Runtime Talk",
                "A detailed agent runtime discussion",
                "2026-06-03T12:00:00Z",
                600,
                "",
                100,
                10,
                2,
                '["Agent","MCP"]',
            ),
        )
        conn.execute(
            "INSERT INTO youtube_videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "stan123",
                "Stanford Online",
                "https://www.youtube.com/watch?v=stan123",
                "Research Seminar on Agents",
                "A university seminar about agent evaluation",
                "2026-06-02T12:00:00Z",
                1800,
                "",
                80,
                8,
                1,
                '["Agent","Eval"]',
            ),
        )
        conn.execute(
            "INSERT INTO youtube_videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "nop123",
                "No Priors",
                "https://www.youtube.com/watch?v=nop123",
                "Founder Interview on AI Agents",
                "A high-impact interview about agent products",
                "2026-06-04T12:00:00Z",
                2400,
                "",
                100000,
                3000,
                400,
                '["Agent","Founder"]',
            ),
        )
        conn.execute(
            "INSERT INTO youtube_transcripts VALUES (?,?,?,?,?,?,?)",
            ("abc123", "T1", 0.86, "youtube_auto_caption", "succeeded", "transcript body", ""),
        )
        conn.execute(
            "INSERT INTO youtube_transcripts VALUES (?,?,?,?,?,?,?)",
            ("stan123", "T1", 0.82, "standard_caption", "succeeded", "stanford transcript", ""),
        )
        conn.execute(
            "INSERT INTO youtube_transcripts VALUES (?,?,?,?,?,?,?)",
            ("nop123", "T1", 0.9, "youtube_auto_caption", "succeeded", "no priors transcript", ""),
        )
        conn.execute(
            "INSERT INTO evidence_atoms VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ev1", "youtube", "abc123", "youtube_videos", "summary", "Agent runtime 摘要", "{}", 0.9, 0, 0, 1, "2026-06-03", "local"),
        )
        conn.execute(
            "INSERT INTO evidence_atoms VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ev2", "youtube", "stan123", "youtube_videos", "summary", "学术研讨摘要", "{}", 0.9, 0, 0, 1, "2026-06-02", "local"),
        )
        conn.execute(
            "INSERT INTO evidence_atoms VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ev3", "youtube", "nop123", "youtube_videos", "summary", "高影响力访谈摘要", "{}", 0.95, 0, 0, 1, "2026-06-04", "local"),
        )

    monkeypatch.setattr(mod, "TECH_HOTSPOT_DB", db_path)
    monkeypatch.setattr(mod, "AI_INFLUENCE_YOUTUBE_VIDEO_ARCHIVE", archive_path)
    monkeypatch.setattr(mod, "YOUTUBE_DIGEST_CONFIG", youtube_config_path)

    payload = mod._ai_influence_youtube_videos_payload(period="all")

    assert payload["ok"] is True
    assert payload["count"] == 3
    assert payload["groups"][0]["channel"] == "No Priors"
    assert payload["groups"][0]["influence_score"] > payload["groups"][1]["influence_score"]
    assert payload["channel_sections"][0]["label"] == "大V/访谈频道"
    assert payload["channel_sections"][0]["channels"][0]["channel"] == "No Priors"
    assert payload["channel_sections"][0]["channels"][1]["channel"] == "AI Engineer"
    assert payload["channel_sections"][1]["label"] == "学术/机构频道"
    assert payload["channel_sections"][1]["channels"][0]["channel"] == "Stanford Online"
    item = payload["items"][0]
    assert item["channel_type"] == "influencer"
    assert item["channel_type_label"] == "大V/访谈频道"
    assert item["thumbnail"].endswith("/abc123/hqdefault.jpg")
    assert item["summary"] == "Agent runtime 摘要"
    assert item["tags"] == ["Agent", "MCP"]

    html = mod._ai_influence_youtube_videos_html(period="all")
    assert "大V/访谈频道" in html
    assert "学术/机构频道" in html
    assert "type-influencer" in html
    assert "type-academic" in html
    assert "channel-tabs" in html
    assert "data-channel-tab" in html
    assert "data-channel-section hidden" in html
    assert "showChannelSection" in html
    assert "Channel Group" not in html
    assert "频道分组" in html
    assert "影响力" in html
    assert "推荐关注" in html
    assert "addRecommendedChannels" in html

    recommendations = mod._youtube_subscription_recommendations(limit=5)
    assert recommendations
    assert all(item["name"] != "AI Engineer" for item in recommendations)
    add_result = mod._append_youtube_recommended_subscriptions({"channels": [{"url": "https://www.youtube.com/@LatentSpacePod"}]})
    assert add_result["added"] == 1
    saved = mod._read_yaml_file(youtube_config_path)
    assert any(item.get("name") == "Latent Space" for item in saved["channels"])
    exists_result = mod._append_youtube_recommended_subscriptions({"channels": [{"url": "https://www.youtube.com/@LatentSpacePod"}]})
    assert exists_result["exists"] == 1

    result = mod._ai_influence_youtube_videos_archive({"video_ids": ["abc123"]})
    assert result["ok"] is True
    assert mod._ai_influence_youtube_videos_payload(period="all")["count"] == 2
    assert mod._ai_influence_youtube_videos_payload(period="all", include_archived=True)["count"] == 3


def test_ai_influence_transcript_view_resolves_planned_video(tmp_path, monkeypatch):
    mod = _load_module()
    hotspot_root = tmp_path / "tech-hotspot-radar"
    planned_report = hotspot_root / "ai-influence-planned" / "2026-05-26" / "reports" / "planned-one"
    planned_report.mkdir(parents=True, exist_ok=True)
    (planned_report / "report.html").write_text("<html>planned</html>", encoding="utf-8")
    (planned_report / "report-result.json").write_text(json.dumps({"headline": "专题报告 A"}, ensure_ascii=False), encoding="utf-8")
    (planned_report / "evidence-pack.json").write_text(
        json.dumps(
            {
                "videos": [
                    {
                        "video_ref": "V001",
                        "video_id": "abc123",
                        "channel": "AI Engineer",
                        "title": "Your Agent Is an Infinite Canvas",
                        "url": "https://www.youtube.com/watch?v=abc123",
                        "published_at": "2026-05-23T18:00:06Z",
                        "duration_min": 23.1,
                        "transcript_clean": "line 1\\nline 2",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_tech_hotspot_raw_dir", lambda: hotspot_root)

    item = mod._planned_report_item(planned_report)
    payload = mod._resolve_ai_influence_transcript(item["id"], "V001", "abc123")

    assert payload is not None
    assert payload["video"]["title"] == "Your Agent Is an Infinite Canvas"
    html = mod._ai_influence_transcript_html(payload["report_id"], payload["video"], payload["transcript"])
    assert "原始转写素材" in html
    assert "打开 YouTube 原视频" in html
    assert "line 1" in html
    assert str(planned_report) not in html


def test_ai_influence_report_resolves_by_public_id(tmp_path, monkeypatch):
    mod = _load_module()
    hotspot_root = tmp_path / "tech-hotspot-radar"
    planned_report = hotspot_root / "ai-influence-planned" / "2026-05-26" / "reports" / "planned-one"
    planned_report.mkdir(parents=True, exist_ok=True)
    (planned_report / "report.html").write_text("<html>planned</html>", encoding="utf-8")
    (planned_report / "report.md").write_text("# planned\n", encoding="utf-8")
    (planned_report / "report-result.json").write_text(json.dumps({"headline": "专题报告 A"}, ensure_ascii=False), encoding="utf-8")
    (planned_report / "evidence-pack.json").write_text(json.dumps({"videos": []}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(mod, "_tech_hotspot_raw_dir", lambda: hotspot_root)
    monkeypatch.setattr(mod, "_allowed_open_path", lambda _path: True)

    item = mod._planned_report_item(planned_report)
    target = mod._resolve_ai_influence_report(item["id"], "report_html")

    assert target == planned_report / "report.html"
