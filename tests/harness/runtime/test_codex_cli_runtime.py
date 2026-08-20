from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3] / "harness"


def _load_runtime():
    path = ROOT / "lib" / "codex_cli_runtime.py"
    spec = importlib.util.spec_from_file_location("codex_cli_runtime_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_codex_cli_prefers_runnable_configured_path(tmp_path):
    runtime = _load_runtime()
    configured = tmp_path / "codex"
    configured.write_bytes(b"\x7fELFfixture")
    configured.chmod(0o700)

    resolved, reason = runtime.resolve_codex_cli(
        tmp_path / "harness",
        env={"PATH": ""},
        configured_path=str(configured),
    )

    assert resolved == configured.resolve()
    assert reason == "configured_path"


def test_resolve_codex_cli_finds_user_local_bin_without_login_shell_path(tmp_path):
    runtime = _load_runtime()
    home = tmp_path / "home"
    user_local = home / ".local" / "bin" / "codex"
    user_local.parent.mkdir(parents=True)
    user_local.write_bytes(b"\x7fELFfixture")
    user_local.chmod(0o700)

    resolved, reason = runtime.resolve_codex_cli(
        tmp_path / "harness",
        env={"PATH": "", "HOME": str(home)},
        configured_path="/opt/homebrew/bin/codex",
    )

    assert resolved == user_local.resolve()
    assert reason == "user_local_bin"


def test_resolve_codex_cli_materializes_windows_desktop_binary_for_wsl(tmp_path, monkeypatch):
    runtime = _load_runtime()
    source = tmp_path / "WindowsApps" / "OpenAI.Codex_1" / "app" / "resources" / "codex"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x7fELF" + b"fixture" * 32)
    source.chmod(0o400)
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(runtime, "_is_wsl", lambda: True)
    monkeypatch.setattr(runtime, "_desktop_cli_sources", lambda _env: [source])

    resolved, reason = runtime.resolve_codex_cli(
        tmp_path / "harness",
        env={"PATH": "", "SOLAR_CODEX_RUNTIME_DIR": str(runtime_root)},
        configured_path="/opt/homebrew/bin/codex",
    )

    assert resolved is not None
    assert resolved != source
    assert resolved.read_bytes() == source.read_bytes()
    assert os.access(resolved, os.X_OK)
    assert reason == "windows_desktop_wsl_copy"
    reused, reused_reason = runtime.resolve_codex_cli(
        tmp_path / "harness",
        env={"PATH": "", "SOLAR_CODEX_RUNTIME_DIR": str(runtime_root)},
        configured_path="/opt/homebrew/bin/codex",
    )
    assert reused == resolved
    assert reused_reason == reason


def test_resolve_codex_cli_rejects_untrusted_non_elf_desktop_source(tmp_path, monkeypatch):
    runtime = _load_runtime()
    source = tmp_path / "codex"
    source.write_text("not an executable", encoding="utf-8")
    monkeypatch.setattr(runtime, "_is_wsl", lambda: True)
    monkeypatch.setattr(runtime, "_desktop_cli_sources", lambda _env: [source])

    resolved, reason = runtime.resolve_codex_cli(
        tmp_path / "harness",
        env={"PATH": ""},
    )

    assert resolved is None
    assert reason == "command_path_missing:codex"
