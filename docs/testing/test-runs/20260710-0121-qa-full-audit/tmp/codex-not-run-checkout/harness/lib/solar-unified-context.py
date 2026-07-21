#!/usr/bin/env python3
"""Solar unified context injector.

Routes agent context through Mirage search, which fans out to safe filesystem
mounts, QMD, and Solar DB. Output is bounded and fail-open so it is safe for
Claude hooks, Codex startup instructions, and Solar dispatch prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
HARNESS = Path(os.environ.get("HARNESS_DIR", str(HOME / ".solar" / "harness")))
MIRAGE = HARNESS / "lib" / "solar_mirage.py"
RAGFLOW_ADAPTER = HARNESS / "lib" / "ragflow_adapter.py"
RAGFLOW_CONFIG = HARNESS / "config" / "ragflow.solar.json"
DEFAULT_MAX_CHARS = int(os.environ.get("SOLAR_CONTEXT_MAX_CHARS", "2600"))
DEFAULT_MAX_HITS = int(os.environ.get("SOLAR_CONTEXT_MAX_HITS", "8"))
DEFAULT_TIMEOUT_MS = int(os.environ.get("SOLAR_CONTEXT_TIMEOUT_MS", "8000"))
DEFAULT_RAGFLOW_TIMEOUT_MS = int(os.environ.get("SOLAR_CONTEXT_RAGFLOW_TIMEOUT_MS", "1200"))

LAYER_PRIORITY = {
    "synthesis": 0,
    "concepts": 1,
    "references": 2,
    "code-symbol": 3,
    "code-callgraph": 4,
    "code-chunk": 5,
    "understanding-summary": 6,
    "understanding-claim": 7,
    "understanding-entity": 8,
    "retrieval-evidence": 9,
    "raw-evidence": 10,
    "curated": 11,
    "other": 40,
}

sys.path.insert(0, str(HARNESS / "lib"))
try:
    from resource_telemetry import record_usage
except Exception:  # pragma: no cover - fail-open for hook paths
    record_usage = None  # type: ignore


def _run_mirage(
    query: str,
    max_hits: int,
    max_chars: int,
    timeout_ms: int,
    sources: list[str] | None = None,
) -> dict:
    if not MIRAGE.exists():
        return {"hits": [], "degraded_sources": ["mirage:missing"], "query": query}
    try:
        cmd = [
                sys.executable,
                str(MIRAGE),
                "search",
                query,
                "--json",
                "--max-hits",
                str(max_hits),
                "--max-chars",
                str(max_chars),
        ]
        if sources:
            cmd.extend(["--sources", ",".join(sources)])
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=max(1.0, timeout_ms / 1000.0),
        )
    except subprocess.TimeoutExpired:
        return {"hits": [], "degraded_sources": ["mirage:timeout"], "query": query}
    except Exception as exc:
        return {"hits": [], "degraded_sources": [f"mirage:error:{type(exc).__name__}"], "query": query}
    if proc.returncode != 0:
        return {
            "hits": [],
            "degraded_sources": ["mirage:nonzero"],
            "query": query,
            "stderr": proc.stderr[-500:],
        }
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"hits": [], "degraded_sources": ["mirage:bad_json"], "query": query}
    data.setdefault("query", query)
    return data


def _compact_hit(hit: dict) -> dict:
    path = hit.get("path") or ""
    mount = hit.get("mount") or ""
    source_type = hit.get("source_type") or ""
    compact = {
        "source": source_type,
        "mount": mount,
        "path": path,
        "title": hit.get("title") or path.rsplit("/", 1)[-1],
        "snippet": (hit.get("snippet") or "")[:450],
        "provenance": hit.get("provenance") or "",
        "score": hit.get("score_or_rank", 0),
        "source_hash": hit.get("source_hash") or "",
        "lineage": hit.get("lineage") or [],
        "degraded": bool(hit.get("degraded", False)),
        "degraded_reason": hit.get("degraded_reason"),
    }
    compact["layer"] = hit.get("layer") or _context_layer(compact)
    return compact


def _context_path_text(hit: dict) -> str:
    return " ".join(
        str(hit.get(k) or "").lower()
        for k in ("path", "mount", "title", "snippet", "provenance", "source")
    )


def _extract_cjk_keywords(query: str) -> str:
    cleaned = re.sub(
        r'帮我|请你|请问|帮忙|告诉我|给我|分析一下|分析下|解释一下|介绍一下|讲解|'
        r'详细说明|总结|简单|怎么|如何|基于|关于|是什么|有哪些|有什么|什么是|'
        r'做了什么|负责什么|解决了什么问题|当前是否|当前|现在|是否',
        ' ',
        query,
    )
    cleaned = re.sub(
        r'分析|研究|探讨|优化|改进|实现|设计|解决|处理|应用|使用|部署|集成|'
        r'配置|与.*关系|和.*关系',
        ' ',
        cleaned,
    )
    cleaned = re.sub(r'[的了在里与和及/？?，,。:：()（）]', ' ', cleaned)
    segments = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{4,}', cleaned)
    if segments:
        return max(segments, key=len)
    cjk_any = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{2,}', cleaned)
    return max(cjk_any, key=len) if cjk_any else ""


def _context_relevance(hit: dict, query: str) -> float:
    topic = _extract_cjk_keywords(query) or query.strip()
    if not topic:
        return 0.0
    hay = _context_path_text(hit)
    topic_l = topic.lower()
    boost = 0.0
    if topic_l in hay:
        boost += 2.0
    if query.strip().lower() and query.strip().lower() in hay:
        boost += 0.5
    if "solar-harness-pm-1210-context-inject-fix" in hay:
        boost -= 1.5
    ascii_tokens = [t.lower() for t in re.findall(r'[A-Za-z][A-Za-z0-9_.-]*', query) if len(t) >= 3]
    if ascii_tokens:
        matched = sum(1 for t in ascii_tokens if t in hay)
        if matched == len(ascii_tokens):
            boost += 2.5
        else:
            boost += 0.4 * matched
    return boost


def _is_runtime_noise(hit: dict, query: str) -> bool:
    q = query.lower()
    if any(term in q for term in ("solar-harness", "1210", "context inject", "模型", "修复", "debug")):
        return False
    hay = _context_path_text(hit)
    return any(
        marker in hay
        for marker in (
            "solar-harness-pm-1210-context-inject-fix",
            "solar-interactive-context-policy-fix",
            "solar-context-inject-recall-ranking-fix",
            "context-inject-fix",
            "context inject recall and ranking fix",
        )
    )


def _filter_runtime_noise(hits: list[dict], query: str) -> list[dict]:
    topic = _extract_cjk_keywords(query) or query.strip()
    if not topic:
        return hits
    topical_non_noise = [
        h for h in hits
        if topic.lower() in _context_path_text(h) and not _is_runtime_noise(h, query)
    ]
    if len(topical_non_noise) < 2:
        return hits
    return [h for h in hits if not _is_runtime_noise(h, query)]


def _context_layer(hit: dict) -> str:
    text = _context_path_text(hit)
    source = str(hit.get("source") or "").lower()
    if source == "cocoindex":
        return str(hit.get("layer") or "code-symbol")
    if source == "understanding":
        return str(hit.get("layer") or "understanding-summary")
    if "qmd://solar-wiki/synthesis/" in text or "/knowledge/synthesis/" in text or "/synthesis/" in text:
        return "synthesis"
    if "qmd://solar-wiki/concepts/" in text or "/knowledge/concepts/" in text or "/concepts/" in text:
        return "concepts"
    if "qmd://solar-wiki/references/" in text or "/knowledge/references/" in text or "/references/" in text:
        return "references"
    if any(f"qmd://solar-wiki/{bucket}/" in text or f"/knowledge/{bucket}/" in text or f"/{bucket}/" in text
           for bucket in ("entities", "projects", "skills", "theses", "timelines", "contradictions", "indexes")):
        return "curated"
    if "qmd://solar-wiki/raw/" in text or "/knowledge/_raw/" in text or "/_raw/" in text or "/raw/" in text:
        return "raw-evidence"
    if str(hit.get("source") or "").lower() == "ragflow":
        return "retrieval-evidence"
    return "other"


def _layer_priority(layer: str) -> int:
    return LAYER_PRIORITY.get(layer, 50)


def _sort_context_hits(hits: list[dict], query: str = "") -> list[dict]:
    source_priority = {"qmd": 0, "solar_db": 1, "cocoindex": 2, "understanding": 3, "mirage_path": 4, "ragflow": 5}
    for hit in hits:
        hit["layer"] = _context_layer(hit)
    return sorted(
        hits,
        key=lambda h: (
            -_context_relevance(h, query),
            _layer_priority(str(h.get("layer") or "other")),
            source_priority.get(str(h.get("source") or ""), 9),
            -float(h.get("score") or 0),
            str(h.get("title") or ""),
        ),
    )


def _ragflow_enabled() -> bool:
    if os.environ.get("SOLAR_CONTEXT_RAGFLOW", "").strip() in {"1", "true", "TRUE", "yes"}:
        return True
    if not RAGFLOW_CONFIG.exists():
        return False
    try:
        data = json.loads(RAGFLOW_CONFIG.read_text(encoding="utf-8"))
        return bool(data.get("enabled"))
    except Exception:
        return False


def _run_ragflow(query: str, max_hits: int, timeout_ms: int) -> dict:
    if not _ragflow_enabled():
        return {"hits": [], "degraded": []}
    if not RAGFLOW_ADAPTER.exists():
        return {"hits": [], "degraded": ["ragflow:adapter_missing"]}
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(RAGFLOW_ADAPTER),
                "search",
                "--query",
                query,
                "--source",
                "both",
                "--page-size",
                str(max_hits),
                "--timeout-sec",
                str(max(0.5, timeout_ms / 1000.0)),
                "--json",
                "--fail-open",
            ],
            text=True,
            capture_output=True,
            timeout=max(1.0, timeout_ms / 1000.0 + 0.5),
        )
    except subprocess.TimeoutExpired:
        return {"hits": [], "degraded": ["ragflow:timeout"]}
    except Exception as exc:
        return {"hits": [], "degraded": [f"ragflow:error:{type(exc).__name__}"]}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"hits": [], "degraded": ["ragflow:bad_json"]}
    if proc.returncode not in (0, 2):
        data.setdefault("degraded", []).append(f"ragflow:rc={proc.returncode}")
    return data


def _compact_ragflow_hit(hit: dict) -> dict:
    title = hit.get("title") or hit.get("document_id") or hit.get("id") or "RAGFlow chunk"
    compact = {
        "source": "ragflow",
        "mount": "ragflow://",
        "path": str(hit.get("document_id") or hit.get("id") or ""),
        "title": title,
        "snippet": (hit.get("snippet") or "")[:450],
        "provenance": "ragflow:retrieval",
        "score": hit.get("score", 0),
    }
    compact["layer"] = _context_layer(compact)
    return compact


def retrieve(
    query: str,
    max_hits: int = DEFAULT_MAX_HITS,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    *,
    sources: list[str] | None = None,
    layers: list[str] | None = None,
    limit: int | None = None,
    task_kind: str = "general",
    token_budget: int | None = None,
) -> dict:
    started = time.monotonic()
    if limit is not None:
        max_hits = limit
    if token_budget is not None:
        max_chars = min(max_chars, max(200, token_budget * 4))
    if sources is None and task_kind == "code":
        sources = ["mirage_path", "qmd", "solar_db", "cocoindex"]
    elif sources is None and task_kind in {"paper", "doc"}:
        sources = ["mirage_path", "qmd", "solar_db", "understanding"]
    data = _run_mirage(query, max_hits=max_hits, max_chars=max_chars, timeout_ms=timeout_ms, sources=sources)
    if not data.get("hits") and any("\u4e00" <= ch <= "\u9fff" for ch in query):
        fallback_query = "obsidian wiki integration solar harness"
        data = _run_mirage(fallback_query, max_hits=max_hits, max_chars=max_chars, timeout_ms=timeout_ms, sources=sources)
        data["fallback_query"] = fallback_query
    hits = [_compact_hit(h) for h in data.get("hits", []) if isinstance(h, dict)]
    ragflow_data = _run_ragflow(
        query,
        max_hits=max(1, min(3, max_hits)),
        timeout_ms=DEFAULT_RAGFLOW_TIMEOUT_MS,
    )
    hits += [_compact_ragflow_hit(h) for h in ragflow_data.get("hits", []) if isinstance(h, dict)]
    if layers:
        allowed_layers = set(layers)
        hits = [h for h in hits if h.get("layer") in allowed_layers]
    if not hits:
        hits = [
            {
                "source": "default",
                "mount": "/knowledge",
                "path": str(HOME / "Knowledge"),
                "title": "Solar Obsidian Vault",
                "snippet": "本机默认知识库。优先用 `solar-harness wiki qmd-search \"<query>\" --json` 或 `solar-harness mirage search \"<query>\" --json` 检索。",
                "provenance": "static:solar-unified-context",
                "score": 0.1,
                "layer": "other",
            },
            {
                "source": "default",
                "mount": "/qmd",
                "path": "qmd://solar-wiki",
                "title": "QMD solar-wiki",
                "snippet": "MinerU Document Explorer 负责 PDF/Markdown/文档索引和语义检索；后台 `solar-harness wiki qmd-embed status` 处理 embedding backlog。",
                "provenance": "static:solar-unified-context",
                "score": 0.1,
                "layer": "other",
            },
            {
                "source": "default",
                "mount": "/solar-db",
                "path": str(HOME / ".solar" / "solar.db"),
                "title": "Solar DB",
                "snippet": "Solar DB 保存 sprint、cortex、accepted artifacts、obsidian_vault_index 和 FTS 索引。设计/开发前先查已有资产，避免重复造轮子。",
                "provenance": "static:solar-unified-context",
                "score": 0.1,
                "layer": "other",
            },
        ][:max_hits]
    hits = _filter_runtime_noise(_sort_context_hits(hits, query=query), query)
    seen: dict[tuple[str, str], dict] = {}
    for hit in hits:
        key = (str(hit.get("source_hash") or hit.get("path") or ""), str(hit.get("layer") or ""))
        current = seen.get(key)
        if current is None or float(hit.get("score") or 0) > float(current.get("score") or 0):
            seen[key] = hit
    hits = list(seen.values())
    hits = _filter_runtime_noise(_sort_context_hits(hits, query=query), query)
    total = 0
    kept = []
    for hit in hits:
        payload = f"{hit['source']} {hit['path']} {hit['snippet']}"
        if total + len(payload) > max_chars:
            break
        kept.append(hit)
        total += len(payload)
    source_counts: dict[str, int] = {}
    degraded_sources = list(data.get("degraded_sources", [])) + list(ragflow_data.get("degraded", []))
    for hit in kept:
        source = str(hit.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
        if hit.get("degraded"):
            reason = hit.get("degraded_reason") or f"{source}:degraded"
            degraded_sources.append(str(reason))
    return {
        "query": query,
        "hits": kept,
        "source_counts": source_counts,
        "degraded_sources": sorted(set(str(x) for x in degraded_sources if x)),
        "lineage_refs": sorted({str(x) for h in kept for x in (h.get("lineage") or []) if x})[:50],
        "source_hash_refs": sorted({str(h.get("source_hash")) for h in kept if h.get("source_hash")})[:50],
        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        "total_chars": total,
        "backend": "mirage+qmd+solar_db+obsidian+cocoindex+understanding+ragflow_optional",
    }


def format_hook(data: dict, max_chars: int) -> str:
    hits = data.get("hits") or []
    if not hits:
        return ""
    lines = [
        "<solar-unified-context>",
        "来源: Mirage + QMD solar-wiki + Obsidian Vault + Solar DB + CocoIndex + Understanding + RAGFlow(optional)",
        "规则: 开始开发/设计/分析前，优先参考这些命中；如不足，再主动搜索 vault/qmd。",
        "排序: synthesis/concepts/references/code/understanding 分层融合；raw 只作为证据层靠后。",
    ]
    total = sum(len(x) for x in lines)
    for hit in hits:
        path = str(hit.get("path") or "")
        mount = "" if "://" in path or path.startswith(str(HOME)) or path.startswith("obsidian:") else str(hit.get("mount") or "")
        entry = f"- [{hit.get('source')}:{hit.get('layer') or 'N/A'}] {hit.get('title') or 'N/A'} ({mount}{path}): {hit.get('snippet')}"
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)
    degraded = data.get("degraded_sources") or []
    if degraded:
        lines.append("降级源: " + ", ".join(str(x) for x in degraded[:5]))
    lines.append("</solar-unified-context>")
    return "\n".join(lines)


def format_markdown(data: dict, max_chars: int) -> str:
    text = format_hook(data, max_chars)
    if not text:
        return "没有命中统一知识上下文。"
    return text.replace("<solar-unified-context>", "## Solar Unified Context").replace("</solar-unified-context>", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Solar unified knowledge context")
    parser.add_argument("--query", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--format", choices=("hook", "markdown"), default="hook")
    parser.add_argument("--max-hits", type=int, default=DEFAULT_MAX_HITS)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--fail-open", action="store_true")
    args = parser.parse_args()

    started = time.monotonic()
    success = True
    error = ""
    try:
        data = retrieve(args.query, args.max_hits, args.max_chars, args.timeout_ms)
    except Exception as exc:
        success = False
        error = str(exc)
        if args.fail_open:
            data = {"query": args.query, "hits": [], "degraded_sources": [str(exc)], "backend": "error"}
        else:
            raise
    finally:
        if record_usage is not None:
            try:
                record_usage(
                    "tool",
                    "solar-unified-context",
                    intent="context.inject",
                    input_summary=args.query,
                    success=success,
                    output_summary=(
                        f"hits={len(data.get('hits', [])) if 'data' in locals() else 0}; "
                        f"degraded={','.join(str(x) for x in (data.get('degraded_sources', []) if 'data' in locals() else []))}"
                    ),
                    error=error,
                    started_at=started,
                    description="Solar-Harness unified context injector over Mirage, QMD, Obsidian, Solar DB and optional RAGFlow.",
                    keywords=["context", "mirage", "qmd", "obsidian", "solar-db", "knowledge"],
                    config={"backend": "mirage+qmd+solar_db+obsidian+cocoindex+understanding+ragflow_optional"},
                )
            except Exception:
                pass

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        print(format_markdown(data, args.max_chars))
    else:
        text = format_hook(data, args.max_chars)
        if text:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
