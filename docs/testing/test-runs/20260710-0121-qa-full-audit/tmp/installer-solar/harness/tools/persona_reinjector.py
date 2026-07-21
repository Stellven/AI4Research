"""PersonaReinjector — inject persona + runtime policy + solar context into TUI panes.

Per interfaces.md §4 + OQ-03: clean→running full inject; same session skip persona/policy.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol


class LedgerWriterProto(Protocol):
    def record_reinject(self, pane_id: str, *, success: bool,
                        components: list[str], reason: str = "") -> None: ...


class RegistryProto(Protocol):
    def update_context_fields(self, pane_id: str, *,
                              context_hash: Optional[str] = None,
                              persona: Optional[str] = None,
                              runtime_policy_hash: Optional[str] = None) -> None: ...


@dataclass
class InjectionResult:
    pane_id: str
    success: bool
    injected: list[str] = field(default_factory=list)
    failed_at: Optional[str] = None
    reason: str = ""
    ts: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_truncated(content: str, length: int = 12) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:length]


def _default_send(pane_id: str, text: str) -> None:
    import subprocess
    subprocess.run(
        ["tmux", "send-keys", "-t", pane_id, text, "Enter"],
        capture_output=True, timeout=5,
    )


def _default_capture(pane_id: str) -> str:
    import subprocess
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", "-50"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout


def _resolve_persona_template(template_base: Path, role: str) -> Path:
    name = f"{role}.md"
    candidates = [
        template_base / "persona" / name,
        template_base.parent / "personas" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Persona template not found for {role!r}; searched: {searched}")


class PersonaReinjector:
    INJECT_SETTLE_S: float = 0.5

    def __init__(
        self,
        registry: RegistryProto,
        ledger: LedgerWriterProto,
        *,
        template_base: Optional[str] = None,
        send_fn: Optional[Callable[[str, str], None]] = None,
        capture_fn: Optional[Callable[[str], str]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._registry = registry
        self._ledger = ledger
        self._template_base = Path(template_base or "~/.solar/harness/templates").expanduser()
        self._send = send_fn or _default_send
        self._capture = capture_fn or _default_capture
        self._sleep = sleep_fn or time.sleep

    def inject_persona(self, pane_id: str, role: str) -> bool:
        template_path = _resolve_persona_template(self._template_base, role)
        content = template_path.read_text()
        self._send(pane_id, content)
        self._sleep(self.INJECT_SETTLE_S)
        keyword = content.strip().split("\n")[0][:80] if content.strip() else role
        return self.verify_injection(pane_id, "persona", keyword)

    def inject_runtime_policy(self, pane_id: str) -> bool:
        template_path = self._template_base / "runtime_policy.md"
        content = template_path.read_text()
        self._send(pane_id, content)
        self._sleep(self.INJECT_SETTLE_S)
        keyword = content.strip().split("\n")[0][:80] if content.strip() else "runtime_policy"
        return self.verify_injection(pane_id, "runtime_policy", keyword)

    def inject_solar_context(
        self,
        pane_id: str,
        *,
        sprint_id: str,
        context_template_path: Optional[str] = None,
    ) -> bool:
        if context_template_path:
            path = Path(context_template_path)
        else:
            path = self._template_base / f"solar_context_{sprint_id}.md"
        content = path.read_text()
        self._send(pane_id, content)
        self._sleep(self.INJECT_SETTLE_S)
        keyword = content.strip().split("\n")[0][:80] if content.strip() else "solar_context"
        return self.verify_injection(pane_id, "solar_context", keyword)

    def inject_all(
        self,
        pane_id: str,
        role: str,
        sprint_id: str,
    ) -> InjectionResult:
        components = ["persona", "runtime_policy", "solar_context"]
        injected = []
        ts = _utc_now()

        result = self.inject_persona(pane_id, role)
        if not result:
            self._ledger.record_reinject(
                pane_id, success=False, components=injected,
                reason="persona_inject_failed",
            )
            return InjectionResult(pane_id, False, injected, "persona", "inject_failed", ts)
        injected.append("persona")

        result = self.inject_runtime_policy(pane_id)
        if not result:
            self._ledger.record_reinject(
                pane_id, success=False, components=injected,
                reason="runtime_policy_inject_failed",
            )
            return InjectionResult(pane_id, False, injected, "runtime_policy", "inject_failed", ts)
        injected.append("runtime_policy")

        result = self.inject_solar_context(pane_id, sprint_id=sprint_id)
        if not result:
            self._ledger.record_reinject(
                pane_id, success=False, components=injected,
                reason="solar_context_inject_failed",
            )
            return InjectionResult(pane_id, False, injected, "solar_context", "inject_failed", ts)
        injected.append("solar_context")

        persona_hash = _hash_truncated(role)
        policy_hash = _hash_truncated("runtime_policy")
        context_hash = _hash_truncated(sprint_id)
        self._registry.update_context_fields(
            pane_id, context_hash=context_hash,
            persona=role, runtime_policy_hash=policy_hash,
        )
        self._ledger.record_reinject(
            pane_id, success=True, components=injected, reason="ok",
        )
        return InjectionResult(pane_id, True, injected, reason="ok", ts=ts)

    def verify_injection(
        self,
        pane_id: str,
        component: str,
        expected_keyword: str,
    ) -> bool:
        output = self._capture(pane_id)
        return expected_keyword in output
