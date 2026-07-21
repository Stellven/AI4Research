from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import youtube_influence_digest as yid


def _base_meta() -> dict[str, str]:
    return {
        "video_id": "abc123xyz00",
        "channel_id": "chan1",
        "channel_name": "Demo Channel",
        "category": "AI / Tech",
        "priority": "tier1",
        "title": "Build an AI agent demo with tools",
        "url": "https://www.youtube.com/watch?v=abc123xyz00",
        "published_at": "2026-05-30T10:00:00Z",
        "fetched_at": "2026-05-30T11:00:00Z",
        "source": "fixture:feed",
    }


def test_assess_transcript_quality_marks_short_text_t3():
    result = yid.assess_transcript_quality(
        meta=_base_meta(),
        transcript="bad",
        status="ok_asr",
        source="browser_agent_operator:abc123xyz00",
        config={"analysis_keywords": {"agent": ["agent", "tools"]}},
    )
    assert result["tier"] == "T3"
    assert result["status"] == "degraded"


def test_render_transcript_for_report_hides_t3_body():
    video = yid.build_video(
        _base_meta(),
        "bad",
        "ok_asr",
        "browser_agent_operator:abc123xyz00",
        {"analysis_keywords": {"agent": ["agent", "tools"]}},
    )
    rendered = yid.render_transcript_for_report(video)
    assert "质量门禁判定为 `T3`" in rendered
