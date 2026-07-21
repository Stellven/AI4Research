"""PaneLifecycleJobs — archive, TTL cleanup, backup for pane hygiene data.

Per data_models.md §5:
  - pane-hygiene.json: archive when > 100 KB, retain 30 days
  - dispatch-ledger.jsonl: archive when > 50 MB / 100K lines, retain 90 days
  - model_call_ledger.sqlite: TTL 90 days, vacuum after cleanup
  - Daily backup before cleanup
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


class PaneLifecycleJobs:

    def __init__(
        self,
        *,
        hygiene_json_path: str,
        ledger_jsonl_path: str,
        sqlite_db_path: str,
        archive_dir: Optional[str] = None,
    ) -> None:
        self._hygiene_path = Path(hygiene_json_path)
        self._ledger_path = Path(ledger_jsonl_path)
        self._sqlite_path = Path(sqlite_db_path)
        self._archive_dir = Path(archive_dir or self._hygiene_path.parent / "archive")

    # ── pane-hygiene.json archive (30-day retention) ────────────────

    def archive_hygiene(self, *, max_size_kb: int = 100) -> Optional[str]:
        if not self._hygiene_path.exists():
            return None
        size_kb = self._hygiene_path.stat().st_size / 1024
        if size_kb < max_size_kb:
            return None
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = _date_stamp()
        dest = self._archive_dir / f"pane-hygiene.{stamp}.json"
        shutil.copy2(str(self._hygiene_path), str(dest))
        return str(dest)

    def cleanup_hygiene_archives(self, *, retention_days: int = 30) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed: list[str] = []
        for f in self._archive_dir.glob("pane-hygiene.*.json"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                removed.append(str(f))
        return removed

    # ── dispatch-ledger.jsonl archive (90-day retention) ────────────

    def archive_ledger(self, *, max_size_mb: float = 50, max_lines: int = 100_000) -> Optional[str]:
        if not self._ledger_path.exists():
            return None
        size_mb = self._ledger_path.stat().st_size / (1024 * 1024)
        if size_mb < max_size_mb:
            with open(self._ledger_path) as f:
                line_count = sum(1 for _ in f)
            if line_count < max_lines:
                return None
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = _date_stamp()
        dest = self._archive_dir / f"dispatch-ledger.{stamp}.jsonl"
        shutil.move(str(self._ledger_path), str(dest))
        self._ledger_path.touch()
        return str(dest)

    def cleanup_ledger_archives(self, *, retention_days: int = 90) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed: list[str] = []
        for f in self._archive_dir.glob("dispatch-ledger.*.jsonl*"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                removed.append(str(f))
        return removed

    def compress_ledger_archives(self) -> list[str]:
        compressed: list[str] = []
        for f in self._archive_dir.glob("dispatch-ledger.*.jsonl"):
            gz_path = Path(str(f) + ".gz")
            if gz_path.exists():
                continue
            with open(f, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            f.unlink()
            compressed.append(str(gz_path))
        return compressed

    # ── model_call_ledger.sqlite TTL (90 days) ──────────────────────

    def backup_sqlite(self) -> Optional[str]:
        if not self._sqlite_path.exists():
            return None
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = _date_stamp()
        dest = self._archive_dir / f"model_call_ledger.{stamp}.sqlite.bak"
        shutil.copy2(str(self._sqlite_path), str(dest))
        return str(dest)

    def ttl_sqlite(self, *, retention_days: int = 90) -> int:
        if not self._sqlite_path.exists():
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days))
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        conn = sqlite3.connect(str(self._sqlite_path))
        before = conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0]
        conn.execute(
            "DELETE FROM ledger_events WHERE ts < ?", (cutoff_str,)
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0]
        conn.close()
        conn = sqlite3.connect(str(self._sqlite_path))
        conn.execute("VACUUM")
        conn.close()
        return before - after

    # ── Daily job (cron registration placeholder) ───────────────────

    def run_daily(self) -> dict[str, object]:
        self.backup_sqlite()
        deleted = self.ttl_sqlite()
        hygiene_archive = self.archive_hygiene()
        ledger_archive = self.archive_ledger()
        self.compress_ledger_archives()
        h_cleaned = self.cleanup_hygiene_archives()
        l_cleaned = self.cleanup_ledger_archives()
        return {
            "ts": _utc_now(),
            "sqlite_ttl_deleted": deleted,
            "hygiene_archive": hygiene_archive,
            "ledger_archive": ledger_archive,
            "hygiene_cleaned": len(h_cleaned),
            "ledger_cleaned": len(l_cleaned),
        }
