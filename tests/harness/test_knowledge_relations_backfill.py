from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.knowledge_relations_backfill import backfill


SCHEMA = """
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_adapter TEXT NOT NULL,
  content_kind TEXT NOT NULL,
  declared_doc_type TEXT,
  source_sha256 TEXT NOT NULL,
  current_state TEXT NOT NULL,
  ingest_policy TEXT NOT NULL DEFAULT 'default',
  extract_policy TEXT NOT NULL DEFAULT 'default',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  provenance_quality TEXT NOT NULL DEFAULT 'observed',
  UNIQUE (source_kind, source_path)
);
CREATE TABLE extract_outputs (
  output_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE relations (
  relation_id TEXT PRIMARY KEY,
  source_doc_id TEXT NOT NULL,
  target_doc_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  ts TEXT NOT NULL
);
"""


def test_backfill_registers_extracted_doc_and_lineage_relations(tmp_path: Path) -> None:
    db = tmp_path / "knowledge.sqlite"
    raw = tmp_path / "raw.md"
    raw.write_text("# Raw\n\nsource body\n", encoding="utf-8")
    extracted = tmp_path / "out.extracted.md"
    extracted.write_text(
        "---\n"
        f"source_path: {raw}\n"
        "source_sha256: abc\n"
        "extractor: thunderomlx\n"
        "schema_version: extracted-md-v1\n"
        "---\n\n# Semantic Extraction\n",
        encoding="utf-8",
    )

    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO documents (
              doc_id, source_kind, source_path, source_adapter, content_kind,
              declared_doc_type, source_sha256, current_state, created_at, updated_at
            )
            VALUES ('raw:1', 'raw', ?, 'test', 'markdown', 'raw_md', 'rawsha', 'DONE', 't', 't')
            """,
            (str(raw),),
        )
        conn.execute(
            "INSERT INTO extract_outputs(output_id, job_id, kind, path, sha256, created_at) VALUES ('out:1', 'job:1', 'markdown', ?, 'sha', 't')",
            (str(extracted),),
        )
        conn.commit()

    result = backfill(db, tmp_path, limit=None, dry_run=False)
    assert result["seen"] == 1
    assert result["registered_extracted_docs"] == 1
    assert result["relations_inserted"] == 2

    with sqlite3.connect(db) as conn:
        docs = conn.execute("SELECT source_kind, current_state FROM documents ORDER BY source_kind").fetchall()
        assert ("extracted", "DONE") in docs
        rels = conn.execute("SELECT kind, source_doc_id, target_doc_id FROM relations ORDER BY kind").fetchall()
        assert [row[0] for row in rels] == ["derived_from", "has_semantic_extract"]


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "knowledge.sqlite"
    raw = tmp_path / "raw.md"
    raw.write_text("raw", encoding="utf-8")
    extracted = tmp_path / "out.extracted.md"
    extracted.write_text(f"---\nsource_path: {raw}\n---\n\nbody\n", encoding="utf-8")

    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO documents (
              doc_id, source_kind, source_path, source_adapter, content_kind,
              source_sha256, current_state, created_at, updated_at
            )
            VALUES ('raw:1', 'raw', ?, 'test', 'markdown', 'rawsha', 'DONE', 't', 't')
            """,
            (str(raw),),
        )
        conn.execute(
            "INSERT INTO extract_outputs(output_id, job_id, kind, path, sha256, created_at) VALUES ('out:1', 'job:1', 'markdown', ?, 'sha', 't')",
            (str(extracted),),
        )
        conn.commit()

    first = backfill(db, tmp_path, limit=None, dry_run=False)
    second = backfill(db, tmp_path, limit=None, dry_run=False)

    assert first["relations_inserted"] == 2
    assert second["relations_inserted"] == 0
    assert second["relations_existing"] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 2
