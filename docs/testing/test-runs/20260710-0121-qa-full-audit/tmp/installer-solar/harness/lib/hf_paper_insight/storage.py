"""Storage — SQLite WAL persistence for HF Paper Insight Flow entities.

Per OQ-01: SQLite WAL + JSON fields, with PG migration in scope.
Per data_models.md §5: Snapshot permanent append, Enrichment TTL 30d,
Packet TTL 7d, Graph rebuildable.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from schema import (
    ALL_DDL,
    ENTITY_TABLE_MAP,
    PaperCanonical,
    PaperEnrichment,
    PaperEvidencePacket,
    PaperSignal,
    PaperSnapshot,
    PaperTaxonomy,
    entity_to_row,
)

SCHEMA_VERSION = "hf_paper_insight.v1"

ENTITY_CLASSES = {
    "paper_snapshots": PaperSnapshot,
    "paper_canonical": PaperCanonical,
    "paper_enrichment": PaperEnrichment,
    "paper_taxonomy": PaperTaxonomy,
    "paper_signals": PaperSignal,
    "paper_evidence_packets": PaperEvidencePacket,
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


class PaperStore:
    """SQLite WAL storage for all 6 core entities."""

    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            self._conn = _connect(self._path)
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        for stmt in ALL_DDL.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.execute(
            "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Generic CRUD ───────────────────────────────────────────────

    def _table_for(self, entity: object) -> str:
        cls_name = type(entity).__name__
        table = ENTITY_TABLE_MAP.get(cls_name)
        if table is None:
            raise ValueError(f"Unknown entity type: {cls_name}")
        return table

    def upsert(self, entity: object) -> str:
        table = self._table_for(entity)
        row = entity_to_row(entity)
        pk_col = list(row.keys())[0]
        pk_val = row[pk_col]

        existing = self.conn.execute(
            f"SELECT {pk_col} FROM {table} WHERE {pk_col} = ?",
            (pk_val,),
        ).fetchone()

        if existing:
            sets = ", ".join(f"{k} = ?" for k in row.keys() if k != pk_col)
            vals = [v for k, v in row.items() if k != pk_col]
            self.conn.execute(
                f"UPDATE {table} SET {sets} WHERE {pk_col} = ?",
                vals + [pk_val],
            )
        else:
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
        self.conn.commit()
        return pk_val

    def get(self, entity_cls: type, pk: str) -> Optional[object]:
        table = ENTITY_TABLE_MAP.get(entity_cls.__name__)
        if table is None:
            return None
        pk_col = "snapshot_id" if entity_cls is PaperSnapshot else (
            "paper_id" if entity_cls is PaperCanonical else (
            "enrichment_id" if entity_cls is PaperEnrichment else (
            "taxonomy_id" if entity_cls is PaperTaxonomy else (
            "signal_id" if entity_cls is PaperSignal else "packet_id"
        ))))
        row = self.conn.execute(
            f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        return entity_cls(**d)

    def query(self, table: str, where: str = "", params: tuple = ()) -> list[dict]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Entity-specific helpers ────────────────────────────────────

    def find_canonical_by_arxiv(self, arxiv_id: str) -> Optional[PaperCanonical]:
        row = self.conn.execute(
            "SELECT * FROM paper_canonical WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
        return PaperCanonical(**dict(row)) if row else None

    def find_canonical_by_title_hash(self, title_hash: str) -> Optional[PaperCanonical]:
        row = self.conn.execute(
            "SELECT * FROM paper_canonical WHERE title_hash = ?", (title_hash,)
        ).fetchone()
        return PaperCanonical(**dict(row)) if row else None

    def get_expired_enrichments(self, as_of: str) -> list[PaperEnrichment]:
        rows = self.conn.execute(
            "SELECT * FROM paper_enrichment WHERE ttl_expires_at <= ?", (as_of,)
        ).fetchall()
        return [PaperEnrichment(**dict(r)) for r in rows]

    def get_expired_packets(self, as_of: str) -> list[PaperEvidencePacket]:
        rows = self.conn.execute(
            "SELECT * FROM paper_evidence_packets WHERE cache_expires_at <= ?", (as_of,)
        ).fetchall()
        return [PaperEvidencePacket(**dict(r)) for r in rows]

    def merge_seen_window(self, paper_id: str, window_type: str, observed_at: str) -> None:
        canonical = self.get(PaperCanonical, paper_id)
        if canonical is None:
            return
        windows = json.loads(canonical.seen_windows_json)
        entry = {"window_type": window_type, "observed_at": observed_at}
        if entry not in windows:
            windows.append(entry)
        canonical.seen_windows_json = json.dumps(windows)
        canonical.last_seen_at = observed_at
        self.upsert(canonical)
