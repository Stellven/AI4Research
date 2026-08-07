"""DeepResearch SQLite storage layer and JSONL artifact writers.

Spec: sprint-20260513-solar-deepresearch-product-line-s02-architecture
      / deepresearch.storage.md §2 (SQLite) + §3 (JSONL) + §5 (feature flag)

Provides:
- init_db(path): create/verify all 7 tables via migration SQL
- get_connection(path): thread-safe connection with foreign keys enabled
- JSONL append/read helpers for artifact files
- feature_flag('research.evidence_ledger'): reads ~/.solar/config.json
- span verification helpers
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
CONFIG_PATH = Path.home() / ".solar" / "config.json"

SEVEN_TABLES = (
    "research_runs",
    "research_sources",
    "evidence_items",
    "claims",
    "claim_evidence",
    "report_sections",
    "section_checks",
)


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a Connection with foreign keys and WAL mode enabled.

    Args:
        db_path: Path to the SQLite database file, or ':memory:'.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> sqlite3.Connection:
    """Create all 7 DeepResearch tables (idempotent).

    Runs 001_init.sql from the migrations directory. Uses CREATE TABLE IF NOT
    EXISTS so repeated calls are safe.

    Args:
        db_path: Path to the SQLite database file, or ':memory:'.

    Returns:
        A configured sqlite3.Connection ready for use.
    """
    conn = get_connection(db_path)
    migration_sql = (MIGRATIONS_DIR / "001_init.sql").read_text()
    conn.executescript(migration_sql)
    conn.commit()
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check whether a table exists in the database."""
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def table_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Return the number of rows in a table."""
    cur = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


def feature_flag(flag_name: str, default: bool = False) -> bool:
    """Read a boolean feature flag from ~/.solar/config.json.

    Falls back to `default` if the config file does not exist or the key is
    absent.  The primary consumer is ``research.evidence_ledger`` which
    defaults to *on* so deterministic evidence artifacts stay enabled unless
    explicitly turned off.
    """
    if not CONFIG_PATH.exists():
        return default
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        val = cfg.get("feature_flags", {}).get(flag_name)
        if val is None:
            return default
        return bool(val)
    except (json.JSONDecodeError, OSError):
        return default


def evidence_ledger_enabled() -> bool:
    """Shorthand for ``feature_flag('research.evidence_ledger')``."""
    return feature_flag("research.evidence_ledger", default=True)


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------


def append_jsonl(path: str, record: Dict[str, Any]) -> None:
    """Append a single JSON line to a JSONL file.

    Creates parent directories if they do not exist.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read all JSON lines from a JSONL file.

    Skips blank lines. Raises ValueError on malformed JSON.
    """
    results: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return results
    with open(path, "r", encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            stripped = raw.rstrip("\n")
            if not stripped:
                continue
            try:
                results.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_num}: {exc}") from exc
    return results


def validate_jsonl(path: str) -> List[str]:
    """Return a list of error strings for malformed lines (empty = valid)."""
    errors: List[str] = []
    if not os.path.exists(path):
        return errors
    with open(path, "r", encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            stripped = raw.rstrip("\n")
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_num}: {exc}")
    return errors


class ResearchRunStateStore:
    """Canonical, single-writer state transaction for provider-backed runs.

    The state document and append-only journal are written by this class only.
    Callers must not maintain a wiki sidecar or legacy status file in parallel.
    """

    def __init__(self, run_dir: str | Path) -> None:
        self.root = Path(run_dir)
        self.state_path = self.root / "research-run-state.json"
        self.journal_path = self.root / "research-run-state.jsonl"

    def load(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"revision": 0, "completed_nodes": [], "state": "init", "resume_token": ""}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def commit(
        self,
        *,
        state: str,
        completed_nodes: List[str],
        resume_token: str = "",
        evidence_refs: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        current = self.load()
        payload = {
            "schema": "opensolar.research_run_state.v1",
            "revision": int(current.get("revision") or 0) + 1,
            "state": state,
            "completed_nodes": list(dict.fromkeys(str(node) for node in completed_nodes)),
            "resume_token": resume_token,
            "evidence_refs": list(evidence_refs or []),
            "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            tmp = Path(handle.name)
        os.replace(tmp, self.state_path)
        append_jsonl(str(self.journal_path), payload)
        return payload


# ---------------------------------------------------------------------------
# Span verification
# ---------------------------------------------------------------------------


def verify_span(
    source_content: str,
    evidence_content: str,
    span_start: int,
    span_end: int,
) -> Dict[str, Any]:
    """Verify that evidence_content matches source[span_start:span_end].

    Returns a dict with ``status`` of 'match', 'fuzzy_match', or 'mismatch'.
    Tolerance: 5 % length difference for whitespace normalization.
    """
    source_bytes = source_content.encode("utf-8")
    slice_bytes = source_bytes[span_start:span_end]
    actual = slice_bytes.decode("utf-8", errors="replace")

    normalized_actual = actual.strip()
    normalized_evidence = evidence_content.strip()

    if normalized_actual == normalized_evidence:
        return {"status": "match", "span_start": span_start, "span_end": span_end}

    len_diff = abs(len(normalized_actual) - len(normalized_evidence))
    threshold = max(len(normalized_actual), len(normalized_evidence)) * 0.05

    if len_diff <= threshold:
        return {
            "status": "fuzzy_match",
            "span_start": span_start,
            "span_end": span_end,
            "length_diff_pct": round(
                len_diff / max(len(normalized_actual), 1) * 100, 2
            ),
        }

    return {
        "status": "mismatch",
        "span_start": span_start,
        "span_end": span_end,
        "source_slice_preview": normalized_actual[:200],
        "evidence_preview": normalized_evidence[:200],
    }
