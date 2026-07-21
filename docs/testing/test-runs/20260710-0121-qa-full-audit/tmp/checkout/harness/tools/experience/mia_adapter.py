"""MIA Memory-Serve adapter for Solar Experience Memory.

The upstream ECNU-SII/MIA runtime is a Flask service with heavyweight model
dependencies. Solar uses it through this fail-open HTTP adapter so the local
experience index remains available when MIA is not installed or not running.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


DEFAULT_BASE_URL = "http://127.0.0.1:5197"
DEFAULT_TIMEOUT_SEC = 8.0


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _timeout() -> float:
    raw = os.environ.get("SOLAR_MIA_TIMEOUT_SEC") or os.environ.get("MIA_TIMEOUT_SEC")
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        return max(0.02, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SEC


def base_url() -> str:
    return (
        os.environ.get("SOLAR_MIA_BASE_URL")
        or os.environ.get("MIA_MEMORY_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")


def enabled() -> bool:
    return _env_bool("SOLAR_MIA_ENABLED", True)


def _request_json(path: str, payload: Optional[Any] = None, timeout: Optional[float] = None) -> Any:
    url = f"{base_url()}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout if timeout is not None else _timeout()) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        if not raw:
            return {}
        return json.loads(raw)


def health(timeout: float = 0.25) -> Dict[str, Any]:
    """Return adapter/runtime health without raising."""
    started = time.time()
    if not enabled():
        return {
            "ok": False,
            "status": "disabled",
            "base_url": base_url(),
            "latency_ms": 0,
            "reason": "SOLAR_MIA_ENABLED=0",
        }
    try:
        data = _request_json("/hallo", timeout=timeout)
        return {
            "ok": True,
            "status": "ok",
            "base_url": base_url(),
            "latency_ms": round((time.time() - started) * 1000, 1),
            "response": data,
        }
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "unreachable",
            "base_url": base_url(),
            "latency_ms": round((time.time() - started) * 1000, 1),
            "reason": str(exc)[:300],
        }


def memory_context(
    question: str,
    *,
    image_caption: str = "",
    limit: int = 5,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Query MIA /memory and normalize the response."""
    if not enabled():
        return {"ok": False, "status": "disabled", "reason": "SOLAR_MIA_ENABLED=0"}

    payload = [{
        "data_id": "solar-experience-query",
        "question": question,
        "image_caption": [image_caption] if image_caption else [],
        "mem_top_k": max(1, int(limit)),
        "pass_num": 0,
    }]
    started = time.time()
    try:
        response = _request_json("/memory", payload, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "unreachable",
            "base_url": base_url(),
            "latency_ms": round((time.time() - started) * 1000, 1),
            "reason": str(exc)[:300],
        }

    item: Dict[str, Any] = {}
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            item = first
    elif isinstance(response, dict):
        item = response

    context = str(item.get("context") or item.get("memories_context") or "").strip()
    return {
        "ok": True,
        "status": "ok",
        "base_url": base_url(),
        "latency_ms": round((time.time() - started) * 1000, 1),
        "context": context,
        "pos_indices": item.get("pos_indices", []),
        "neg_indices": item.get("neg_indices", []),
        "raw_count": len(response) if isinstance(response, list) else 1,
    }


def plan(question: str, *, image_caption: str = "", limit: int = 5) -> Dict[str, Any]:
    """Call MIA /plan when the runtime is available."""
    payload = [{
        "data_id": "solar-experience-plan",
        "question": question,
        "image_caption": [image_caption] if image_caption else [],
        "mem_top_k": max(1, int(limit)),
        "pass_num": 0,
    }]
    started = time.time()
    try:
        response = _request_json("/plan", payload)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "unreachable",
            "base_url": base_url(),
            "latency_ms": round((time.time() - started) * 1000, 1),
            "reason": str(exc)[:300],
        }
    return {
        "ok": True,
        "status": "ok",
        "base_url": base_url(),
        "latency_ms": round((time.time() - started) * 1000, 1),
        "result": response,
    }
