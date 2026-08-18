from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote


STATUS_SERVER = Path(__file__).resolve().parents[2] / "harness" / "lib" / "symphony" / "status-server.py"


def _load_status_server(monkeypatch, tmp_path: Path):
    harness = tmp_path / "harness"
    for name in ("events", "reports", "run", "sessions", "sprints", "state"):
        (harness / name).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HARNESS_DIR", str(harness))
    monkeypatch.setenv("SOLAR_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("SOLAR_REQUIRE_TOKEN", "1")
    monkeypatch.setenv("SOLAR_AUTH_TOKEN", "phase22-status-auth-test-token")
    spec = importlib.util.spec_from_file_location(f"phase22_status_auth_{uuid.uuid4().hex}", STATUS_SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(base_url: str, path: str, *, method: str = "GET", token: str = "") -> tuple[int, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Solar-Token"] = token
    request = urllib.request.Request(base_url + path, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def test_enforced_token_does_not_leak_through_dashboard_bootstrap(monkeypatch, tmp_path: Path) -> None:
    module = _load_status_server(monkeypatch, tmp_path)
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _request(base_url, "/")
        assert status == 403
        assert module.AUTH_TOKEN not in body

        status, body = _request(base_url, "/", token=module.AUTH_TOKEN)
        assert status == 200
        assert f"window.__SOLAR_TOKEN__={json.dumps(module.AUTH_TOKEN)}" in body

        status, body = _request(base_url, f"/?token={quote(module.AUTH_TOKEN, safe='')}")
        assert status == 200
        assert f"window.__SOLAR_TOKEN__={json.dumps(module.AUTH_TOKEN)}" in body

        status, body = _request(base_url, "/status")
        assert status == 403
        assert module.AUTH_TOKEN not in body

        status, _ = _request(base_url, "/healthz")
        assert status == 200

        status, body = _request(base_url, "/status", method="HEAD")
        assert status == 403
        assert body == ""

        status, _ = _request(base_url, "/status", method="HEAD", token=module.AUTH_TOKEN)
        assert status == 200
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
