#!/usr/bin/env python3
"""CocoIndex adapter surface for Mirage search.

The adapter prefers a configured CocoIndex command when available.  When that
command is not installed yet, it falls back to a bounded read-only code scan and
marks the source as degraded so callers can see that this is not a healthy
CocoIndex index response.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
ADAPTER_TIMEOUT_S = float(os.environ.get("SOLAR_COCO_TIMEOUT_S", "3"))


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _configured_query_cmd(query: str, limit: int) -> list[str] | None:
    template = os.environ.get("SOLAR_COCO_QUERY_CMD", "").strip()
    if template:
        return template.format(query=query, limit=limit).split()
    solar_bin = shutil.which("solar-harness")
    if solar_bin:
        return [solar_bin, "coco", "query", query, "--json", "--limit", str(limit)]
    return None


def _normalize_command_hit(item: dict[str, Any], index: int) -> dict[str, Any]:
    snippet = str(item.get("snippet") or item.get("text") or item.get("summary") or "")[:500]
    path = str(item.get("path") or item.get("symbol") or item.get("id") or f"hit-{index}")
    layer = str(item.get("layer") or item.get("capability") or "code-symbol")
    if layer in {"callgraph", "code_callgraph"}:
        layer = "code-callgraph"
    elif layer in {"chunk", "code_chunk"}:
        layer = "code-chunk"
    elif layer not in {"code-symbol", "code-callgraph", "code-chunk", "retrieval-evidence"}:
        layer = "code-symbol"
    source_hash = str(item.get("source_hash") or _hash_text(path + "\n" + snippet))
    return {
        "mount": "/cocoindex",
        "path": str(item.get("uri") or f"cocoindex://{path.lstrip('/')}"),
        "source_type": "cocoindex",
        "layer": layer,
        "snippet": snippet,
        "provenance": str(item.get("provenance") or "cocoindex:query"),
        "score_or_rank": float(item.get("score_or_rank", item.get("score", 0.5)) or 0.5),
        "source_hash": source_hash,
        "lineage": item.get("lineage") if isinstance(item.get("lineage"), list) else [path],
        "degraded": bool(item.get("degraded", False)),
        "degraded_reason": item.get("degraded_reason"),
    }


def _query_external(query: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    cmd = _configured_query_cmd(query, limit)
    if not cmd:
        return [], "cocoindex_cli_unavailable"
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=ADAPTER_TIMEOUT_S)
    except FileNotFoundError:
        return [], "cocoindex_cli_unavailable"
    except subprocess.TimeoutExpired:
        return [], "cocoindex_timeout"
    except Exception as exc:
        return [], f"cocoindex_error:{type(exc).__name__}"
    if proc.returncode != 0:
        return [], f"cocoindex_rc:{proc.returncode}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [], "cocoindex_bad_json"
    raw_hits = data.get("hits", data) if isinstance(data, dict) else data
    if not isinstance(raw_hits, list):
        return [], "cocoindex_bad_json"
    return [_normalize_command_hit(item, i) for i, item in enumerate(raw_hits) if isinstance(item, dict)][:limit], None


def _query_variants(query: str) -> list[str]:
    variants = [query.strip()]
    variants.extend(t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query) if t.lower() not in {"code", "the", "and"})
    seen: list[str] = []
    for item in variants:
        if item and item not in seen:
            seen.append(item)
    return seen


def _local_code_scan(query: str, limit: int) -> list[dict[str, Any]]:
    roots = [
        HARNESS_DIR / "lib",
        HARNESS_DIR / "tools",
        HARNESS_DIR / "scripts",
        HARNESS_DIR / "tests",
    ]
    existing = [str(p) for p in roots if p.is_dir()]
    if not existing:
        return []
    rg = shutil.which("rg")
    if not rg:
        return []
    hits: list[dict[str, Any]] = []
    for variant in _query_variants(query):
        cmd = [
            rg,
            "--json",
            "--ignore-case",
            "--max-count",
            str(max(1, limit)),
            "--max-filesize",
            "512K",
            "-g",
            "*.py",
            "--",
            variant,
            *existing,
        ]
        try:
            proc = subprocess.run(cmd, text=True, capture_output=True, timeout=ADAPTER_TIMEOUT_S)
        except Exception:
            continue
        if proc.returncode not in (0, 1):
            continue
        for line in proc.stdout.splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "match":
                continue
            data = entry.get("data") or {}
            file_path = str((data.get("path") or {}).get("text") or "")
            line_no = data.get("line_number", 0)
            text = str((data.get("lines") or {}).get("text") or "").strip()
            if not file_path or not text:
                continue
            rel = os.path.relpath(file_path, str(HARNESS_DIR))
            source_hash = _hash_text(f"{rel}:{line_no}:{text}")
            hits.append({
                "mount": "/cocoindex",
                "path": f"cocoindex://code/{rel}:{line_no}",
                "source_type": "cocoindex",
                "layer": "code-chunk",
                "snippet": text[:500],
                "provenance": f"cocoindex:local-code-scan:{rel}:{line_no}",
                "score_or_rank": 0.45,
                "source_hash": source_hash,
                "lineage": [f"repo:Solar", f"file:{rel}", f"line:{line_no}"],
                "degraded": True,
                "degraded_reason": "cocoindex_cli_unavailable:local_code_scan_fallback",
            })
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    return hits


def search(query: str, *, limit: int = 5, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], bool, str | None]:
    hits, degraded_reason = _query_external(query, limit)
    if hits:
        return hits, True, degraded_reason
    fallback_hits = _local_code_scan(query, limit)
    if fallback_hits:
        return fallback_hits, True, fallback_hits[0].get("degraded_reason")
    return [], degraded_reason is None, degraded_reason or "cocoindex:no_results"


def health_check() -> dict[str, Any]:
    cmd = _configured_query_cmd("__health__", 1)
    command_available = bool(cmd and shutil.which(cmd[0]))
    return {
        "ok": command_available,
        "source_type": "cocoindex",
        "command_available": command_available,
        "degraded": not command_available,
        "degraded_reason": None if command_available else "cocoindex_cli_unavailable",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
