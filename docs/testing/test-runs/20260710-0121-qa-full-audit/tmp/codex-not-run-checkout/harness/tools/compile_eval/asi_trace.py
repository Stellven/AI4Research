"""asi_trace.py — ASI trace records in SQLite.

Stores per-compilation evaluation traces including ASI score, dimension
scores, hard validator results, and golden case references.

SQLite table ``asi_traces``::

    trace_id                TEXT PRIMARY KEY
    timestamp               TEXT NOT NULL
    profile_id              TEXT
    profile_version         INTEGER
    task_type               TEXT
    sprint_id               TEXT
    asi_score               REAL
    dimension_scores        TEXT (JSON)
    hard_validators_passed  TEXT (JSON)
    hard_validators_failed  TEXT (JSON)
    golden_case_used        TEXT
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


@dataclasses.dataclass
class ASITrace:
    """A single ASI evaluation trace record."""

    trace_id: str
    timestamp: str
    profile_id: str = ""
    profile_version: int = 0
    task_type: str = ""
    sprint_id: str = ""
    asi_score: float = 0.0
    dimension_scores: dict[str, float] = dataclasses.field(default_factory=dict)
    hard_validators_passed: list[str] = dataclasses.field(default_factory=list)
    hard_validators_failed: list[str] = dataclasses.field(default_factory=list)
    golden_case_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS asi_traces (
    trace_id                TEXT PRIMARY KEY,
    timestamp               TEXT NOT NULL,
    profile_id              TEXT NOT NULL DEFAULT '',
    profile_version         INTEGER NOT NULL DEFAULT 0,
    task_type               TEXT NOT NULL DEFAULT '',
    sprint_id               TEXT NOT NULL DEFAULT '',
    asi_score               REAL NOT NULL DEFAULT 0.0,
    dimension_scores        TEXT NOT NULL DEFAULT '{}',
    hard_validators_passed  TEXT NOT NULL DEFAULT '[]',
    hard_validators_failed  TEXT NOT NULL DEFAULT '[]',
    golden_case_used        TEXT NOT NULL DEFAULT ''
)
"""

_INSERT_SQL = """
INSERT INTO asi_traces (
    trace_id, timestamp, profile_id, profile_version,
    task_type, sprint_id, asi_score,
    dimension_scores, hard_validators_passed,
    hard_validators_failed, golden_case_used
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def init_trace_db(db_path: str | Path) -> None:
    """Create the ``asi_traces`` table if it does not exist.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database file.
    """
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def write_trace(db_path: str | Path, trace: ASITrace) -> str:
    """Insert an ASI trace record.

    Parameters
    ----------
    db_path : str or Path
    trace : ASITrace

    Returns
    -------
    str
        The ``trace_id`` that was inserted.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            _INSERT_SQL,
            (
                trace.trace_id,
                trace.timestamp,
                trace.profile_id,
                trace.profile_version,
                trace.task_type,
                trace.sprint_id,
                trace.asi_score,
                json.dumps(trace.dimension_scores),
                json.dumps(trace.hard_validators_passed),
                json.dumps(trace.hard_validators_failed),
                trace.golden_case_used,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return trace.trace_id


def query_traces(
    db_path: str | Path,
    *,
    profile_id: Optional[str] = None,
    task_type: Optional[str] = None,
    time_range: Optional[tuple[str, str]] = None,
    limit: int = 100,
) -> list[ASITrace]:
    """Query ASI trace records.

    Parameters
    ----------
    db_path : str or Path
    profile_id : str, optional
    task_type : str, optional
    time_range : tuple[str, str], optional
        (start_iso, end_iso) inclusive range filter.
    limit : int
        Maximum records to return.

    Returns
    -------
    list[ASITrace]
    """
    conn = sqlite3.connect(str(db_path))
    try:
        sql = "SELECT * FROM asi_traces WHERE 1=1"
        params: list[Any] = []

        if profile_id is not None:
            sql += " AND profile_id = ?"
            params.append(profile_id)

        if task_type is not None:
            sql += " AND task_type = ?"
            params.append(task_type)

        if time_range is not None:
            sql += " AND timestamp >= ? AND timestamp <= ?"
            params.extend(time_range)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        col_names = [d[0] for d in conn.execute(
            "SELECT * FROM asi_traces LIMIT 0"
        ).description]

        traces: list[ASITrace] = []
        for row in rows:
            row_dict = dict(zip(col_names, row))
            traces.append(ASITrace(
                trace_id=row_dict["trace_id"],
                timestamp=row_dict["timestamp"],
                profile_id=row_dict.get("profile_id", ""),
                profile_version=row_dict.get("profile_version", 0),
                task_type=row_dict.get("task_type", ""),
                sprint_id=row_dict.get("sprint_id", ""),
                asi_score=row_dict.get("asi_score", 0.0),
                dimension_scores=json.loads(row_dict.get("dimension_scores", "{}")),
                hard_validators_passed=json.loads(row_dict.get("hard_validators_passed", "[]")),
                hard_validators_failed=json.loads(row_dict.get("hard_validators_failed", "[]")),
                golden_case_used=row_dict.get("golden_case_used", ""),
            ))
        return traces
    finally:
        conn.close()
