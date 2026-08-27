from __future__ import annotations

from pathlib import Path

from journey_runner import bootstrap_live_environment


def test_bootstrap_live_environment_propagates_semantic_scholar_key(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    harness.mkdir()
    harness.joinpath(".env").write_text(
        "SEMANTIC_SCHOLAR_API_KEY=opaque-test-key\n",
        encoding="utf-8",
    )

    result = bootstrap_live_environment(tmp_path, {})

    assert result["SEMANTIC_SCHOLAR_API_KEY"] == "opaque-test-key"
