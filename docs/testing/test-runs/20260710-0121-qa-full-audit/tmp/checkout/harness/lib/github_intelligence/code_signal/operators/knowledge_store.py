"""G6 — GitHubKnowledgeStoreOperator (L5 Resonance+Store).

Persists all unified objects to the Knowledge directory structure
and computes cross-source resonance levels (G0–G5).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models import (
    GitHubEvidencePacket,
    OutputAsset,
    RepoCanonical,
    RepoEnrichment,
    RepoSignal,
    RepoSnapshot,
    apply_schema,
    _json_dump,
)


class GitHubKnowledgeStoreOperator:
    """Persists unified objects to SQLite + Knowledge directory."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        knowledge_root: str | Path | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.db_path = Path(db_path) if db_path else Path(":memory:")
        self.knowledge_root = Path(knowledge_root) if knowledge_root else None
        self.config = config or {}
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            apply_schema(self._conn)
        return self._conn

    def store_snapshots(self, snapshots: list[RepoSnapshot]) -> int:
        count = 0
        for snap in snapshots:
            row = snap.to_row()
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT OR REPLACE INTO {snap.TABLE} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            count += 1
        self.conn.commit()
        return count

    def store_canonicals(self, canonicals: list[RepoCanonical]) -> int:
        count = 0
        for c in canonicals:
            row = c.to_row()
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT OR REPLACE INTO {c.TABLE} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            count += 1
        self.conn.commit()
        return count

    def store_enrichments(self, enrichments: list[RepoEnrichment]) -> int:
        count = 0
        for e in enrichments:
            row = e.to_row()
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT OR REPLACE INTO {e.TABLE} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            count += 1
        self.conn.commit()
        return count

    def store_signals(self, signals: list[RepoSignal]) -> int:
        count = 0
        for s in signals:
            row = s.to_row()
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT OR REPLACE INTO {s.TABLE} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            count += 1
        self.conn.commit()
        return count

    def store_packets(self, packets: list[GitHubEvidencePacket]) -> int:
        count = 0
        for p in packets:
            row = p.to_row()
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT OR REPLACE INTO {p.TABLE} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            count += 1
        self.conn.commit()
        return count

    def store_assets(self, assets: list[OutputAsset]) -> int:
        count = 0
        for a in assets:
            row = a.to_row()
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            self.conn.execute(
                f"INSERT OR REPLACE INTO {a.TABLE} ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
            count += 1
        self.conn.commit()
        return count

    def write_asset_files(self, assets: list[OutputAsset]) -> int:
        if not self.knowledge_root:
            return 0
        out_dir = self.knowledge_root / "extracted" / "code_signal_assets"
        out_dir.mkdir(parents=True, exist_ok=True)
        for a in assets:
            fname = f"{a.asset_type}_{a.asset_id}.json"
            data = {
                "asset_id": a.asset_id,
                "asset_type": a.asset_type,
                "repo_key": a.repo_key,
                "generated_at": a.generated_at,
                "evidence_refs": json.loads(a.evidence_refs_json),
                "content": json.loads(a.content_json),
            }
            (out_dir / fname).write_text(
                json.dumps(data, ensure_ascii=False, indent=2)
            )
        return len(assets)

    def query_latest_signals(self, limit: int = 20) -> list[dict[str, Any]]:
        cur = self.conn.execute(
            f"SELECT * FROM {RepoSignal.TABLE} ORDER BY scored_at DESC LIMIT ?",
            (limit,),
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
