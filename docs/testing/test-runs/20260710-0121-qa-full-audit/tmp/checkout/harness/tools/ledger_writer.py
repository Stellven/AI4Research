"""LedgerWriter — dual-write audit ledger: JSONL append-only + SQLite WAL.

Per interfaces.md §5 + data_models.md §2: sync dual-write with fallback.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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
    sprint_id: Optional[str] = None
    attempt: Optional[int] = None
    success: Optional[bool] = None
    extra: dict = field(default_factory=dict)


def _utc_now_ms() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class LedgerWriter:
    JSONL_FIELDS = [
        "pane_id", "action", "before_state", "after_state", "ts",
        "reason", "task_id", "from_pane", "to_pane", "extra",
    ]

    def __init__(self, ledger_jsonl_path: str, sqlite_db_path: str) -> None:
        self._jsonl_path = Path(ledger_jsonl_path)
        self._sqlite_path = Path(sqlite_db_path)
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_calls (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts            TEXT NOT NULL,
                    pane_id       TEXT NOT NULL,
                    model         TEXT NOT NULL DEFAULT '',
                    call_type     TEXT NOT NULL,
                    dispatch_id   TEXT,
                    prompt_hash   TEXT,
                    input_tokens  INTEGER,
                    output_tokens INTEGER,
                    duration_ms   INTEGER,
                    status        TEXT NOT NULL,
                    error_code    TEXT,
                    ledger_ts     TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mc_pane_ts ON model_calls(pane_id, ts)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._sqlite_path))

    def _write_jsonl(self, record: LedgerRecord) -> bool:
        try:
            row = {k: v for k, v in asdict(record).items() if k in self.JSONL_FIELDS}
            with open(self._jsonl_path, "a") as f:
                f.write(json.dumps(row, default=str) + "\n")
            return True
        except OSError:
            return False

    def _write_sqlite(self, record: LedgerRecord) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO model_calls (ts, pane_id, call_type, status, ledger_ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (record.ts, record.pane_id, record.action,
                     "success" if record.success else "failed", record.ts),
                )
            return True
        except (sqlite3.Error, OSError):
            return False

    def _dual_write(self, record: LedgerRecord) -> None:
        jsonl_ok = self._write_jsonl(record)
        sqlite_ok = self._write_sqlite(record)
        if not jsonl_ok or not sqlite_ok:
            fallback_path = self._jsonl_path.parent / "ledger_fallback.jsonl"
            try:
                row = asdict(record)
                row["_fallback_reason"] = f"jsonl={jsonl_ok},sqlite={sqlite_ok}"
                with open(fallback_path, "a") as f:
                    f.write(json.dumps(row, default=str) + "\n")
            except OSError:
                pass

    def record_recover(
        self, pane_id: str, *, before_state: str, after_state: str,
        success: bool, reason: str, attempt: int = 1,
        sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="recover", before_state=before_state,
            after_state=after_state, ts=_utc_now_ms(), reason=reason,
            sprint_id=sprint_id, attempt=attempt, success=success,
        )
        self._dual_write(rec)

    def record_clear(
        self, pane_id: str, *, before_state: str = "", after_state: str = "",
        success: bool, reason: str, attempt: int = 1,
        sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="clear", before_state=before_state,
            after_state=after_state, ts=_utc_now_ms(), reason=reason,
            sprint_id=sprint_id, attempt=attempt, success=success,
        )
        self._dual_write(rec)

    def record_reassign(
        self, pane_id: str, *, from_pane: str, to_pane: str,
        task_id: str, reason: str, sprint_id: Optional[str] = None,
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="reassign", before_state="", after_state="",
            ts=_utc_now_ms(), reason=reason, from_pane=from_pane,
            to_pane=to_pane, task_id=task_id, sprint_id=sprint_id,
        )
        self._dual_write(rec)

    def record_reinject(
        self, pane_id: str, *, success: bool,
        components: list[str], reason: str = "",
    ) -> None:
        rec = LedgerRecord(
            pane_id=pane_id, action="reinject", before_state="", after_state="",
            ts=_utc_now_ms(), reason=reason, success=success,
            extra={"components": components},
        )
        self._dual_write(rec)

    def query_history(
        self, pane_id: str, *, limit: int = 100, action: Optional[str] = None,
    ) -> list[dict]:
        results: list[dict] = []
        if self._jsonl_path.exists():
            with open(self._jsonl_path) as f:
                for line in f:
                    try:
                        row = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    if row.get("pane_id") == pane_id:
                        if action is None or row.get("action") == action:
                            results.append(row)
        return results[-limit:]
