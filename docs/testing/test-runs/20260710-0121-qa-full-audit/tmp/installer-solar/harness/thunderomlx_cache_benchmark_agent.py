#!/usr/bin/env python3
"""Headless ThunderOMLX cache benchmark worker for multi-task tmux panes."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import statistics
import time
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
TASK_DIR = Path(os.environ.get("TASK_DIR", HARNESS_DIR / "run" / "multi-task" / "manual-thunderomlx-cache-benchmark"))
BASE_URL = os.environ.get("THUNDEROMLX_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
PROXY_MODEL = os.environ.get("THUNDEROMLX_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
LOCAL_MODEL = os.environ.get("THUNDEROMLX_LOCAL_MODEL", "Qwen3.6-35b-a3b")
API_KEY = os.environ.get("THUNDEROMLX_AUTH_TOKEN", "local-thunderomlx")
MAX_TOKENS = int(os.environ.get("SOLAR_THUNDEROMLX_BENCH_MAX_TOKENS", "320") or "320")


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


def bad_chars(text: str) -> bool:
    return bool(re.search(r"[\ufffd\ue000-\uf8ff]", text))


def read_corpus(paths: list[str]) -> str:
    chunks: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.exists() and path.is_file():
            chunks.append(f"# Source: {path}\n\n{path.read_text(encoding='utf-8', errors='replace')}")
    if not chunks:
        raise SystemExit("benchmark read_scope is empty or missing")
    return "\n\n".join(chunks)


def call_thunderomlx(prompt: str) -> dict[str, Any]:
    payload = {
        "model": PROXY_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        raise SystemExit(f"ThunderOMLX HTTP {exc.code}: {body}") from exc
    elapsed = time.perf_counter() - started
    data = json.loads(body)
    data["_wall_seconds"] = elapsed
    return data


def content_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        elif isinstance(item, dict) and "text" in item:
            parts.append(str(item.get("text") or ""))
    return "\n".join(parts).strip()


def build_prompt(label: str, chars: int, trial: int, corpus: str) -> str:
    clipped = corpus[:chars]
    salt = f"BENCH-SALT {SID} {NODE_ID} {label} trial-{trial} generated-{now()}"
    return f"""你是 Solar Harness 的知识抽取性能基准 worker。请基于下面材料输出一个简短中文结构化摘要。

要求：
- 不输出 secrets、token、API key。
- 不输出乱码。
- 固定输出 4 节：功能模块、用户价值、关键命令、风险边界。
- 每节 2 条以内，保持输出长度稳定。

{salt}

```markdown
{clipped}
```
"""


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[idx]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_len: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_len.setdefault(row["length"], []).append(row)
    summary: dict[str, Any] = {}
    for label, items in by_len.items():
        cold = [r for r in items if r["phase"] == "cold"]
        hot = [r for r in items if r["phase"] == "hot"]
        cold_lat = [float(r["wall_seconds"]) for r in cold]
        hot_lat = [float(r["wall_seconds"]) for r in hot]
        hot_hit = [float(r["cache_hit_ratio"]) for r in hot]
        summary[label] = {
            "cold_p50_seconds": percentile(cold_lat, 0.50),
            "cold_p95_seconds": percentile(cold_lat, 0.95),
            "hot_p50_seconds": percentile(hot_lat, 0.50),
            "hot_p95_seconds": percentile(hot_lat, 0.95),
            "hot_cache_hit_avg": statistics.mean(hot_hit) if hot_hit else 0.0,
            "speedup_p50": (percentile(cold_lat, 0.50) / percentile(hot_lat, 0.50)) if hot_lat and percentile(hot_lat, 0.50) else 0.0,
            "bad_chars": any(bool(r["bad_chars"]) for r in items),
        }
    return summary


def output_paths(node: dict[str, Any]) -> tuple[Path, Path]:
    report = HARNESS_DIR / "monitor-reports" / f"{SID}.md"
    results = TASK_DIR / "results.json"
    for raw in listify(node.get("write_scope")):
        path = Path(raw).expanduser()
        if path.name.endswith(".md") and "monitor-reports" in str(path):
            report = path
        elif path.name == "results.json":
            results = path
        elif path.suffix == "":
            results = path / "results.json"
    return report, results


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not GRAPH.exists():
        raise SystemExit(f"GRAPH missing: {GRAPH}")
    graph = load_json(GRAPH)
    node = node_from_graph(graph)
    corpus = read_corpus(listify(node.get("read_scope")))
    lengths = [
        ("short", 2400),
        ("medium", 9000),
        ("large", 18000),
    ]
    trials = int(os.environ.get("SOLAR_THUNDEROMLX_BENCH_TRIALS", "3") or "3")
    rows: list[dict[str, Any]] = []
    started_at = now()
    for label, chars in lengths:
        for trial in range(1, trials + 1):
            prompt = build_prompt(label, chars, trial, corpus)
            cold = call_thunderomlx(prompt)
            hot = call_thunderomlx(prompt)
            for phase, response in [("cold", cold), ("hot", hot)]:
                text = content_text(response)
                usage = response.get("usage") or {}
                input_tokens = int(usage.get("input_tokens") or 0)
                cache_read = int(usage.get("cache_read_input_tokens") or 0)
                rows.append(
                    {
                        "length": label,
                        "trial": trial,
                        "phase": phase,
                        "prompt_chars": len(prompt),
                        "wall_seconds": round(float(response.get("_wall_seconds") or 0.0), 3),
                        "input_tokens": input_tokens,
                        "output_tokens": int(usage.get("output_tokens") or 0),
                        "cache_read_input_tokens": cache_read,
                        "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0),
                        "cache_hit_ratio": round((cache_read / input_tokens), 4) if input_tokens else 0.0,
                        "bad_chars": bad_chars(text),
                    }
                )
    summary = summarize(rows)
    report, results = output_paths(node)
    payload = {
        "generated_at": now(),
        "started_at": started_at,
        "backend": "ThunderOMLX",
        "base_url": BASE_URL,
        "proxy_model": PROXY_MODEL,
        "local_model": LOCAL_MODEL,
        "trials_per_length": trials,
        "summary": summary,
        "rows": rows,
    }
    lines = [
        f"# ThunderOMLX 知识抽取缓存基准报告",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- backend: `{payload['backend']}`",
        f"- proxy_model: `{PROXY_MODEL}`",
        f"- local_model: `{LOCAL_MODEL}`",
        f"- trials_per_length: `{trials}`",
        "",
        "## 汇总",
        "",
        "| length | cold_p50_s | hot_p50_s | speedup_p50 | hot_cache_hit_avg | bad_chars |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for label, item in summary.items():
        lines.append(
            f"| {label} | {item['cold_p50_seconds']:.3f} | {item['hot_p50_seconds']:.3f} | "
            f"{item['speedup_p50']:.2f} | {item['hot_cache_hit_avg']:.2%} | {str(item['bad_chars']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## 原始行",
            "",
            "```json",
            json.dumps(rows, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    write(results, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write(report, "\n".join(lines) + "\n")
    handoff = f"""# Handoff — {SID} / {NODE_ID}

## 已完成

- 执行 ThunderOMLX 知识抽取缓存基准：3 档文档长度，每档冷跑/热跑各 {trials} 次。
- 生成报告: `{report}`
- 生成 JSON: `{results}`

## 已验证

- backend=ThunderOMLX
- base_url={BASE_URL}
- proxy_model={PROXY_MODEL}
- local_model={LOCAL_MODEL}
- bad_chars={str(any(row['bad_chars'] for row in rows)).lower()}

## 关键结论

```json
{json.dumps(summary, ensure_ascii=False, indent=2)}
```
"""
    write(HANDOFF, handoff)
    print(json.dumps({"ok": True, "report": str(report), "results": str(results), "summary": summary}, ensure_ascii=False))
    return 0 if not any(row["bad_chars"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
