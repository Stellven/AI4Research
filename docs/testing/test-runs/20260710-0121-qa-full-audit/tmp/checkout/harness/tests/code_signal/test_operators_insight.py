"""Test G5 — GitHubHotspotInsightOperator."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.insight import GitHubHotspotInsightOperator
from github_intelligence.code_signal.models import GitHubEvidencePacket, OutputAsset, ASSET_TYPES


def _pkt(repo_key="test/repo"):
    return GitHubEvidencePacket(
        repo_key=repo_key,
        evidence_refs_json='["ev-1", "ev-2"]',
        questions_for_high_model_json='["What is X?"]',
    )


def test_produces_7_asset_types():
    op = GitHubHotspotInsightOperator()
    assets = op.run([_pkt()])
    assert len(assets) == 7
    types = {a.asset_type for a in assets}
    assert types == set(ASSET_TYPES)


def test_each_asset_has_evidence_refs():
    op = GitHubHotspotInsightOperator()
    assets = op.run([_pkt()])
    for a in assets:
        refs = json.loads(a.evidence_refs_json)
        assert len(refs) >= 1, f"{a.asset_type} has no evidence_refs"


def test_each_asset_validates():
    op = GitHubHotspotInsightOperator()
    assets = op.run([_pkt()])
    for a in assets:
        a.validate_evidence_refs()  # should not raise


def test_rejects_non_packet():
    op = GitHubHotspotInsightOperator()
    try:
        op.run([{"not": "a packet"}])
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "GitHubEvidencePacket" in str(e)


def test_empty_packets():
    op = GitHubHotspotInsightOperator()
    assets = op.run([])
    assert assets == []


def test_multiple_packets():
    op = GitHubHotspotInsightOperator()
    pkts = [_pkt("a/1"), _pkt("b/2")]
    assets = op.run(pkts)
    assert len(assets) == 14  # 7 per packet
    repos = {a.repo_key for a in assets}
    assert repos == {"a/1", "b/2"}
