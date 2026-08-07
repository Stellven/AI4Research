"""Tests for the CI-safe fake-operator runtime path.

Proves the REAL ActorRuntime dispatch (submit -> lease -> scheduler_decision -> mailbox inbox ->
evidence ledger) hands off to the DETERMINISTIC fake operator, which writes a REAL result +
artifact + session event — fully isolated (outputs under the sandbox HARNESS_DIR, no LLM)."""
import sys
import tempfile
import uuid
from pathlib import Path

LIB = (Path(__file__).resolve().parents[2] / 'harness') / "lib"
sys.path.insert(0, str(LIB))


def _sandbox() -> Path:
    td = Path(tempfile.mkdtemp(prefix="fakeop-"))
    for d in ("config", "run", "sprints", "events", "sessions", "reports", "actors"):
        (td / d).mkdir(parents=True, exist_ok=True)
    return td


def test_fake_operator_refuses_without_env(monkeypatch):
    import fake_operator
    monkeypatch.delenv("SOLAR_FAKE_OPERATOR", raising=False)
    try:
        fake_operator.run_once("op.fake.test.01", "s", harness_dir=_sandbox())
    except RuntimeError:
        return
    raise AssertionError("fake_operator must refuse to run without SOLAR_FAKE_OPERATOR")


def test_real_submit_then_fake_operator_end_to_end(monkeypatch):
    monkeypatch.setenv("SOLAR_FAKE_OPERATOR", "1")
    import actor_runtime
    import fake_operator
    from actor_mailbox import ActorMailbox

    hd = _sandbox()
    actor_id, sid = "op.fake.test.01", "fakeop-pytest"
    task_id = "t-" + uuid.uuid4().hex[:8]

    # REAL dispatch
    rt = actor_runtime.ActorRuntime(harness_dir=hd)
    env = {"task_id": task_id, "objective": "write a short status report",
           "sprint_id": sid, "node_id": "n1", "actor_id": actor_id}
    res = rt.submit(env, actor_id=actor_id, sprint_id=sid, node_id="n1")
    assert res.success, getattr(res, "error", None)
    assert res.inbox_path and Path(res.inbox_path).exists()
    assert res.evidence_ledger_path and Path(res.evidence_ledger_path).exists()
    assert res.scheduler_decision
    assert res.lease

    # FAKE operator consumes the REAL inbox
    out = fake_operator.run_once(actor_id, sid, harness_dir=hd)
    assert out["processed_count"] == 1
    p = out["processed"][0]
    assert Path(p["result_path"]).exists()
    assert Path(p["deliverable"]).exists() and Path(p["deliverable"]).stat().st_size > 0
    assert Path(p["events_file"]).exists()

    # the REAL outbox surfaces the result via the real mailbox API
    mb = ActorMailbox(actor_id, hd / "actors")
    results = mb.read_results(task_id)
    assert results and results[0]["status"] == "completed"
    assert results[0]["produced_by"] == "fake_operator"

    # the session event carries the marker (what the status-server reads)
    assert p["marker"] in (hd / "sessions" / sid / "events.jsonl").read_text(encoding="utf-8")

    # isolation: every produced path is under the sandbox, never the real home
    for x in (res.inbox_path, res.evidence_ledger_path, p["result_path"], p["deliverable"], p["events_file"]):
        assert str(x).startswith(str(hd)), f"path escaped sandbox: {x}"
