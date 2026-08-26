import json
import sys
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(ROOT / "lib"))

import graph_node_dispatcher as gnd  # noqa: E402


def test_pop_graph_queue_item_releases_advisory_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    qdir = tmp_path / "run" / "queue"
    qdir.mkdir(parents=True)
    qf = qdir / "sprint-lock-cleanup.jsonl"
    qf.write_text(
        json.dumps(
            {
                "id": "q1",
                "intent": "graph_node|node_id=N1",
                "priority": 10,
                "enqueued_at": "2026-05-21T00:00:00Z",
                "payload": {"node": {"id": "N1"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    item = gnd._pop_graph_queue_item("sprint-lock-cleanup")

    assert item and item["id"] == "q1"
    # Windows cannot unlink an open lock sidecar, while POSIX can.  The
    # portable contract is that the lock is released and immediately
    # reacquirable, not that its empty filename disappears.
    with open(str(qf) + ".lock", "a") as lock_file:
        gnd.fcntl.flock(lock_file, gnd.fcntl.LOCK_EX | gnd.fcntl.LOCK_NB)
        gnd.fcntl.flock(lock_file, gnd.fcntl.LOCK_UN)
