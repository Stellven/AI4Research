#!/usr/bin/env python3
"""ThunderOMLX control surface tests for status-server."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_thunderomlx_status_reports_healthy_service(monkeypatch, tmp_path):
    monkeypatch.setattr(status_server, "_THUNDEROMLX_STATUS_CACHE", {})
    monkeypatch.setattr(status_server, "THUNDEROMLX_BASE_URL", "http://127.0.0.1:8002")
    monkeypatch.setattr(status_server, "THUNDEROMLX_LOG_FILE", tmp_path / "thunder.log")
    monkeypatch.setattr(status_server, "_thunderomlx_listening_pids", lambda port: [12345])
    monkeypatch.setattr(status_server, "_thunderomlx_tmux_alive", lambda: True)

    def fake_http(url, **kwargs):
        if url.endswith("/health"):
            return 200, {
                "status": "healthy",
                "default_model": "Qwen3.6-35b-a3b",
                "engine_pool": {"models": [{"id": "Qwen3.6-35b-a3b", "loaded": True}]},
            }
        return 200, {"data": [{"id": "Qwen3.6-35b-a3b"}]}

    monkeypatch.setattr(status_server, "_http_json", fake_http)

    payload = status_server._thunderomlx_status(refresh=True)

    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["port_listening"] is True
    assert payload["tmux_alive"] is True
    assert payload["model_count"] == 1
    assert payload["loaded_models"] == ["Qwen3.6-35b-a3b"]


def test_start_thunderomlx_from_status_spawns_start_script(monkeypatch, tmp_path):
    start_script = tmp_path / "thunderomlx_start_8002.sh"
    start_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    log_path = tmp_path / "start.log"
    captured: dict[str, object] = {}

    monkeypatch.setattr(status_server, "_THUNDEROMLX_STATUS_CACHE", {})
    monkeypatch.setattr(status_server, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(status_server, "THUNDEROMLX_START_SCRIPT", start_script)
    monkeypatch.setattr(status_server, "THUNDEROMLX_STATUS_START_LOG", log_path)
    monkeypatch.setattr(status_server, "_thunderomlx_status", lambda refresh=False: {"ok": False, "status": "stopped"})

    class FakePopen:
        pid = 24680

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    result = status_server._start_thunderomlx_from_status()

    assert result["ok"] is True
    assert result["status"] == "starting"
    assert result["pid"] == 24680
    assert captured["cmd"] == ["/bin/bash", str(start_script)]
    assert captured["kwargs"]["cwd"] == str(tmp_path)


def test_status_page_contains_thunderomlx_control_surface():
    source = MODULE.read_text(encoding="utf-8")
    assert "overview-thunderomlx" in source
    assert "thunderomlx-card" in source
    assert "/api/thunderomlx/start" in source
    assert "启动 ThunderOMLX" in source
