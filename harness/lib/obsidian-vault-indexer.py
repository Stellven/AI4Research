#!/usr/bin/env python3
"""
obsidian-vault-indexer.py — Index Obsidian vault markdown into obsidian_vault_index
and register documents into fts_unified_search.

Usage:
  python3 obsidian-vault-indexer.py [--vault PATH] [--db PATH] [--once]
                                     [--max-files N] [--dry-run]

Environment:
  OBSIDIAN_VAULT_PATH  — vault root (default ~/Knowledge)
  SOLAR_DB             — database path (default ~/.solar/solar.db)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))
VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Knowledge")))
EXCLUDE_DIRS = {".obsidian", ".trash", ".git", ".dispatch", "_raw"}
RAW_INDEX_ALLOW_PREFIXES = {
    Path("_raw") / "solar-harness" / "accepted",
}
EXTENSIONS = {".md", ".markdown"}
MAX_CONTENT_CHARS = 2000
MAX_SUMMARY_CHARS = 400


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter; return (meta_dict, body)."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta, text
    for raw in parts[1].splitlines():
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            # Handle list values [a, b, c]
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
            meta[k] = v
    return meta, parts[2]


def extract_title(meta: dict, body: str, file_stem: str) -> str:
    if meta.get("title"):
        return str(meta["title"])
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return file_stem


def extract_tags(meta: dict, body: str) -> list[str]:
    tags: list[str] = []
    raw_tags = meta.get("tags", [])
    if isinstance(raw_tags, list):
        tags.extend(str(t) for t in raw_tags)
    elif raw_tags:
        tags.append(str(raw_tags))
    # Inline #tags from body
    for m in re.finditer(r"#([a-zA-Z\u4e00-\u9fff][\w\u4e00-\u9fff-]*)", body):
        t = m.group(1)
        if t not in tags:
            tags.append(t)
    return tags[:20]


def summarize(body: str) -> str:
    """Extract first non-empty paragraph up to MAX_SUMMARY_CHARS."""
    for para in body.split("\n\n"):
        stripped = para.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            # Remove markdown formatting
            cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
            cleaned = re.sub(r"[*_`~]+", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned)
            return cleaned[:MAX_SUMMARY_CHARS]
    return body[:MAX_SUMMARY_CHARS]


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create obsidian_vault_index and ensure fts_unified_search exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS obsidian_vault_index (
            file_path     TEXT PRIMARY KEY,
            vault_path    TEXT NOT NULL,
            title         TEXT NOT NULL,
            summary       TEXT,
            tags          TEXT,
            source        TEXT DEFAULT 'obsidian',
            content_hash  TEXT,
            indexed_at    TEXT DEFAULT (datetime('now')),
            deleted_at    TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_obsidian_vault_indexed_at
        ON obsidian_vault_index(indexed_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_obsidian_vault_deleted
        ON obsidian_vault_index(deleted_at)
        WHERE deleted_at IS NOT NULL
    """)
    # Ensure fts_unified_search has content; create if missing.
    try:
        conn.execute("SELECT 1 FROM fts_unified_search LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_unified_search
            USING fts5(doc_id, doc_type, title, content, tags, metadata,
                       content='', contentless_delete=1)
        """)
    conn.commit()


def upsert_doc(conn: sqlite3.Connection, file_path: str, vault_path: str,
               title: str, summary: str, tags: list[str],
               content_hash: str, full_content: str) -> str:
    """Insert or update obsidian_vault_index and fts_unified_search. Returns 'new'|'updated'|'skipped'."""
    tags_json = json.dumps(tags, ensure_ascii=False)
    existing = conn.execute(
        "SELECT content_hash FROM obsidian_vault_index WHERE file_path = ? AND deleted_at IS NULL",
        (file_path,)
    ).fetchone()

    if existing and existing[0] == content_hash:
        return "skipped"

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("""
        INSERT INTO obsidian_vault_index
            (file_path, vault_path, title, summary, tags, source, content_hash, indexed_at, deleted_at)
        VALUES (?, ?, ?, ?, ?, 'obsidian', ?, ?, NULL)
        ON CONFLICT(file_path) DO UPDATE SET
            title        = excluded.title,
            summary      = excluded.summary,
            tags         = excluded.tags,
            content_hash = excluded.content_hash,
            indexed_at   = excluded.indexed_at,
            deleted_at   = NULL
    """, (file_path, vault_path, title, summary, tags_json, content_hash, now))

    # Register in fts_unified_search
    doc_id = f"obsidian:{file_path}"
    fts_content = full_content[:MAX_CONTENT_CHARS]
    try:
        conn.execute(
            "INSERT OR REPLACE INTO fts_unified_search(doc_id, doc_type, title, content, tags, metadata) "
            "VALUES (?, 'obsidian_vault_index', ?, ?, ?, ?)",
            (doc_id, title, fts_content, " ".join(tags), json.dumps({"file_path": file_path, "vault": vault_path}))
        )
    except sqlite3.OperationalError:
        # FTS table may be contentless; silently skip FTS registration
        pass

    return "updated" if existing else "new"


def mark_deleted(conn: sqlite3.Connection, file_path: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "UPDATE obsidian_vault_index SET deleted_at = ? WHERE file_path = ? AND deleted_at IS NULL",
        (now, file_path)
    )


def index_vault(vault: Path, db: Path, max_files: int = 0, dry_run: bool = False) -> dict:
    """Scan vault and index all markdown files. Returns stats dict."""
    if not vault.exists():
        return {"error": f"vault not found: {vault}", "indexed": 0, "skipped": 0, "deleted": 0, "errors": 0}

    t0 = time.monotonic()
    conn = sqlite3.connect(str(db), timeout=5.0)
    conn.execute("PRAGMA busy_timeout=500")
    conn.execute("PRAGMA journal_mode=WAL")

    if not dry_run:
        ensure_schema(conn)

    # Collect all .md files in vault
    md_files: list[Path] = []
    for path in vault.rglob("*"):
        try:
            rel = path.relative_to(vault)
        except ValueError:
            rel = path
        allowed_raw = any(rel == prefix or prefix in rel.parents for prefix in RAW_INDEX_ALLOW_PREFIXES)
        if any(part in EXCLUDE_DIRS for part in rel.parts) and not allowed_raw:
            continue
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            md_files.append(path)
            if max_files and len(md_files) >= max_files:
                break

    # Track existing indexed paths for deletion detection
    if not dry_run:
        existing_paths: set[str] = {
            row[0] for row in conn.execute(
                "SELECT file_path FROM obsidian_vault_index WHERE deleted_at IS NULL"
            ).fetchall()
        }
    else:
        existing_paths = set()

    stats = {"indexed": 0, "skipped": 0, "deleted": 0, "errors": 0, "total": len(md_files)}
    seen_paths: set[str] = set()

    for path in md_files:
        str_path = str(path)
        seen_paths.add(str_path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            meta, body = parse_frontmatter(text)
            title = extract_title(meta, body, path.stem)
            tags = extract_tags(meta, body)
            summary = summarize(body)
            content_hash = sha1_hex(text)

            if dry_run:
                stats["indexed"] += 1
                continue

            result = upsert_doc(conn, str_path, str(vault), title, summary, tags, content_hash, body)
            if result == "new":
                stats["indexed"] += 1
            elif result == "updated":
                stats["indexed"] += 1
            else:
                stats["skipped"] += 1

        except Exception as e:
            stats["errors"] += 1
            sys.stderr.write(f"[obsidian-indexer] error processing {path}: {e}\n")

    if not dry_run:
        # Soft-delete files that no longer exist
        for old_path in existing_paths - seen_paths:
            mark_deleted(conn, old_path)
            stats["deleted"] += 1
        conn.commit()

    conn.close()
    stats["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)
    stats["vault"] = str(vault)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Index Obsidian vault into Solar DB")
    parser.add_argument("--vault", default=str(VAULT_PATH), help="Vault root path")
    parser.add_argument("--db", default=str(DB_PATH), help="Solar DB path")
    parser.add_argument("--once", action="store_true", help="Run once (default)")
    parser.add_argument("--max-files", type=int, default=0, help="Limit file count (0=unlimited)")
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not write to DB")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Output JSON")
    args = parser.parse_args()

    vault = Path(args.vault)
    db = Path(args.db)

    result = index_vault(vault, db, max_files=args.max_files, dry_run=args.dry_run)

    if args.json_out:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("error"):
            sys.stderr.write(f"[obsidian-indexer] {result['error']}\n")
            sys.exit(1)
        print(
            f"[obsidian-indexer] vault={vault} "
            f"indexed={result['indexed']} skipped={result['skipped']} "
            f"deleted={result['deleted']} errors={result['errors']} "
            f"elapsed={result.get('elapsed_ms', 0)}ms"
        )
        if result["errors"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
