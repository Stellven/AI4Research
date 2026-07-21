"""Test high-model input invariant — G5 MUST reject non-GitHubEvidencePacket inputs.

Invariant: high models may only consume GitHubEvidencePacket.
If raw dict/list reaches the insight operator, it MUST raise TypeError.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.insight import GitHubHotspotInsightOperator
from github_intelligence.code_signal.models import GitHubEvidencePacket


def test_rejects_raw_dict():
    op = GitHubHotspotInsightOperator()
    try:
        op.run([{"repo_key": "test/repo", "stars": 100}])
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_rejects_raw_list():
    op = GitHubHotspotInsightOperator()
    try:
        op.run([["repo1", "repo2"]])
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_rejects_string():
    op = GitHubHotspotInsightOperator()
    try:
        op.run(["just a string"])
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_accepts_valid_packet():
    op = GitHubHotspotInsightOperator()
    pkt = GitHubEvidencePacket(repo_key="test/repo", evidence_refs_json='["ev-1"]')
    assets = op.run([pkt])
    assert len(assets) == 7


def test_rejects_mixed_batch():
    op = GitHubHotspotInsightOperator()
    pkt = GitHubEvidencePacket(repo_key="test/repo", evidence_refs_json='["ev-1"]')
    try:
        op.run([pkt, {"bad": True}])
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
