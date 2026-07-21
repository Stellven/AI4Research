"""registry.py — Register, query, activate, list, and history for compiler profiles.

Storage
-------
* JSON files in ``~/.solar/harness/profiles/``
* SQLite cache table ``compiler_profiles`` for fast lookups
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .schema import validate_profile

__all__ = [
    "register",
    "query",
    "activate",
    "deactivate",
    "list_profiles",
    "history",
    "get_active",
]

_PROFILES_DIR = Path.home() / ".solar" / "harness" / "profiles"
_DB_PATH = Path.home() / ".solar" / "harness" / "compiler_profiles.db"

_lock = threading.Lock()


def _ensure_dirs() -> None:
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compiler_profiles (
            profile_id  TEXT NOT NULL,
            version     INTEGER NOT NULL,
            name        TEXT NOT NULL,
            tags        TEXT NOT NULL,
            data        TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (profile_id, version)
        )
    """)
    conn.commit()
    return conn


def register(
    profile_json: dict[str, Any],
    *,
    profiles_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Persist a compiler profile to JSON file and SQLite cache.

    Parameters
    ----------
    profile_json : dict
        Valid compiler profile dict.

    Returns
    -------
    dict with ``profile_id``, ``version``, ``path`` keys.

    Raises
    ------
    ValueError
        If the profile fails schema validation.
    """
    is_valid, errors = validate_profile(profile_json)
    if not is_valid:
        raise ValueError(f"Invalid profile: {errors}")

    pid = profile_json["profile_id"]
    version = profile_json["version"]
    base_dir = profiles_dir or _PROFILES_DIR
    _ensure_dirs()

    # Write JSON file
    version_dir = base_dir / pid
    version_dir.mkdir(parents=True, exist_ok=True)
    file_path = version_dir / f"v{version}.json"
    file_path.write_text(
        json.dumps(profile_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Write to SQLite cache
    conn = _get_db(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO compiler_profiles "
            "(profile_id, version, name, tags, data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                pid,
                version,
                profile_json["name"],
                json.dumps(profile_json.get("tags", [])),
                json.dumps(profile_json, ensure_ascii=False),
                profile_json["created_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "profile_id": pid,
        "version": version,
        "path": str(file_path),
    }


def query(
    profile_id: Optional[str] = None,
    tag: Optional[str] = None,
    *,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Return matching profiles from the SQLite cache.

    Parameters
    ----------
    profile_id : str, optional
        Exact profile_id match.
    tag : str, optional
        Tag substring match.

    Returns
    -------
    list[dict]
    """
    conn = _get_db(db_path)
    try:
        sql = "SELECT data FROM compiler_profiles WHERE 1=1"
        params: list[Any] = []

        if profile_id is not None:
            sql += " AND profile_id = ?"
            params.append(profile_id)

        if tag is not None:
            sql += " AND tags LIKE ?"
            params.append(f"%{tag}%")

        # Get the latest version for each profile_id
        sql += " ORDER BY profile_id, version DESC"

        rows = conn.execute(sql, params).fetchall()
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for (data_str,) in rows:
            profile = json.loads(data_str)
            pid = profile.get("profile_id", "")
            if pid not in seen_ids:
                seen_ids.add(pid)
                results.append(profile)

        return results
    finally:
        conn.close()


def activate(
    profile_id: str,
    version: Optional[int] = None,
    *,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Set a profile as the current active profile.

    Only one profile can be active at a time.

    Parameters
    ----------
    profile_id : str
    version : int, optional
        If not given, activates the latest version.

    Returns
    -------
    dict with the activated profile data.
    """
    conn = _get_db(db_path)
    try:
        # Deactivate all
        conn.execute("UPDATE compiler_profiles SET is_active = 0")

        # Find the target version
        if version is None:
            row = conn.execute(
                "SELECT data FROM compiler_profiles "
                "WHERE profile_id = ? ORDER BY version DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT data FROM compiler_profiles "
                "WHERE profile_id = ? AND version = ?",
                (profile_id, version),
            ).fetchone()

        if row is None:
            raise ValueError(f"Profile {profile_id!r} not found")

        target_version = json.loads(row[0])["version"]
        conn.execute(
            "UPDATE compiler_profiles SET is_active = 1 "
            "WHERE profile_id = ? AND version = ?",
            (profile_id, target_version),
        )
        conn.commit()

        return json.loads(row[0])
    finally:
        conn.close()


def deactivate(*, db_path: Optional[Path] = None) -> None:
    """Deactivate all profiles."""
    conn = _get_db(db_path)
    try:
        conn.execute("UPDATE compiler_profiles SET is_active = 0")
        conn.commit()
    finally:
        conn.close()


def list_profiles(*, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return all profiles (latest version per profile_id)."""
    return query(db_path=db_path)


def history(
    profile_id: str,
    *,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Return version history for a specific profile.

    Returns
    -------
    list[dict]
        Ordered from oldest to newest version.
    """
    conn = _get_db(db_path)
    try:
        rows = conn.execute(
            "SELECT data FROM compiler_profiles "
            "WHERE profile_id = ? ORDER BY version ASC",
            (profile_id,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    finally:
        conn.close()


def get_active(*, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Return the currently active profile, or None."""
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT data FROM compiler_profiles WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None
    finally:
        conn.close()
