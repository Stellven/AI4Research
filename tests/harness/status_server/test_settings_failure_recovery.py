"""Fault probes for fail-closed settings updates and publication recovery."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "harness" / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_settings_failure_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(module, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    module._USER_CONFIG_PATH = path
    module._USER_CONFIG_CACHE = None
    module._USER_CONFIG_EVER_LOADED = False


@pytest.mark.parametrize("damage", ["invalid_json", "deleted"])
def test_durable_damage_drops_cache_and_rejects_stale_update(tmp_path: Path, damage: str) -> None:
    module = load_module()
    path = tmp_path / "config" / "solar-user-config.json"
    configure(module, path)
    original = {"runtime": "claude", "models": {"pm": "claude-opus"}}
    path.write_text(json.dumps(original), encoding="utf-8")
    assert module._read_user_config() == original

    if damage == "invalid_json":
        path.write_text('{"runtime":', encoding="utf-8")
    else:
        path.unlink()

    # Read-only views fail closed and must not keep serving the cached document.
    assert module._read_user_config() == {}
    assert module._USER_CONFIG_CACHE is None
    with pytest.raises(RuntimeError, match="unavailable for update"):
        module._write_user_config_runtime("codex")

    if damage == "invalid_json":
        assert path.read_text(encoding="utf-8") == '{"runtime":'
    else:
        assert not path.exists()


def test_failed_publish_keeps_complete_recovery_and_restores_old_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    path = tmp_path / "config" / "solar-user-config.json"
    configure(module, path)
    original = {"runtime": "claude", "models": {"pm": "claude-opus"}}
    requested = {"runtime": "codex", "models": {"pm": "claude-opus"}}
    path.write_text(json.dumps(original), encoding="utf-8")
    assert module._read_user_config() == original

    real_publish = module._publish_user_config

    def remove_target_then_fail(_temporary: Path, target: Path) -> None:
        target.unlink()
        raise PermissionError("injected failure after target removal")

    monkeypatch.setattr(module, "_publish_user_config", remove_target_then_fail)
    with pytest.raises(PermissionError, match="injected failure"):
        module._write_user_config(requested)

    recovery = path.with_suffix(".json.recovery")
    staged = path.with_suffix(".json.tmp")
    assert not path.exists()
    assert json.loads(recovery.read_text(encoding="utf-8")) == original
    assert json.loads(staged.read_text(encoding="utf-8")) == requested

    monkeypatch.setattr(module, "_publish_user_config", real_publish)
    # The next supported read restores the old committed document. The failed
    # request remains unapplied, matching its error response.
    assert module._read_user_config() == original
    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert not recovery.exists()
    assert not staged.exists()
