#!/usr/bin/env python3
"""Auth-aware ThunderOMLX readiness probe.

Exit code is 0 when the service is reachable, including the common protected
case where unauthenticated /v1/models returns 401. Secrets are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_SETTINGS = Path("~/.omlx/settings.json")


def _read_api_key(settings_path: Path) -> str | None:
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = data.get("auth", {}).get("api_key")
    return key if isinstance(key, str) and key else None


def _request_json(url: str, api_key: str | None = None, timeout: float = 3.0) -> tuple[int, Any]:
    headers = {"accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
        headers["authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw[:200]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body: Any = json.loads(raw)
        except Exception:
            body = raw[:200]
        return exc.code, body


def probe(base_url: str, settings_path: Path, timeout: float = 3.0) -> dict[str, Any]:
    base = base_url.rstrip("/")
    result: dict[str, Any] = {
        "base_url": base,
        "status": "error",
        "health_http": None,
        "models_http": None,
        "auth_models_http": None,
        "model_count": None,
        "default_model": None,
        "reason": None,
    }

    try:
        health_code, health_body = _request_json(f"{base}/health", timeout=timeout)
        result["health_http"] = health_code
        if isinstance(health_body, dict):
            result["default_model"] = health_body.get("default_model")
        if health_code == 200 and isinstance(health_body, dict) and health_body.get("status") == "healthy":
            result["status"] = "ok"
            result["reason"] = "health_endpoint_healthy"
    except Exception as exc:
        result["reason"] = f"health_probe_failed:{type(exc).__name__}"

    try:
        models_code, models_body = _request_json(f"{base}/v1/models", timeout=timeout)
        result["models_http"] = models_code
        if models_code == 401 and result["status"] != "ok":
            result["status"] = "auth_required_alive"
            result["reason"] = "models_endpoint_requires_auth"
        elif models_code == 200:
            result["status"] = "ok"
            result["reason"] = "models_endpoint_ok"
            if isinstance(models_body, dict) and isinstance(models_body.get("data"), list):
                result["model_count"] = len(models_body["data"])
    except Exception as exc:
        if result["status"] == "error":
            result["reason"] = f"models_probe_failed:{type(exc).__name__}"

    api_key = _read_api_key(settings_path)
    if api_key:
        try:
            auth_code, auth_body = _request_json(f"{base}/v1/models", api_key=api_key, timeout=timeout)
            result["auth_models_http"] = auth_code
            if auth_code == 200:
                result["status"] = "ok"
                result["reason"] = "authenticated_models_endpoint_ok"
                if isinstance(auth_body, dict) and isinstance(auth_body.get("data"), list):
                    result["model_count"] = len(auth_body["data"])
        except Exception as exc:
            result["auth_models_http"] = f"error:{type(exc).__name__}"

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)

    result = probe(args.base_url, Path(args.settings), timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"ok", "auth_required_alive"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
