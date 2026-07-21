import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.hierarchy import build_hierarchy  # noqa: E402


def test_hierarchy_shape_is_trend_chapter_subsection_evidence_refs() -> None:
    hierarchy = build_hierarchy(
        {
            "items": [
                {"group_type": "keynote", "transcript_grade": "T1", "evidence_ref": "E1"},
                {"group_type": "keynote", "transcript_grade": "T3", "evidence_ref": "E_BAD"},
            ]
        }
    )

    trend = hierarchy["trends"][0]
    chapter = trend["chapters"][0]
    subsection = chapter["subsections"][0]
    assert subsection["evidence_refs"] == ["E1"]
    assert "E_BAD" not in subsection["evidence_refs"]
