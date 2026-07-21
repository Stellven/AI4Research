import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from youtube.cross_source_extractor import extract_cross_source


def test_cross_source_extractor_finds_entities_and_links():
    result = extract_cross_source(
        "OpenAI discussed KV cache in openai/triton and cited arXiv:2501.01234 for GPT-4.",
        source_kind="youtube_segment",
        source_id="seg-1",
    )
    assert "repo" in result.entities
    assert "paper" in result.entities
    assert any(link["target_type"] == "github_repo" for link in result.links)
    assert result.recall_estimate > 0
