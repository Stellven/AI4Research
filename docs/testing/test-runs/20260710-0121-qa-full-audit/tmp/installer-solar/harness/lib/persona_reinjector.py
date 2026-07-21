"""PersonaReinjector — inject persona/runtime_policy/solar_context into TUI panes.

Per interfaces.md §4 + OQ-03:
  - clean→running: full injection (persona + runtime_policy + solar_context)
  - same session: only update solar_context (skip persona/policy)
  - cross session/sprint: full re-injection
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol


class ClearLedgerProto(Protocol):
    def record_reinject(
        self, pane_id: str, *, before_state: str, after_state: str,
        success: bool, reason: str, sprint_id: Optional[str] = None,
    ) -> None: ...


class RegistryProto(Protocol):
    def update_context_fields(
        self, pane_id: str, *, context_hash: Optional[str] = None,
        persona: Optional[str] = None,
        runtime_policy_hash: Optional[str] = None,
    ) -> object: ...

    def get_pane_state(self, pane_id: str) -> object: ...


@dataclass
class InjectionResult:
    pane_id: str
    success: bool
    injected: list[str]
    failed_at: Optional[str]
    reason: str
    ts: str


INJECT_SETTLE_MS: float = 0.5
TEMPLATE_BASE = str(Path.home() / ".solar" / "harness" / "templates")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_trunc(text: str, length: int = 12) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:length]


def _tmux_send_keys(pane_id: str, text: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", pane_id, text, "Enter"],
        capture_output=True, timeout=5,
    )


def _resolve_persona_template(template_base: str | Path, role: str) -> Path:
    base = Path(template_base)
    name = f"{role}.md"
    candidates = [
        base / "persona" / name,
        base.parent / "personas" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Persona template not found for {role!r}; searched: {searched}")


class PersonaReinjector:

    def __init__(
        self,
        registry: RegistryProto,
        ledger: ClearLedgerProto,
        *,
        template_base: Optional[str] = None,
        send_fn: Optional[Callable[[str, str], None]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        capture_fn: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._registry = registry
        self._ledger = ledger
        self._template_base = template_base or TEMPLATE_BASE
        self._send = send_fn or _tmux_send_keys
        self._sleep = sleep_fn or __import__("time").sleep
        self._capture = capture_fn or (lambda pid: "")

    def inject_persona(self, pane_id: str, role: str) -> bool:
        template_path = _resolve_persona_template(self._template_base, role)
        content = template_path.read_text()
        self._send(pane_id, content)
        self._sleep(INJECT_SETTLE_MS)
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        return self.verify_injection(pane_id, "persona", first_line[:30])

    def inject_runtime_policy(self, pane_id: str) -> bool:
        template_path = Path(self._template_base) / "runtime_policy.md"
        if not template_path.exists():
            raise FileNotFoundError(f"Runtime policy template not found: {template_path}")
        content = template_path.read_text()
        self._send(pane_id, content)
        self._sleep(INJECT_SETTLE_MS)
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        return self.verify_injection(pane_id, "runtime_policy", first_line[:30])

    def inject_solar_context(
        self,
        pane_id: str,
        *,
        sprint_id: str,
        context_template_path: Optional[str] = None,
    ) -> bool:
        if context_template_path:
            template_path = Path(context_template_path)
        else:
            template_path = Path(self._template_base) / f"solar_context_{sprint_id}.md"
        if not template_path.exists():
            raise FileNotFoundError(f"Solar context template not found: {template_path}")
        content = template_path.read_text()
        self._send(pane_id, content)
        self._sleep(INJECT_SETTLE_MS)
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        return self.verify_injection(pane_id, "solar_context", first_line[:30])

    def inject_all(
        self,
        pane_id: str,
        role: str,
        sprint_id: str,
    ) -> InjectionResult:
        ts = _utc_now()
        injected: list[str] = []

        # Step 1: Persona
        try:
            if not self.inject_persona(pane_id, role):
                self._ledger.record_reinject(
                    pane_id, before_state="clean", after_state="clean",
                    success=False, reason="persona_verify_failed", sprint_id=sprint_id,
                )
                return InjectionResult(pane_id, False, injected, "persona",
                                       "persona_verify_failed", ts)
            injected.append("persona")
        except FileNotFoundError as e:
            self._ledger.record_reinject(
                pane_id, before_state="clean", after_state="clean",
                success=False, reason=f"persona_template_missing: {e}",
                sprint_id=sprint_id,
            )
            return InjectionResult(pane_id, False, injected, "persona",
                                   str(e), ts)

        # Step 2: Runtime Policy
        try:
            if not self.inject_runtime_policy(pane_id):
                self._ledger.record_reinject(
                    pane_id, before_state="clean", after_state="clean",
                    success=False, reason="runtime_policy_verify_failed",
                    sprint_id=sprint_id,
                )
                return InjectionResult(pane_id, False, injected, "runtime_policy",
                                       "runtime_policy_verify_failed", ts)
            injected.append("runtime_policy")
        except FileNotFoundError as e:
            self._ledger.record_reinject(
                pane_id, before_state="clean", after_state="clean",
                success=False, reason=f"runtime_policy_template_missing: {e}",
                sprint_id=sprint_id,
            )
            return InjectionResult(pane_id, False, injected, "runtime_policy",
                                   str(e), ts)

        # Step 3: Solar Context
        try:
            if not self.inject_solar_context(pane_id, sprint_id=sprint_id):
                self._ledger.record_reinject(
                    pane_id, before_state="clean", after_state="clean",
                    success=False, reason="solar_context_verify_failed",
                    sprint_id=sprint_id,
                )
                return InjectionResult(pane_id, False, injected, "solar_context",
                                       "solar_context_verify_failed", ts)
            injected.append("solar_context")
        except FileNotFoundError as e:
            self._ledger.record_reinject(
                pane_id, before_state="clean", after_state="clean",
                success=False, reason=f"solar_context_template_missing: {e}",
                sprint_id=sprint_id,
            )
            return InjectionResult(pane_id, False, injected, "solar_context",
                                   str(e), ts)

        # Success: update registry context fields
        persona_hash = _sha256_trunc(role)
        policy_hash = _sha256_trunc("runtime_policy")
        context_hash = _sha256_trunc(sprint_id)
        self._registry.update_context_fields(
            pane_id, context_hash=context_hash,
            persona=role, runtime_policy_hash=policy_hash,
        )
        self._ledger.record_reinject(
            pane_id, before_state="clean", after_state="running",
            success=True, reason="all_components_ok", sprint_id=sprint_id,
        )
        return InjectionResult(pane_id, True, injected, None, "ok", ts)

    def verify_injection(
        self,
        pane_id: str,
        component: str,
        expected_keyword: str,
    ) -> bool:
        if not expected_keyword:
            return True
        output = self._capture(pane_id)
        return expected_keyword in output
