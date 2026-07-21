import pytest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.compat import (  # noqa: E402
    TranscriptStatusDriftError,
    compat_adapter_v1,
)


def test_compat_adapter_normalizes_legacy_aliases() -> None:
    row = compat_adapter_v1(
        {
            "id": "video-1",
            "grade": "T1",
            "technical_term_hit_rate": 0.8,
            "word_error_rate": 0.2,
            "segments_per_minute": 0.6,
            "version": "legacy",
        }
    )

    assert row["schema_version"] == "transcript_status_compat.v1"
    assert row["video_id"] == "video-1"
    assert row["quality_tier"] == "T1"
    assert row["source_schema_version"] == "legacy"


def test_compat_adapter_reports_drift_instead_of_silent_fallback() -> None:
    with pytest.raises(TranscriptStatusDriftError, match="entity_recall"):
        compat_adapter_v1(
            {
                "video_id": "video-1",
                "quality_tier": "T1",
                "wer": 0.2,
                "segment_density": 0.6,
            }
        )
