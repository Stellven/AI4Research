"""Tests for logical_operator_router.py — Operator routing and bindings."""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from logical_operator_router import LogicalOperatorRouter, P0_LOGICAL_OPERATORS

def _make_bindings(tmpdir, actors_tmp=None):
    bindings = {}
    for i, op in enumerate(sorted(P0_LOGICAL_OPERATORS)):
        bindings[op] = {
            "operator_type": op,
            "candidates": [
                {"actor_id": f"actor-a-{i%3}", "priority": 1, "condition": "always"},
                {"actor_id": f"actor-b-{i%3}", "priority": 2, "condition": "fallback"},
            ],
            "selection_policy": "score",
            "fallback_policy": "next_candidate",
        }
    bp = Path(tmpdir) / "logical-operators.json"
    bp.write_text(json.dumps({"bindings": bindings}))
    # Minimal actors
    actors = {}
    for i in range(3):
        actors[f"actor-a-{i}"] = {"actor_id": f"actor-a-{i}", "capability_profile": {}}
        actors[f"actor-b-{i}"] = {"actor_id": f"actor-b-{i}", "capability_profile": {}}
    ap = Path(tmpdir) / "agent-actors.json"
    ap.write_text(json.dumps({"actors": actors}))
    return bp, ap

def test_all_17_operators():
    assert len(P0_LOGICAL_OPERATORS) == 17
    expected = {
        "DeepArchitect", "RootCauseDebugger", "ImplementationWorker", "PatchWorker",
        "TestDesigner", "TestRunner", "BenchmarkRunner", "ParallelExplorer",
        "ResearchScout", "ResearchSynthesizer", "Critic", "Verifier", "VerifierLite",
        "SecurityGate", "QuotaBroker", "ContextCompressor", "ArtifactCurator",
    }
    assert P0_LOGICAL_OPERATORS == expected
    print("PASS: all_17_operators")

def test_binding_changes_actor():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_bindings(td)
        router = LogicalOperatorRouter(bp, ap)
        # DeepArchitect -> first candidate
        c1 = router.get_candidates("DeepArchitect")
        assert len(c1) > 0

        # Change binding: swap candidates
        data = json.loads(bp.read_text())
        data["bindings"]["DeepArchitect"]["candidates"] = [
            {"actor_id": "actor-new-1", "priority": 1, "condition": "always"},
            {"actor_id": "actor-new-2", "priority": 2, "condition": "fallback"},
        ]
        bp.write_text(json.dumps(data))

        # Reload
        router2 = LogicalOperatorRouter(bp, ap)
        c2 = router2.get_candidates("DeepArchitect")
        assert c2 != c1
        assert "actor-new-1" in c2
        print("PASS: binding_changes_actor")

def test_fallback_candidate_ordering():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_bindings(td)
        router = LogicalOperatorRouter(bp, ap)

        # Find the actual primary candidate for DeepArchitect
        candidates = router.get_candidates("DeepArchitect")
        primary = candidates[0]

        # Primary unavailable -> fallback
        sel, rej = router.select_actor(
            "DeepArchitect",
            unavailable={primary},
        )
        assert sel is not None
        assert sel != primary
        assert any(r["reason"] == "unavailable" for r in rej)
        print("PASS: fallback_candidate_ordering")

def test_quota_blocked_fallback():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_bindings(td)
        router = LogicalOperatorRouter(bp, ap)
        primary = router.get_candidates("DeepArchitect")[0]
        sel, rej = router.select_actor(
            "DeepArchitect",
            quota_blocked={primary},
        )
        assert sel is not None
        assert any(r["reason"] == "quota_blocked" for r in rej)
        print("PASS: quota_blocked_fallback")

def test_risk_denied_fallback():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_bindings(td)
        router = LogicalOperatorRouter(bp, ap)
        primary = router.get_candidates("DeepArchitect")[0]
        sel, rej = router.select_actor(
            "DeepArchitect",
            risk_denied={primary},
        )
        assert sel is not None
        assert any(r["reason"] == "risk_denied" for r in rej)
        print("PASS: risk_denied_fallback")

def test_all_operators_bound():
    with tempfile.TemporaryDirectory() as td:
        bp, ap = _make_bindings(td)
        router = LogicalOperatorRouter(bp, ap)
        unbound = router.validate_all_operators_bound()
        assert unbound == [], f"unbound: {unbound}"
        print("PASS: all_operators_bound")

if __name__ == "__main__":
    test_all_17_operators()
    test_binding_changes_actor()
    test_fallback_candidate_ordering()
    test_quota_blocked_fallback()
    test_risk_denied_fallback()
    test_all_operators_bound()
    print("\n6/6 passed")
