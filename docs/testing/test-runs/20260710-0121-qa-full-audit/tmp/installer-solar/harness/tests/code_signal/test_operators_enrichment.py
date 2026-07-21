"""Test G2 — RepoEnrichmentOperator."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.enrichment import RepoEnrichmentOperator
from github_intelligence.code_signal.models import RepoSnapshot, RepoCanonical, RepoEnrichment


def _snap(repo_key="test/repo", **kw):
    return RepoSnapshot(repo_key=repo_key, **kw)


def test_empty_snapshots():
    op = RepoEnrichmentOperator()
    result = op.run([])
    assert result["canonicals"] == []
    assert result["enrichments"] == []


def test_basic_enrichment():
    op = RepoEnrichmentOperator()
    snaps = [_snap("owner/repo")]
    meta = {"owner/repo": {"stars": 1000, "readme": "A great project", "readme_tags": ["ai"]}}
    result = op.run(snaps, meta)
    assert len(result["canonicals"]) == 1
    assert len(result["enrichments"]) == 1
    assert result["canonicals"][0].repo_key == "owner/repo"
    assert result["canonicals"][0].owner == "owner"
    assert result["enrichments"][0].readme_compressed == "A great project"


def test_enrichment_evidence_ids():
    op = RepoEnrichmentOperator()
    snaps = [_snap("a/b")]
    meta = {"a/b": {"readme": "X", "latest_release": "v1.0"}}
    result = op.run(snaps, meta)
    ev_ids = json.loads(result["enrichments"][0].evidence_ids_json)
    assert len(ev_ids) == 2  # readme + release


def test_no_metadata():
    op = RepoEnrichmentOperator()
    snaps = [_snap("bare/repo")]
    result = op.run(snaps)
    assert len(result["canonicals"]) == 1
    assert result["enrichments"][0].readme_compressed is None


def test_filled_snapshot_carries_metadata():
    op = RepoEnrichmentOperator()
    snaps = [_snap("x/y")]
    meta = {"x/y": {"stars": 9000, "language": "Go"}}
    result = op.run(snaps, meta)
    filled = result["filled_snapshots"][0]
    assert filled.stars == 9000
    assert filled.language == "Go"


def test_multiple_repos():
    op = RepoEnrichmentOperator()
    snaps = [_snap("a/1"), _snap("b/2"), _snap("c/3")]
    result = op.run(snaps)
    assert len(result["canonicals"]) == 3
    assert len(result["enrichments"]) == 3
