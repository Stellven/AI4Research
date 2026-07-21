#!/usr/bin/env python3
"""runtime_session_e2e.py — drive the REAL ActorRuntime dispatch path + the deterministic fake
operator, then print a JSON summary the gate (scripts/verify-runtime-session.sh) asserts on.

REAL (production runtime code, unmodified): ActorRuntime.submit -> capability/safety checks ->
actor resolve -> lease (broker) -> scheduler_decision -> ActorMailbox inbox envelope -> evidence
ledger. FAKE (only the LLM/pane execution step): fake_operator.run_once consumes the REAL inbox
and writes a REAL result + artifact + session event. Everything is under HARNESS_DIR (sandbox)."""
import json
import os
import sys
import uuid
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(LIB))

import actor_runtime  # noqa: E402
import fake_operator  # noqa: E402


def main() -> int:
    hd = Path(os.environ["HARNESS_DIR"])
    actor_id = os.environ.get("FAKE_ACTOR_ID", "op.fake.test.01")
    sprint_id = os.environ.get("FAKE_SPRINT_ID", "fakeop-sprint")
    task_id = "t-" + uuid.uuid4().hex[:8]
    node_id = "n1"
    steps: dict = {}

    # ── 1. REAL dispatch via ActorRuntime.submit ──────────────────────────────
    rt = actor_runtime.ActorRuntime(harness_dir=hd)
    envelope = {
        "task_id": task_id,
        "objective": "write a short status report",
        "task": "Produce a short status report for verification.",
        "sprint_id": sprint_id, "node_id": node_id, "actor_id": actor_id,
    }
    res = rt.submit(envelope, actor_id=actor_id, sprint_id=sprint_id, node_id=node_id)
    err = getattr(res, "error", None)
    steps["submit_success"] = bool(getattr(res, "success", False))
    steps["lease_acquired"] = bool(getattr(res, "lease", None))
    steps["scheduler_decision"] = bool(getattr(res, "scheduler_decision", None))
    ip = getattr(res, "inbox_path", None)
    steps["envelope_in_inbox"] = bool(ip and Path(ip).exists())
    elp = getattr(res, "evidence_ledger_path", None)
    steps["evidence_ledger_written"] = bool(elp and Path(elp).exists())

    # ── 2. FAKE operator consumes the REAL inbox -> result + artifact + event ──
    p: dict = {}
    if steps["envelope_in_inbox"]:
        out = fake_operator.run_once(actor_id, sprint_id, harness_dir=hd)
        steps["fake_operator_consumed_envelope"] = out["processed_count"] >= 1
        p = (out.get("processed") or [{}])[0]
        rp = p.get("result_path")
        steps["result_in_outbox"] = bool(rp and Path(rp).exists())
        dv = p.get("deliverable")
        steps["artifact_nonempty"] = bool(dv and Path(dv).exists() and Path(dv).stat().st_size > 0)
        ef = p.get("events_file")
        steps["session_event_written"] = bool(ef and Path(ef).exists())
    else:
        steps["fake_operator_consumed_envelope"] = False

    # Everything must live under the sandbox HARNESS_DIR (isolation), not real ~/.solar.
    paths = [ip, elp, p.get("result_path"), p.get("deliverable"), p.get("events_file")]
    steps["all_paths_under_sandbox"] = all(str(x).startswith(str(hd)) for x in paths if x)

    summary = {
        "sprint_id": sprint_id, "actor_id": actor_id, "task_id": task_id,
        "marker": p.get("marker", ""), "inbox_path": ip, "evidence_ledger_path": elp,
        "result_path": p.get("result_path"), "deliverable": p.get("deliverable"),
        "deliverable_bytes": p.get("deliverable_bytes"), "events_file": p.get("events_file"),
        "error": err, "steps": steps, "all_pass": (not err) and all(steps.values()),
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
