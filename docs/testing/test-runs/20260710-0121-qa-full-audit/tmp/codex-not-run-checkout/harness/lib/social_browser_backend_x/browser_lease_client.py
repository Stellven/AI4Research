"""BrowserLeaseClient — 6-method API per S02 A1 §3 interface 1.

Methods (per O2): open / wait / scroll / dom_extract / screenshot / release.

Per S03 design §C2:
  - Real mode dispatches to `solar.physical_operator.browser.lease(...)`.
  - Mock mode (BROWSER_AGENT_MOCK_MODE=1 or HardBlockerGuard reports the
    upstream lease unavailable) dispatches to `MockBrowserBackend`.
  - The real-mode backend hook is an injection point; until hard_blocker
    `sprint-20260525-browser-agent-global-operator-cutover` passes, calling
    a real backend raises `OperatorNotReady`. This is intentional — S03
    Stop Rule "不真跑 browser_agent".
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Protocol

from .mock_browser_fixture import (
    MOCK_MODE_ENV_VAR,
    MockBrowserBackend,
    mock_mode_enabled,
)

logger = logging.getLogger(__name__)

# 6 method names — single source of truth, used by tests + introspection
BROWSER_LEASE_METHODS = (
    "open",
    "wait",
    "scroll",
    "dom_extract",
    "screenshot",
    "release",
)


class OperatorNotReady(RuntimeError):
    """Raised when the physical browser operator lease is not available.

    Triggered when:
      - real-mode is requested but no real-backend hook is wired, or
      - HardBlockerGuard reports the upstream blocker is unmet, or
      - the operator lease layer itself raises.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"OperatorNotReady: {reason}")


class _BrowserBackend(Protocol):
    """Structural protocol the 6 methods must satisfy.

    Both `MockBrowserBackend` and any future real-lease wrapper implement
    this — `BrowserLeaseClient` does not care which.
    """

    def open(self, url: str) -> Dict[str, Any]: ...
    def wait(self, selector: str, timeout_ms: int = 5000) -> Dict[str, Any]: ...
    def scroll(self, delta_y: int = 800) -> Dict[str, Any]: ...
    def dom_extract(self) -> Dict[str, Any]: ...
    def screenshot(self, path: str) -> Dict[str, Any]: ...
    def release(self) -> Dict[str, Any]: ...


def _default_real_backend_factory() -> _BrowserBackend:
    """Default real-backend factory using Solar's browser profile control plane."""
    try:
        from .real_browser_backend import RealBrowserBackend
    except Exception as exc:  # noqa: BLE001
        raise OperatorNotReady(f"real browser backend import failed: {type(exc).__name__}: {exc}") from exc
    try:
        return RealBrowserBackend()
    except OperatorNotReady:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OperatorNotReady(f"real browser backend init failed: {type(exc).__name__}: {exc}") from exc


class BrowserLeaseClient:
    """6-method browser lease client.

    Constructor parameters:
        backend: pre-instantiated backend (mock or real). If None, the
                 client picks based on env / blocker_guard.
        blocker_guard: optional zero-arg callable; if it returns False,
                       mock-mode is used regardless of env.
        real_backend_factory: zero-arg callable to produce a real backend.
                              Default raises OperatorNotReady.
        mock_backend_factory: zero-arg callable to produce a mock backend.
                              Default = `MockBrowserBackend()`.
    """

    def __init__(
        self,
        backend: Optional[_BrowserBackend] = None,
        *,
        blocker_guard: Optional[Callable[[], bool]] = None,
        real_backend_factory: Callable[[], _BrowserBackend] = _default_real_backend_factory,
        mock_backend_factory: Callable[[], _BrowserBackend] = MockBrowserBackend,
    ) -> None:
        self._blocker_guard = blocker_guard
        self._real_factory = real_backend_factory
        self._mock_factory = mock_backend_factory

        if backend is not None:
            self._backend: _BrowserBackend = backend
            self._is_mock = isinstance(backend, MockBrowserBackend)
            self._mode_reason = "explicit_backend"
        else:
            self._backend, self._is_mock, self._mode_reason = self._pick_backend()

    # ---- backend resolution -------------------------------------------

    def _pick_backend(self) -> "tuple[_BrowserBackend, bool, str]":
        if mock_mode_enabled():
            return self._mock_factory(), True, "env_mock_mode"
        if self._blocker_guard is not None:
            try:
                ok = bool(self._blocker_guard())
            except Exception as exc:  # noqa: BLE001 — defensive: blocker probes are external
                logger.warning("blocker_guard raised %s — defaulting to mock", exc)
                return self._mock_factory(), True, f"blocker_guard_exception:{type(exc).__name__}"
            if not ok:
                return self._mock_factory(), True, "blocker_guard_unmet"
        # Real-mode requested. The factory will raise OperatorNotReady if
        # the operator lease is not actually wired.
        return self._real_factory(), False, "real_mode"

    # ---- 6 methods ----------------------------------------------------

    def open(self, url: str) -> Dict[str, Any]:
        return self._backend.open(url)

    def wait(self, selector: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        return self._backend.wait(selector, timeout_ms)

    def scroll(self, delta_y: int = 800) -> Dict[str, Any]:
        return self._backend.scroll(delta_y)

    def dom_extract(self) -> Dict[str, Any]:
        return self._backend.dom_extract()

    def screenshot(self, path: str) -> Dict[str, Any]:
        return self._backend.screenshot(path)

    def release(self) -> Dict[str, Any]:
        return self._backend.release()

    # ---- introspection ------------------------------------------------

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    @property
    def mode_reason(self) -> str:
        return self._mode_reason

    @property
    def backend(self) -> _BrowserBackend:
        return self._backend

    @classmethod
    def method_names(cls) -> tuple:
        return BROWSER_LEASE_METHODS
