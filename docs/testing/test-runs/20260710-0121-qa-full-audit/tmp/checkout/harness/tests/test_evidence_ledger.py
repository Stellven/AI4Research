"""Tests for evidence_ledger.py — Evidence path and scheduler decision."""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from evidence_ledger import EvidenceLedger, build_scheduler_decision

def test_write_run_entry():
    with tempfile.TemporaryDirectory() as td:
        el = EvidenceLedger(Path(td))
        sd = build_scheduler_decision("a1", "ImplementationWorker", {"TaskFit": 0.3}, {}, [])
        path = el.write_run_entry("t1", "s1", "n1", "a1", "ImplementationWorker", sd)
        assert Path(path).exists()
        lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["task_id"] == "t1"
        assert data["actor_id"] == "a1"
        assert "per_node" in data
        assert "final_report_target" in data
        print("PASS: write_run_entry")

def test_scheduler_decision_serialization():
    sd = build_scheduler_decision(
        selected_actor="a1",
        logical_operator="DeepArchitect",
        score_factors={"TaskFit": 0.27},
        penalties={"RecentFailurePenalty": 0.15},
        rejected=[{"actor_id": "a2", "reason": "quota_blocked"}],
        quota_reason="monthly_limit",
    )
    assert sd["selected_actor"] == "a1"
    assert sd["logical_operator"] == "DeepArchitect"
    assert len(sd["rejected_candidates"]) == 1
    assert sd["quota_reason"] == "monthly_limit"
    print("PASS: scheduler_decision_serialization")

if __name__ == "__main__":
    test_write_run_entry()
    test_scheduler_decision_serialization()
    print("\n2/2 passed")
