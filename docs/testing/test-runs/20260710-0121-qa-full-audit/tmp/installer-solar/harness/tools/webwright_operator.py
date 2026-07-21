#!/usr/bin/env python3
"""Command backend adapter for Webwright Playwright logical operator tasks.

Delegates real execution to ``lib/webwright_adapter.py`` to keep operator and
dispatch control aligned with shared runtime policy.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from browser import runtime_control as brtc  # noqa: E402
from browser.executors.webwright_bridge import (  # noqa: E402
    apply_webwright_bridge_env,
    prepare_webwright_bridge,
)
import operator_flow_control as ofc  # noqa: E402

DEFAULT_OPERATOR_ID = "op.browser.webwright.playwright.01"
DEFAULT_BROWSER_USE_PYTHON = Path.home() / ".claude" / "mcp-servers" / "browser-use" / ".venv" / "bin" / "python"
DEFAULT_OUTPUT_ROOT = ROOT / "runs"
DEFAULT_ADAPTER = ROOT / "lib" / "webwright_adapter.py"


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _task_dir(envelope: dict[str, Any] | None = None) -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    env = envelope or {}
    dispatch_id = str(
        env.get("dispatch_id")
        or os.environ.get("DISPATCH_ID")
        or os.environ.get("SOLAR_DISPATCH_ID")
        or f"webwright-{int(time.time())}"
    ).strip()
    if not dispatch_id:
        dispatch_id = f"webwright-{int(time.time())}"

    base_root = Path(
        str(env.get("output_dir") or os.environ.get("WEBWRIGHT_OUTPUT_ROOT") or str(DEFAULT_OUTPUT_ROOT))
    ).expanduser()
    base_root.mkdir(parents=True, exist_ok=True)
    path = base_root / dispatch_id / "webwright"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_url(text: str) -> str:
    """Extract a target URL from the objective or prompt, default to 知乎 if none found."""
    text_lower = text.lower()
    if "zhihu" in text_lower or "知乎" in text_lower:
        return "https://www.zhihu.com"
    
    # Try regex URL match
    match = re.search(r'https?://[^\s"\'()]+', text)
    if match:
        return match.group(0)
    
    # Check domain patterns
    match_domain = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if match_domain:
        return f"https://{match_domain.group(1)}"
        
    return "https://www.zhihu.com"


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    request = {}
    objective = str(envelope.get("objective") or envelope.get("prompt") or "").strip()
    explicit_profile_id = str(
        envelope.get("browser_profile_id")
        or envelope.get("profile_id")
        or ""
    ).strip()
    request["objective"] = objective
    request["url"] = str(envelope.get("start_url") or _extract_url(objective))
    request["dispatch_id"] = str(
        envelope.get("dispatch_id")
        or os.environ.get("DISPATCH_ID")
        or os.environ.get("SOLAR_DISPATCH_ID")
        or (task_dir.parent.name if task_dir else "")
    ).strip() or f"webwright-{int(time.time())}"
    request["timeout_seconds"] = int(envelope.get("timeout_seconds") or 300)
    request["max_retries"] = int(envelope.get("max_retries") or 3)
    request["output_dir"] = str(envelope.get("output_dir") or str(task_dir or Path.cwd()))
    request["browser_profile_id"] = explicit_profile_id
    request["browser_service"] = str(
        envelope.get("browser_service")
        or (explicit_profile_id.split("/", 1)[0] if "/" in explicit_profile_id else "")
    ).strip().lower()
    request["profile_mode"] = str(envelope.get("profile_mode") or "storage_state_clone").strip().lower()
    return request


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "operator_id": DEFAULT_OPERATOR_ID,
        "success_cooldown_seconds": 60,
        "rate_limit_cooldown_seconds": 600,
        "auth_cooldown_seconds": 3600,
        "defer_on_cooldown": True,
        "defer_on_auth": True,
    }


def run_request(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    python_bin = str(DEFAULT_BROWSER_USE_PYTHON) if DEFAULT_BROWSER_USE_PYTHON.exists() else sys.executable
    if not DEFAULT_ADAPTER.exists():
        raise RuntimeError(f"webwright adapter missing: {DEFAULT_ADAPTER}")
    if not task_dir.exists():
        task_dir.mkdir(parents=True, exist_ok=True)

    dispatch_id = str(request.get("dispatch_id") or f"webwright-{int(time.time())}")
    command = [
        python_bin,
        str(DEFAULT_ADAPTER),
        "run",
        "--task",
        request["objective"],
        "--start-url",
        request["url"],
        "--dispatch-id",
        dispatch_id,
        "--out",
        str(task_dir),
        "--json",
    ]

    start_time = time.time()
    env = os.environ.copy()
    if "BROWSER_AGENT_HEADLESS" not in env:
        env["BROWSER_AGENT_HEADLESS"] = "true"
    control_ctx = None
    bridge_manifest = None
    final_error_text: str | None = None
    service = str(request.get("browser_service") or "web").strip().lower() or "web"
    explicit_profile_id = str(request.get("browser_profile_id") or "").strip()
    if explicit_profile_id:
        control_ctx = brtc.initialize_runtime_contract(
            request_dir=task_dir,
            service=service,
            runtime_owner="webwright",
            wrapper_kind="webwright",
            profile_directory=explicit_profile_id.split("/")[-1],
            user_data_dir="",
            staged_user_data_dir="",
            explicit_profile_id=explicit_profile_id,
            task_id=str(request.get("dispatch_id") or task_dir.name),
            control_modes={
                "browser_use_session": False,
                "playwright_cdp_attach": False,
                "webwright_bridge": True,
            },
            metadata={
                "objective": request.get("objective") or "",
                "url": request.get("url") or "",
                "profile_mode": request.get("profile_mode") or "storage_state_clone",
            },
        )
        bridge_manifest = prepare_webwright_bridge(
            profile_id=explicit_profile_id,
            run_dir=task_dir,
            mode=str(request.get("profile_mode") or "storage_state_clone"),
            registry=control_ctx["registry"],
        )
        env = apply_webwright_bridge_env(env, bridge_manifest)

    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            env=env,
            timeout=request["timeout_seconds"],
            cwd=str(ROOT),
        )
        duration = time.time() - start_time

        (task_dir / "webwright-run.log").write_text(
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n",
            encoding="utf-8",
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"webwright_adapter run failed with code {proc.returncode}; dispatch_id={dispatch_id}; log={task_dir/'webwright-run.log'}"
            )

        report_path = task_dir / "report.json"
        try:
            report = json.loads(proc.stdout)
            if isinstance(report, dict) and "artifacts" in report:
                report["duration_seconds"] = report.get("duration_seconds", duration)
                report["dispatch_id"] = dispatch_id
        except Exception:
            report = {
                "ok": proc.returncode == 0,
                "duration_seconds": duration,
                "dispatch_id": dispatch_id,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
            if task_dir.exists():
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        if bridge_manifest is not None and isinstance(report, dict):
            report["browser_profile_bridge"] = bridge_manifest
        print(f"\n# Webwright Execution Success\n- Dispatch ID: {dispatch_id}\n- Duration: {duration:.2f}s", flush=True)
        return report
    except Exception as exc:
        final_error_text = str(exc)
        raise
    finally:
        if control_ctx is not None:
            brtc.finalize_runtime_contract(
                control_ctx,
                success=not final_error_text,
                error_text=final_error_text,
                page_state={"url": request.get("url") or ""},
                logged_in_state_verified=not final_error_text,
                details={
                    "provider": "webwright_operator",
                    "dispatch_id": dispatch_id,
                    "profile_mode": request.get("profile_mode") or "storage_state_clone",
                    "bridge": bridge_manifest or {},
                },
                requires_precise_page_control=True,
            )


def main() -> int:
    try:
        envelope = _load_envelope()
    except Exception as exc:
        print(f"Failed to load envelope: {exc}", file=sys.stderr)
        return 1

    task_dir = _task_dir(envelope)
    ofc.clear_task_control(task_dir)
    request = build_request(envelope, task_dir=task_dir)
    rate_control = _rate_control_settings(envelope)
    operator_id = str(rate_control["operator_id"])
    try:
        ofc.ensure_operator_available(operator_id)
        run_request(request, task_dir=task_dir)
        ofc.apply_success_cooldown(
            operator_id,
            success_cooldown_seconds=int(rate_control.get("success_cooldown_seconds") or 0),
        )
        return 0
    except Exception as exc:
        ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=str(exc),
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        print(f"webwright_operator failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
