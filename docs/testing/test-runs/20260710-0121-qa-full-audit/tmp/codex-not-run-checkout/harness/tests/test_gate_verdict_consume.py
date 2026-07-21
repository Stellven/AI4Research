"""Regression: required gates must consume verifier/critic verdict CONTENT,
not merely node completion.

Reproduces the de49b5a4 failure mode — a G_REVIEW gate whose member nodes all
reached `passed` STATUS but whose verifier_decision.json=FAIL / critic
gate_decision=block must NOT self-heal the gate to passed. Self-contained:
synthesizes verdict artifacts in a temp sprints dir; no live runtime needed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _load_scheduler(sprints_dir: Path):
    os.environ["HARNESS_DIR"] = str(sprints_dir.parent)
    os.environ["HARNESS_SPRINTS_DIR"] = str(sprints_dir)
    lib = str(Path(__file__).resolve().parents[1] / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import graph_scheduler  # noqa: E402

    # SPRINTS_DIR is computed at import; pin it per-test so each tmp_path is honored.
    graph_scheduler.SPRINTS_DIR = sprints_dir
    return graph_scheduler


def _graph(verifier_decision: str):
    return {
        "sprint_id": "t",
        "nodes": [
            {"id": "V", "gate": "G_REVIEW", "status": "passed", "write_scope": ["g.verifier_decision.json"]},
            {"id": "R", "gate": "G_REVIEW", "status": "passed", "write_scope": []},
        ],
        "node_results": {"V": {"status": "passed"}, "R": {"status": "passed"}},
    }


def test_gate_blocks_on_failed_verifier_verdict(tmp_path):
    sp = tmp_path / "sprints"
    sp.mkdir()
    gs = _load_scheduler(sp)

    (sp / "g.verifier_decision.json").write_text(json.dumps({"decision": "FAIL"}))
    res = gs.parent_ready_check(_graph("FAIL"))
    assert "G_REVIEW" in res["missing_gates"], res
    assert res["ready"] is False


def test_gate_passes_on_approved_verifier_verdict(tmp_path):
    sp = tmp_path / "sprints"
    sp.mkdir()
    gs = _load_scheduler(sp)

    (sp / "g.verifier_decision.json").write_text(json.dumps({"decision": "pass"}))
    res = gs.parent_ready_check(_graph("pass"))
    assert "G_REVIEW" not in res["missing_gates"], res
    assert res["ready"] is True


def test_critic_gate_decision_block(tmp_path):
    sp = tmp_path / "sprints"
    sp.mkdir()
    gs = _load_scheduler(sp)

    (sp / "c.contradictions.jsonl").write_text(
        json.dumps({"type": "gate_verdict", "gate_decision": "block"}) + "\n"
    )
    ok, detail = gs._node_gate_verdict_ok({"write_scope": ["c.contradictions.jsonl"]})
    assert ok is False and "block" in detail, detail


def test_node_without_verdict_artifact_passes_on_completion(tmp_path):
    sp = tmp_path / "sprints"
    sp.mkdir()
    gs = _load_scheduler(sp)

    assert gs._node_gate_verdict_ok({"write_scope": ["source_manifest.json"]})[0] is True


def test_missing_verdict_artifact_fails_closed(tmp_path):
    sp = tmp_path / "sprints"
    sp.mkdir()
    gs = _load_scheduler(sp)

    assert gs._node_gate_verdict_ok({"write_scope": ["nope.verifier_decision.json"]})[0] is False


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
