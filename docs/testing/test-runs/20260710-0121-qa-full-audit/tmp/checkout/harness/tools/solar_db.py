#!/usr/bin/env python3
"""
solar_db.py — Shared SQLite connection factory for Solar data plane.

All Solar/harness writers should use open_solar_db() for consistent:
  - WAL journal mode (concurrent readers don't block writers)
  - busy_timeout=5000ms (retry on lock contention)
  - optional read-only mode

Usage:
    from solar_db import open_solar_db
    conn = open_solar_db()
    conn = open_solar_db(readonly=True)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
import os

SOLAR_DB = Path(os.environ.get("SOLAR_DB", str(Path.home() / ".solar" / "solar.db")))


def open_solar_db(path: str | Path | None = None, readonly: bool = False) -> sqlite3.Connection:
    """Open solar.db with consistent concurrency settings.

    Args:
        path: Override database path. Defaults to ~/.solar/solar.db or $SOLAR_DB.
        readonly: If True, enable query_only pragma for safe reads.

    Returns:
        sqlite3.Connection with WAL mode and busy_timeout configured.
    """
    db_path = Path(path) if path else SOLAR_DB
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    if readonly:
        conn.execute("PRAGMA query_only=1")
    return conn
