"""Test G6 — GitHubKnowledgeStoreOperator."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.knowledge_store import GitHubKnowledgeStoreOperator
from github_intelligence.code_signal.models import (
    GitHubEvidencePacket, OutputAsset, RepoCanonical, RepoEnrichment, RepoSignal, RepoSnapshot,
)


def test_store_snapshots():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    snaps = [RepoSnapshot(repo_key="a/b", stars=100), RepoSnapshot(repo_key="c/d", stars=200)]
    count = store.store_snapshots(snaps)
    assert count == 2
    cur = store.conn.execute("SELECT COUNT(*) FROM cs_repo_snapshots")
    assert cur.fetchone()[0] == 2


def test_store_canonicals():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    cans = [RepoCanonical(repo_key="a/b", owner="a")]
    store.store_canonicals(cans)
    cur = store.conn.execute("SELECT owner FROM cs_repo_canonicals WHERE repo_key='a/b'")
    assert cur.fetchone()[0] == "a"


def test_store_enrichments():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    enrs = [RepoEnrichment(repo_key="a/b", readme_compressed="test")]
    store.store_enrichments(enrs)
    cur = store.conn.execute("SELECT readme_compressed FROM cs_repo_enrichments WHERE repo_key='a/b'")
    assert cur.fetchone()[0] == "test"


def test_store_signals():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    sigs = [RepoSignal(repo_key="a/b", github_hotspot=0.9)]
    store.store_signals(sigs)
    cur = store.conn.execute("SELECT github_hotspot FROM cs_repo_signals WHERE repo_key='a/b'")
    assert cur.fetchone()[0] == 0.9


def test_store_packets():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    pkts = [GitHubEvidencePacket(repo_key="a/b", evidence_refs_json='["ev-1"]')]
    store.store_packets(pkts)
    cur = store.conn.execute("SELECT repo_key FROM cs_github_evidence_packets")
    assert cur.fetchone()[0] == "a/b"


def test_store_assets():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    assets = [
        OutputAsset(asset_type="github_hotspot_card", repo_key="a/b", evidence_refs_json='["ev-1"]'),
        OutputAsset(asset_type="action_queue", repo_key="a/b", evidence_refs_json='["ev-2"]'),
    ]
    count = store.store_assets(assets)
    assert count == 2


def test_query_latest_signals():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    store.store_signals([
        RepoSignal(repo_key="a/1"),
        RepoSignal(repo_key="a/2"),
    ])
    results = store.query_latest_signals(limit=1)
    assert len(results) == 1


def test_write_asset_files(tmp_path):
    store = GitHubKnowledgeStoreOperator(db_path=":memory:", knowledge_root=tmp_path)
    assets = [
        OutputAsset(asset_type="github_hotspot_card", repo_key="a/b",
                    evidence_refs_json='["ev-1"]', content_json='{"title": "test"}'),
    ]
    count = store.write_asset_files(assets)
    assert count == 1
    files = list((tmp_path / "extracted" / "code_signal_assets").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["asset_type"] == "github_hotspot_card"


def test_write_asset_files_no_root():
    store = GitHubKnowledgeStoreOperator(db_path=":memory:")
    count = store.write_asset_files([OutputAsset()])
    assert count == 0
