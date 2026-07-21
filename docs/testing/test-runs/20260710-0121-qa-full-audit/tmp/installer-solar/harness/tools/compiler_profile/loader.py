"""loader.py — Load compiler profiles from JSON files and SQLite cache.

Provides convenience functions for loading profiles from disk (JSON) or
from the SQLite cache managed by the registry module.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .schema import validate_profile

__all__ = ["load_from_json", "load_from_db"]

_PROFILES_DIR = Path.home() / ".solar" / "harness" / "profiles"


def load_from_json(
    profile_id: str,
    version: Optional[int] = None,
    *,
    profiles_dir: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Load a profile from a JSON file on disk.

    Parameters
    ----------
    profile_id : str
    version : int, optional
        If not given, loads the highest version found.

    Returns
    -------
    dict or None
    """
    base_dir = profiles_dir or _PROFILES_DIR
    profile_dir = base_dir / profile_id

    if not profile_dir.exists():
        return None

    if version is not None:
        target = profile_dir / f"v{version}.json"
        if not target.exists():
            return None
        return _load_and_validate(target)

    # Find the highest version
    versions: list[int] = []
    for f in profile_dir.glob("v*.json"):
        try:
            v = int(f.stem[1:])  # strip 'v' prefix
            versions.append(v)
        except ValueError:
            continue

    if not versions:
        return None

    latest = max(versions)
    return _load_and_validate(profile_dir / f"v{latest}.json")


def load_from_db(
    profile_id: str,
    version: Optional[int] = None,
    *,
    db_path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Load a profile from the SQLite cache.

    Parameters
    ----------
    profile_id : str
    version : int, optional
        If not given, loads the highest version.

    Returns
    -------
    dict or None
    """
    import sqlite3

    from .registry import _get_db

    conn = _get_db(db_path)
    try:
        if version is not None:
            row = conn.execute(
                "SELECT data FROM compiler_profiles "
                "WHERE profile_id = ? AND version = ?",
                (profile_id, version),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT data FROM compiler_profiles "
                "WHERE profile_id = ? ORDER BY version DESC LIMIT 1",
                (profile_id,),
            ).fetchone()

        if row is None:
            return None
        return json.loads(row[0])
    finally:
        conn.close()


def _load_and_validate(path: Path) -> Optional[dict[str, Any]]:
    """Load JSON from path, validate, and return."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    is_valid, errors = validate_profile(data)
    if not is_valid:
        return None
    return data
