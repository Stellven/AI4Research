#!/usr/bin/env python3
"""SQLite registry for Solar Knowledge ingest control plane.

The registry is the authoritative state ledger for the knowledge ingest
dispatcher. JSON manifests may be exported later, but state is recorded here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
UTC = dt.timezone.utc
DEFAULT_DB = Path(os.environ.get("SOLAR_KNOWLEDGE_REGISTRY_DB", str(Path.home() / "Knowledge" / "_registry" / "knowledge_ingest.sqlite"))).expanduser()


def now_iso() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
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

CREATE TABLE IF NOT EXISTS spans (
  span_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  heading_path TEXT,
  text_sha256 TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  byte_offset_start INTEGER,
  byte_offset_end INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_events (
  event_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  event_kind TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT,
  source_adapter TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qmd_index_events (
  event_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  layer TEXT NOT NULL,
  qmd_batch_id TEXT,
  qmd_status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extract_jobs (
  job_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  source_span_ids TEXT NOT NULL,
  prompt_template_id TEXT NOT NULL,
  model TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  repair_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS extract_outputs (
  output_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES extract_jobs(job_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_results (
  result_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES extract_jobs(job_id) ON DELETE CASCADE,
  layer TEXT NOT NULL,
  passed INTEGER NOT NULL,
  error_code TEXT,
  detail_json TEXT,
  ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
  relation_id TEXT PRIMARY KEY,
  source_doc_id TEXT NOT NULL,
  target_doc_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watermarks (
  layer TEXT PRIMARY KEY,
  last_indexed_ts TEXT,
  pending_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  last_batch_id TEXT,
  last_batch_ts TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_log (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  checksum TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(current_state);
CREATE INDEX IF NOT EXISTS idx_documents_source_kind ON documents(source_kind);
CREATE INDEX IF NOT EXISTS idx_spans_doc_id ON spans(doc_id);
CREATE INDEX IF NOT EXISTS idx_ingest_events_doc_id ON ingest_events(doc_id);
CREATE INDEX IF NOT EXISTS idx_qmd_index_events_doc_layer ON qmd_index_events(doc_id, layer);
CREATE INDEX IF NOT EXISTS idx_extract_jobs_doc_id ON extract_jobs(doc_id);
CREATE INDEX IF NOT EXISTS idx_extract_jobs_state ON extract_jobs(state);
CREATE INDEX IF NOT EXISTS idx_validation_results_job_id ON validation_results(job_id);
"""

MIGRATION_V2_SQL = """
-- v2: add 4 columns to extract_jobs
ALTER TABLE extract_jobs ADD COLUMN schema_version INTEGER;
ALTER TABLE extract_jobs ADD COLUMN endpoint TEXT;
ALTER TABLE extract_jobs ADD COLUMN started_at TEXT;
ALTER TABLE extract_jobs ADD COLUMN finished_at TEXT;

-- v2: add 5 columns to extract_outputs
ALTER TABLE extract_outputs ADD COLUMN latency_ms INTEGER;
ALTER TABLE extract_outputs ADD COLUMN token_input_count INTEGER;
ALTER TABLE extract_outputs ADD COLUMN token_output_count INTEGER;
ALTER TABLE extract_outputs ADD COLUMN cost_estimate REAL;
ALTER TABLE extract_outputs ADD COLUMN model_fingerprint TEXT;
"""


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    checksum = sha256_text(SCHEMA_SQL)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR IGNORE INTO migration_log(version, applied_at, checksum) VALUES (?, ?, ?)",
            (SCHEMA_VERSION, now_iso(), checksum),
        )
        for layer in ("raw", "vault", "semantic"):
            conn.execute(
                "INSERT OR IGNORE INTO watermarks(layer, updated_at) VALUES (?, ?)",
                (layer, now_iso()),
            )
        # B3 naming migration: replace extracted watermark with semantic
        conn.execute(
            "INSERT OR IGNORE INTO watermarks(layer, updated_at) VALUES ('semantic', ?)",
            (now_iso(),),
        )
        conn.execute("DELETE FROM watermarks WHERE layer = 'extracted'")

        # v2 migration: add columns idempotently
        v2_applied = conn.execute(
            "SELECT COUNT(*) FROM migration_log WHERE version = 2"
        ).fetchone()[0]
        if not v2_applied:
            for stmt in MIGRATION_V2_SQL.strip().split(";"):
                stmt = stmt.strip()
                if not stmt or stmt.startswith("--"):
                    continue
                try:
                    conn.execute(stmt)
                except Exception:
                    pass  # column already exists — idempotent
            conn.execute(
                "INSERT OR IGNORE INTO migration_log(version, applied_at, checksum) VALUES (?, ?, ?)",
                (2, now_iso(), sha256_text(MIGRATION_V2_SQL)),
            )

        conn.commit()
    return {"ok": True, "db": str(db_path), "schema_version": SCHEMA_VERSION, "checksum": checksum}


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def stable_doc_id(source_kind: str, source_path: str) -> str:
    return f"{source_kind}:{sha256_text(source_path)[:16]}"


def upsert_document(
    *,
    source_kind: str,
    source_path: str,
    source_adapter: str,
    content_kind: str = "markdown",
    declared_doc_type: str | None = None,
    source_sha256: str | None = None,
    current_state: str = "NEW",
    ingest_policy: str = "default",
    extract_policy: str = "default",
    provenance_quality: str = "observed",
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    migrate(db_path)
    source_sha256 = source_sha256 or sha256_text(source_path)
    doc_id = stable_doc_id(source_kind, source_path)
    ts = now_iso()
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT doc_id FROM documents WHERE source_kind=? AND source_path=?",
            (source_kind, source_path),
        ).fetchone()
        if existing:
            doc_id = existing["doc_id"]
            conn.execute(
                """
                UPDATE documents
                SET source_adapter=?,
                    content_kind=?,
                    declared_doc_type=?,
                    source_sha256=?,
                    current_state=?,
                    ingest_policy=?,
                    extract_policy=?,
                    updated_at=?,
                    provenance_quality=?
                WHERE doc_id=?
                """,
                (
                    source_adapter,
                    content_kind,
                    declared_doc_type,
                    source_sha256,
                    current_state,
                    ingest_policy,
                    extract_policy,
                    ts,
                    provenance_quality,
                    doc_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO documents(
                  doc_id, source_kind, source_path, source_adapter, content_kind,
                  declared_doc_type, source_sha256, current_state, ingest_policy,
                  extract_policy, created_at, updated_at, provenance_quality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                  source_sha256=excluded.source_sha256,
                  current_state=excluded.current_state,
                  updated_at=excluded.updated_at,
                  provenance_quality=excluded.provenance_quality
                """,
                (
                    doc_id,
                    source_kind,
                    source_path,
                    source_adapter,
                    content_kind,
                    declared_doc_type,
                    source_sha256,
                    current_state,
                    ingest_policy,
                    extract_policy,
                    ts,
                    ts,
                    provenance_quality,
                ),
            )
        event_id = "evt_" + sha256_text(f"{doc_id}:upsert:{source_sha256}:{ts}")[:24]
        conn.execute(
            """
            INSERT OR IGNORE INTO ingest_events(event_id, doc_id, event_kind, from_state, to_state, source_adapter, payload_json, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                doc_id,
                "upsert_document",
                None,
                current_state,
                source_adapter,
                json.dumps({"source_path": source_path, "source_kind": source_kind}, ensure_ascii=False, sort_keys=True),
                ts,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    return row_to_dict(row) or {}


def replace_spans(
    *,
    doc_id: str,
    spans: list[dict[str, Any]],
    source_sha256: str,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    """Replace all spans for a document.

    The DB span_id is globally unique (`doc_id:S001`). The local Sxxx ID remains
    in the sidecar JSON and can be reconstructed by splitting on the final colon.
    """
    migrate(db_path)
    ts = now_iso()
    with connect(db_path) as conn:
        conn.execute("DELETE FROM spans WHERE doc_id=?", (doc_id,))
        for span in spans:
            local_span_id = span["span_id"]
            conn.execute(
                """
                INSERT INTO spans(
                  span_id, doc_id, start_line, end_line, heading_path,
                  text_sha256, source_sha256, byte_offset_start, byte_offset_end, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{doc_id}:{local_span_id}",
                    doc_id,
                    int(span["start_line"]),
                    int(span["end_line"]),
                    json.dumps(span.get("heading_path") or [], ensure_ascii=False),
                    span["text_sha256"],
                    source_sha256,
                    span.get("byte_offset_start"),
                    span.get("byte_offset_end"),
                    ts,
                ),
            )
        conn.commit()
    return {"ok": True, "doc_id": doc_id, "span_count": len(spans)}


def transition_document(
    doc_id: str,
    from_state: str,
    to_state: str,
    *,
    source_adapter: str = "dispatcher",
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    """Transition a document from one state to another, recording an ingest_event."""
    migrate(db_path)
    ts = now_iso()
    with connect(db_path) as conn:
        current = conn.execute(
            "SELECT current_state FROM documents WHERE doc_id=?", (doc_id,)
        ).fetchone()
        if current is None:
            return {"ok": False, "error": f"doc_id {doc_id} not found"}
        actual_state = current["current_state"]
        if actual_state != from_state:
            return {"ok": False, "error": f"state mismatch: expected {from_state}, actual {actual_state}", "doc_id": doc_id}
        conn.execute(
            "UPDATE documents SET current_state=?, updated_at=? WHERE doc_id=?",
            (to_state, ts, doc_id),
        )
        event_id = "evt_" + sha256_text(f"{doc_id}:transition:{from_state}:{to_state}:{ts}")[:24]
        conn.execute(
            """
            INSERT OR IGNORE INTO ingest_events(event_id, doc_id, event_kind, from_state, to_state, source_adapter, payload_json, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                doc_id,
                "transition",
                from_state,
                to_state,
                source_adapter,
                json.dumps({"from": from_state, "to": to_state}, ensure_ascii=False),
                ts,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    return row_to_dict(row) or {"ok": True, "doc_id": doc_id, "from_state": from_state, "to_state": to_state}


def status(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    migrate(db_path)
    with connect(db_path) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        states = {r["current_state"]: r["n"] for r in conn.execute("SELECT current_state, COUNT(*) AS n FROM documents GROUP BY current_state")}
        watermarks = [row_to_dict(r) for r in conn.execute("SELECT * FROM watermarks ORDER BY layer")]
    return {"ok": True, "db": str(db_path), "schema_version": SCHEMA_VERSION, "tables": tables, "counts": counts, "states": states, "watermarks": watermarks}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solar Knowledge ingest registry")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("status")
    upsert = sub.add_parser("upsert-document")
    upsert.add_argument("--source-kind", required=True)
    upsert.add_argument("--source-path", required=True)
    upsert.add_argument("--source-adapter", required=True)
    upsert.add_argument("--content-kind", default="markdown")
    upsert.add_argument("--declared-doc-type")
    upsert.add_argument("--source-sha256")
    upsert.add_argument("--state", default="NEW")
    upsert.add_argument("--provenance-quality", default="observed")
    return parser.parse_args()


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload)


def main() -> int:
    args = parse_args()
    db = Path(args.db).expanduser()
    if args.cmd == "migrate":
        emit(migrate(db), args.json)
        return 0
    if args.cmd == "status":
        emit(status(db), args.json)
        return 0
    if args.cmd == "upsert-document":
        emit(
            upsert_document(
                source_kind=args.source_kind,
                source_path=args.source_path,
                source_adapter=args.source_adapter,
                content_kind=args.content_kind,
                declared_doc_type=args.declared_doc_type,
                source_sha256=args.source_sha256,
                current_state=args.state,
                provenance_quality=args.provenance_quality,
                db_path=db,
            ),
            args.json,
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
