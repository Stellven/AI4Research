"""Real browser backend for social X profile capture.

This adapts the Browser three-layer control plane into the synchronous
six-method surface expected by ``BrowserLeaseClient``.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXTRA_PYTHON_PACKAGE_DIRS = [
    Path(os.environ.get("SOLAR_BROWSER_PYTHON_PACKAGES", "")).expanduser()
    if os.environ.get("SOLAR_BROWSER_PYTHON_PACKAGES")
    else None,
    Path.home() / ".solar" / "harness" / "python-packages" / "browser",
]
for package_dir in EXTRA_PYTHON_PACKAGE_DIRS:
    if package_dir and package_dir.exists() and str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))

import browser_job_runtime as bjrt
from browser import runtime_control as brtc
from browser.profile_lease import ProfileLease
from playwright.sync_api import sync_playwright


DEFAULT_USER_DATA_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
DEFAULT_PROFILE_DIRECTORY = "Profile 1"
DEFAULT_ALLOWED_HOSTS = {"x.com", "twitter.com", "mobile.twitter.com"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class RealBrowserBackend:
    """Synchronous Playwright backend using the shared browser profile registry."""

    def __init__(
        self,
        *,
        profile_directory: str | None = None,
        user_data_dir: str | Path | None = None,
        headless: bool | None = None,
        request_dir: str | Path | None = None,
        task_id: str | None = None,
    ) -> None:
        self.profile_directory = str(
            profile_directory
            or os.environ.get("BROWSER_AGENT_PROFILE_DIRECTORY")
            or os.environ.get("SOCIAL_BROWSER_PROFILE_DIRECTORY")
            or DEFAULT_PROFILE_DIRECTORY
        )
        self.user_data_dir = Path(
            user_data_dir
            or os.environ.get("BROWSER_AGENT_USER_DATA_DIR")
            or os.environ.get("SOCIAL_BROWSER_USER_DATA_DIR")
            or DEFAULT_USER_DATA_DIR
        ).expanduser()
        if headless is None:
            force_headed = _env_flag("BROWSER_AGENT_FORCE_HEADED", False) or _env_flag("SOCIAL_BROWSER_FORCE_HEADED", False)
            headless = False if force_headed else _env_flag("SOCIAL_BROWSER_HEADLESS", _env_flag("BROWSER_AGENT_HEADLESS", True))
        self.headless = bool(headless)
        self.request_dir = Path(
            request_dir
            or os.environ.get("BROWSER_AGENT_REQUEST_DIR")
            or os.environ.get("SOCIAL_BROWSER_REQUEST_DIR")
            or Path.home() / ".solar" / "harness" / "run" / "social-browser-backend-x" / str(int(time.time()))
        ).expanduser()
        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.profile_id = str(os.environ.get("BROWSER_AGENT_PROFILE_ID") or brtc.default_profile_id("x", profile_directory=self.profile_directory))
        self.task_id = str(task_id or os.environ.get("TASK_ID") or f"social-browser-{int(time.time())}")
        self._lease_manager = ProfileLease()
        self._profile_lease_acquired = False
        self._staged_dir: str | Path | None = None
        self._cleanup_dir: Optional[Path] = None
        self._playwright = None
        self._context = None
        self._page = None

    def _write_json(self, name: str, payload: dict[str, Any]) -> None:
        path = self.request_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _ensure_started(self) -> None:
        if self._page is not None:
            return
        lease = self._lease_manager.acquire(
            profile_id=self.profile_id,
            task_id=self.task_id,
            runtime="social_browser_backend_x",
            mode="exclusive",
            allowed_attach=True,
        )
        if not lease.get("acquired"):
            raise RuntimeError("browser_profile_lease_acquire_failed:" + json.dumps(lease, ensure_ascii=False))
        self._profile_lease_acquired = True
        staged_dir, cleanup_dir = bjrt._stage_browser_profile(self.user_data_dir, self.profile_directory)
        if self.user_data_dir and not staged_dir:
            raise RuntimeError("protected_browser_profile_cache_missing")
        self._staged_dir = staged_dir
        self._cleanup_dir = cleanup_dir
        self._playwright = sync_playwright().start()
        args = [
            f"--profile-directory={self.profile_directory}",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-features=Translate",
        ]
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(staged_dir or self.user_data_dir),
            channel="chrome",
            headless=self.headless,
            args=args,
            viewport={"width": 1440, "height": 1200},
            locale="en-US",
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._write_json(
            "browser-runtime.json",
            {
                "profile_id": self.profile_id,
                "profile_directory": self.profile_directory,
                "headless": self.headless,
                "request_dir": str(self.request_dir),
            },
        )

    def _assert_allowed_url(self, url: str) -> None:
        from urllib.parse import urlparse

        parsed = urlparse(str(url or ""))
        host = parsed.hostname or ""
        if host not in DEFAULT_ALLOWED_HOSTS:
            raise ValueError(f"disallowed_social_browser_host:{host}")

    def open(self, url: str) -> Dict[str, Any]:
        self._assert_allowed_url(url)
        self._ensure_started()
        self._page.goto(url, wait_until="domcontentloaded", timeout=int(os.environ.get("SOCIAL_BROWSER_NAV_TIMEOUT_MS") or "30000"))
        self._page.wait_for_timeout(int(os.environ.get("SOCIAL_BROWSER_SETTLE_MS") or "2500"))
        return {"ok": True, "url": self._page.url}

    def wait(self, selector: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        self._ensure_started()
        try:
            self._page.wait_for_selector(selector, timeout=timeout_ms)
            return {"ok": True, "selector": selector}
        except Exception as exc:  # noqa: BLE001
            html = self._page.content() if self._page is not None else ""
            login_required = (
                ("data-testid=\"loginButton\"" in html)
                or ("Sign in with Google" in html)
                or ("Log in" in html and "Sign up" in html and "/i/flow/login" in html)
            )
            state = {
                "ok": False,
                "selector": selector,
                "error": f"{type(exc).__name__}: {exc}",
                "url": self._page.url if self._page is not None else "",
                "title": self._page.title() if self._page is not None else "",
                "login_required": login_required,
            }
            self._write_json("wait-failed.json", state)
            try:
                (self.request_dir / "wait-failed.html").write_text(html, encoding="utf-8")
            except Exception:
                pass
            if login_required:
                raise RuntimeError("x_login_required_or_profile_session_missing")
            raise RuntimeError("browser_wait_failed:" + state["error"])

    def scroll(self, delta_y: int = 800) -> Dict[str, Any]:
        self._ensure_started()
        self._page.mouse.wheel(0, int(delta_y or 800))
        self._page.wait_for_timeout(int(os.environ.get("SOCIAL_BROWSER_SCROLL_SETTLE_MS") or "1000"))
        return {"ok": True, "delta_y": int(delta_y or 800)}

    def dom_extract(self) -> Dict[str, Any]:
        self._ensure_started()
        html = self._page.content()
        dom_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        return {
            "ok": True,
            "html": html,
            "dom_hash": dom_hash,
            "url": self._page.url,
            "title": self._page.title(),
        }

    def screenshot(self, path: str) -> Dict[str, Any]:
        self._ensure_started()
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            self._page.screenshot(path=str(out), full_page=True)
            return {"ok": True, "path": str(out), "kind": "image"}
        payload = {"url": self._page.url, "title": self._page.title(), "captured_at": time.time()}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(out), "kind": "json"}

    def release(self) -> Dict[str, Any]:
        errors: list[str] = []
        try:
            if self._context is not None:
                self._context.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"context:{type(exc).__name__}:{exc}")
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"playwright:{type(exc).__name__}:{exc}")
        if self._profile_lease_acquired:
            try:
                self._lease_manager.release(self.profile_id, self.task_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"profile_lease:{type(exc).__name__}:{exc}")
        if self._cleanup_dir is not None:
            shutil.rmtree(self._cleanup_dir, ignore_errors=True)
        self._context = None
        self._page = None
        self._playwright = None
        return {"ok": not errors, "errors": errors}
