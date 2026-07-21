"""Persistent runtime store for logical binding selection policies."""

from __future__ import annotations

import datetime as _dt
import fcntl
import json
from pathlib import Path
from typing import Any

from actor_lease import LEASED, RUNNING, FINALIZING
from harness_paths import resolve_runtime_harness_dir

HARNESS_DIR = resolve_runtime_harness_dir()
SELECTOR_STATE_DIR = HARNESS_DIR / "run" / "selector-state"
SELECTOR_STATE_PATH = SELECTOR_STATE_DIR / "runtime.json"
SELECTOR_LOCK_PATH = SELECTOR_STATE_DIR / "runtime.lock"
ACTOR_LEASE_DIR = HARNESS_DIR / "run" / "actor-leases"

_ACTIVE_LEASE_STATES = {LEASED, RUNNING, FINALIZING}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    SELECTOR_STATE_DIR.mkdir(parents=True, exist_ok=True)
    ACTOR_LEASE_DIR.mkdir(parents=True, exist_ok=True)


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": _now(), "bindings": {}, "actors": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": _now(), "bindings": {}, "actors": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": _now(), "bindings": {}, "actors": {}}
    payload.setdefault("version", 1)
    payload.setdefault("updated_at", _now())
    payload.setdefault("bindings", {})
    payload.setdefault("actors", {})
    return payload


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _update_state(mutator, *, state_path: Path | None = None, lock_path: Path | None = None) -> Any:
    _ensure_dirs()
    target = Path(state_path or SELECTOR_STATE_PATH)
    lock = Path(lock_path or SELECTOR_LOCK_PATH)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a", encoding="utf-8") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            payload = _read_state(target)
            result = mutator(payload)
            payload["updated_at"] = _now()
            _write_state(target, payload)
            return result
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def round_robin_start_index(
    operator_type: str,
    candidate_count: int,
    *,
    state_path: Path | None = None,
    lock_path: Path | None = None,
) -> int:
    if candidate_count <= 0:
        return 0

    def _mutate(payload: dict[str, Any]) -> int:
        bindings = payload.setdefault("bindings", {})
        entry = dict(bindings.get(operator_type) or {})
        current = int(entry.get("round_robin_cursor", 0) or 0) % candidate_count
        entry["round_robin_cursor"] = (current + 1) % candidate_count
        entry["candidate_count"] = candidate_count
        entry["last_policy"] = "round_robin"
        bindings[operator_type] = entry
        return current

    return int(_update_state(_mutate, state_path=state_path, lock_path=lock_path) or 0)


def record_selection(
    operator_type: str,
    actor_id: str,
    *,
    selection_policy: str = "",
    state_path: Path | None = None,
    lock_path: Path | None = None,
) -> None:
    actor_id = str(actor_id or "").strip()
    operator_type = str(operator_type or "").strip()
    if not actor_id:
        return

    def _mutate(payload: dict[str, Any]) -> None:
        now = _now()
        bindings = payload.setdefault("bindings", {})
        actors = payload.setdefault("actors", {})

        binding_entry = dict(bindings.get(operator_type) or {})
        binding_entry["last_selected_actor"] = actor_id
        binding_entry["last_selected_at"] = now
        binding_entry["selection_count"] = int(binding_entry.get("selection_count", 0) or 0) + 1
        if selection_policy:
            binding_entry["last_policy"] = str(selection_policy)
        bindings[operator_type] = binding_entry

        actor_entry = dict(actors.get(actor_id) or {})
        actor_entry["selection_count"] = int(actor_entry.get("selection_count", 0) or 0) + 1
        actor_entry["last_selected_at"] = now
        by_operator = dict(actor_entry.get("logical_operators") or {})
        op_entry = dict(by_operator.get(operator_type) or {})
        op_entry["selection_count"] = int(op_entry.get("selection_count", 0) or 0) + 1
        op_entry["last_selected_at"] = now
        by_operator[operator_type] = op_entry
        actor_entry["logical_operators"] = by_operator
        actors[actor_id] = actor_entry

    _update_state(_mutate, state_path=state_path, lock_path=lock_path)


def actor_selection_stats(
    actor_id: str,
    *,
    state_path: Path | None = None,
) -> dict[str, Any]:
    payload = _read_state(Path(state_path or SELECTOR_STATE_PATH))
    actors = payload.get("actors") or {}
    return dict(actors.get(str(actor_id or ""), {}) or {})


def actor_active_lease_count(
    actor_id: str,
    *,
    lease_dir: Path | None = None,
) -> int:
    path = Path(lease_dir or ACTOR_LEASE_DIR) / f"{actor_id}.json"
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    state = str((payload or {}).get("state") or "").strip().upper()
    return 1 if state in _ACTIVE_LEASE_STATES else 0


def actor_load_snapshot(
    actor_id: str,
    *,
    state_path: Path | None = None,
    lease_dir: Path | None = None,
) -> dict[str, Any]:
    stats = actor_selection_stats(actor_id, state_path=state_path)
    return {
        "active_lease_count": actor_active_lease_count(actor_id, lease_dir=lease_dir),
        "selection_count": int(stats.get("selection_count", 0) or 0),
        "last_selected_at": str(stats.get("last_selected_at") or ""),
    }
