import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "thunderomlx_health_probe.py"
spec = importlib.util.spec_from_file_location("thunderomlx_health_probe", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_unauth_models_401_is_alive_when_health_unavailable(monkeypatch, tmp_path):
    def fake_request(url, api_key=None, timeout=3.0):
        if url.endswith("/health"):
            raise TimeoutError("no health")
        if url.endswith("/v1/models"):
            return (401, {"detail": "API key required"})
        raise AssertionError(url)

    monkeypatch.setattr(mod, "_request_json", fake_request)
    result = mod.probe("http://127.0.0.1:8002", tmp_path / "missing.json")

    assert result["status"] == "auth_required_alive"
    assert result["models_http"] == 401


def test_authenticated_models_success_sets_ok(monkeypatch, tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"auth": {"api_key": "secret-value"}}), encoding="utf-8")

    def fake_request(url, api_key=None, timeout=3.0):
        if url.endswith("/health"):
            return (200, {"status": "healthy", "default_model": "Qwen3.6-35b-a3b"})
        if url.endswith("/v1/models") and api_key:
            return (200, {"data": [{"id": "Qwen3.6-35b-a3b"}]})
        if url.endswith("/v1/models"):
            return (401, {"detail": "API key required"})
        raise AssertionError(url)

    monkeypatch.setattr(mod, "_request_json", fake_request)
    result = mod.probe("http://127.0.0.1:8002", settings)

    assert result["status"] == "ok"
    assert result["reason"] == "authenticated_models_endpoint_ok"
    assert result["model_count"] == 1
    assert "secret-value" not in json.dumps(result)
