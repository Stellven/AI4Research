#!/usr/bin/env python3
"""fake_operator.py — DETERMINISTIC fake operator for CI-safe runtime verification.

Consumes the REAL ActorMailbox inbox envelope that ActorRuntime.submit() wrote, and produces a
REAL result + artifact + completion event — replacing ONLY the final LLM/pane execution step.
NO Claude/Codex/GLM/LLM calls. Gated by SOLAR_FAKE_OPERATOR (refuses to run otherwise) so it can
never silently stand in for a real operator in production.

Real path preserved (everything except this module's body runs the real runtime code):
  ActorRuntime.submit -> capability/safety checks -> router/actor resolve -> lease (broker) ->
  scheduler_decision -> ActorMailbox inbox envelope -> evidence ledger        [REAL, upstream]
  THIS MODULE: read_inbox -> write deterministic artifact + ActorMailbox.write_result (outbox) +
  session event under sessions/<sprint>/events.jsonl                          [REAL outbox/artifact/event]
  -> status-server /status?sprint_id / /events surfaces the session+marker    [REAL, downstream]

Run:  SOLAR_FAKE_OPERATOR=1 HARNESS_DIR=/tmp/... python3 fake_operator.py --actor <id> --sprint <sid>
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # harness/lib
from actor_mailbox import ActorMailbox  # noqa: E402


def _enabled() -> bool:
    return os.environ.get("SOLAR_FAKE_OPERATOR", "").strip().lower() in ("1", "true", "yes")


def _harness_dir() -> Path:
    return Path(os.environ.get("HARNESS_DIR") or (Path.home() / ".solar" / "harness")).expanduser()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _artifact_body(env: dict, task_id: str, sprint_id: str, marker: str) -> str:
    obj = env.get("objective") or env.get("task") or env.get("goal") or "(no objective)"
    return (
        f"# Operator result: {task_id}\n\n"
        f"- sprint_id: {sprint_id}\n"
        f"- actor_id: {env.get('actor_id', '?')}\n"
        f"- objective: {obj}\n"
        f"- produced_by: fake_operator (deterministic, no LLM)\n"
        f"- marker: {marker}\n\n"
        f"## Output\n\nDeterministic processing of the real operator envelope for {task_id}.\n"
    )


def run_once(actor_id: str, sprint_id: str = "", *, harness_dir=None, mailbox_base=None) -> dict:
    """Consume the actor's REAL inbox and write real result + artifact + completion event per task.

    Returns a summary dict. Raises if SOLAR_FAKE_OPERATOR is not set (so it can't run in prod)."""
    if not _enabled():
        raise RuntimeError("fake_operator refuses to run without SOLAR_FAKE_OPERATOR=1")
    hd = Path(harness_dir) if harness_dir else _harness_dir()
    mb = Path(mailbox_base) if mailbox_base else (hd / "actors")
    mailbox = ActorMailbox(actor_id, mb)
    envelopes = mailbox.read_inbox()  # REAL envelope(s) written by ActorRuntime.submit
    processed = []
    for env in envelopes:
        task_id = str(env.get("task_id") or uuid.uuid4())
        sid = sprint_id or str(env.get("sprint_id") or env.get("sprint") or "fake-sprint")
        node_id = str(env.get("node_id") or "n1")
        marker = f"FAKEOP-{task_id[:8]}"

        # 1) REAL artifact / deliverable (non-empty, deterministic, derived from the envelope).
        deliv_dir = hd / "sprints" / sid / "deliverables"
        deliv_dir.mkdir(parents=True, exist_ok=True)
        deliv = deliv_dir / f"{node_id}-result.md"
        deliv.write_text(_artifact_body(env, task_id, sid, marker), encoding="utf-8")

        # 2) REAL machine-readable result -> the actor's outbox (real ActorMailbox API).
        result = {
            "task_id": task_id, "actor_id": actor_id, "sprint_id": sid, "node_id": node_id,
            "status": "completed", "produced_by": "fake_operator", "marker": marker,
            "deliverable": str(deliv), "deliverable_bytes": deliv.stat().st_size,
            "summary": f"fake operator completed {task_id} ({marker})", "completed_at": _now_iso(),
        }
        result_path = mailbox.write_result(task_id, result)

        # 3) REAL session event so the status-server / session view surfaces the new result.
        ev_dir = hd / "sessions" / sid
        ev_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "event_id": f"{task_id}-done", "session_id": sid, "sprint_id": sid, "seq": 1,
            "ts": _now_iso(), "type": "operator_result", "actor": actor_id,
            "source": "fake_operator", "message": result["summary"],
            "deliverable": str(deliv), "marker": marker, "status": "completed",
        }
        with (ev_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

        processed.append({
            "task_id": task_id, "sprint_id": sid, "node_id": node_id, "marker": marker,
            "deliverable": str(deliv), "deliverable_bytes": result["deliverable_bytes"],
            "result_path": result_path, "events_file": str(ev_dir / "events.jsonl"),
        })
    return {"actor_id": actor_id, "processed_count": len(processed), "processed": processed}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic fake operator (CI runtime verification).")
    ap.add_argument("--actor", required=True)
    ap.add_argument("--sprint", default="")
    args = ap.parse_args(argv)
    if not _enabled():
        print("NOT VERIFIED: SOLAR_FAKE_OPERATOR is not set; refusing to run.", file=sys.stderr)
        return 2
    out = run_once(args.actor, args.sprint)
    print(json.dumps(out, indent=2))
    return 0 if out["processed_count"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
