"""Percentile ranker — compute and query percentile distributions.

Provides:
- ``refresh_percentiles()``: recompute and replace entire snapshot_percentiles content.
- ``query_percentiles()``: query percentile values by (topic, age_band).
- ``get_age_band()`` / ``get_star_band()``: bucket classification helpers.

Age buckets: <7d, 8-30d, 31-180d, 181-365d, 1y+
Star buckets: <100, 100-1k, 1k-10k, 10k+

Spec: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade
      design.md §A2 (percentile buckets) + scoring-contract.md §2 (normalization)
Node: B5
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


# 5 age buckets and 4 star buckets per design.md §A2
AGE_BANDS = ("<7d", "8-30d", "31-180d", "181-365d", "1y+")
AGE_BAND_DAYS = (7, 30, 180, 365)

STAR_BANDS = ("<100", "100-1k", "1k-10k", "10k+")
STAR_BAND_THRESHOLDS = (100, 1000, 10000)


def get_age_band(repo_age_days: int) -> str:
    """Classify repo age into a bucket."""
    if repo_age_days <= 7:
        return "<7d"
    elif repo_age_days <= 30:
        return "8-30d"
    elif repo_age_days <= 180:
        return "31-180d"
    elif repo_age_days <= 365:
        return "181-365d"
    else:
        return "1y+"


def get_star_band(stars: int) -> str:
    """Classify star count into a bucket."""
    if stars < 100:
        return "<100"
    elif stars < 1000:
        return "100-1k"
    elif stars < 10000:
        return "1k-10k"
    else:
        return "10k+"


def refresh_percentiles(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    """Recompute and replace snapshot_percentiles content.

    This deletes existing percentiles for the given date (or all dates)
    and reinserts fresh percentile values derived from snapshot data.

    Parameters
    ----------
    conn : sqlite3.Connection
    snapshot_date : str, optional
        ISO date string (YYYY-MM-DD). Defaults to today UTC.
    topic : str, optional
        If given, only refresh for this topic. Otherwise refresh all.

    Returns
    -------
    dict with ``rows_inserted``, ``snapshot_date``.
    """
    if snapshot_date is None:
        snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Delete existing percentiles for this date (+ optional topic)
    if topic is not None:
        conn.execute(
            "DELETE FROM snapshot_percentiles WHERE snapshot_date = ? AND topic = ?",
            (snapshot_date, topic),
        )
    else:
        conn.execute(
            "DELETE FROM snapshot_percentiles WHERE snapshot_date = ?",
            (snapshot_date,),
        )

    # Query snapshot data joined with repo_master for topic and age info.
    # We need: full_name, topic, stars, star_velocity, created_at (for age)
    # The snapshot table is github_star_snapshots; repo info is in github_repo_master or repo_master.
    # We'll try to join against whatever repo table exists.

    # First, discover the repo table name
    repo_table = _find_repo_table(conn)
    if repo_table is None:
        conn.commit()
        return {"rows_inserted": 0, "snapshot_date": snapshot_date, "warning": "no_repo_table_found"}

    # Get latest snapshot per repo
    latest_snapshots = conn.execute(f"""
        SELECT s.full_name, s.stars, s.snapshot_at,
               s.stars_delta_24h
        FROM github_star_snapshots s
        INNER JOIN (
            SELECT full_name, MAX(snapshot_at) AS max_at
            FROM github_star_snapshots
            GROUP BY full_name
        ) latest ON s.full_name = latest.full_name AND s.snapshot_at = latest.max_at
    """).fetchall()

    if not latest_snapshots:
        conn.commit()
        return {"rows_inserted": 0, "snapshot_date": snapshot_date}

    # For each snapshot, determine topic, age_band, star_band and compute velocity percentile
    # Group by (topic, age_band, star_band) to compute percentiles
    bucket_data: dict[tuple[str, str, str], list[tuple[str, float]]] = {}

    for row in latest_snapshots:
        full_name, stars, snapshot_at, delta_24h = row
        stars = stars or 0
        delta_24h = delta_24h or 0

        # Get topic from repo table
        repo_topic = _get_repo_topic(conn, repo_table, full_name)

        # Compute age from first snapshot or repo created_at
        age_days = _get_repo_age_days(conn, full_name)

        age_band = get_age_band(age_days)
        star_band = get_star_band(stars)

        # Velocity: stars_delta_24h normalized to daily
        velocity = float(delta_24h)

        key = (repo_topic, age_band, star_band)
        if key not in bucket_data:
            bucket_data[key] = []
        bucket_data[key].append((full_name, velocity))

    # Compute percentiles within each bucket
    rows_inserted = 0
    for (t, ab, sb), repos in bucket_data.items():
        # Sort by velocity descending
        repos.sort(key=lambda x: x[1], reverse=True)
        peer_count = len(repos)

        for rank, (full_name, velocity) in enumerate(repos):
            # Percentile = percentage of repos in this bucket with lower velocity
            if peer_count <= 1:
                percentile = 50.0
            else:
                percentile = round((peer_count - rank - 1) / (peer_count - 1) * 100, 2)

            try:
                conn.execute(
                    """INSERT INTO snapshot_percentiles
                       (repo_full_name, snapshot_date, topic, age_band, star_band,
                        star_velocity_percentile, bucket_peer_count, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (full_name, snapshot_date, t, ab, sb,
                     percentile, peer_count, created_at),
                )
                rows_inserted += 1
            except sqlite3.IntegrityError:
                # Duplicate key — skip
                pass

    conn.commit()
    return {
        "rows_inserted": rows_inserted,
        "snapshot_date": snapshot_date,
        "buckets": len(bucket_data),
    }


def query_percentiles(
    conn: sqlite3.Connection,
    *,
    topic: str | None = None,
    age_band: str | None = None,
    snapshot_date: str | None = None,
) -> list[dict[str, Any]]:
    """Query percentile values by (topic, age_band).

    If topic is empty/None, returns global percentiles as fallback.

    Parameters
    ----------
    conn : sqlite3.Connection
    topic : str, optional
    age_band : str, optional
    snapshot_date : str, optional
        Defaults to latest date in table.

    Returns
    -------
    list[dict] with repo_full_name, topic, age_band, star_band,
               star_velocity_percentile, bucket_peer_count.
    """
    if snapshot_date is None:
        row = conn.execute(
            "SELECT MAX(snapshot_date) FROM snapshot_percentiles"
        ).fetchone()
        snapshot_date = row[0] if row and row[0] else None

    if snapshot_date is None:
        return []

    conditions = ["snapshot_date = ?"]
    params: list[Any] = [snapshot_date]

    if topic:
        conditions.append("topic = ?")
        params.append(topic)
    # If topic is None/empty, we return all (global fallback)

    if age_band:
        conditions.append("age_band = ?")
        params.append(age_band)

    rows = conn.execute(
        f"""SELECT repo_full_name, topic, age_band, star_band,
                   star_velocity_percentile, bucket_peer_count
            FROM snapshot_percentiles
            WHERE {' AND '.join(conditions)}
            ORDER BY star_velocity_percentile DESC""",
        params,
    ).fetchall()

    return [
        {
            "repo_full_name": r[0],
            "topic": r[1],
            "age_band": r[2],
            "star_band": r[3],
            "star_velocity_percentile": r[4],
            "bucket_peer_count": r[5],
        }
        for r in rows
    ]


def get_global_percentiles(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str | None = None,
) -> list[dict[str, Any]]:
    """Get global percentiles (all topics combined) as fallback.

    Queries with topic='untagged' or aggregates across all topics.
    """
    if snapshot_date is None:
        row = conn.execute(
            "SELECT MAX(snapshot_date) FROM snapshot_percentiles"
        ).fetchone()
        snapshot_date = row[0] if row and row[0] else None

    if snapshot_date is None:
        return []

    rows = conn.execute(
        """SELECT repo_full_name, topic, age_band, star_band,
                  star_velocity_percentile, bucket_peer_count
           FROM snapshot_percentiles
           WHERE snapshot_date = ?
           ORDER BY star_velocity_percentile DESC""",
        (snapshot_date,),
    ).fetchall()

    return [
        {
            "repo_full_name": r[0],
            "topic": r[1],
            "age_band": r[2],
            "star_band": r[3],
            "star_velocity_percentile": r[4],
            "bucket_peer_count": r[5],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_repo_table(conn: sqlite3.Connection) -> str | None:
    """Find the repo master table in the database."""
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    for candidate in ("github_repo_master", "repo_master", "repos"):
        if candidate in tables:
            return candidate
    return None


def _get_repo_topic(conn: sqlite3.Connection, table: str, full_name: str) -> str:
    """Get topic for a repo from the repo master table."""
    try:
        row = conn.execute(
            f"SELECT topic FROM {table} WHERE full_name = ? LIMIT 1",
            (full_name,),
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except sqlite3.OperationalError:
        pass

    # Try topic_tags or tags column
    for col in ("topic_tags", "tags", "category"):
        try:
            row = conn.execute(
                f"SELECT {col} FROM {table} WHERE full_name = ? LIMIT 1",
                (full_name,),
            ).fetchone()
            if row and row[0]:
                # Could be JSON array or comma-separated
                val = str(row[0])
                if val.startswith("["):
                    import json
                    tags = json.loads(val)
                    if tags:
                        return tags[0]
                return val.split(",")[0].strip()
        except (sqlite3.OperationalError, json.JSONDecodeError):
            continue

    return "untagged"


def _get_repo_age_days(conn: sqlite3.Connection, full_name: str) -> int:
    """Estimate repo age in days from first snapshot date."""
    row = conn.execute(
        """SELECT MIN(snapshot_at) FROM github_star_snapshots
           WHERE full_name = ?""",
        (full_name,),
    ).fetchone()

    if row and row[0]:
        try:
            first_seen = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - first_seen
            return max(0, age.days)
        except (ValueError, AttributeError):
            pass

    return 365  # default to old
