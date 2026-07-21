"""Test evidence_refs required — every output asset MUST carry evidence_refs.

Stop rule: Missing evidence_refs on any compiler-emitted claim → evaluator FAIL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.models import (
    ASSET_TYPES,
    GitHubEvidencePacket,
    OutputAsset,
    _gen_id,
    _json_dump,
    utc_now_iso,
)
from github_intelligence.code_signal.operators.insight import GitHubHotspotInsightOperator


def test_output_asset_empty_refs_raises():
    a = OutputAsset(asset_type="github_hotspot_card", evidence_refs_json="[]")
    try:
        a.validate_evidence_refs()
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "evidence_refs" in str(e)


def test_output_asset_with_refs_ok():
    a = OutputAsset(asset_type="github_hotspot_card", evidence_refs_json='["ev-1"]')
    a.validate_evidence_refs()  # no raise


def test_packet_empty_refs_raises():
    p = GitHubEvidencePacket(repo_key="test/repo", evidence_refs_json="[]")
    try:
        p.validate_evidence_refs()
        assert False
    except ValueError:
        pass


def test_insight_operator_produces_refs():
    op = GitHubHotspotInsightOperator()
    pkt = GitHubEvidencePacket(
        repo_key="test/repo",
        evidence_refs_json='["ev-1", "ev-2"]',
        questions_for_high_model_json='["Q1"]',
    )
    assets = op.run([pkt])
    for a in assets:
        refs = json.loads(a.evidence_refs_json)
        assert len(refs) >= 1, f"{a.asset_type} missing evidence_refs"


def test_all_asset_types_produced():
    op = GitHubHotspotInsightOperator()
    pkt = GitHubEvidencePacket(
        repo_key="test/repo",
        evidence_refs_json='["ev-1"]',
    )
    assets = op.run([pkt])
    types = {a.asset_type for a in assets}
    assert types == set(ASSET_TYPES)
