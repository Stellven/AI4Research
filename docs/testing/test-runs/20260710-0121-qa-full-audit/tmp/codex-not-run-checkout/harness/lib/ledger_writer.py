"""LedgerWriter — dual-write audit ledger: JSONL append-only + SQLite WAL.

Per interfaces.md §5 + data_models.md §2:
  - dispatch-ledger.jsonl: 11 fields, append-only
  - model_call_ledger.sqlite: 13 columns, WAL mode
  - Sync dual-write; fail-open (never blocks dispatch)
  - Fallback file on both-engine failure
"""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class LedgerRecord:
    pane_id: str
    action: str
    before_state: str
    after_state: str
    ts: str
    reason: str
    from_pane: Optional[str] = None
    to_pane: Optional[str] = None
    task_id: Optional[str] = None
    detector_id: Optional[str] = None
    sprint_id: Optional[str] = None
    attempt: Optional[int] = None
    success: Optional[bool] = None
    extra: Optional[dict[str, Any]] = None


def _utc_now_ms() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _record_to_jsonl(rec: LedgerRecord) -> str:
    d = asdict(rec)
    for k, v in list(d.items()):
        if v is None:
            del d[k]
    return json.dumps(d, default=str, ensure_ascii=False)


class LedgerWriter:

    def __init__(
        self,
        ledger_jsonl_path: str,
        sqlite_db_path: str,
        *,
        fallback_path: Optional[str] = None,
    ) -> None:
        self._jsonl_path = Path(ledger_jsonl_path)
        self._sqlite_path = Path(sqlite_db_path)
        self._fallback_path = Path(
            fallback_path
            or str(self._jsonl_path.parent / "ledger-fallback.jsonl")
        )
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()
        except (OSError, sqlite3.Error) as exc:
            self._sqlite_init_error = exc
        else:
            self._sqlite_init_error = None

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(str(self._sqlite_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ledger_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pane_id     TEXT NOT NULL,
                action      TEXT NOT NULL,
                before_state TEXT,
                after_state  TEXT,
                ts          TEXT NOT NULL,
                reason      TEXT,
                from_pane   TEXT,
                to_pane     TEXT,
                task_id     TEXT,
                detector_id TEXT,
                sprint_id   TEXT,
                attempt     INTEGER,
                success     INTEGER,
                extra       TEXT,
                ledger_ts   TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_le_pane_ts ON ledger_events(pane_id, ts)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_le_action ON ledger_events(action)"
        )
        conn.commit()
        conn.close()

    # ── Write Methods ────────────────────────────────────────────────

    def _dual_write(self, rec: LedgerRecord) -> None:
        jsonl_ok = self._write_jsonl(rec)
        sqlite_ok = self._write_sqlite(rec)
        if not jsonl_ok and not sqlite_ok:
            self._write_fallback(rec)
        elif not jsonl_ok or not sqlite_ok:
            self._write_partial_failure_fallback(rec)

    def _write_jsonl(self, rec: LedgerRecord) -> bool:
        try:
            line = _record_to_jsonl(rec) + "\n"
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(line)
            return True
        except OSError as e:
            print(f"[ledger-writer] JSONL write failed: {e}", file=sys.stderr)
            return False

    def _write_sqlite(self, rec: LedgerRecord) -> bool:
        try:
            if self._sqlite_init_error is not None:
                raise sqlite3.Error(str(self._sqlite_init_error))
            conn = sqlite3.connect(str(self._sqlite_path), timeout=5)
            conn.execute(
                "INSERT INTO ledger_events "
                "(pane_id, action, before_state, after_state, ts, reason, "
                "from_pane, to_pane, task_id, detector_id, sprint_id, "
                "attempt, success, extra, ledger_ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.pane_id, rec.action, rec.before_state, rec.after_state,
                    rec.ts, rec.reason, rec.from_pane, rec.to_pane, rec.task_id,
                    rec.detector_id, rec.sprint_id, rec.attempt,
                    1 if rec.success else (0 if rec.success is False else None),
                    json.dumps(rec.extra) if rec.extra else None,
                    _utc_now_ms(),
                ),
            )
            conn.commit()
            conn.close()
            return True
        except (sqlite3.Error, OSError) as e:
            print(f"[ledger-writer] SQLite write failed: {e}", file=sys.stderr)
            return False

    def _write_fallback(self, rec: LedgerRecord) -> None:
        try:
            self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
            line = _record_to_jsonl(rec) + "\n"
            with open(self._fallback_path, "a", encoding="utf-8") as f:
                f.write(line)
            print(f"[ledger-writer] CRITICAL: both engines failed, wrote to fallback",
                  file=sys.stderr)
        except OSError:
            print(f"[ledger-writer] FATAL: fallback write also failed",
                  file=sys.stderr)

    def _write_partial_failure_fallback(self, rec: LedgerRecord) -> None:
        try:
            self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
            line = _record_to_jsonl(rec) + "\n"
            with open(self._fallback_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def record_recover(
        self,
        pane_id: str,
        *,
        before_state: str,
        after_state: str,
        success: bool,
        reason: str,
        attempt: int = 1,
        sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="recover",
            before_state=before_state, after_state=after_state,
            ts=_utc_now_ms(), reason=reason,
            sprint_id=sprint_id, attempt=attempt, success=success,
        )
        self._dual_write(rec)

    def record_respawn(
        self,
        pane_id: str,
        *,
        before_state: str,
        after_state: str,
        success: bool,
        reason: str,
        attempt: int = 1,
        sprint_id: Optional[str] = None,
        from_pane: Optional[str] = None,
        to_pane: Optional[str] = None,
        task_id: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="respawn",
            before_state=before_state, after_state=after_state,
            ts=_utc_now_ms(), reason=reason,
            from_pane=from_pane, to_pane=to_pane, task_id=task_id,
            sprint_id=sprint_id, attempt=attempt, success=success,
            extra=extra,
        )
        self._dual_write(rec)

    def record_clear(
        self,
        pane_id: str,
        *,
        before_state: str = "",
        after_state: str = "",
        success: bool,
        reason: str,
        attempt: int = 1,
        sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="clear",
            before_state=before_state, after_state=after_state,
            ts=_utc_now_ms(), reason=reason,
            sprint_id=sprint_id, attempt=attempt, success=success,
        )
        self._dual_write(rec)

    def record_reassign(
        self,
        from_pane: str,
        to_pane: str,
        *,
        task_id: str,
        before_state: str,
        after_state: str,
        reason: str,
        sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=from_pane, action="reassign",
            before_state=before_state, after_state=after_state,
            ts=_utc_now_ms(), reason=reason,
            from_pane=from_pane, to_pane=to_pane,
            task_id=task_id, sprint_id=sprint_id,
        )
        self._dual_write(rec)

    def record_reinject(
        self,
        pane_id: str,
        *,
        before_state: str,
        after_state: str,
        success: bool,
        reason: str,
        sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="reinject",
            before_state=before_state, after_state=after_state,
            ts=_utc_now_ms(), reason=reason,
            sprint_id=sprint_id, success=success,
        )
        self._dual_write(rec)

    # ── Query Methods ────────────────────────────────────────────────

    def query_history(
        self,
        pane_id: str,
        *,
        action: Optional[str] = None,
        limit: int = 50,
        since_iso: Optional[str] = None,
    ) -> list[LedgerRecord]:
        if not self._jsonl_path.exists():
            return []
        records: list[LedgerRecord] = []
        with open(self._jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("pane_id") != pane_id:
                    continue
                if action and d.get("action") != action:
                    continue
                if since_iso and d.get("ts", "") < since_iso:
                    continue
                records.append(LedgerRecord(
                    pane_id=d.get("pane_id", ""),
                    action=d.get("action", ""),
                    before_state=d.get("before_state", ""),
                    after_state=d.get("after_state", ""),
                    ts=d.get("ts", ""),
                    reason=d.get("reason", ""),
                    from_pane=d.get("from_pane"),
                    to_pane=d.get("to_pane"),
                    task_id=d.get("task_id"),
                    detector_id=d.get("detector_id"),
                    sprint_id=d.get("sprint_id"),
                    attempt=d.get("attempt"),
                    success=d.get("success"),
                ))
        records.sort(key=lambda r: r.ts, reverse=True)
        return records[:limit]
