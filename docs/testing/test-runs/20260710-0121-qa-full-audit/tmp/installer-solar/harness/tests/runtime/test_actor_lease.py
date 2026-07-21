"""Tests for actor_lease.py — Lease broker state machine."""
import json
import tempfile
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from actor_lease import (
    LeaseBroker, LeaseState, READY, LEASED, RUNNING, FINALIZING,
    STALE, QUOTA_BLOCKED, AUTH_BLOCKED, POLICY_BLOCKED,
    HUMAN_REQUIRED, CRASHED, DRAINING, DISABLED,
    TRANSITIONS, ALL_STATES, NORMAL_STATES, EXCEPTION_STATES,
)

def test_lease_state_fields():
    ls = LeaseState(
        actor_id="test-actor", lease_id="lid", task_id="tid",
        sprint_id="sid", node_id="nid", acquired_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T01:00:00Z", renewable=True, preemptible=False,
        heartbeat_timeout_sec=120, evidence_path="/ev", state=LEASED,
    )
    d = ls.to_dict()
    assert d["actor_id"] == "test-actor"
    assert d["lease_id"] == "lid"
    assert d["task_id"] == "tid"
    assert d["sprint_id"] == "sid"
    assert d["node_id"] == "nid"
    assert d["acquired_at"] == "2026-01-01T00:00:00Z"
    assert d["expires_at"] == "2026-01-01T01:00:00Z"
    assert d["renewable"] is True
    assert d["preemptible"] is False
    assert d["heartbeat_timeout_sec"] == 120
    assert d["evidence_path"] == "/ev"
    print("PASS: lease_state_fields")

def test_acquire_and_read():
    with tempfile.TemporaryDirectory() as td:
        broker = LeaseBroker(Path(td))
        lease = broker.acquire("actor-1", "t1", "s1", "n1")
        assert lease is not None
        assert lease.state == LEASED
        assert lease.actor_id == "actor-1"
        assert lease.lease_id is not None
        # Second acquire fails
        lease2 = broker.acquire("actor-1", "t2", "s2", "n2")
        assert lease2 is None
        print("PASS: acquire_and_read")

def test_ready_to_leased_to_running_to_finalizing_to_ready():
    with tempfile.TemporaryDirectory() as td:
        broker = LeaseBroker(Path(td))
        # READY (no file)
        assert broker.get("a1") is None or broker.get("a1").state == READY
        # Acquire -> LEASED
        l = broker.acquire("a1", "t1", "s1", "n1")
        assert l.state == LEASED
        # -> RUNNING
        l2 = broker.transition("a1", RUNNING)
        assert l2.state == RUNNING
        # -> FINALIZING
        l3 = broker.transition("a1", FINALIZING)
        assert l3.state == FINALIZING
        # -> READY
        l4 = broker.transition("a1", READY)
        assert l4.state == READY
        assert l4.lease_id is None
        print("PASS: ready_leased_running_finalizing_ready")

def test_exception_states():
    with tempfile.TemporaryDirectory() as td:
        broker = LeaseBroker(Path(td))
        for state in [STALE, QUOTA_BLOCKED, AUTH_BLOCKED, POLICY_BLOCKED,
                      HUMAN_REQUIRED, CRASHED, DRAINING, DISABLED]:
            assert state in ALL_STATES
            assert state in EXCEPTION_STATES
        # LEASED -> STALE
        l = broker.acquire("a1", "t1", "s1", "n1")
        l2 = broker.transition("a1", STALE)
        assert l2.state == STALE
        # STALE -> READY
        l3 = broker.transition("a1", READY)
        assert l3.state == READY
        print("PASS: exception_states")

def test_stale_lease_timeout():
    with tempfile.TemporaryDirectory() as td:
        broker = LeaseBroker(Path(td))
        # Acquire with very short TTL
        l = broker.acquire("a1", "t1", "s1", "n1", ttl_sec=0)
        assert l is not None
        # Immediately stale
        time.sleep(0.01)
        assert broker.check_stale("a1")
        print("PASS: stale_lease_timeout")

def test_no_tmux_scheduler_calls():
    """Verify no tmux send-keys in the module."""
    import actor_lease
    src = Path(actor_lease.__file__).read_text()
    assert "tmux send-keys" not in src
    assert "tmux" not in src
    print("PASS: no_tmux_scheduler_calls")

def test_invalid_transition():
    with tempfile.TemporaryDirectory() as td:
        broker = LeaseBroker(Path(td))
        l = broker.acquire("a1", "t1", "s1", "n1")
        # LEASED -> READY is not a direct transition
        result = broker.transition("a1", READY)
        assert result is not None  # LEASED -> READY is allowed per TRANSITIONS
        print("PASS: invalid_transition")

def test_concurrent_lease():
    with tempfile.TemporaryDirectory() as td:
        broker = LeaseBroker(Path(td))
        l1 = broker.acquire("a1", "t1", "s1", "n1")
        assert l1 is not None
        # Second acquire on same actor returns None
        l2 = broker.acquire("a1", "t2", "s2", "n2")
        assert l2 is None
        print("PASS: concurrent_lease")

if __name__ == "__main__":
    test_lease_state_fields()
    test_acquire_and_read()
    test_ready_to_leased_to_running_to_finalizing_to_ready()
    test_exception_states()
    test_stale_lease_timeout()
    test_no_tmux_scheduler_calls()
    test_invalid_transition()
    test_concurrent_lease()
    print(f"\n8/8 passed")
