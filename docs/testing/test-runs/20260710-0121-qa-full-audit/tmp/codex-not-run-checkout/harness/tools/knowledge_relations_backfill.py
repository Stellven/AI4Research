#!/usr/bin/env python3
"""Backfill deterministic knowledge registry relations.

This tool is intentionally conservative. It does not infer semantic meaning
with an LLM; it only records lineage that already exists in extracted markdown
frontmatter:

  extracted document -> raw/vault source document
  raw/vault source document -> extracted document

The goal is to make the registry relation ledger non-empty and auditable for
query grounding and lineage checks.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB = Path.home() / "Knowledge" / "_registry" / "knowledge_ingest.sqlite"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_doc_id(source_kind: str, source_path: str) -> str:
    return f"{source_kind}:{sha256_text(source_path)[:16]}"


def stable_relation_id(source_doc_id: str, target_doc_id: str, kind: str) -> str:
    return f"rel:{sha256_text(source_doc_id + '|' + target_doc_id + '|' + kind)[:24]}"


def read_frontmatter(path: Path) -> dict[str, str]:
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
    for raw in text[4:end].splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    return meta


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_relation_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_doc_id, kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_doc_id, kind)")


def source_doc_for_path(conn: sqlite3.Connection, source_path: str) -> sqlite3.Row | None:
    rows = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE source_path = ?
        ORDER BY
          CASE current_state
            WHEN 'DONE' THEN 0
            WHEN 'RAW_MATERIALIZED' THEN 1
            WHEN 'VAULT_DISCOVERED' THEN 2
            ELSE 9
          END,
          CASE source_kind
            WHEN 'raw_chatgpt' THEN 0
            WHEN 'raw_github' THEN 0
            WHEN 'raw' THEN 1
            ELSE 2
          END
        LIMIT 1
        """,
        (source_path,),
    ).fetchall()
    return rows[0] if rows else None


def upsert_extracted_document(conn: sqlite3.Connection, path: Path, meta: dict[str, str], ts: str) -> str:
    source_path = str(path)
    doc_id = stable_doc_id("extracted", source_path)
    digest = meta.get("output_sha256") or sha256_file(path)
    doc_type = meta.get("schema_version") or "extracted-md"
    adapter = meta.get("extractor") or "semantic_extract"
    conn.execute(
        """
        INSERT INTO documents (
          doc_id, source_kind, source_path, source_adapter, content_kind,
          declared_doc_type, source_sha256, current_state, ingest_policy,
          extract_policy, created_at, updated_at, provenance_quality
        )
        VALUES (?, 'extracted', ?, ?, 'markdown', ?, ?, 'DONE', 'derived', 'off', ?, ?, 'observed')
        ON CONFLICT(source_kind, source_path) DO UPDATE SET
          source_adapter=excluded.source_adapter,
          declared_doc_type=excluded.declared_doc_type,
          source_sha256=excluded.source_sha256,
          current_state='DONE',
          updated_at=excluded.updated_at,
          provenance_quality='observed'
        """,
        (doc_id, source_path, adapter, doc_type, digest, ts, ts),
    )
    row = conn.execute(
        "SELECT doc_id FROM documents WHERE source_kind='extracted' AND source_path=?",
        (source_path,),
    ).fetchone()
    return str(row["doc_id"])


def insert_relation(conn: sqlite3.Connection, source_doc_id: str, target_doc_id: str, kind: str, weight: float, ts: str) -> bool:
    relation_id = stable_relation_id(source_doc_id, target_doc_id, kind)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO relations(relation_id, source_doc_id, target_doc_id, kind, weight, ts)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (relation_id, source_doc_id, target_doc_id, kind, weight, ts),
    )
    return cur.rowcount > 0


def output_paths_from_registry(conn: sqlite3.Connection, limit: int | None = None) -> list[Path]:
    sql = """
        SELECT path
        FROM extract_outputs
        WHERE kind IN ('markdown', 'md', 'extracted_md', 'semantic_md')
           OR path LIKE '%.extracted.md'
           OR path LIKE '%.semantic.md'
        ORDER BY created_at DESC
    """
    params: tuple[Any, ...] = ()
    if limit:
        sql += " LIMIT ?"
        params = (limit,)
    return [Path(str(row["path"])) for row in conn.execute(sql, params).fetchall()]


def output_paths_from_filesystem(root: Path, limit: int | None = None) -> list[Path]:
    paths = sorted(root.glob("**/*.extracted.md"), key=lambda p: str(p))
    if limit:
        paths = paths[:limit]
    return paths


def backfill(db_path: Path, extracted_root: Path, limit: int | None, dry_run: bool) -> dict[str, Any]:
    ts = now_iso()
    stats = {
        "ok": True,
        "db": str(db_path),
        "dry_run": dry_run,
        "seen": 0,
        "registered_extracted_docs": 0,
        "missing_file": 0,
        "missing_frontmatter_source": 0,
        "missing_source_doc": 0,
        "relations_inserted": 0,
        "relations_existing": 0,
        "sample_missing_sources": [],
    }
    with connect(db_path) as conn:
        ensure_relation_indexes(conn)
        paths = output_paths_from_registry(conn, limit=limit)
        if not paths:
            paths = output_paths_from_filesystem(extracted_root, limit=limit)
        for path in paths:
            stats["seen"] += 1
            if not path.exists():
                stats["missing_file"] += 1
                continue
            meta = read_frontmatter(path)
            source_path = meta.get("source_path") or meta.get("source")
            if not source_path:
                stats["missing_frontmatter_source"] += 1
                continue
            source = source_doc_for_path(conn, source_path)
            if not source:
                stats["missing_source_doc"] += 1
                if len(stats["sample_missing_sources"]) < 10:
                    stats["sample_missing_sources"].append(source_path)
                continue
            extracted_doc_id = stable_doc_id("extracted", str(path))
            existing = conn.execute(
                "SELECT 1 FROM documents WHERE source_kind='extracted' AND source_path=?",
                (str(path),),
            ).fetchone()
            if not existing:
                stats["registered_extracted_docs"] += 1
            if not dry_run:
                extracted_doc_id = upsert_extracted_document(conn, path, meta, ts)
                inserted = 0
                inserted += int(insert_relation(conn, extracted_doc_id, str(source["doc_id"]), "derived_from", 1.0, ts))
                inserted += int(insert_relation(conn, str(source["doc_id"]), extracted_doc_id, "has_semantic_extract", 1.0, ts))
                stats["relations_inserted"] += inserted
                stats["relations_existing"] += 2 - inserted
            else:
                # Dry-run estimates only whether the relation IDs already exist.
                for src, dst, kind in (
                    (extracted_doc_id, str(source["doc_id"]), "derived_from"),
                    (str(source["doc_id"]), extracted_doc_id, "has_semantic_extract"),
                ):
                    rid = stable_relation_id(src, dst, kind)
                    if conn.execute("SELECT 1 FROM relations WHERE relation_id=?", (rid,)).fetchone():
                        stats["relations_existing"] += 1
                    else:
                        stats["relations_inserted"] += 1
        if not dry_run:
            conn.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--extracted-root", type=Path, default=Path.home() / "Knowledge" / "_extracted")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = backfill(args.db.expanduser(), args.extracted_root.expanduser(), args.limit, args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
