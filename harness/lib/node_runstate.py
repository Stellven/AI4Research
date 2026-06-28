"""Durable, sprint-co-located per-node runstate ledger.

Two facts the live status windows compute but do not persist durably next to the sprint:

  * worker attribution -- which backend/vendor/model/operator/profile ran a node, plus exit_code.
    (multi_task_runner already writes this, but only to RUN_DIR/<dispatch_id>/status.json, which is
    keyed by dispatch_id and reaped after SOLAR_MULTI_TASK_REAP_TTL_MIN minutes -- so after reaping
    there is no node-keyed, sprint-co-located proof that "node N1 ran on Anthropic".)
  * eval/repair state -- repair attempts, eval-dispatch failures, last verdict/reason, next_action.
    (A node stuck in `reviewing` because no evaluator was available would otherwise only be visible by
    grepping hundreds of `graph_eval_dispatch_failed` events.)

This module writes both next to the sprint so they survive RUN_DIR reaping and are findable by
(sid, node_id). Layout (under SPRINTS_DIR):

  <sid>.runstate.jsonl              append-only event ledger (one JSON object per line)
  <sid>.<safe_node>-runstate.json   latest snapshot per node (attribution + eval_state merged)

Pure/standalone: stdlib only; every write is best-effort and never raises into the caller's hot path.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_node_id(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(node_id or "")).strip("-") or "node"


def ledger_path(sprints_dir: Any, sid: str) -> Path:
    return Path(sprints_dir) / f"{sid}.runstate.jsonl"


def snapshot_path(sprints_dir: Any, sid: str, node_id: str) -> Path:
    return Path(sprints_dir) / f"{sid}.{_safe_node_id(node_id)}-runstate.json"


def _clean(fields: dict[str, Any] | None) -> dict[str, Any]:
    # Drop None values so an absent field never clobbers a previously-known one in the snapshot.
    return {k: v for k, v in (fields or {}).items() if v is not None}


def record(sprints_dir: Any, sid: str, node_id: str, kind: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Append one ledger line and merge-update the per-node snapshot.

    ``kind`` is typically "attribution" or "eval_state"; each kind is merged into its own snapshot
    section so a single file proves both "ran on X" and "eval state Y". Best-effort: returns the
    snapshot written, or None on any failure (never raises)."""
    try:
        sid = str(sid or "").strip()
        node_id = str(node_id or "").strip()
        if not sid or not node_id:
            return None
        sprints = Path(sprints_dir)
        sprints.mkdir(parents=True, exist_ok=True)
        ts = _utc_now()
        clean = _clean(fields)

        entry = {"ts": ts, "kind": str(kind), "sprint_id": sid, "node_id": node_id}
        entry.update(clean)
        with ledger_path(sprints, sid).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        snap_path = snapshot_path(sprints, sid, node_id)
        snap: dict[str, Any] = {}
        if snap_path.exists():
            try:
                loaded = json.loads(snap_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    snap = loaded
            except Exception:
                snap = {}
        snap["sprint_id"] = sid
        snap["node_id"] = node_id
        snap["updated_at"] = ts
        section = snap.get(kind) if isinstance(snap.get(kind), dict) else {}
        section.update(clean)
        section["updated_at"] = ts
        snap[kind] = section

        tmp = snap_path.with_suffix(snap_path.suffix + ".tmp")
        tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, snap_path)
        return snap
    except Exception:
        return None


def read_snapshot(sprints_dir: Any, sid: str, node_id: str) -> dict[str, Any]:
    try:
        path = snapshot_path(sprints_dir, sid, node_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}
