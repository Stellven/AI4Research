"""Test G4 — GitHubEvidencePacketCompiler."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.packet_compiler import GitHubEvidencePacketCompiler
from github_intelligence.code_signal.models import (
    GitHubEvidencePacket, RepoSnapshot, RepoCanonical, RepoEnrichment, RepoSignal,
)


def _snap():
    return RepoSnapshot(repo_key="test/repo", stars=1000, stars_delta_24h=50, description="A hot project")


def _enr():
    return RepoEnrichment(repo_key="test/repo", evidence_ids_json='["ev-1"]')


def _sig():
    return RepoSignal(repo_key="test/repo", github_hotspot=0.8, noise_risk=0.2, evidence_ids_json='["ev-2"]')


def test_basic_packet():
    compiler = GitHubEvidencePacketCompiler()
    pkt = compiler.run(_snap())
    assert isinstance(pkt, GitHubEvidencePacket)
    assert pkt.repo_key == "test/repo"
    assert pkt.packet_version == "v1"


def test_packet_evidence_refs():
    compiler = GitHubEvidencePacketCompiler()
    pkt = compiler.run(_snap(), enrichment=_enr(), signal=_sig())
    refs = json.loads(pkt.evidence_refs_json)
    assert "ev-1" in refs
    assert "ev-2" in refs


def test_packet_snapshot_summary():
    compiler = GitHubEvidencePacketCompiler()
    pkt = compiler.run(_snap())
    summary = json.loads(pkt.snapshot_summary_json)
    assert summary["stars"] == 1000
    assert summary["stars_delta_24h"] == 50


def test_packet_questions_generated():
    compiler = GitHubEvidencePacketCompiler()
    pkt = compiler.run(_snap())
    questions = json.loads(pkt.questions_for_high_model_json)
    assert len(questions) >= 1
    assert "test/repo" in questions[0]


def test_packet_cross_source_refs():
    compiler = GitHubEvidencePacketCompiler()
    cross = {"social_mentions": ["thesis-1"], "paper_ids": ["paper-1"]}
    pkt = compiler.run(_snap(), cross_source_refs=cross)
    refs = json.loads(pkt.cross_source_refs_json)
    assert refs["social_mentions"] == ["thesis-1"]


def test_packet_signal_summary():
    compiler = GitHubEvidencePacketCompiler()
    pkt = compiler.run(_snap(), signal=_sig())
    sig_sum = json.loads(pkt.signal_summary_json)
    assert sig_sum["github_hotspot"] == 0.8


def test_packet_noise_question():
    compiler = GitHubEvidencePacketCompiler()
    noisy_sig = RepoSignal(repo_key="test/repo", noise_risk=0.7)
    pkt = compiler.run(_snap(), signal=noisy_sig)
    questions = json.loads(pkt.questions_for_high_model_json)
    assert any("hype" in q.lower() for q in questions)
