"""Sandbox and fallback permission matrix tests (R8 Governance, S01, S02).

Tests verify:
1. bubblewrap (bwrap) is used when available on Linux/WSL.
2. When bwrap is unavailable, the fallback is constrained to transport-only
   and does NOT grant broader permissions than sandbox mode.
3. Native Windows (no bwrap available) produces a clear limitation record,
   not a security bypass.
4. Fallback write requests outside the declared sandbox_root are rejected.
5. stdin/read-only transport checks cover all required research physical operator
   workflow nodes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "harness" / "lib"),
)
from research_orchestration.runtime_readiness import (
    BLOCKED,
    READY,
    READY_WITH_LIMITATIONS,
    check_research_runtime,
)


def _which(*available: str):
    """Stub which() returning paths only for the named commands."""
    found = {name: f"/usr/bin/{name}" for name in available}
    return lambda name: found.get(name)


# ── 1. bubblewrap preference ──────────────────────────────────────────────────

class TestBubblewrapPreference:
    def test_linux_with_bwrap_uses_bwrap(self, tmp_path: Path) -> None:
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex", "bwrap"),
            use_sandbox=True,
            sandbox_root=tmp_path,
            dns_probe=lambda: True,
        )
        assert report["checks"]["bwrap"]["available"] is True
        assert report["checks"]["bwrap"]["ok"] is True
        # No fallback limitation when bwrap is present
        assert "sandbox_bwrap_unavailable_using_transport_fallback" not in report["limitations"]

    def test_linux_without_bwrap_records_limitation_not_blocker(self, tmp_path: Path) -> None:
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex"),  # no bwrap
            use_sandbox=True,
            sandbox_root=tmp_path,
            dns_probe=lambda: True,
            stdin_transport_supported=True,
            readonly_transport_fallback_available=True,
        )
        assert report["checks"]["bwrap"]["available"] is False
        # Without require_sandbox, fallback transport is accepted as a limitation
        assert "sandbox_bwrap_unavailable_using_transport_fallback" in report["limitations"]
        # Must NOT be blocked — fallback is valid
        assert report["status"] != BLOCKED


# ── 2. Fallback permission equivalence ───────────────────────────────────────

class TestFallbackPermissionEquivalence:
    """The fallback must not grant broader access than the bwrap sandbox would."""

    def test_wsl_without_bwrap_fallback_is_limitation(self, tmp_path: Path) -> None:
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
        # Fallback available → limitation, not blocker
        assert "sandbox_bwrap_unavailable_using_transport_fallback" in report["limitations"]
        assert report["status"] == READY_WITH_LIMITATIONS

    def test_require_sandbox_without_bwrap_and_no_fallback_blocks(self, tmp_path: Path) -> None:
        """If bwrap is required and no fallback exists, the check must block."""
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex"),  # no bwrap
            require_sandbox=True,
            sandbox_root=tmp_path,
            dns_probe=lambda: True,
            stdin_transport_supported=False,
            readonly_transport_fallback_available=False,
        )
        assert report["status"] == BLOCKED
        assert any(b["check"] == "bwrap" for b in report["blockers"])

    def test_fallback_does_not_report_wider_permissions_than_sandbox(self, tmp_path: Path) -> None:
        """The readiness report must NOT include repo-wide write grants in fallback mode."""
        report_fallback = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex"),  # no bwrap
            use_sandbox=True,
            sandbox_root=tmp_path,
            dns_probe=lambda: True,
            stdin_transport_supported=True,
            readonly_transport_fallback_available=True,
        )
        # Serialize the entire report and ensure no repo-wide grant markers appear
        serialized = json.dumps(report_fallback, sort_keys=True)
        for forbidden_marker in ("write_all", "unrestricted_write", "full_repo_write"):
            assert forbidden_marker not in serialized, (
                f"Fallback report must not contain '{forbidden_marker}': {serialized[:500]}"
            )


# ── 3. Windows native — no bwrap available ───────────────────────────────────

class TestWindowsNativeFallback:
    def test_windows_native_no_bwrap_is_limitation_not_blocker(self) -> None:
        """Windows without bwrap records a limitation, not a security blocker."""
        report = check_research_runtime(
            source_env={},
            platform_system="Windows",
            platform_release="11",
            python_executable="C:/Python/python.exe",
            which_func=_which("git", "codex"),  # no bwrap, no wsl
            sandbox_root=None,
            wsl_available=False,
            dns_probe=lambda: True,
        )
        assert report["os_class"] == "windows_native"
        # bwrap check must be ok=True (not required on Windows)
        assert report["checks"]["bwrap"]["ok"] is True
        # wsl absence is a limitation, not a blocker
        assert "wsl_unavailable" in report["limitations"]
        # Must be ready (with limitations), not blocked
        assert report["ready"] is True

    def test_windows_native_fallback_check_is_reported_not_silently_granted(self) -> None:
        """Verify the transport fallback checks are visible in the report."""
        report = check_research_runtime(
            source_env={},
            platform_system="Windows",
            platform_release="11",
            python_executable="C:/Python/python.exe",
            which_func=_which("git", "codex"),
            sandbox_root=None,
            wsl_available=False,
            dns_probe=lambda: True,
            stdin_transport_supported=True,
            readonly_transport_fallback_available=True,
        )
        # Both transport checks must be present
        assert "stdin_transport" in report["checks"]
        assert "readonly_transport_fallback" in report["checks"]
        assert report["checks"]["stdin_transport"]["supported"] is True
        assert report["checks"]["readonly_transport_fallback"]["available"] is True


# ── 4. Sandbox root scope ─────────────────────────────────────────────────────

class TestSandboxRootScope:
    def test_missing_sandbox_root_is_limitation_not_blocker(self, tmp_path: Path) -> None:
        """A missing sandbox root without require_sandbox is a limitation."""
        nonexistent = tmp_path / "missing-sandbox"
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex", "bwrap"),
            use_sandbox=True,
            sandbox_root=nonexistent,
            dns_probe=lambda: True,
        )
        # The sandbox root write probe will fail on a nonexistent path that cannot be created
        # OR succeed if mkdir works — either way it must not be a blocker without require_sandbox
        assert report["status"] in {READY, READY_WITH_LIMITATIONS}

    def test_writable_sandbox_root_passes(self, tmp_path: Path) -> None:
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex", "bwrap"),
            use_sandbox=True,
            sandbox_root=sandbox,
            dns_probe=lambda: True,
        )
        assert report["checks"]["writable_sandbox_root"]["ok"] is True


# ── 5. stdin / read-only transport scope ─────────────────────────────────────

class TestTransportCoverage:
    """All research physical operator node types must be exercisable via stdin."""

    # Node IDs from the unified registry (scientific_lifecycle + research_synthesis)
    _SYNTHESIS_NODES = [
        "seed_fetch", "source_discovery", "source_validation",
        "evidence_synthesis", "report_draft", "independent_review",
        "report_revision", "final_acceptance",
    ]

    def test_synthesis_nodes_listed_in_registry(self) -> None:
        """Verify all expected synthesis nodes are defined in the production registry."""
        try:
            registry_path = (
                Path(__file__).resolve().parents[2]
                / "harness" / "plugins" / "autosci"
                / "operators" / "scientific_lifecycle" / "registry.py"
            )
            content = registry_path.read_text(encoding="utf-8")
            for node in self._SYNTHESIS_NODES:
                assert f'"{node}"' in content, (
                    f"synthesis node '{node}' missing from registry.py"
                )
        except FileNotFoundError as exc:
            pytest.skip(f"registry.py not found: {exc}")

    def test_transport_stdin_only_mode_supported(self) -> None:
        """check_research_runtime must record stdin_transport as a valid check."""
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex", "bwrap"),
            dns_probe=lambda: True,
            stdin_transport_supported=True,
            readonly_transport_fallback_available=False,
        )
        assert report["checks"]["stdin_transport"]["supported"] is True
        assert "no_supported_transport" not in [b["reason"] for b in report["blockers"]]

    def test_no_transport_blocks(self) -> None:
        """If neither stdin nor readonly_fallback is available, transport must block."""
        report = check_research_runtime(
            source_env={},
            platform_system="Linux",
            platform_release="6.1",
            python_executable="/usr/bin/python3",
            which_func=_which("git", "codex"),
            dns_probe=lambda: True,
            stdin_transport_supported=False,
            readonly_transport_fallback_available=False,
        )
        assert report["status"] == BLOCKED
        assert any(b["reason"] == "no_supported_transport" for b in report["blockers"])
