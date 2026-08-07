"""Secret-safe research runtime readiness checks."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


READY = "ready"
READY_WITH_LIMITATIONS = "ready_with_limitations"
BLOCKED = "blocked"


def sanitize_provider_environment(source_env: Mapping[str, Any], allowed_names: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Return an in-memory provider env subset for child processes only."""

    if not isinstance(source_env, Mapping):
        raise ValueError("source_env must be a mapping")
    if not isinstance(allowed_names, (list, tuple, set, frozenset)):
        raise ValueError("allowed_names must be a sequence")

    sanitized: dict[str, str] = {}
    for raw_name in allowed_names:
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("allowed provider names must be non-empty strings")
        name = raw_name.strip()
        value = source_env.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"provider environment value for {name} must be a string")
        if value:
            sanitized[name] = value
    return sanitized


def check_research_runtime(
    *,
    source_env: Mapping[str, Any] | None = None,
    allowed_provider_env_names: list[str] | tuple[str, ...] = (),
    require_provider: str | Sequence[str] | None = None,
    live_provider_approval_ref: str | None = None,
    offline: bool = False,
    require_network: bool = False,
    require_tmux: bool = False,
    require_sandbox: bool = False,
    use_sandbox: bool = False,
    sandbox_root: str | Path | None = None,
    platform_system: str | None = None,
    platform_release: str | None = None,
    python_executable: str | None = None,
    which_func: Callable[[str], str | None] | None = None,
    dns_probe: Callable[[], bool] | None = None,
    wsl_available: bool | None = None,
    stdin_transport_supported: bool = True,
    readonly_transport_fallback_available: bool = True,
) -> dict[str, Any]:
    """Return deterministic readiness details without exposing secret values."""

    env = source_env if source_env is not None else os.environ
    if not isinstance(env, Mapping):
        raise ValueError("source_env must be a mapping")

    which = which_func or shutil.which
    system = (platform_system or platform.system() or "Unknown").strip()
    release = (platform_release or platform.release() or "").strip()
    os_class = _classify_os(system, release, env)

    required_providers = _required_provider_names(require_provider)
    provider_names = _provider_names(allowed_provider_env_names, required_providers)
    provider_env = sanitize_provider_environment(env, provider_names)
    provider_presence = {
        name: ("present" if name in provider_env else "missing")
        for name in sorted(provider_names)
    }

    checks: dict[str, dict[str, Any]] = {}
    limitations: list[str] = []
    blockers: list[dict[str, str]] = []

    _add_check(checks, "host_os", True, classification=os_class, system=system, release=release)

    py_exe = python_executable or sys.executable
    _add_check(checks, "python_executable", bool(py_exe), path=py_exe or "")
    if not py_exe:
        blockers.append({"check": "python_executable", "reason": "missing_python"})

    for name, command in (("git", "git"), ("codex_cli", "codex")):
        found = bool(which(command))
        _add_check(checks, name, found, command=command)
        if name == "codex_cli" and not found:
            blockers.append({"check": name, "reason": "missing_codex_cli"})
        elif name == "git" and not found:
            blockers.append({"check": name, "reason": "missing_git"})

    tmux_found = bool(which("tmux"))
    _add_check(checks, "tmux", tmux_found, required=require_tmux)
    if require_tmux and not tmux_found:
        blockers.append({"check": "tmux", "reason": "missing_tmux"})
    elif not tmux_found:
        limitations.append("tmux_unavailable")

    bwrap_required = os_class in {"linux", "wsl"} and (use_sandbox or require_sandbox)
    bwrap_found = bool(which("bwrap"))
    _add_check(checks, "bwrap", bwrap_found or not bwrap_required, available=bwrap_found, required=bwrap_required)
    fallback_available = bool(stdin_transport_supported or readonly_transport_fallback_available)
    sandbox_mode = "bubblewrap" if bwrap_found and bwrap_required else "restricted_fallback"
    permission_matrix = {
        "mode": sandbox_mode,
        "write_scope": "sandbox_root_only" if sandbox_root is not None else "no_writes",
        "home_access": False,
        "network_access": False,
        "secret_access": False,
        "stdin_only": bool(stdin_transport_supported),
        "readonly_transport": bool(readonly_transport_fallback_available),
    }
    _add_check(
        checks,
        "sandbox_permissions",
        bool(bwrap_found or not bwrap_required or fallback_available),
        **permission_matrix,
    )
    if bwrap_required and not bwrap_found:
        if require_sandbox and not fallback_available:
            blockers.append({"check": "bwrap", "reason": "missing_bwrap_for_required_sandbox"})
        elif require_sandbox:
            blockers.append({"check": "bwrap", "reason": "missing_bwrap_for_required_sandbox"})
        else:
            limitations.append("sandbox_bwrap_unavailable_using_transport_fallback")

    wsl_ok = _detect_wsl_available(wsl_available, which)
    _add_check(checks, "wsl", wsl_ok, required=False, available=wsl_ok)
    if system.lower() == "windows" and not wsl_ok:
        limitations.append("wsl_unavailable")

    sandbox = _check_sandbox_root(sandbox_root)
    _add_check(checks, "writable_sandbox_root", sandbox["ok"], path=sandbox.get("path", ""), message=sandbox["message"])
    if require_sandbox and not sandbox["ok"]:
        blockers.append({"check": "writable_sandbox_root", "reason": sandbox["message"]})
    elif not sandbox["ok"]:
        limitations.append("sandbox_root_unavailable")

    network_ok = True if offline and not require_network else _probe_network(dns_probe)
    _add_check(checks, "network_probe", network_ok, offline=offline, required=require_network)
    if require_network and not network_ok:
        blockers.append({"check": "network_probe", "reason": "network_unavailable"})
    elif offline:
        limitations.append("offline_mode")

    _add_check(
        checks,
        "provider_environment",
        all(provider_presence.get(name) == "present" for name in required_providers),
        providers=provider_presence,
        required=required_providers,
    )
    for name in required_providers:
        if provider_presence.get(name) != "present":
            blockers.append(
                {"check": "provider_environment", "reason": f"missing_provider_{name}"}
            )

    approval_present = bool(str(live_provider_approval_ref or "").strip())
    _add_check(
        checks,
        "live_provider_approval",
        approval_present or not required_providers,
        present="present" if approval_present else "missing",
        required=bool(required_providers),
    )
    if required_providers and not approval_present:
        blockers.append({"check": "live_provider_approval", "reason": "missing_live_provider_approval_ref"})

    _add_check(checks, "stdin_transport", bool(stdin_transport_supported), supported=bool(stdin_transport_supported))
    _add_check(
        checks,
        "readonly_transport_fallback",
        bool(readonly_transport_fallback_available),
        available=bool(readonly_transport_fallback_available),
    )
    if not stdin_transport_supported and not readonly_transport_fallback_available:
        blockers.append({"check": "transport", "reason": "no_supported_transport"})
    elif not stdin_transport_supported:
        limitations.append("stdin_transport_unavailable_readonly_fallback_available")

    status = BLOCKED if blockers else READY_WITH_LIMITATIONS if limitations else READY
    return {
        "schema": "research_runtime_readiness.v1",
        "status": status,
        "ready": status != BLOCKED,
        "ready_with_limitations": status == READY_WITH_LIMITATIONS,
        "blocked": status == BLOCKED,
        "os_class": os_class,
        "checks": {key: checks[key] for key in sorted(checks)},
        "limitations": sorted(set(limitations)),
        "blockers": blockers,
        "provider_environment": provider_presence,
        "sandbox_permissions": permission_matrix,
    }


def _classify_os(system: str, release: str, env: Mapping[str, Any]) -> str:
    lower = system.lower()
    release_lower = release.lower()
    if lower == "windows":
        return "windows_native"
    if lower == "darwin":
        return "macos"
    if lower == "linux":
        if "microsoft" in release_lower or env.get("WSL_DISTRO_NAME") or env.get("WSL_INTEROP"):
            return "wsl"
        return "linux"
    return "unknown"


def _provider_names(
    allowed: list[str] | tuple[str, ...], required_providers: Sequence[str]
) -> list[str]:
    names = [str(item).strip() for item in allowed if str(item).strip()]
    names.extend(required_providers)
    return sorted(set(names))


def _required_provider_names(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    raw_names = [value] if isinstance(value, str) else list(value)
    names: list[str] = []
    for raw_name in raw_names:
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("required provider names must be non-empty strings")
        names.append(raw_name.strip())
    return sorted(set(names))


def _add_check(checks: dict[str, dict[str, Any]], name: str, ok: bool, **details: Any) -> None:
    checks[name] = {"ok": bool(ok), **{key: details[key] for key in sorted(details)}}


def _detect_wsl_available(wsl_available: bool | None, which: Callable[[str], str | None]) -> bool:
    if wsl_available is not None:
        return bool(wsl_available)
    if not which("wsl"):
        return False
    try:
        proc = subprocess.run(["wsl", "--status"], capture_output=True, text=True, timeout=3)
        return proc.returncode == 0
    except Exception:
        return False


def _check_sandbox_root(sandbox_root: str | Path | None) -> dict[str, Any]:
    if sandbox_root is None:
        return {"ok": True, "message": "not_required", "path": ""}
    path = Path(sandbox_root)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".research-runtime-write-probe"
        probe.write_text("ok", encoding="utf-8")
        mode = probe.stat().st_mode
        probe.unlink()
        return {"ok": stat.S_ISREG(mode), "message": "writable", "path": str(path)}
    except Exception as exc:
        return {"ok": False, "message": f"not_writable:{type(exc).__name__}", "path": str(path)}


def _probe_network(dns_probe: Callable[[], bool] | None) -> bool:
    if dns_probe is not None:
        try:
            return bool(dns_probe())
        except Exception:
            return False
    try:
        socket.getaddrinfo("example.com", 443, proto=socket.IPPROTO_TCP)
        return True
    except Exception:
        return False
