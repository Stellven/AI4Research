#!/usr/bin/env python3
"""understand-anything artifact adapter for Mirage search."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
DEFAULT_STORES = [
    Path(os.environ.get("SOLAR_UNDERSTANDING_STORE", str(Path.home() / ".solar" / "understanding"))),
    HARNESS_DIR / ".understand-anything",
]


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _artifact_files(stores: list[Path] | None = None) -> list[Path]:
    roots = stores or DEFAULT_STORES
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".json":
            files.append(root)
            continue
        files.extend(root.glob("*/artifact.json"))
        files.extend(root.glob("**/knowledge_graph.json"))
        files.extend(root.glob("**/semantic_proof.json"))
    return sorted(set(files))


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _artifact_id(path: Path, data: dict[str, Any]) -> str:
    return str(data.get("artifact_id") or data.get("id") or path.parent.name or path.stem)


def _contains_query(value: str, query_terms: list[str]) -> bool:
    lower = value.lower()
    return any(term in lower for term in query_terms)


def _iter_hit_fields(data: dict[str, Any]) -> list[tuple[str, str, str, float]]:
    rows: list[tuple[str, str, str, float]] = []
    summary = str(data.get("summary") or data.get("overview") or data.get("description") or "")
    if summary:
        rows.append(("summary", "understanding-summary", summary, float(data.get("confidence", 0.65) or 0.65)))
    for key in ("claims", "decisions", "open_questions", "entities"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("name") or item.get("summary") or "")
                score = float(item.get("confidence", data.get("confidence", 0.6)) or 0.6)
            else:
                text = str(item)
                score = float(data.get("confidence", 0.6) or 0.6)
            if not text:
                continue
            layer = "understanding-claim" if key == "claims" else "understanding-entity" if key == "entities" else "understanding-summary"
            rows.append((f"{key}-{index}", layer, text, score))
    return rows


def search(query: str, *, limit: int = 5, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], bool, str | None]:
    query_terms = [t.lower() for t in query.split() if t.strip()]
    files = _artifact_files()
    if not files:
        return [], False, "understanding_store_missing_or_empty"
    hits: list[dict[str, Any]] = []
    for artifact_path in files:
        data = _load_json(artifact_path)
        if not data:
            continue
        aid = _artifact_id(artifact_path, data)
        source_path = str(data.get("source_path") or data.get("repo_path") or artifact_path)
        source_hash = str(data.get("source_hash") or _hash_text(source_path + ":" + aid))
        for field_id, layer, text, score in _iter_hit_fields(data):
            if query_terms and not _contains_query(" ".join([aid, source_path, text]), query_terms):
                continue
            hits.append({
                "mount": "/understanding",
                "path": f"ua://{aid}/{field_id}",
                "source_type": "understanding",
                "layer": layer,
                "snippet": text[:500],
                "provenance": f"ua:artifact@{aid}",
                "score_or_rank": score,
                "source_hash": source_hash,
                "lineage": [f"file:{source_path}", f"artifact:{aid}", f"artifact_file:{artifact_path}"],
                "degraded": bool(data.get("degraded")),
                "degraded_reason": ";".join(str(x) for x in data.get("degraded", []) if x) if isinstance(data.get("degraded"), list) else None,
            })
            if len(hits) >= limit:
                return hits, True, None
    return hits[:limit], True, "understanding:no_results" if not hits else None


def health_check() -> dict[str, Any]:
    files = _artifact_files()
    return {
        "ok": bool(files),
        "source_type": "understanding",
        "artifact_count": len(files),
        "stores": [str(p) for p in DEFAULT_STORES],
        "degraded": not bool(files),
        "degraded_reason": None if files else "understanding_store_missing_or_empty",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
