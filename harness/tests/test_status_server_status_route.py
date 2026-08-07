"""Production-route regression tests for the status server ``/status`` endpoint."""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.request
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_route_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _get_json(base_url: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _get_text(base_url: str, path: str) -> tuple[int, str]:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_status_route_fails_closed_without_leaking_exception_details() -> None:
    module = _load_module()
    sensitive_detail = r"C:\\Users\\operator\\secrets\\provider-token.txt raw-token-sensitive-marker"

    def fail_status_payload(*_args, **_kwargs):
        raise RuntimeError(sensitive_detail)

    module._status_payload = fail_status_payload
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status_code, payload = _get_json(base_url, "/status")

        assert status_code == 200
        assert payload == {
            "ok": False,
            "status": "degraded",
            "error": "status_payload_unavailable",
            "panes": [],
            "current_sprint": {},
        }
        serialized = json.dumps(payload)
        assert sensitive_detail not in serialized
        assert "RuntimeError" not in serialized
        assert "provider-token" not in serialized

        health_code, health_body = _get_text(base_url, "/healthz")
        assert health_code == 200
        assert health_body == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
