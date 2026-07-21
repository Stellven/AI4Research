"""Test G1 — GitHubCandidateDiscoveryOperator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.discovery import GitHubCandidateDiscoveryOperator
from github_intelligence.code_signal.models import RepoSnapshot


def test_empty_inputs():
    op = GitHubCandidateDiscoveryOperator()
    result = op.run()
    assert result == []


def test_trending_source():
    op = GitHubCandidateDiscoveryOperator()
    trending = [
        {"full_name": "test/hot", "stars": 5000},
        {"full_name": "test/warm", "stars": 500},
    ]
    result = op.run(trending=trending)
    assert len(result) == 2
    assert all(isinstance(s, RepoSnapshot) for s in result)
    assert result[0].source == "trending"
    assert result[0].stars == 5000


def test_dedup_across_sources():
    op = GitHubCandidateDiscoveryOperator()
    trending = [{"full_name": "test/repo", "stars": 100}]
    tracked = [{"full_name": "test/repo", "stars": 200}]
    result = op.run(trending=trending, tracked=tracked)
    assert len(result) == 1
    assert result[0].source == "trending"


def test_skips_empty_repo_key():
    op = GitHubCandidateDiscoveryOperator()
    items = [{"full_name": "", "stars": 100}, {"full_name": "test/valid"}]
    result = op.run(trending=items)
    assert len(result) == 1
    assert result[0].repo_key == "test/valid"


def test_discovery_provenance():
    op = GitHubCandidateDiscoveryOperator()
    result = op.run(trending=[{"full_name": "a/b"}])
    import json
    prov = json.loads(result[0].discovery_provenance_json)
    assert prov["source"] == "trending"


def test_all_four_sources():
    op = GitHubCandidateDiscoveryOperator()
    r = op.run(
        trending=[{"full_name": "a/1"}],
        search_results=[{"full_name": "a/2"}],
        tracked=[{"full_name": "a/3"}],
        mention_seeds=[{"full_name": "a/4"}],
    )
    assert len(r) == 4
    sources = {s.source for s in r}
    assert sources == {"trending", "search", "tracked", "social_mention"}
