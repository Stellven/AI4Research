import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.render import render_report_html  # noqa: E402


def test_render_report_html_embeds_inline_svg_and_sources() -> None:
    html = render_report_html(
        "正文",
        {
            "entries": [
                {
                    "channel": "AI Engineer",
                    "title": "Agent Platforms",
                    "published_at": "2026-05-25T00:00:00Z",
                    "transcript_grade": "T1",
                    "citation_span": "agent runtime",
                }
            ]
        },
        {"title": "测试报告"},
    )

    assert "<svg" in html
    assert "AI Engineer" in html
    assert "video_id" not in html
