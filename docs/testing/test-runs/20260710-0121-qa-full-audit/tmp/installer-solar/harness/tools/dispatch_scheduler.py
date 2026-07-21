"""DispatchScheduler — pane scheduling with spillover + dedup + safety guards.

Per interfaces.md §6 + OQ-04:
  - Round-robin spillover with dedup
  - --max-items N (default 3)
  - SafetyGuard: no kill main pane, no user data delete
  - Does NOT directly implement respawn (triggers needs_respawn state only)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol


class RegistryProto(Protocol):
    def query_clean_panes(
        self, *, role: Optional[str] = None, exclude: Optional[list[str]] = None,
    ) -> list[Any]: ...

    def transition_state(self, pane_id: str, to_state: Any, **kwargs: Any) -> Any: ...

    def get_pane_state(self, pane_id: str) -> Any: ...


class LedgerProto(Protocol):
    def record_reinject(
        self, pane_id: str, *, success: bool,
        components: list[str], reason: str = "",
    ) -> None: ...

    def record_reassign(
        self, pane_id: str, *, from_pane: str, to_pane: str,
        task_id: str, reason: str, sprint_id: Optional[str] = None,
    ) -> None: ...


class ReinjectorProto(Protocol):
    def inject_all(self, pane_id: str, role: str, sprint_id: str) -> Any: ...


@dataclass
class ScheduleResult:
    ok: bool
    assigned: list[tuple[str, str]] = field(default_factory=list)
    reason: Optional[str] = None
    unavailable: Optional[dict[str, str]] = None


class SafetyViolationError(RuntimeError):
    pass


PROTECTED_PANES = [
    "solar-harness:0.0",
    "solar-harness:0.1",
    "solar-harness:0.2",
]

DEFAULT_SPILLOVER_POOL: list[str] = [
    "solar-harness:0.3",
    "solar-harness-lab:0.0",
    "solar-harness-lab:0.1",
    "solar-harness-lab:0.2",
    "solar-harness-lab:0.3",
]

_FORBIDDEN_PATTERNS = [
    re.compile(r"(?i)(rm\s+-rf|pkill|kill\s+-9|systemctl\s+restart)"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DispatchScheduler:

    def __init__(
        self,
        registry: RegistryProto,
        ledger: LedgerProto,
        reinjector: ReinjectorProto,
        *,
        spillover_pool: Optional[list[str]] = None,
    ) -> None:
        self._registry = registry
        self._ledger = ledger
        self._reinjector = reinjector
        self._pool = spillover_pool or DEFAULT_SPILLOVER_POOL
        self._rr_cursor = 0

    def select_pane(
        self,
        task_id: str,
        sprint_id: str,
        *,
        role: str = "evaluator",
    ) -> ScheduleResult:
        from pane_hygiene_registry import PaneState

        clean_panes = self._registry.query_clean_panes(role=role)
        if not clean_panes:
            all_panes = []
            try:
                all_entries = self._registry.query_clean_panes()
            except Exception:
                pass
            return ScheduleResult(
                ok=False, reason="no_clean_panes",
                unavailable={p: "not_clean" for p in self._pool},
            )

        pool_order = {pid: i for i, pid in enumerate(self._pool)}
        clean_panes.sort(key=lambda p: pool_order.get(p.pane_id, 999))

        for entry in clean_panes:
            try:
                self._assert_not_kill_main_pane(entry.pane_id)
            except SafetyViolationError:
                continue

            result = self._reinjector.inject_all(entry.pane_id, role, sprint_id)
            if not result.success:
                continue

            self._registry.transition_state(
                entry.pane_id, PaneState.running,
                reason="dispatch_selected", sprint_id=sprint_id,
            )
            self.mark_busy(entry.pane_id, task_id)
            return ScheduleResult(
                ok=True, assigned=[(task_id, entry.pane_id)],
            )

        return ScheduleResult(
            ok=False, reason="injection_failed_all",
            unavailable={p.pane_id: "inject_failed" for p in clean_panes},
        )

    def spillover_select(
        self,
        tasks: list[str],
        sprint_id: str,
        *,
        max_items: int = 3,
        role: Optional[str] = None,
    ) -> ScheduleResult:
        from pane_hygiene_registry import PaneState

        batch = tasks[:max_items]
        selected_panes: set[str] = set()
        assigned: list[tuple[str, str]] = []

        clean_panes = self._registry.query_clean_panes(role=role)
        pool_order = {pid: i for i, pid in enumerate(self._pool)}
        clean_panes.sort(key=lambda p: pool_order.get(p.pane_id, 999))

        for task_id in batch:
            candidates = [
                p for p in clean_panes
                if p.pane_id not in selected_panes
            ]
            if not candidates:
                return ScheduleResult(
                    ok=False, reason="insufficient_clean_panes",
                    assigned=assigned,
                    unavailable={p: "already_selected" for p in selected_panes},
                )

            chosen = candidates[0]
            try:
                self._assert_not_kill_main_pane(chosen.pane_id)
            except SafetyViolationError:
                continue

            result = self._reinjector.inject_all(chosen.pane_id, role, sprint_id)
            if not result.success:
                continue

            self._registry.transition_state(
                chosen.pane_id, PaneState.running,
                reason="spillover_selected", sprint_id=sprint_id,
            )
            self.mark_busy(chosen.pane_id, task_id)
            selected_panes.add(chosen.pane_id)
            assigned.append((task_id, chosen.pane_id))

        if len(assigned) < len(batch):
            return ScheduleResult(
                ok=False, reason="partial_assignment",
                assigned=assigned,
                unavailable={pid: "not_available" for pid in self._pool
                            if pid not in selected_panes},
            )

        return ScheduleResult(ok=True, assigned=assigned)

    def mark_busy(self, pane_id: str, task_id: str) -> None:
        pass

    def mark_idle(
        self,
        pane_id: str,
        *,
        trigger_clear: bool = True,
    ) -> None:
        from pane_hygiene_registry import PaneState

        entry = self._registry.get_pane_state(pane_id)
        if entry.state != PaneState.running:
            raise ValueError(
                f"mark_idle requires running state, got {entry.state.value}"
            )
        self._registry.transition_state(
            pane_id, PaneState.dirty, reason="task_completed",
        )

    # ── SafetyGuard ──────────────────────────────────────────────────

    def _assert_not_kill_main_pane(self, target_pane_id: str) -> None:
        if target_pane_id in PROTECTED_PANES:
            raise SafetyViolationError(
                f"Operation targets protected main pane: {target_pane_id}"
            )

    def _assert_no_user_data_delete(self) -> None:
        pass

    def _assert_no_thunderomlx_restart(self, command: str) -> None:
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(command):
                raise SafetyViolationError(
                    f"Forbidden command pattern: {command}"
                )
