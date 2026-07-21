#!/usr/bin/env python3
"""Minimal OpenAI-compatible local model PM operator.

This adapter is intentionally conservative: it asks a local OpenAI-compatible
endpoint for a structured handoff and writes PM_RESULT_PATH. It is suitable for
local GLM/ThunderOMLX builder slots when the service is healthy, but evaluators
must still reject missing concrete code/test evidence.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _read_dispatch() -> str:
    dispatch_file = os.environ.get("DISPATCH_FILE") or os.environ.get("SOLAR_MULTI_TASK_DISPATCH_FILE")
    if dispatch_file:
        path = Path(dispatch_file).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _chat_completion(base_url: str, model: str, prompt: str, api_key: str, timeout: float) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Solar-Harness local builder. Return a concise PM task result in Chinese. "
                    "If you cannot modify files through tools, be explicit and provide concrete patch guidance."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "solar-openai-compatible-operator/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def _write_pm_result(output: str, backend: str) -> None:
    result_path = os.environ.get("PM_RESULT_PATH") or os.environ.get("RESULT_PATH")
    if not result_path:
        print(output)
        return
    path = Path(result_path).expanduser()
    if path.exists() and path.stat().st_size > 0:
        print(output)
        return
    text = output.strip()
    if len(text) > 20000:
        text = text[:20000] + "\n\n[truncated]"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            f"# PM Task Result — {os.environ.get('TASK_ID', backend)}\n\n"
            "## 已完成\n"
            f"- {backend} OpenAI-compatible local operator 已处理 dispatch。\n\n"
            "## 已验证\n"
            "- 本地 HTTP 模型服务调用成功。\n"
            f"- backend={backend}\n\n"
            "## 结论摘要\n"
            f"{text or 'N/A'}\n\n"
            "## 风险/限制\n"
            "- 本 adapter 不具备通用文件编辑工具；若任务需要真实代码修改，应作为低成本分析/草稿，或交给具备工具的 builder 继续执行。\n\n"
            "## 后续建议\n"
            "- 如本结果缺少真实文件 diff 与测试证据，请调度 Sonnet/Codex/DeepSeek builder 执行落地修改。\n"
        ),
        encoding="utf-8",
    )
    print(output)


def main() -> int:
    dispatch = _read_dispatch().strip()
    if not dispatch:
        print("ERROR: empty dispatch for local OpenAI-compatible operator", file=sys.stderr)
        return 64
    base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8002").strip()
    model = os.environ.get("LOCAL_LLM_MODEL", "thunderomlx").strip()
    api_key = os.environ.get("LOCAL_LLM_API_KEY", "local-thunderomlx")
    backend = os.environ.get("LOCAL_LLM_BACKEND", model)
    timeout = float(os.environ.get("LOCAL_LLM_TIMEOUT_SECONDS", "180"))
    try:
        output = _chat_completion(base_url, model, dispatch, api_key, timeout)
    except urllib.error.URLError as exc:
        print(f"ERROR: local model service unreachable: {exc}", file=sys.stderr)
        return 75
    except Exception as exc:
        print(f"ERROR: local model call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 65
    _write_pm_result(output, backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
