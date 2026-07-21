"""Gate ledger — append-only gate/status evidence; node status as a projection.

Lane 3 of the workflow-contract plan (design §1.4, R4/R5). Extends the
``node_runstate`` durability pattern (sprint-co-located, append-only jsonl,
best-effort writes that never raise into the caller's hot path).

Storage: ``sprints/<sid>.gate-ledger.jsonl`` — one JSON object per line.

Record shape (design §1.4, schema v1.1):

    {record_id, sid, node_id,
     kind: eval_verdict | auto_resolution | repair_start | repair_exhausted |
           human_verdict | gate_check | status_transition | route_record,
     author: {type: evaluator|doctor|policy|human|scheduler|operator, operator_id?},
     verdict?, verdict_kind: content|mechanical|infrastructure,
     eval_generation?, repair_attempt?, pm_task_id?, evidence_snapshot_at?,
     created_at,
     route?: {provider, model, operator_id, backend, exit_code, started_at, finished_at}}

Status-transition records additionally carry ``from_status``/``to_status``,
``writer`` (the code seam that performed the write — the AC-R4.3 audit key),
``applied`` (False for neutralized doctor would-be writes) and ``reopen``
(True for the legacy ``reopening_from_pass`` allowance in
``graph_scheduler.set_node_status``).

Everything here is flag-gated by ``SOLAR_GATE_LEDGER`` at the call sites via
``record_status_transition``/``enabled``; the raw ``append_record``/read/projection
APIs are unconditional so tests and consumers can operate on recorded evidence
regardless of the live flag.
"""
from __future__ import annotations

import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

RECORD_KINDS = {
    "eval_verdict",
    "auto_resolution",
    "repair_start",
    "repair_exhausted",
    "human_verdict",
    "gate_check",
    "status_transition",
    "route_record",
    # G4-lite run 2: deterministic relocation of builder output written under
    # the stray sprints/<sid>.workdir spelling (the P2 recovery-net class).
    "artifact_recovery",
}

VERDICT_KINDS = {"content", "mechanical", "infrastructure"}

# design §1.4 enum + "operator" for route records emitted at the operatord seam
# (F7's second hook; the executing operator is the author of route facts —
# recorded as a deviation in docs/product/lane3-spec-mismatches.md).
AUTHOR_TYPES = {"evaluator", "doctor", "policy", "human", "scheduler", "operator"}

# Ported from graph_scheduler.TERMINAL_STATUSES (rank rules source); the ledger
# must not import the scheduler (operatord-side writers load this module without
# the scheduler's import graph).
TERMINAL_STATUSES = {"passed", "failed", "skipped", "cancelled", "skipped_parent_passed"}
PASS_STATUSES = {"passed"}

ROUTE_KEYS = ("provider", "model", "operator_id", "backend", "exit_code", "started_at", "finished_at")

# eval.json generation_mode values that are never gate-consumable (the 4df6477d
# provenance rule; mirrors graph_node_dispatcher's stale-eval classification).
NON_CONSUMABLE_GENERATION_MODES = {"repair_backfill", "manual_node_eval"}


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enabled() -> bool:
    """The SOLAR_GATE_LEDGER flag (design §3; default off = legacy behavior)."""
    # G4 default-on: the gate ledger is the runtime default; explicit 0 kills it.
    return str(os.environ.get("SOLAR_GATE_LEDGER", "") or "").strip().lower() not in {"0", "false", "no", "off"}


def contracted(graph: Any) -> bool:
    """A graph is on the contracted path when it carries a workflow contract identity."""
    try:
        return bool(str((graph or {}).get("workflow_contract_id") or "").strip())
    except Exception:
        return False


def default_sprints_dir() -> Path:
    env_sprints = os.environ.get("HARNESS_SPRINTS_DIR")
    if env_sprints:
        return Path(env_sprints)
    harness_dir = os.environ.get("HARNESS_DIR") or os.environ.get("SOLAR_HARNESS_DIR")
    if harness_dir:
        return Path(harness_dir) / "sprints"
    return Path.home() / ".solar" / "harness" / "sprints"


def ledger_path(sprints_dir: Any, sid: str) -> Path:
    return Path(sprints_dir) / f"{sid}.gate-ledger.jsonl"


def _clean(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None}


def append_record(
    sprints_dir: Any,
    sid: str,
    *,
    node_id: str,
    kind: str,
    author: Optional[Dict[str, Any]] = None,
    verdict: Optional[str] = None,
    verdict_kind: Optional[str] = None,
    eval_generation: Optional[int] = None,
    repair_attempt: Optional[int] = None,
    pm_task_id: Optional[str] = None,
    evidence_snapshot_at: Optional[str] = None,
    route: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Optional[Dict[str, Any]]:
    """Append one validated record; returns it, or None on any failure.

    Best-effort by contract: gate evidence must never break the dispatch hot
    path, so validation failures and IO errors both return None.
    """
    try:
        sid = str(sid or "").strip()
        node_id = str(node_id or "").strip()
        kind = str(kind or "").strip()
        if not sid or not node_id or kind not in RECORD_KINDS:
            return None
        if verdict_kind is not None and verdict_kind not in VERDICT_KINDS:
            return None
        if author is not None:
            if not isinstance(author, dict):
                return None
            if str(author.get("type") or "") not in AUTHOR_TYPES:
                return None
        if kind == "route_record" and not (isinstance(route, dict) and _clean(route)):
            return None

        record: Dict[str, Any] = {
            "record_id": uuid.uuid4().hex,
            "sid": sid,
            "node_id": node_id,
            "kind": kind,
            "created_at": _utc_now(),
        }
        record.update(_clean({
            "author": author,
            "verdict": verdict,
            "verdict_kind": verdict_kind,
            "eval_generation": eval_generation,
            "repair_attempt": repair_attempt,
            "pm_task_id": pm_task_id,
            "evidence_snapshot_at": evidence_snapshot_at,
            "route": route,
        }))
        record.update(_clean(dict(extra)))

        sprints = Path(sprints_dir)
        sprints.mkdir(parents=True, exist_ok=True)
        with ledger_path(sprints, sid).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
    except Exception:
        return None


def read_records(
    sprints_dir: Any,
    sid: str,
    *,
    node_id: Optional[str] = None,
    kind: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """All records for a sprint in append order; malformed lines are skipped."""
    rows: List[Dict[str, Any]] = []
    try:
        path = ledger_path(sprints_dir, sid)
        if not path.exists():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if node_id is not None and str(row.get("node_id") or "") != node_id:
                continue
            if kind is not None and str(row.get("kind") or "") != kind:
                continue
            rows.append(row)
    except Exception:
        pass
    return rows


# ---------------------------------------------------------------------------
# Status projection (R4: transitions exist only via records)
# ---------------------------------------------------------------------------

def project_node_status(sprints_dir: Any, sid: str, node_id: str) -> str:
    """Fold status_transition records into the node's projected status.

    Terminal statuses are absorbing against UNRECORDED writes (which, by
    definition, leave no record here) and against neutralized would-be writes
    (``applied`` False — the doctor-on-contract shape). Any APPLIED record
    projects, including terminal→terminal and terminal→non-terminal: applied
    records exist only via audited writers, so refusing to fold one would make
    the projection contradict a real recorded write (the round-4 G6
    passed→failed laundering). Absorbing = "no exit from terminal without an
    applied audited record", per AC-R4.3's disposition in
    docs/product/lane3-spec-mismatches.md.
    """
    status = ""
    for row in read_records(sprints_dir, sid, node_id=node_id, kind="status_transition"):
        if row.get("applied") is False:
            continue
        to_status = str(row.get("to_status") or "").strip().lower()
        if not to_status:
            continue
        status = to_status
    return status


def record_status_transition(
    sprints_dir: Any,
    sid: str,
    node_id: str,
    *,
    from_status: str,
    to_status: str,
    author_type: str = "scheduler",
    writer: str = "",
    operator_id: Optional[str] = None,
    applied: bool = True,
    note: Optional[str] = None,
    **extra: Any,
) -> Optional[Dict[str, Any]]:
    """The single status-transition recording seam (flag-gated, no-op when off).

    Every writer on the C4 surface calls this after (or, for neutralized doctor
    writes, instead of) its raw write. Same-status no-ops are not recorded.
    """
    if not enabled():
        return None
    old = str(from_status or "").strip().lower()
    new = str(to_status or "").strip().lower()
    if old == new:
        return None
    author: Dict[str, Any] = {"type": author_type}
    if operator_id:
        author["operator_id"] = operator_id
    reopen = old in PASS_STATUSES and new not in TERMINAL_STATUSES
    return append_record(
        sprints_dir,
        sid,
        node_id=node_id,
        kind="status_transition",
        author=author,
        from_status=old,
        to_status=new,
        writer=writer or None,
        applied=applied if applied is not True else None,
        reopen=True if reopen else None,
        note=note,
        **extra,
    )


# ---------------------------------------------------------------------------
# Gate consumability (R4: doctor backfill flagged, never consumed)
# ---------------------------------------------------------------------------

def is_gate_consumable(record: Dict[str, Any], *, current_generation: Optional[int] = None) -> bool:
    """Whether a verdict-bearing record may feed a gate decision.

    Fail-closed: anything not provably an assigned-evaluator (or human) verdict
    for the current generation is non-consumable.
    """
    try:
        if not isinstance(record, dict):
            return False
        if record.get("gate_consumable") is False:
            return False
        if record.get("applied") is False:
            return False
        author_type = str((record.get("author") or {}).get("type") or "")
        if author_type not in {"evaluator", "human"}:
            return False
        if str(record.get("generation_mode") or "").strip().lower() in NON_CONSUMABLE_GENERATION_MODES:
            return False
        if record.get("self_graded"):
            return False
        if current_generation is not None:
            generation = record.get("eval_generation")
            # Fail-closed (round-4 G9): a record that cannot prove which
            # generation it evaluated is not consumable at any specific one.
            if generation is None or int(generation) != int(current_generation):
                return False
        return True
    except Exception:
        return False


def latest_consumable_verdict(
    sprints_dir: Any,
    sid: str,
    node_id: str,
    *,
    current_generation: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Most recent gate-consumable verdict record for a node, or None (fail-closed)."""
    latest: Optional[Dict[str, Any]] = None
    for row in read_records(sprints_dir, sid, node_id=node_id):
        if row.get("kind") not in {"eval_verdict", "human_verdict"}:
            continue
        if not is_gate_consumable(row, current_generation=current_generation):
            continue
        latest = row
    return latest


# ---------------------------------------------------------------------------
# Route records (R5 / AC-R5.1 — the operatord-seam hook, F7)
# ---------------------------------------------------------------------------

def append_route_record(
    sprints_dir: Any,
    sid: str,
    *,
    node_id: str,
    task_id: str,
    phase: str,
    route: Dict[str, Any],
    operator_id: Optional[str] = None,
    **extra: Any,
) -> Optional[Dict[str, Any]]:
    """Append a per-stage-execution route record.

    ``phase`` is ``submitted`` (envelope write — proves the stage started) or
    ``completed`` (result write — carries exit_code/finished_at). A run killed
    between the two already has its ``submitted`` record (AC-R5.1).
    """
    if not isinstance(route, dict) or not _clean(route):
        return None
    payload = {key: route.get(key) for key in ROUTE_KEYS}
    payload.update({k: v for k, v in route.items() if k not in ROUTE_KEYS})
    author: Dict[str, Any] = {"type": "operator"}
    if operator_id or payload.get("operator_id"):
        author["operator_id"] = str(operator_id or payload.get("operator_id"))
    return append_record(
        sprints_dir,
        sid,
        node_id=node_id,
        kind="route_record",
        author=author,
        route=_clean(payload),
        task_id=str(task_id or "") or None,
        phase=str(phase or "") or None,
        **extra,
    )
