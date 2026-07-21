#!/usr/bin/env python3
"""Headless ThunderOMLX knowledge extraction worker for multi-task tmux panes."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))
GRAPH = Path(os.environ.get("GRAPH", ""))
NODE_ID = os.environ.get("NODE_ID", "")
SID = os.environ.get("SID", GRAPH.name.replace(".task_graph.json", "") if GRAPH.name else "")
HANDOFF = Path(os.environ.get("HANDOFF", SPRINTS_DIR / f"{SID}.{NODE_ID}-handoff.md"))
TASK_DIR = Path(os.environ.get("TASK_DIR", HARNESS_DIR / "run" / "multi-task" / "manual-thunderomlx-knowledge"))
BASE_URL = os.environ.get("THUNDEROMLX_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
LOCAL_MODEL = os.environ.get("THUNDEROMLX_LOCAL_MODEL", "Qwen3.6-35b-a3b")
PROXY_MODEL = os.environ.get("THUNDEROMLX_ANTHROPIC_MODEL", LOCAL_MODEL)
API_KEY = os.environ.get("THUNDEROMLX_AUTH_TOKEN", "local-thunderomlx")
MAX_SOURCE_CHARS = int(os.environ.get("SOLAR_KNOWLEDGE_EXTRACT_MAX_SOURCE_CHARS", "42000") or "42000")
MAX_TOKENS = int(os.environ.get("SOLAR_KNOWLEDGE_EXTRACT_MAX_TOKENS", "2200") or "2200")
MODEL_POLICY = "local_thunderomlx_default_for_knowledge_extraction_preprocess"
THUNDEROMLX_PAUSE_FILE = Path(os.environ.get("THUNDEROMLX_PAUSE_FILE", HOME / ".omlx" / "run" / "maintenance.json"))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"failed to load json {path}: {exc}") from exc


def node_from_graph(graph: dict[str, Any]) -> dict[str, Any]:
    for node in graph.get("nodes") or []:
        if str(node.get("id") or "") == NODE_ID:
            return node
    raise SystemExit(f"node not found: {NODE_ID}")


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def read_sources(paths: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    remaining = MAX_SOURCE_CHARS
    for raw in paths:
        path = Path(raw).expanduser()
        item: dict[str, Any] = {"path": str(path), "exists": path.exists(), "chars": 0, "text": ""}
        if path.exists() and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            item["chars"] = len(text)
            take = max(0, min(len(text), remaining))
            item["text"] = text[:take]
            item["truncated"] = take < len(text)
            remaining -= take
        out.append(item)
        if remaining <= 0:
            break
    return out


def choose_output_paths(node: dict[str, Any]) -> tuple[Path, Path]:
    report = HARNESS_DIR / "monitor-reports" / "thunderomlx-knowledge-extract-smoke.md"
    extracted = TASK_DIR / "extracted-knowledge.md"
    for raw in listify(node.get("write_scope")):
        path = Path(raw).expanduser()
        if path.name.endswith(".md") and "monitor-reports" in str(path):
            report = path
        elif path.suffix == ".md" and path.name == "extracted-knowledge.md":
            extracted = path
        elif path.suffix == "":
            extracted = path / "extracted-knowledge.md"
    return report, extracted


def bad_chars(text: str) -> bool:
    return bool(re.search(r"[\ufffd\ue000-\uf8ff]", text))


def thunderomlx_ingest_paused() -> str | None:
    if not THUNDEROMLX_PAUSE_FILE.exists():
        return None
    try:
        data = json.loads(THUNDEROMLX_PAUSE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"unreadable pause file: {exc}"
    if not data.get("enabled", True):
        return None
    if str(data.get("mode") or "ingest_pause") not in {"ingest_pause", "all"}:
        return None
    return str(data.get("reason") or THUNDEROMLX_PAUSE_FILE)


def call_thunderomlx(prompt: str) -> dict[str, Any]:
    pause_reason = thunderomlx_ingest_paused()
    if pause_reason:
        raise SystemExit(f"ThunderOMLX ingest pause active: {pause_reason}")
    payload = {
        "model": PROXY_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        raise SystemExit(f"ThunderOMLX HTTP {exc.code}: {body}") from exc


def content_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for choice in response.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        if isinstance(message, dict):
            content = str(message.get("content") or "").strip()
            reasoning = str(message.get("reasoning_content") or "").strip()
            parts.append(content or reasoning)
        if "text" in choice:
            parts.append(str(choice.get("text") or ""))
    for item in response.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        elif isinstance(item, dict) and "text" in item:
            parts.append(str(item.get("text") or ""))
    return strip_thinking_text("\n".join(parts))


def strip_thinking_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"(?is)<think>.*?</think>\s*", "", text).strip()
    for pattern in (
        r"(?is)\bFinal Answer\s*:\s*",
        r"(?is)\bFinal\s*:\s*",
        r"(?is)最终答案\s*[:：]\s*",
        r"(?is)正式输出\s*[:：]\s*",
        r"(?is)答案\s*[:：]\s*",
    ):
        matches = list(re.finditer(pattern, text))
        if matches:
            return text[matches[-1].end():].strip()
    if re.match(r"(?is)^\s*(Thinking Process:|1\.\s+\*\*Analyze)", text):
        return ""
    return text


def build_prompt(node: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    source_blocks = []
    for item in sources:
        source_blocks.append(
            f"### Source: {item['path']}\n"
            f"- exists: {item['exists']}\n"
            f"- chars: {item['chars']}\n"
            f"- truncated: {item.get('truncated', False)}\n\n"
            f"```markdown\n{item.get('text') or ''}\n```"
        )
    return f"""你是 Solar Harness 的知识库抽取 worker。请只基于下面的源文档做中文知识抽取，不要编造。

模型策略：
- 当前任务属于知识库抽取/清洗/预处理，默认使用 ThunderOMLX 本地模型。
- 不做趋势研判、战略总结或最终高级报告；这些任务必须由 reasoning_packet 之后的 premium reasoner 处理。
- 不改变 embedding 路线；本 worker 不执行向量化。

输出必须是 Markdown，并包含这些固定章节：

1. 功能模块
2. 用户价值
3. 设计结构
4. 关键文件或命令
5. 核心 API/命令
6. 验证方法
7. 风险边界
8. 后续改进

要求：
- 语言简洁、信息密度高。
- 不要输出 secrets、token、API key。
- 不要输出乱码；如果源文档不足，明确写 N/A。
- 结尾给出 3 条可检索关键词。

任务目标：
{node.get('goal') or 'N/A'}

源文档：

{chr(10).join(source_blocks)}
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not GRAPH.exists():
        raise SystemExit(f"GRAPH missing: {GRAPH}")
    graph = load_json(GRAPH)
    node = node_from_graph(graph)
    sources = read_sources(listify(node.get("read_scope")))
    prompt = build_prompt(node, sources)
    started = now()
    response = call_thunderomlx(prompt)
    text = content_text(response)
    if not text:
        raise SystemExit("ThunderOMLX returned empty text")
    report, extracted = choose_output_paths(node)
    usage = response.get("usage") or {}
    meta = {
        "generated_at": now(),
        "started_at": started,
        "backend": "ThunderOMLX",
        "base_url": BASE_URL,
        "proxy_model": PROXY_MODEL,
        "local_model": LOCAL_MODEL,
        "model_policy": MODEL_POLICY,
        "embedding_route": "unchanged",
        "source_count": len(sources),
        "source_chars": sum(int(item.get("chars") or 0) for item in sources),
        "prompt_chars": len(prompt),
        "bad_chars": bad_chars(text),
        "usage": usage,
    }
    body = (
        "---\n"
        "source: solar-harness\n"
        "artifact_type: thunderomlx_knowledge_extract_smoke\n"
        f"generated_at: {meta['generated_at']}\n"
        f"backend: {meta['backend']}\n"
        f"proxy_model: {PROXY_MODEL}\n"
        f"local_model: {LOCAL_MODEL}\n"
        f"model_policy: {MODEL_POLICY}\n"
        "embedding_route: unchanged\n"
        "---\n\n"
        + text.strip()
        + "\n\n## 运行证据\n\n"
        + "```json\n"
        + json.dumps(meta, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    write(extracted, body)
    write(report, body)
    handoff = f"""# Handoff — {SID} / {NODE_ID}

## 已完成

- 使用后台 tmux multi-task worker 调用 ThunderOMLX API 完成知识抽取。
- 生成报告: `{report}`
- 生成知识页: `{extracted}`

## 已验证

- backend=ThunderOMLX
- base_url={BASE_URL}
- proxy_model={PROXY_MODEL}
- local_model={LOCAL_MODEL}
- model_policy={MODEL_POLICY}
- embedding_route=unchanged
- bad_chars={str(meta['bad_chars']).lower()}
- usage={json.dumps(usage, ensure_ascii=False)}

## 未验证

- 未执行 QMD embed，本节点只验证抽取与输出。

## 风险

- 首次同类 prompt cache miss 时延迟较高；重复抽取可观察 cache_read_input_tokens。

## 后续待办

- 将该 agent 固定为知识抽取默认 profile，避免 Claude Code wrapper 膨胀 prompt。
"""
    write(HANDOFF, handoff)
    write(TASK_DIR / "usage.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "report": str(report), "extracted": str(extracted), "bad_chars": meta["bad_chars"], "usage": usage}, ensure_ascii=False))
    return 0 if not meta["bad_chars"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
