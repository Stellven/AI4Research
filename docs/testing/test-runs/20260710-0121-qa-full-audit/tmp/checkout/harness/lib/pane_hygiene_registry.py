"""PaneHygieneRegistry — 6-state FSM + atomic write + flock (per D1+OQ-01)."""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PaneState(str, Enum):
    clean = "clean"
    running = "running"
    dirty = "dirty"
    cooling = "cooling"
    needs_recover = "needs_recover"
    needs_respawn = "needs_respawn"


_LEGAL_TRANSITIONS: dict[PaneState, set[PaneState]] = {
    PaneState.clean: {PaneState.running},
    PaneState.running: {PaneState.dirty, PaneState.needs_recover},
    PaneState.dirty: {PaneState.clean, PaneState.cooling, PaneState.needs_recover},
    PaneState.cooling: {PaneState.needs_recover, PaneState.dirty},
    PaneState.needs_recover: {PaneState.running, PaneState.needs_respawn},
    PaneState.needs_respawn: {PaneState.running},
}

_FORBIDDEN_TRANSITIONS = [
    (PaneState.clean, PaneState.dirty),
    (PaneState.running, PaneState.clean),
    (PaneState.cooling, PaneState.running),
    (PaneState.needs_respawn, PaneState.clean),
]


class IllegalTransitionError(ValueError):
    def __init__(self, pane_id: str, from_state: PaneState, to_state: PaneState) -> None:
        self.pane_id = pane_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal transition for {pane_id}: {from_state.value} → {to_state.value}"
        )


@dataclass
class PaneEntry:
    pane_id: str
    state: PaneState
    pane_role: str
    last_state_transition_at: str
    last_transition_trigger: str = ""
    dispatch_id: Optional[str] = None
    persona: Optional[str] = None
    runtime_policy_hash: Optional[str] = None
    context_hash: Optional[str] = None
    session_id: Optional[str] = None
    last_task_sprint_id: Optional[str] = None
    last_task_dispatch_group: Optional[str] = None
    last_task_completed_at: Optional[str] = None
    consecutive_fail_count: int = 0
    clear_attempts: int = 0
    cooldown_until: Optional[str] = None
    cooldown_reason: Optional[str] = None
    respawn_count: int = 0
    last_respawned_at: Optional[str] = None
    pane_index: Optional[int] = None
    session_name: Optional[str] = None
    model: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PaneHygieneRegistry:
    SCHEMA_VERSION = "solar.pane_hygiene.v1"

    def __init__(self, registry_path: str) -> None:
        self._path = registry_path
        self._lock_path = registry_path + ".lock"
        self._cache: dict[str, PaneEntry] = {}
        if os.path.exists(registry_path):
            self._load()
        else:
            self._atomic_write({})

    # ── Read ─────────────────────────────────────────────────────────

    def get_pane_state(self, pane_id: str) -> PaneEntry:
        if pane_id not in self._cache:
            raise KeyError(f"Pane not registered: {pane_id}")
        return self._cache[pane_id]

    def query_clean_panes(
        self,
        *,
        role: Optional[str] = None,
        exclude: Optional[list[str]] = None,
    ) -> list[PaneEntry]:
        exclude_set = set(exclude) if exclude else set()
        results = []
        for entry in sorted(self._cache.values(), key=lambda e: e.pane_id):
            if entry.state != PaneState.clean:
                continue
            if entry.pane_id in exclude_set:
                continue
            if role and entry.pane_role != role:
                continue
            results.append(entry)
        return results

    def list_all_panes(self) -> list[PaneEntry]:
        return sorted(self._cache.values(), key=lambda e: e.pane_id)

    # ── Write ────────────────────────────────────────────────────────

    def register_pane(
        self,
        pane_id: str,
        role: str,
        *,
        initial_state: PaneState = PaneState.clean,
        model: Optional[str] = None,
    ) -> PaneEntry:
        if pane_id in self._cache:
            raise ValueError(f"Pane already registered: {pane_id}")
        entry = PaneEntry(
            pane_id=pane_id,
            state=initial_state,
            pane_role=role,
            last_state_transition_at=_now_iso(),
            last_transition_trigger="register",
            model=model,
        )
        self._cache[pane_id] = entry
        self._persist()
        return entry

    def ensure_pane(
        self,
        pane_id: str,
        role: str,
        *,
        initial_state: PaneState = PaneState.clean,
        model: Optional[str] = None,
    ) -> PaneEntry:
        if pane_id not in self._cache:
            return self.register_pane(
                pane_id,
                role,
                initial_state=initial_state,
                model=model,
            )
        entry = self._cache[pane_id]
        changed = False
        if role and entry.pane_role != role:
            entry.pane_role = role
            changed = True
        if model is not None and entry.model != model:
            entry.model = model
            changed = True
        if changed:
            self._persist()
            entry = self._cache[pane_id]
        return entry

    def unregister_pane(self, pane_id: str) -> None:
        if pane_id not in self._cache:
            raise KeyError(f"Pane not registered: {pane_id}")
        del self._cache[pane_id]
        self._persist()

    def transition_state(
        self,
        pane_id: str,
        to_state: PaneState,
        *,
        reason: str = "",
        sprint_id: Optional[str] = None,
        dispatch_group: Optional[str] = None,
        increment_fail: bool = False,
        reset_fail: bool = False,
    ) -> PaneEntry:
        if pane_id not in self._cache:
            raise KeyError(f"Pane not registered: {pane_id}")
        entry = self._cache[pane_id]
        from_state = entry.state
        if to_state not in _LEGAL_TRANSITIONS.get(from_state, set()):
            raise IllegalTransitionError(pane_id, from_state, to_state)
        entry.state = to_state
        entry.last_state_transition_at = _now_iso()
        entry.last_transition_trigger = reason or "transition"
        if sprint_id:
            entry.last_task_sprint_id = sprint_id
        if dispatch_group:
            entry.last_task_dispatch_group = dispatch_group
        if increment_fail:
            entry.consecutive_fail_count += 1
        if reset_fail:
            entry.consecutive_fail_count = 0
        if to_state in (PaneState.clean, PaneState.running):
            entry.clear_attempts = 0
        self._persist()
        return entry

    def update_context_fields(
        self,
        pane_id: str,
        *,
        context_hash: Optional[str] = None,
        persona: Optional[str] = None,
        runtime_policy_hash: Optional[str] = None,
    ) -> PaneEntry:
        if pane_id not in self._cache:
            raise KeyError(f"Pane not registered: {pane_id}")
        entry = self._cache[pane_id]
        if context_hash is not None:
            entry.context_hash = context_hash
        if persona is not None:
            entry.persona = persona
        if runtime_policy_hash is not None:
            entry.runtime_policy_hash = runtime_policy_hash
        self._persist()
        return entry

    # ── Persistence ──────────────────────────────────────────────────

    def _persist(self) -> None:
        data = {k: asdict(v) for k, v in self._cache.items()}
        for v in data.values():
            v["state"] = v["state"].value if isinstance(v["state"], PaneState) else v["state"]
        self._atomic_write(data)

    def _atomic_write(self, data: dict) -> None:
        tmp_path = self._path + ".tmp"
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._lock_path, "w") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                with open(tmp_path, "w") as f:
                    json.dump(data, f, indent=2, default=str)
                os.replace(tmp_path, self._path)
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
        self._save_cache(data)

    def _save_cache(self, data: dict) -> None:
        for k, v in data.items():
            if isinstance(v.get("state"), str):
                v["state"] = PaneState(v["state"])
        self._cache = {k: PaneEntry(**v) for k, v in data.items()}

    def _load(self) -> None:
        with open(self._path) as f:
            data = json.load(f)
        self._save_cache(data)
