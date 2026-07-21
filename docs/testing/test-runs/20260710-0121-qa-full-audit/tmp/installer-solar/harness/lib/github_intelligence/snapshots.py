"""Snapshot & Delta engine for GitHub repo metrics.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C2_adapters_snapshots / snapshots

Public API:
    take_snapshot(full_name, stars, ..., conn) -> RepoSnapshot
        Create and persist a RepoSnapshot row. Calls compute_deltas automatically.

    compute_deltas(full_name, snapshot_at, conn) -> dict
        Look up historical snapshots and fill delta fields.
        Updates the DB row in-place.
        Returns the delta dict (only populated fields).

Delta strategy (S02 §A2):
    stars_delta_Xh  — nearest historical snapshot within [snapshot_at - X hours ± 30 min]
    star_acceleration — stars_delta_24h / max(avg_delta_24h_last_7d, 1)
    history_status  — 'sufficient' | 'insufficient_history'
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# Allow standalone execution
if __name__ == "__main__" or __package__ is None or __package__ == "":
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from schema import RepoSnapshot, apply_schema, insert_row, fetch_rows, utc_now_iso
else:
    from .schema import RepoSnapshot, apply_schema, insert_row, fetch_rows, utc_now_iso


_TABLE = RepoSnapshot.TABLE

# Delta windows in hours
_DELTA_WINDOWS: tuple[int, ...] = (1, 6, 24, 168, 720)  # 1h, 6h, 24h, 7d, 30d
_WINDOW_FIELD: dict[int, str] = {
    1: "stars_delta_1h",
    6: "stars_delta_6h",
    24: "stars_delta_24h",
    168: "stars_delta_7d",
    720: "stars_delta_30d",
}

# Tolerance window: ±30 minutes around target historical time
_TOLERANCE_MINUTES = 30


def _parse_iso(ts: str) -> datetime:
    """Parse ISO-8601 UTC string to timezone-aware datetime."""
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: datetime) -> str:
    """Format timezone-aware datetime as ISO-8601 UTC string."""
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_nearest_snapshot(
    full_name: str,
    target_dt: datetime,
    tolerance_minutes: int,
    conn: sqlite3.Connection,
) -> dict[str, Any] | None:
    """Find the nearest snapshot within ±tolerance_minutes of target_dt.

    Returns the row dict or None.
    """
    low = _iso(target_dt - timedelta(minutes=tolerance_minutes))
    high = _iso(target_dt + timedelta(minutes=tolerance_minutes))

    rows = fetch_rows(
        conn,
        _TABLE,
        "full_name = ? AND snapshot_at >= ? AND snapshot_at <= ? AND stars IS NOT NULL",
        (full_name, low, high),
    )
    if not rows:
        return None

    # Return the one closest to target_dt
    def _dist(r: dict[str, Any]) -> float:
        try:
            return abs((_parse_iso(r["snapshot_at"]) - target_dt).total_seconds())
        except Exception:
            return float("inf")

    rows.sort(key=_dist)
    return rows[0]


def compute_deltas(
    full_name: str,
    snapshot_at: str,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Compute delta fields for a snapshot and update the DB row.

    Args:
        full_name: Repo full name (owner/repo).
        snapshot_at: ISO-8601 timestamp of the snapshot to update.
        conn: Open sqlite3 connection.

    Returns:
        Dict of populated delta fields (keys with None are omitted).
    """
    snap_dt = _parse_iso(snapshot_at)

    # Fetch current snapshot to get current stars
    current_rows = fetch_rows(
        conn,
        _TABLE,
        "full_name = ? AND snapshot_at = ?",
        (full_name, snapshot_at),
    )
    if not current_rows:
        return {}

    current = current_rows[0]
    current_stars = current.get("stars")
    if current_stars is None:
        return {"history_status": "insufficient_history"}

    deltas: dict[str, Any] = {}
    any_delta_found = False

    for hours in _DELTA_WINDOWS:
        target_dt = snap_dt - timedelta(hours=hours)
        field = _WINDOW_FIELD[hours]

        hist = _find_nearest_snapshot(full_name, target_dt, _TOLERANCE_MINUTES, conn)
        if hist is not None and hist.get("stars") is not None:
            deltas[field] = current_stars - hist["stars"]
            any_delta_found = True
        else:
            deltas[field] = None

    # star_acceleration: stars_delta_24h / max(avg_delta_24h_last_7d, 1)
    delta_24h = deltas.get("stars_delta_24h")
    delta_7d = deltas.get("stars_delta_7d")
    star_acceleration: float | None = None

    if delta_24h is not None and delta_7d is not None:
        avg_delta_24h_last_7d = delta_7d / 7.0  # average daily delta over 7 days
        star_acceleration = round(delta_24h / max(avg_delta_24h_last_7d, 1.0), 4)

    deltas["star_acceleration"] = star_acceleration
    deltas["history_status"] = "sufficient" if any_delta_found else "insufficient_history"

    # Update the DB row in-place via INSERT OR REPLACE with merged fields
    merged = dict(current)
    merged.update({k: v for k, v in deltas.items() if v is not None})
    # Always set history_status
    merged["history_status"] = deltas["history_status"]
    if star_acceleration is not None:
        merged["star_acceleration"] = star_acceleration

    insert_row(conn, _TABLE, merged)
    conn.commit()

    return {k: v for k, v in deltas.items() if v is not None}


def take_snapshot(
    full_name: str,
    stars: int | None = None,
    forks: int | None = None,
    watchers: int | None = None,
    open_issues: int | None = None,
    commit_count_7d: int | None = None,
    active_contributors_30d: int | None = None,
    latest_release_tag: str | None = None,
    latest_release_at: str | None = None,
    pushed_at: str | None = None,
    conn: sqlite3.Connection | None = None,
    snapshot_at: str | None = None,
) -> RepoSnapshot:
    """Create and persist a RepoSnapshot, then compute deltas.

    Args:
        full_name: Repo full name (owner/repo).
        stars, forks, ... : Current metric values.
        conn: Optional sqlite3 connection. If None, creates in-memory DB (test use).
        snapshot_at: Override timestamp (ISO-8601 UTC). Defaults to utc_now_iso().

    Returns:
        Persisted RepoSnapshot with delta fields populated.
    """
    _manage_conn = conn is None
    if _manage_conn:
        conn = sqlite3.connect(":memory:")
        apply_schema(conn)

    assert conn is not None

    ts = snapshot_at or utc_now_iso()
    snap_id = RepoSnapshot.make_id(full_name, ts)

    snap = RepoSnapshot(
        snapshot_id=snap_id,
        full_name=full_name,
        snapshot_at=ts,
        stars=stars,
        forks=forks,
        watchers=watchers,
        open_issues=open_issues,
        commit_count_7d=commit_count_7d,
        active_contributors_30d=active_contributors_30d,
        latest_release_tag=latest_release_tag,
        latest_release_at=latest_release_at,
        pushed_at=pushed_at,
        history_status="insufficient_history",
    )

    insert_row(conn, _TABLE, snap.to_row())
    conn.commit()

    # Compute deltas (updates DB in-place)
    deltas = compute_deltas(full_name, ts, conn)

    # Reload from DB to get the updated delta fields
    rows = fetch_rows(conn, _TABLE, "snapshot_id = ?", (snap_id,))
    if rows:
        snap = RepoSnapshot.from_row(rows[0])

    return snap


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _build_history(
    conn: sqlite3.Connection,
    full_name: str,
    base_time: datetime,
    star_series: list[tuple[int, int]],  # (offset_hours_back, stars)
) -> None:
    """Insert historical snapshots for testing.

    star_series: list of (hours_before_base, stars_count)
    """
    for hours_back, stars in star_series:
        ts_dt = base_time - timedelta(hours=hours_back)
        ts = _iso(ts_dt)
        snap_id = RepoSnapshot.make_id(full_name, ts)
        snap = RepoSnapshot(
            snapshot_id=snap_id,
            full_name=full_name,
            snapshot_at=ts,
            stars=stars,
        )
        insert_row(conn, _TABLE, snap.to_row())
    conn.commit()


def _self_test() -> dict[str, Any]:
    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "details": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["details"].append({"test": name, "status": "pass"})

    def _fail(name: str, reason: str) -> None:
        metrics["tests_run"] += 1
        metrics["details"].append({"test": name, "status": "fail", "reason": reason})

    # -----------------------------------------------------------------------
    # Test 1: take_snapshot with no history → insufficient_history
    # -----------------------------------------------------------------------
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)

    snap1 = take_snapshot("owner/repo", stars=1000, forks=50, conn=conn)
    if snap1.history_status == "insufficient_history":
        _ok("snapshots.no_history_status")
    else:
        _fail("snapshots.no_history_status", f"got {snap1.history_status}")

    if snap1.stars_delta_1h is None and snap1.stars_delta_24h is None:
        _ok("snapshots.no_history_deltas_null")
    else:
        _fail("snapshots.no_history_deltas_null",
              f"1h={snap1.stars_delta_1h}, 24h={snap1.stars_delta_24h}")

    # -----------------------------------------------------------------------
    # Test 2: 1h delta — inject snapshot exactly 1h ago
    # -----------------------------------------------------------------------
    base_time = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)
    base_ts = _iso(base_time)

    _build_history(conn, "delta/repo", base_time, [
        (1, 900),    # 1h ago: 900 stars
        (6, 800),    # 6h ago: 800 stars
        (24, 600),   # 24h ago: 600 stars
        (168, 200),  # 7d ago: 200 stars
        (720, 0),    # 30d ago: 0 stars
    ])

    snap2 = take_snapshot("delta/repo", stars=1000, conn=conn, snapshot_at=base_ts)

    if snap2.stars_delta_1h == 100:
        _ok("snapshots.delta_1h_correct")
    else:
        _fail("snapshots.delta_1h_correct", f"got {snap2.stars_delta_1h}, expected 100")

    if snap2.stars_delta_6h == 200:
        _ok("snapshots.delta_6h_correct")
    else:
        _fail("snapshots.delta_6h_correct", f"got {snap2.stars_delta_6h}, expected 200")

    if snap2.stars_delta_24h == 400:
        _ok("snapshots.delta_24h_correct")
    else:
        _fail("snapshots.delta_24h_correct", f"got {snap2.stars_delta_24h}, expected 400")

    if snap2.stars_delta_7d == 800:
        _ok("snapshots.delta_7d_correct")
    else:
        _fail("snapshots.delta_7d_correct", f"got {snap2.stars_delta_7d}, expected 800")

    if snap2.stars_delta_30d == 1000:
        _ok("snapshots.delta_30d_correct")
    else:
        _fail("snapshots.delta_30d_correct", f"got {snap2.stars_delta_30d}, expected 1000")

    # -----------------------------------------------------------------------
    # Test 3: star_acceleration = delta_24h / avg_delta_24h_last_7d
    # delta_24h = 400, delta_7d = 800 → avg_daily = 800/7 ≈ 114.28
    # acceleration ≈ 400 / 114.28 ≈ 3.5
    # -----------------------------------------------------------------------
    if snap2.star_acceleration is not None:
        expected_acc = round(400 / (800 / 7.0), 4)
        if abs(snap2.star_acceleration - expected_acc) < 0.01:
            _ok("snapshots.star_acceleration_correct")
        else:
            _fail("snapshots.star_acceleration_correct",
                  f"got {snap2.star_acceleration}, expected ~{expected_acc}")
    else:
        _fail("snapshots.star_acceleration_correct", "star_acceleration is None")

    # -----------------------------------------------------------------------
    # Test 4: history_status == 'sufficient' when at least one delta found
    # -----------------------------------------------------------------------
    if snap2.history_status == "sufficient":
        _ok("snapshots.history_status_sufficient")
    else:
        _fail("snapshots.history_status_sufficient", f"got {snap2.history_status}")

    # -----------------------------------------------------------------------
    # Test 5: tolerance window — historical snapshot at 1h ± 25min still matches
    # -----------------------------------------------------------------------
    tol_time = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
    tol_ts = _iso(tol_time)
    # Insert historical at 1h 20min ago (within 30-min tolerance)
    hist_ts = _iso(tol_time - timedelta(hours=1, minutes=20))
    hist_snap = RepoSnapshot(
        snapshot_id=RepoSnapshot.make_id("tol/repo", hist_ts),
        full_name="tol/repo",
        snapshot_at=hist_ts,
        stars=500,
    )
    insert_row(conn, _TABLE, hist_snap.to_row())
    conn.commit()

    snap_tol = take_snapshot("tol/repo", stars=600, conn=conn, snapshot_at=tol_ts)
    if snap_tol.stars_delta_1h == 100:
        _ok("snapshots.tolerance_window_match")
    else:
        _fail("snapshots.tolerance_window_match",
              f"got stars_delta_1h={snap_tol.stars_delta_1h}, expected 100")

    # -----------------------------------------------------------------------
    # Test 6: historical snapshot just outside tolerance → no match → delta=None
    # -----------------------------------------------------------------------
    far_time = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    far_ts = _iso(far_time)
    # Insert at 1h 45min ago — outside 30-min tolerance → no 1h match
    far_hist_ts = _iso(far_time - timedelta(hours=1, minutes=45))
    far_hist = RepoSnapshot(
        snapshot_id=RepoSnapshot.make_id("far/repo", far_hist_ts),
        full_name="far/repo",
        snapshot_at=far_hist_ts,
        stars=400,
    )
    insert_row(conn, _TABLE, far_hist.to_row())
    conn.commit()

    snap_far = take_snapshot("far/repo", stars=500, conn=conn, snapshot_at=far_ts)
    if snap_far.stars_delta_1h is None:
        _ok("snapshots.outside_tolerance_no_match")
    else:
        _fail("snapshots.outside_tolerance_no_match",
              f"expected None, got {snap_far.stars_delta_1h}")

    # -----------------------------------------------------------------------
    # Test 7: compute_deltas returns populated dict
    # -----------------------------------------------------------------------
    d = compute_deltas("delta/repo", base_ts, conn)
    if "stars_delta_24h" in d and d["stars_delta_24h"] == 400:
        _ok("snapshots.compute_deltas_returns_dict")
    else:
        _fail("snapshots.compute_deltas_returns_dict", f"got {d}")

    # -----------------------------------------------------------------------
    # Test 8: compute_deltas on non-existent snapshot returns {}
    # -----------------------------------------------------------------------
    d_empty = compute_deltas("nonexistent/repo", "2026-01-01T00:00:00Z", conn)
    if d_empty == {}:
        _ok("snapshots.compute_deltas_nonexistent_returns_empty")
    else:
        _fail("snapshots.compute_deltas_nonexistent_returns_empty", f"got {d_empty}")

    # -----------------------------------------------------------------------
    # Test 9: multiple take_snapshot calls accumulate history
    # -----------------------------------------------------------------------
    for i in range(5):
        ts_i = _iso(datetime(2026, 6, 1, i, 0, 0, tzinfo=timezone.utc))
        take_snapshot("accum/repo", stars=100 * (i + 1), conn=conn, snapshot_at=ts_i)

    rows = fetch_rows(conn, _TABLE, "full_name = ?", ("accum/repo",))
    if len(rows) == 5:
        _ok("snapshots.multiple_snapshots_accumulated")
    else:
        _fail("snapshots.multiple_snapshots_accumulated", f"expected 5 rows, got {len(rows)}")

    # -----------------------------------------------------------------------
    # Test 10: take_snapshot with all optional fields
    # -----------------------------------------------------------------------
    ts_full = _iso(datetime(2026, 6, 10, 0, 0, 0, tzinfo=timezone.utc))
    snap_full = take_snapshot(
        "full/repo",
        stars=9999,
        forks=500,
        watchers=9999,
        open_issues=42,
        commit_count_7d=150,
        active_contributors_30d=30,
        latest_release_tag="v2.0.0",
        latest_release_at="2026-06-09T00:00:00Z",
        pushed_at="2026-06-09T12:00:00Z",
        conn=conn,
        snapshot_at=ts_full,
    )
    if (
        snap_full.watchers == 9999
        and snap_full.open_issues == 42
        and snap_full.commit_count_7d == 150
        and snap_full.latest_release_tag == "v2.0.0"
    ):
        _ok("snapshots.all_optional_fields_persisted")
    else:
        _fail("snapshots.all_optional_fields_persisted",
              f"watchers={snap_full.watchers}, issues={snap_full.open_issues}, "
              f"commits={snap_full.commit_count_7d}, tag={snap_full.latest_release_tag}")

    conn.close()

    # -----------------------------------------------------------------------
    # Test 11: reproducibility — same inputs always yield same deltas
    # -----------------------------------------------------------------------
    conn2 = sqlite3.connect(":memory:")
    apply_schema(conn2)
    base2 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    base2_ts = _iso(base2)
    _build_history(conn2, "repro/repo", base2, [(24, 100), (168, 0)])
    snap_r1 = take_snapshot("repro/repo", stars=200, conn=conn2, snapshot_at=base2_ts)
    d_r1 = snap_r1.stars_delta_24h

    # Same thing again on fresh connection
    conn3 = sqlite3.connect(":memory:")
    apply_schema(conn3)
    _build_history(conn3, "repro/repo", base2, [(24, 100), (168, 0)])
    snap_r2 = take_snapshot("repro/repo", stars=200, conn=conn3, snapshot_at=base2_ts)
    d_r2 = snap_r2.stars_delta_24h

    if d_r1 == d_r2 == 100:
        _ok("snapshots.reproducible_deltas")
    else:
        _fail("snapshots.reproducible_deltas", f"r1={d_r1}, r2={d_r2}")

    conn2.close()
    conn3.close()

    return metrics


if __name__ == "__main__":
    m = _self_test()
    print(json.dumps(m, indent=2))
    sys.exit(0 if m["tests_run"] == m["tests_passed"] else 1)
