"""Tests for actor_mailbox.py — File mailbox submit/read."""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from actor_mailbox import ActorMailbox

def test_submit_and_read():
    with tempfile.TemporaryDirectory() as td:
        mb = ActorMailbox("test-actor", Path(td))
        envelope = {"task_id": "t1", "action": "run", "sprint_id": "s1"}
        path = mb.submit_task(envelope)
        assert Path(path).exists()
        tasks = mb.read_inbox()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "t1"
        print("PASS: submit_and_read")

def test_write_and_read_results():
    with tempfile.TemporaryDirectory() as td:
        mb = ActorMailbox("test-actor", Path(td))
        mb.write_result("t1", {"task_id": "t1", "status": "pass"})
        mb.write_result("t1", {"task_id": "t1", "status": "pass", "step": 2})
        mb.write_result("t2", {"task_id": "t2", "status": "fail"})
        all_r = mb.read_results()
        assert len(all_r) == 3
        t1_r = mb.read_results("t1")
        assert len(t1_r) == 2
        t2_r = mb.read_results("t2")
        assert len(t2_r) == 1
        print("PASS: write_and_read_results")

def test_heartbeat():
    with tempfile.TemporaryDirectory() as td:
        mb = ActorMailbox("test-actor", Path(td))
        mb.write_heartbeat("running", {"load": 0.5})
        hb = mb.read_heartbeat()
        assert hb["status"] == "running"
        assert hb["actor_id"] == "test-actor"
        print("PASS: heartbeat")

if __name__ == "__main__":
    test_submit_and_read()
    test_write_and_read_results()
    test_heartbeat()
    print("\n3/3 passed")
