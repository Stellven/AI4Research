"""Test models — 5 unified dataclasses round-trip + DDL."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.models import (
    ASSET_TYPES,
    GitHubEvidencePacket,
    OutputAsset,
    RepoCanonical,
    RepoEnrichment,
    RepoSignal,
    RepoSnapshot,
    apply_schema,
    utc_now_iso,
    _gen_id,
    _json_dump,
    _json_load,
    SCHEMA_VERSION,
)


def test_schema_version():
    assert SCHEMA_VERSION == "code_signal.v1"


def test_utc_now_iso_format():
    ts = utc_now_iso()
    assert ts.endswith("Z")
    assert "T" in ts


def test_gen_id_prefix():
    sid = _gen_id("snap-")
    assert sid.startswith("snap-")
    assert len(sid) > 10


def test_json_round_trip():
    data = {"a": [1, 2], "b": "hello"}
    dumped = _json_dump(data)
    assert isinstance(dumped, str)
    assert _json_load(dumped) == data


def test_repo_snapshot_defaults():
    s = RepoSnapshot()
    assert s.snapshot_id.startswith("snap-")
    assert s.repo_key == ""
    assert _json_load(s.topics_json) == []


def test_repo_snapshot_to_from_row():
    s = RepoSnapshot(repo_key="owner/repo", stars=100, source="trending")
    row = s.to_row()
    s2 = RepoSnapshot.from_row(row)
    assert s2.repo_key == "owner/repo"
    assert s2.stars == 100


def test_repo_canonical_round_trip():
    c = RepoCanonical(repo_key="owner/repo", owner="owner")
    row = c.to_row()
    c2 = RepoCanonical.from_row(row)
    assert c2.repo_key == "owner/repo"
    assert c2.owner == "owner"


def test_repo_enrichment_round_trip():
    e = RepoEnrichment(repo_key="owner/repo", readme_compressed="A project")
    row = e.to_row()
    e2 = RepoEnrichment.from_row(row)
    assert e2.repo_key == "owner/repo"
    assert e2.readme_compressed == "A project"


def test_repo_signal_noise_filter():
    s = RepoSignal(noise_risk=0.7)
    assert s.is_noise_filtered()
    s2 = RepoSignal(noise_risk=0.3)
    assert not s2.is_noise_filtered()


def test_evidence_packet_validate():
    p = GitHubEvidencePacket(repo_key="owner/repo", evidence_refs_json='["ev-123"]')
    p.validate_evidence_refs()  # should not raise


def test_evidence_packet_validate_empty():
    p = GitHubEvidencePacket(repo_key="owner/repo", evidence_refs_json="[]")
    try:
        p.validate_evidence_refs()
        assert False, "Should have raised"
    except ValueError:
        pass


def test_output_asset_validate_evidence():
    a = OutputAsset(asset_type="github_hotspot_card", evidence_refs_json='["ev-1"]')
    a.validate_evidence_refs()  # ok


def test_output_asset_validate_empty():
    a = OutputAsset(asset_type="github_hotspot_card", evidence_refs_json="[]")
    try:
        a.validate_evidence_refs()
        assert False, "Should have raised"
    except ValueError:
        pass


def test_apply_schema():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    assert "cs_repo_snapshots" in tables
    assert "cs_repo_canonicals" in tables
    assert "cs_repo_enrichments" in tables
    assert "cs_repo_signals" in tables
    assert "cs_github_evidence_packets" in tables
    assert "cs_output_assets" in tables
    conn.close()


def test_insert_and_query_snapshot():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    s = RepoSnapshot(repo_key="test/repo", stars=500)
    row = s.to_row()
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO cs_repo_snapshots ({cols}) VALUES ({placeholders})", list(row.values()))
    conn.commit()
    cur = conn.execute("SELECT repo_key, stars FROM cs_repo_snapshots WHERE repo_key = ?", ("test/repo",))
    r = cur.fetchone()
    assert r == ("test/repo", 500)
    conn.close()


def test_asset_types_constant():
    assert len(ASSET_TYPES) == 7
    assert "github_hotspot_card" in ASSET_TYPES
    assert "action_queue" in ASSET_TYPES
