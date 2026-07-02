from __future__ import annotations

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[3]
PLUGIN = HARNESS / "plugins" / "autosci"
sys.path.insert(0, str(PLUGIN))

from backends import literature_discover  # noqa: E402


def test_from_wiki_uses_recent_arxiv_anchors_and_honors_limit(monkeypatch, tmp_path: Path) -> None:
    wiki = tmp_path / "artifacts" / "autosci" / "workspace" / "wiki"
    paper_dir = wiki / "papers"
    paper_dir.mkdir(parents=True)
    paper_dir.joinpath("seed.md").write_text(
        "---\ntitle: Seed Paper\narxiv: 2401.00001\n---\n# Seed Paper\n",
        encoding="utf-8",
    )

    def fake_recommend(positive_ids, negative_ids, limit):
        assert positive_ids == ["2401.00001"]
        return [
            {
                "paperId": "s2-a",
                "title": "First New Candidate",
                "abstract": "Skill synthesis and agent learning.",
                "externalIds": {"ArXiv": "2401.00002"},
                "citationCount": 25,
                "year": 2025,
                "url": "https://example.test/a",
            },
            {
                "paperId": "s2-b",
                "title": "Second New Candidate",
                "abstract": "Agent skill discovery.",
                "externalIds": {"ArXiv": "2401.00003"},
                "citationCount": 5,
                "year": 2024,
                "url": "https://example.test/b",
            },
        ]

    monkeypatch.setattr(literature_discover, "_s2_recommend", fake_recommend)
    monkeypatch.setattr(literature_discover, "_s2_references", lambda arxiv_id, limit: [])
    monkeypatch.setattr(literature_discover, "_s2_citations", lambda arxiv_id, limit: [])
    result = literature_discover.discover_literature(
        mode="wiki",
        limit=1,
        wiki_root=wiki,
        workspace_root=tmp_path,
        repository_root=HARNESS,
    )
    assert result["status"] == "completed"
    assert result["mode"] == "wiki"
    assert result["anchors"] == ["2401.00001"]
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["candidate_id"] == "arxiv:2401.00002"
    assert candidate["source_channels"] == ["recommend"]
    assert candidate["dedup_status"] == "new"


def test_from_wiki_without_network_returns_inconclusive_not_fixture(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    paper_dir = wiki / "papers"
    paper_dir.mkdir(parents=True)
    paper_dir.joinpath("seed.md").write_text(
        "---\ntitle: Seed Paper\narxiv_id: 2401.00001\n---\n",
        encoding="utf-8",
    )
    result = literature_discover.discover_literature(
        mode="wiki",
        limit=10,
        wiki_root=wiki,
        workspace_root=tmp_path,
        repository_root=HARNESS,
        allow_network_fetch=False,
    )
    assert result["status"] == "inconclusive"
    assert result["candidates"] == []
    assert "fixture" not in " ".join(result["limitations"]).lower()
