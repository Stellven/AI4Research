"""Test G3 — RepoSignalScoringOperator."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.operators.scoring import RepoSignalScoringOperator
from github_intelligence.code_signal.models import RepoSnapshot, RepoEnrichment, RepoSignal


def _snap(repo_key="test/repo", stars=100, delta24=10, archived=False):
    return RepoSnapshot(
        repo_key=repo_key, stars=stars,
        stars_delta_24h=delta24, archived=archived,
    )


def _enr(repo_key="test/repo", readme="A project"):
    return RepoEnrichment(repo_key=repo_key, readme_compressed=readme)


def test_empty_inputs():
    op = RepoSignalScoringOperator()
    result = op.run([], [])
    assert result == []


def test_basic_scoring():
    op = RepoSignalScoringOperator()
    snaps = [_snap("a/b", stars=500, delta24=50)]
    enrs = [_enr("a/b")]
    result = op.run(snaps, enrs)
    assert len(result) == 1
    sig = result[0]
    assert isinstance(sig, RepoSignal)
    assert sig.github_hotspot >= 0.0
    assert sig.technical_substance > 0.0  # has readme
    assert sig.signal_class in ("hot", "rising", "sustained", "cooling")


def test_noise_gate_archived():
    op = RepoSignalScoringOperator()
    snaps = [_snap("archived/repo", stars=10, delta24=0, archived=True)]
    result = op.run(snaps, [])
    assert result[0].noise_risk >= 0.5
    assert result[0].is_noise_filtered()
    flags = json.loads(result[0].actionability_flags_json)
    assert "noise_filtered" in flags


def test_signal_class_hot():
    op = RepoSignalScoringOperator()
    snaps = [_snap("hot/repo", stars=1000, delta24=500)]
    result = op.run(snaps, [])
    assert result[0].signal_class == "hot"


def test_signal_class_cooling():
    op = RepoSignalScoringOperator()
    snaps = [_snap("cool/repo", stars=100, delta24=0)]
    result = op.run(snaps, [])
    assert result[0].signal_class == "cooling"


def test_scores_bounded():
    op = RepoSignalScoringOperator()
    snaps = [_snap("x/y")]
    result = op.run(snaps, [])
    sig = result[0]
    for attr in ("github_hotspot", "technical_substance", "community_health",
                 "intervention_opportunity", "open_project_opportunity",
                 "strategic_fit", "noise_risk"):
        val = getattr(sig, attr)
        assert 0.0 <= val <= 1.0, f"{attr}={val} out of [0,1]"


def test_evidence_ids_carried():
    op = RepoSignalScoringOperator()
    snaps = [_snap("a/b")]
    enrs = [RepoEnrichment(repo_key="a/b", evidence_ids_json='["ev-1", "ev-2"]')]
    result = op.run(snaps, enrs)
    ev_ids = json.loads(result[0].evidence_ids_json)
    assert len(ev_ids) == 2


def test_custom_noise_gate():
    op = RepoSignalScoringOperator(config={"noise_risk_gate": 0.3})
    assert op.noise_gate == 0.3
