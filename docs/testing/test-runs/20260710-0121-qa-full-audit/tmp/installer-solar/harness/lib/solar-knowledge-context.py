#!/usr/bin/env python3
"""
solar-knowledge-context.py — Solar KB + Obsidian vault retrieval router.

Usage:
  python3 solar-knowledge-context.py --query TEXT [--json] [--max-chars N]
                                       [--timeout-ms N] [--fail-open]
                                       [--max-hits N]

Environment:
  SOLAR_DB          — override ~/.solar/solar.db path
  OBSIDIAN_VAULT_PATH — override ~/Knowledge
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from qmd_resolver import resolve_qmd_bin

DB_PATH = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))
VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Knowledge")))
DEFAULT_MAX_CHARS = int(os.environ.get("SOLAR_KB_MAX_CHARS", "2000"))
DEFAULT_TIMEOUT_MS = int(os.environ.get("SOLAR_KB_TIMEOUT_MS", "700"))
DEFAULT_MAX_HITS = 8


def _read_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta


def _ground_derived_hit(hit: dict) -> dict:
    """If a QMD hit is derived extracted.md, attach source grounding metadata."""
    path_text = str(hit.get("path") or hit.get("id") or "")
    if "_extracted/" not in path_text and "/_extracted/" not in path_text:
        return hit
    local_path = path_text
    if local_path.startswith("qmd://"):
        local_path = local_path.replace("qmd://solar-wiki/", str(VAULT_PATH).rstrip("/") + "/", 1)
    path = Path(local_path)
    meta = _read_frontmatter(path)
    source_path = meta.get("source_path") or meta.get("source")
    source_sha = meta.get("source_sha256")
    if source_path:
        hit["derived"] = True
        hit["source_doc_path"] = source_path
        hit["source_sha256"] = source_sha or ""
        hit["grounding_required"] = True
        source = Path(source_path).expanduser()
        if source.exists():
            source_text = source.read_text(encoding="utf-8", errors="replace")
            source_snippet = _best_source_snippet(source_text, str(hit.get("snippet") or ""), max_chars=700)
            hit["grounding_status"] = "grounded"
            hit["grounding_source_snippet"] = source_snippet
        else:
            hit["grounding_status"] = "weak_missing_source"
        prefix = f"[DERIVED: use source evidence `{source_path}`"
        if source_sha:
            prefix += f" sha={source_sha[:12]}"
        prefix += f" grounding={hit.get('grounding_status', 'unknown')}] "
        snippet = prefix + str(hit.get("snippet") or "")
        if hit.get("grounding_source_snippet"):
            snippet += "\n[SOURCE-GROUNDING]\n" + str(hit["grounding_source_snippet"])
        hit["snippet"] = snippet
    return hit


def _best_source_snippet(source_text: str, derived_snippet: str, max_chars: int = 700) -> str:
    """Return a raw/canonical evidence snippet for a derived hit.

    The matching is intentionally conservative: if no useful overlap is found,
    use the first non-frontmatter section so the caller still has source evidence
    instead of relying only on the derived summary.
    """
    text = source_text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            text = text[end + 4 :]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text.strip()[:max_chars]
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_\-]{4,}|[\u4e00-\u9fff]{2,}", derived_snippet)[:30]]
    best = paragraphs[0]
    best_score = -1
    for para in paragraphs[:80]:
        low = para.lower()
        score = sum(1 for term in terms if term in low)
        if score > best_score:
            best = para
            best_score = score
    return best[:max_chars]


def _fts_query(conn: sqlite3.Connection, query: str, max_hits: int) -> list[dict]:
    """Query fts_unified_search FTS5 table."""
    # Escape FTS5 special chars
    safe_q = re.sub(r'["\'\+\-\*\(\)\:\^]', ' ', query).strip()
    if not safe_q:
        return []
    hits = []
    try:
        rows = conn.execute(
            """
            SELECT doc_id, doc_type, title, content, tags, metadata
            FROM fts_unified_search
            WHERE fts_unified_search MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (safe_q, max_hits),
        ).fetchall()
        for doc_id, doc_type, title, content, tags, metadata in rows:
            snippet = (content or "")[:400]
            hits.append({
                "source": "fts_unified_search",
                "table": doc_type or "unknown",
                "id": doc_id or "",
                "title": title or "",
                "snippet": snippet,
                "path": "",
                "score": 1.0,
            })
    except Exception:
        pass
    return hits


def _cortex_fallback(conn: sqlite3.Connection, query: str, max_hits: int) -> list[dict]:
    """Fallback: cortex_sources LIKE query."""
    like = f"%{query[:60]}%"
    hits = []
    try:
        rows = conn.execute(
            """
            SELECT citation_key, title, finding, credibility
            FROM cortex_sources
            WHERE title LIKE ? OR finding LIKE ?
            ORDER BY credibility DESC
            LIMIT ?
            """,
            (like, like, max_hits),
        ).fetchall()
        for key, title, finding, cred in rows:
            hits.append({
                "source": "cortex_sources",
                "table": "cortex_sources",
                "id": key or "",
                "title": title or "",
                "snippet": (finding or "")[:400],
                "path": "",
                "score": float(cred or 0.5),
            })
    except Exception:
        pass
    return hits


def _semantic_hits(conn: sqlite3.Connection, query: str, max_hits: int) -> list[dict]:
    """Query evo_memory_semantic.value (correct column name)."""
    like = f"%{query[:60]}%"
    hits = []
    try:
        rows = conn.execute(
            """
            SELECT memory_id, namespace, key, value, confidence
            FROM evo_memory_semantic
            WHERE (namespace LIKE 'rule%' OR namespace LIKE 'knowledge%')
              AND (key LIKE ? OR CAST(value AS TEXT) LIKE ?)
            ORDER BY confidence DESC
            LIMIT ?
            """,
            (like, like, max_hits),
        ).fetchall()
        for mid, ns, key, value, conf in rows:
            # value is JSON or plain text
            raw = ""
            try:
                raw = json.dumps(json.loads(value), ensure_ascii=False)[:300]
            except Exception:
                raw = str(value or "")[:300]
            hits.append({
                "source": "evo_memory_semantic",
                "table": "evo_memory_semantic",
                "id": mid or "",
                "title": f"{ns}/{key}",
                "snippet": raw,
                "path": "",
                "score": float(conf or 0.5),
            })
    except Exception:
        pass
    return hits


def _vault_hits(conn: sqlite3.Connection, query: str, max_hits: int) -> list[dict]:
    """Query obsidian_vault_index if it exists, else skip."""
    hits = []
    try:
        conn.execute("SELECT 1 FROM obsidian_vault_index LIMIT 1")
    except Exception:
        return hits
    # Split into tokens for multi-token queries; each token must match in at least one column
    tokens = [t for t in re.split(r'\s+', query.strip()) if len(t) >= 2][:8]
    if not tokens:
        tokens = [query[:40]]
    # Build per-token OR clause: (title LIKE ? OR summary LIKE ? OR tags LIKE ?)
    token_clause = " OR ".join(["(title LIKE ? OR summary LIKE ? OR tags LIKE ?)" for _ in tokens])
    params: list = []
    for t in tokens:
        like = f"%{t[:40]}%"
        params.extend([like, like, like])
    params.append(max_hits)
    try:
        rows = conn.execute(
            f"""
            SELECT file_path, title, summary, tags
            FROM obsidian_vault_index
            WHERE deleted_at IS NULL
              AND ({token_clause})
            ORDER BY indexed_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        for fpath, title, summary, tags in rows:
            abs_path = str(VAULT_PATH / fpath) if fpath else str(VAULT_PATH)
            hits.append({
                "source": str(VAULT_PATH),
                "table": "obsidian_vault_index",
                "id": fpath or "",
                "title": title or "",
                "snippet": (summary or "")[:400],
                "path": abs_path,
                "score": 0.8,
            })
    except Exception:
        pass
    return hits


def _extract_cjk_keywords(query: str) -> str:
    """Strip CJK function/action words and return the topical noun phrase."""
    if len(query) <= 4:
        return query
    # Stage 1: strip function words / connectors / request phrases
    stop1 = re.compile(
        r'帮我|请你|请问|帮忙|告诉我|给我|分析一下|解释一下|介绍一下|讲解|'
        r'详细说明|总结|简单|怎么|如何|基于|关于|是什么|有哪些|有什么|什么是'
    )
    cleaned = stop1.sub(' ', query).strip()
    # Stage 2: strip action verbs that follow a topic noun
    stop2 = re.compile(
        r'分析|研究|探讨|优化|改进|实现|设计|解决|处理|应用|使用|部署|'
        r'配置|与.*关系|和.*关系'
    )
    cleaned = stop2.sub(' ', cleaned).strip()
    # Extract all significant CJK segments (4+ chars), pick longest
    segments = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{4,}', cleaned)
    if segments:
        best = max(segments, key=len)
        return best
    # Fallback: return first 12 chars of cleaned or original
    cjk_any = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{2,}', cleaned)
    if cjk_any:
        return max(cjk_any, key=len)
    return query[:20]


def _qmd_hits_from_raw(raw: object) -> list[dict]:
    items = raw if isinstance(raw, list) else (
        raw.get("results") or raw.get("hits") or [] if isinstance(raw, dict) else []
    )
    hits = []
    for r in items:
        if not isinstance(r, dict):
            continue
        file_path = str(r.get("file") or r.get("path") or r.get("docid") or "")
        title = str(r.get("title") or file_path.rsplit("/", 1)[-1] or "")
        snippet = str(r.get("snippet") or r.get("body") or r.get("content") or "")[:400]
        score = float(r.get("score", 0.7))
        hit = {
            "source": "qmd:solar-wiki",
            "table": "qmd",
            "id": file_path,
            "title": title,
            "snippet": snippet,
            "path": file_path,
            "score": score,
        }
        hits.append(_ground_derived_hit(hit))
    return hits


def _qmd_fallback(query: str, max_hits: int, timeout_remaining_ms: float) -> list[dict]:
    """Fallback: qmd search solar-wiki. Returns [] on any failure (fail-open)."""
    if timeout_remaining_ms < 200:
        return []
    qmd_bin = resolve_qmd_bin()
    if not qmd_bin:
        return []
    try:
        per_call = max(0.5, (timeout_remaining_ms / 2) / 1000.0)
        queries = [query]
        kw = _extract_cjk_keywords(query)
        if kw != query:
            queries.append(kw)

        hits: list[dict] = []
        for q in queries:
            proc = subprocess.run(
                [qmd_bin, "search", q, "-c", "solar-wiki", "--json", "-n", str(max(1, max_hits * 2))],
                capture_output=True,
                text=True,
                timeout=per_call,
            )
            if proc.returncode == 0:
                hits += _qmd_hits_from_raw(json.loads(proc.stdout))
        return _rank_hits(_dedup(hits), query)[:max_hits]
    except Exception:
        return []


def _dedup(hits: list[dict]) -> list[dict]:
    """Remove duplicate titles/ids, keep highest score."""
    seen: dict[str, dict] = {}
    for h in hits:
        key = h.get("id") or h.get("title") or ""
        if key not in seen or h["score"] > seen[key]["score"]:
            seen[key] = h
    return list(seen.values())


def _lower_hit_text(hit: dict) -> str:
    return " ".join(
        str(hit.get(k, "")).lower()
        for k in ("id", "path", "title", "snippet", "source", "table")
    )


def _is_solar_artifact_hit(hit: dict) -> bool:
    text = _lower_hit_text(hit)
    return (
        "raw/solar-harness/artifact-ingest/" in text
        or "/_raw/solar-harness/artifact-ingest/" in text
    )


def _curated_path_boost(hit: dict) -> float:
    text = _lower_hit_text(hit)
    if "qmd://solar-wiki/synthesis/" in text or "/knowledge/synthesis/" in text:
        return 0.55
    if any(f"qmd://solar-wiki/{bucket}/" in text for bucket in ("concepts", "references", "entities", "projects", "skills")):
        return 0.45
    if "obsidian_vault_index" in text:
        return 0.35
    return 0.0


def _knowledge_layer(hit: dict) -> str:
    text = _lower_hit_text(hit)
    if bool(hit.get("derived")) or "/_extracted/" in text or "qmd://solar-wiki/_extracted/" in text:
        return "extracted"
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
    return "other"


def _knowledge_layer_priority(hit: dict) -> int:
    return {
        "extracted": 0,
        "synthesis": 0,
        "concepts": 1,
        "references": 2,
        "curated": 3,
        "other": 40,
        "raw-evidence": 80,
    }.get(str(hit.get("layer") or _knowledge_layer(hit)), 50)


def _query_relevance_boost(hit: dict, query: str) -> float:
    kw = _extract_cjk_keywords(query)
    title = str(hit.get("title", ""))
    snippet = str(hit.get("snippet", ""))
    boost = 0.0
    if kw and kw in title:
        boost += 0.75
    if kw and kw in snippet:
        boost += 0.35
    if query and query in title:
        boost += 0.25
    return boost


def _artifact_penalty(hit: dict, query: str) -> float:
    if not _is_solar_artifact_hit(hit):
        return 0.0
    # If the user is explicitly looking for a sprint artifact, keep it searchable.
    if _is_artifact_query(query):
        return 0.35
    return 1.25


def _is_artifact_query(query: str) -> bool:
    artifact_terms = ("contract", "prd", "plan", "handoff", "eval", "sprint", "合约", "验收", "计划")
    return any(term in query.lower() for term in artifact_terms)


def _rank_hits(hits: list[dict], query: str) -> list[dict]:
    """Prefer curated knowledge pages over raw Solar artifact evidence."""
    def adjusted(hit: dict) -> float:
        base = float(hit.get("score", 0.0) or 0.0)
        return base + _curated_path_boost(hit) + _query_relevance_boost(hit, query) - _artifact_penalty(hit, query)

    for hit in hits:
        hit["layer"] = _knowledge_layer(hit)
        hit["rank_score"] = round(adjusted(hit), 4)
    return sorted(
        hits,
        key=lambda h: (
            _knowledge_layer_priority(h),
            -float(h.get("rank_score", 0.0) or 0.0),
            -float(h.get("score", 0.0) or 0.0),
            str(h.get("title", "")),
        ),
    )


def retrieve(query: str, max_chars: int, timeout_ms: int, max_hits: int,
             fail_open: bool) -> dict:
    t0 = time.monotonic()

    def elapsed() -> float:
        return (time.monotonic() - t0) * 1000

    if not DB_PATH.exists():
        if fail_open:
            return {"hits": [], "elapsed_ms": elapsed(), "truncated": False, "error": "db_missing"}
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA query_only=1")
        conn.execute("PRAGMA busy_timeout=5000")
    except Exception as e:
        if fail_open:
            return {"hits": [], "elapsed_ms": elapsed(), "truncated": False, "error": str(e)}
        raise

    try:
        hits: list[dict] = []

        # S1: FTS5 fast path
        hits += _fts_query(conn, query, max_hits)
        if elapsed() < timeout_ms * 0.6 and len(hits) < max_hits:
            hits += _vault_hits(conn, query, max_hits - len(hits))
        if elapsed() < timeout_ms * 0.75 and len(hits) < max_hits:
            hits += _cortex_fallback(conn, query, max_hits - len(hits))
        if elapsed() < timeout_ms * 0.85 and len(hits) < 4:
            hits += _semantic_hits(conn, query, 3)

        # QMD fallback when DB/FTS sources return insufficient hits
        if elapsed() < timeout_ms * 0.90 and len(hits) < max_hits:
            hits += _qmd_fallback(query, max_hits - len(hits), timeout_ms - elapsed())

        hits = _rank_hits(_dedup(hits), query)
        if not _is_artifact_query(query) and any(not _is_solar_artifact_hit(h) for h in hits):
            hits = [h for h in hits if not _is_solar_artifact_hit(h)]
        hits = hits[:max_hits]

        # Enforce char budget
        total_chars = 0
        kept = []
        truncated = False
        for h in hits:
            snippet = h.get("snippet", "")
            if total_chars + len(snippet) > max_chars:
                # Trim snippet
                remaining = max(0, max_chars - total_chars)
                if remaining > 60:
                    h["snippet"] = snippet[:remaining]
                    kept.append(h)
                    total_chars += remaining
                truncated = True
                break
            kept.append(h)
            total_chars += len(snippet)

        return {
            "hits": kept,
            "elapsed_ms": elapsed(),
            "truncated": truncated,
            "total_chars": total_chars,
            "query": query,
        }
    except Exception as e:
        if fail_open:
            return {"hits": [], "elapsed_ms": elapsed(), "truncated": False, "error": str(e)}
        raise
    finally:
        conn.close()


def format_text(result: dict, max_chars: int) -> str:
    """Format result as compact <solar-knowledge-context> block."""
    hits = result.get("hits", [])
    if not hits:
        return ""
    lines = ["<solar-knowledge-context>"]
    total = 0
    for h in hits:
        title = h.get("title", "")
        source = h.get("source", "")
        table = h.get("table", "")
        path = h.get("path", "")
        snippet = h.get("snippet", "")
        src_label = path if path else (table or source)
        entry = f"[{src_label}] {title}: {snippet}"
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)
    lines.append("</solar-knowledge-context>")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Solar KB retrieval router")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--json", dest="json_out", action="store_true")
    parser.add_argument("--format", choices=("hook", "markdown", "text"), default="text")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--fail-open", action="store_true", default=False)
    parser.add_argument("--max-hits", type=int, default=DEFAULT_MAX_HITS)
    args = parser.parse_args()

    try:
        result = retrieve(
            query=args.query,
            max_chars=args.max_chars,
            timeout_ms=args.timeout_ms,
            max_hits=args.max_hits,
            fail_open=args.fail_open,
        )
    except Exception as e:
        if args.json_out:
            print(json.dumps({"hits": [], "elapsed_ms": 0, "error": str(e)}))
        sys.exit(1)

    if args.json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        text = format_text(result, args.max_chars)
        if text:
            print(text)


if __name__ == "__main__":
    main()
