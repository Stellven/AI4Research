import pytest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.evidence_map import assert_reader_safe_mapping, build_evidence_map  # noqa: E402
from ai_influence_youtube_report.source_mapping import render_source_mapping_markdown  # noqa: E402


def test_evidence_map_excludes_t3_and_keeps_required_reader_fields() -> None:
    evidence = build_evidence_map(
        [
            {
                "evidence_ref": "E1",
                "channel": "AI Engineer",
                "title": "Agent Platforms",
                "published_at": "2026-05-25T00:00:00Z",
                "transcript_grade": "T1",
                "citation_span": "agents need runtime primitives",
                "group_type": "conference",
            },
            {
                "evidence_ref": "E2",
                "channel": "Bad ASR",
                "title": "Garbage",
                "published_at": "2026-05-25T00:00:00Z",
                "transcript_grade": "T3",
                "citation_span": "我我我",
                "group_type": "other",
            },
        ]
    )

    assert len(evidence["entries"]) == 1
    assert evidence["entries"][0]["evidence_ref"] == "E1"


def test_source_mapping_does_not_expose_internal_fields() -> None:
    with pytest.raises(ValueError, match="video_id"):
        assert_reader_safe_mapping({"channel": "x", "video_id": "abc"})

    rendered = render_source_mapping_markdown(
        {
            "channel": "AI Engineer",
            "title": "Agent Platforms",
            "published_at": "2026-05-25T00:00:00Z",
            "transcript_grade": "T2",
            "citation_span": "weak evidence",
        }
    )
    assert "video_id" not in rendered
    assert "weak" in rendered
