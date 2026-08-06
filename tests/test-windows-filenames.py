"""Unit tests for scripts/check-windows-filenames.py (R8 Governance)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_windows_filenames",
    Path(__file__).resolve().parents[1] / "scripts" / "check-windows-filenames.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
is_illegal_windows_filename = _mod.is_illegal_windows_filename


class TestReservedDeviceNames:
    @pytest.mark.parametrize(
        "name",
        ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9",
         "con", "nul.txt", "PRN.log", "COM3.py"],
    )
    def test_reserved_names_rejected(self, name: str) -> None:
        reasons = is_illegal_windows_filename(name)
        assert any("reserved_device_name" in r for r in reasons), (
            f"{name!r} should be rejected as a reserved device name"
        )

    @pytest.mark.parametrize(
        "name",
        ["connection.txt", "console.py", "console_output.log",
         "com10.txt", "lpt10.txt", "auxiliary.md"],
    )
    def test_similar_but_legal_names_allowed(self, name: str) -> None:
        reasons = is_illegal_windows_filename(name)
        assert not any("reserved_device_name" in r for r in reasons), (
            f"{name!r} should NOT be rejected as a reserved device name"
        )


class TestForbiddenCharacters:
    @pytest.mark.parametrize("char", list('<>:"|?*'))
    def test_forbidden_chars_rejected(self, char: str) -> None:
        name = f"file{char}name.txt"
        reasons = is_illegal_windows_filename(name)
        assert any("forbidden_char" in r for r in reasons), (
            f"'{char}' in filename should be rejected"
        )

    def test_backslash_rejected(self) -> None:
        reasons = is_illegal_windows_filename("back\\slash.txt")
        assert any("forbidden_char" in r for r in reasons)

    def test_normal_chars_allowed(self) -> None:
        for name in ["normal-file.txt", "module_name.py", "README.md", "schema.v2.json"]:
            assert is_illegal_windows_filename(name) == [], (
                f"{name!r} should be legal on Windows"
            )


class TestTrailingSpaceOrPeriod:
    def test_trailing_space_rejected(self) -> None:
        reasons = is_illegal_windows_filename("filename ")
        assert any("trailing_space_or_period" in r for r in reasons)

    def test_trailing_period_rejected(self) -> None:
        reasons = is_illegal_windows_filename("filename.")
        assert any("trailing_space_or_period" in r for r in reasons)

    def test_normal_extension_allowed(self) -> None:
        assert is_illegal_windows_filename("file.txt") == []
        assert is_illegal_windows_filename("file.py") == []


class TestLegalFilenames:
    """Production filenames in the repo must all be legal."""

    @pytest.mark.parametrize(
        "name",
        [
            "transport.py",
            "runtime_readiness.py",
            "physical-operators.json",
            "phase-22-journey-test-report.md",
            ".gitignore",
            ".env.template",
            "AGENTS.md",
            "check-repo-hygiene.sh",
            "check-safe-staging.py",
            "check-secret-scan.py",
            "check-windows-filenames.py",
        ],
    )
    def test_production_filenames_legal(self, name: str) -> None:
        assert is_illegal_windows_filename(name) == [], (
            f"Production filename {name!r} should be legal on Windows"
        )
