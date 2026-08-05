from __future__ import annotations

import json

import pytest

from harness.lib.research_orchestration.runtime_readiness import (
    BLOCKED,
    READY,
    READY_WITH_LIMITATIONS,
    check_research_runtime,
    sanitize_provider_environment,
)


def _which(*available: str):
    found = {name: f"/usr/bin/{name}" for name in available}
    found["wsl"] = "C:/Windows/System32/wsl.exe" if "wsl" in available else None
    return lambda name: found.get(name)


def test_windows_native_does_not_require_bwrap() -> None:
    report = check_research_runtime(
        source_env={},
        platform_system="Windows",
        platform_release="11",
        python_executable="C:/Python/python.exe",
        which_func=_which("git", "codex", "wsl"),
        sandbox_root=None,
        wsl_available=True,
        dns_probe=lambda: True,
    )

    assert report["os_class"] == "windows_native"
    assert report["checks"]["bwrap"]["ok"] is True
    assert report["status"] == READY_WITH_LIMITATIONS
    assert "tmux_unavailable" in report["limitations"]


def test_wsl_missing_bwrap_can_use_transport_fallback_as_limitation(tmp_path) -> None:
    report = check_research_runtime(
        source_env={"WSL_DISTRO_NAME": "Ubuntu"},
        platform_system="Linux",
        platform_release="5.15.0-microsoft-standard-WSL2",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex"),
        use_sandbox=True,
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
        stdin_transport_supported=False,
        readonly_transport_fallback_available=True,
    )

    assert report["os_class"] == "wsl"
    assert report["status"] == READY_WITH_LIMITATIONS
    assert "sandbox_bwrap_unavailable_using_transport_fallback" in report["limitations"]


def test_linux_with_and_without_bwrap(tmp_path) -> None:
    without_bwrap = check_research_runtime(
        source_env={},
        platform_system="Linux",
        platform_release="6.1",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex"),
        use_sandbox=True,
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
    )
    with_bwrap = check_research_runtime(
        source_env={},
        platform_system="Linux",
        platform_release="6.1",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex", "bwrap"),
        use_sandbox=True,
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
    )

    assert without_bwrap["status"] == READY_WITH_LIMITATIONS
    assert with_bwrap["checks"]["bwrap"]["available"] is True


def test_macos_classification_and_missing_codex_block(tmp_path) -> None:
    report = check_research_runtime(
        source_env={},
        platform_system="Darwin",
        platform_release="25.0",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "tmux"),
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
    )

    assert report["os_class"] == "macos"
    assert report["status"] == BLOCKED
    assert {"check": "codex_cli", "reason": "missing_codex_cli"} in report["blockers"]


def test_required_tmux_blocks_when_missing(tmp_path) -> None:
    report = check_research_runtime(
        source_env={},
        platform_system="Linux",
        platform_release="6.1",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex", "bwrap"),
        require_tmux=True,
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
    )
    assert report["status"] == BLOCKED
    assert {"check": "tmux", "reason": "missing_tmux"} in report["blockers"]


def test_provider_presence_is_secret_safe(tmp_path) -> None:
    secret = "sk-test-secret-value"
    report = check_research_runtime(
        source_env={"OPENAI_API_KEY": secret},
        allowed_provider_env_names=("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        require_provider="OPENAI_API_KEY",
        live_provider_approval_ref="approval-123",
        platform_system="Linux",
        platform_release="6.1",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex", "bwrap"),
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
    )

    output = json.dumps(report, sort_keys=True)
    assert report["provider_environment"]["OPENAI_API_KEY"] == "present"
    assert report["provider_environment"]["ANTHROPIC_API_KEY"] == "missing"
    assert secret not in output


def test_required_provider_missing_blocks(tmp_path) -> None:
    report = check_research_runtime(
        source_env={},
        require_provider="OPENAI_API_KEY",
        live_provider_approval_ref="approval-123",
        platform_system="Linux",
        platform_release="6.1",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex", "bwrap"),
        sandbox_root=tmp_path,
        dns_probe=lambda: True,
    )
    assert report["status"] == BLOCKED
    assert any(item["reason"] == "missing_provider_OPENAI_API_KEY" for item in report["blockers"])


def test_network_required_blocks_when_probe_fails(tmp_path) -> None:
    report = check_research_runtime(
        source_env={},
        require_network=True,
        platform_system="Linux",
        platform_release="6.1",
        python_executable="/usr/bin/python3",
        which_func=_which("git", "codex", "bwrap"),
        sandbox_root=tmp_path,
        dns_probe=lambda: False,
    )
    assert report["status"] == BLOCKED
    assert {"check": "network_probe", "reason": "network_unavailable"} in report["blockers"]


def test_malformed_environment_input_rejected() -> None:
    with pytest.raises(ValueError, match="source_env"):
        sanitize_provider_environment(["OPENAI_API_KEY=secret"], ["OPENAI_API_KEY"])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must be a string"):
        sanitize_provider_environment({"OPENAI_API_KEY": 42}, ["OPENAI_API_KEY"])
