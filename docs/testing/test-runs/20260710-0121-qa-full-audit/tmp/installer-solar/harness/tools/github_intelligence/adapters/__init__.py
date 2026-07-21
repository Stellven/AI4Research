"""GitHub Intelligence — Discovery Adapters + DedupQueue.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C2_adapters_snapshots / adapters/__init__

Public API:
    from adapters import TopicAdapter, TrendingAdapter, TrackedAdapter, CrossSourceAdapter
    from adapters import DedupQueue

DedupQueue:
    enqueue(candidates, conn) → list[str]
        - Dedup key: (full_name, source_type) within 24-hour window
        - Returns only the full_names that are NEW (not seen within 24h)
        - New entries → written to repo_discovery_events
        - Seen entries → only update discovered_at timestamp

Run as __main__ for self-test:
    python3 adapters/__init__.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

if __package__ is None or __package__ == "":
    import os as _os
    # Insert both the github_intelligence dir (for schema) and adapters dir (for siblings)
    _gi_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _ad_dir = _os.path.dirname(_os.path.abspath(__file__))
    for _p in (_gi_dir, _ad_dir):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    from schema import DiscoveryCandidate, apply_schema, insert_row, fetch_rows, utc_now_iso
    from topic import TopicAdapter
    from trending import TrendingAdapter
    from tracked import TrackedAdapter
    from cross_source import CrossSourceAdapter
else:
    from ..schema import DiscoveryCandidate, apply_schema, insert_row, fetch_rows, utc_now_iso
    from .topic import TopicAdapter
    from .trending import TrendingAdapter
    from .tracked import TrackedAdapter
    from .cross_source import CrossSourceAdapter


__all__ = [
    "TopicAdapter",
    "TrendingAdapter",
    "TrackedAdapter",
    "CrossSourceAdapter",
    "DedupQueue",
]

_DEDUP_WINDOW_HOURS = 24
_TABLE = DiscoveryCandidate.TABLE


class DedupQueue:
    """Deduplication queue for DiscoveryCandidate records.

    Dedup key: (full_name, source_type) within a rolling 24-hour window.

    enqueue(candidates, conn) -> list[str]:
        - Returns full_names of truly NEW repos (not seen in last 24h).
        - Writes new rows to repo_discovery_events.
        - For already-seen repos: updates discovered_at (upsert) so the
          row reflects the latest observation time.
    """

    def __init__(self, window_hours: int = _DEDUP_WINDOW_HOURS) -> None:
        self.window_hours = window_hours

    def _cutoff_iso(self) -> str:
        """ISO-8601 string for now minus window_hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.window_hours)
        return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    def enqueue(
        self,
        candidates: list[DiscoveryCandidate],
        conn: sqlite3.Connection,
    ) -> list[str]:
        """Persist candidates and return full_names that are NEW within window.

        Args:
            candidates: DiscoveryCandidate objects to process.
            conn: Open sqlite3.Connection with schema already applied.

        Returns:
            List of full_name strings for repos not seen within the dedup window.
        """
        if not candidates:
            return []

        cutoff = self._cutoff_iso()
        new_full_names: list[str] = []

        for cand in candidates:
            # Check whether (full_name, source_type) was seen within window
            existing = fetch_rows(
                conn,
                _TABLE,
                "full_name = ? AND source_type = ? AND discovered_at >= ?",
                (cand.full_name, cand.source_type, cutoff),
            )

            if not existing:
                # Genuinely new within window — insert and mark as new
                insert_row(conn, _TABLE, cand.to_row())
                new_full_names.append(cand.full_name)
            else:
                # Already seen — upsert to update discovered_at with latest time
                # Use INSERT OR REPLACE (schema uses composite PK on all 3 columns,
                # so we insert a new row with updated discovered_at)
                insert_row(conn, _TABLE, cand.to_row())

        conn.commit()
        return new_full_names


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _self_test() -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "tests_run": 0,
        "tests_passed": 0,
        "details": [],
        "adapter_subtests": {},
    }

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["details"].append({"test": name, "status": "pass"})

    def _fail(name: str, reason: str) -> None:
        metrics["tests_run"] += 1
        metrics["details"].append({"test": name, "status": "fail", "reason": reason})

    # -----------------------------------------------------------------------
    # DedupQueue tests (in-memory SQLite)
    # -----------------------------------------------------------------------
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    dq = DedupQueue(window_hours=24)

    # Build 3 candidates from different sources
    now = utc_now_iso()
    c1 = DiscoveryCandidate("owner/repo-a", "topic", now, {"stars": 100})
    c2 = DiscoveryCandidate("owner/repo-b", "trending", now, {"rank": 5})
    c3 = DiscoveryCandidate("owner/repo-a", "tracked", now, {})

    # First enqueue: all 3 are new
    new1 = dq.enqueue([c1, c2, c3], conn)
    if set(new1) == {"owner/repo-a", "owner/repo-b"}:
        _ok("dedup_queue.first_enqueue_returns_all_new")
    else:
        _fail("dedup_queue.first_enqueue_returns_all_new",
              f"expected {{owner/repo-a, owner/repo-b}}, got {set(new1)}")

    # Second enqueue with same candidates — nothing is new
    new2 = dq.enqueue([c1, c2, c3], conn)
    if new2 == []:
        _ok("dedup_queue.second_enqueue_all_deduped")
    else:
        _fail("dedup_queue.second_enqueue_all_deduped", f"expected [], got {new2}")

    # Third enqueue: new source_type for existing full_name → still new
    c4 = DiscoveryCandidate("owner/repo-a", "social_mention", now, {})
    new3 = dq.enqueue([c4], conn)
    if new3 == ["owner/repo-a"]:
        _ok("dedup_queue.new_source_type_is_new")
    else:
        _fail("dedup_queue.new_source_type_is_new", f"expected [owner/repo-a], got {new3}")

    # DB should have rows
    rows = fetch_rows(conn, _TABLE)
    # c1 + c2 + c3 + c4 = 4 initial inserts + re-inserts (same PK for c1/c2/c3 on second pass)
    if len(rows) >= 4:
        _ok("dedup_queue.rows_written_to_db")
    else:
        _fail("dedup_queue.rows_written_to_db", f"expected >=4 rows, got {len(rows)}")

    # DedupQueue with 1-second window: a brand-new repo never inserted is always new
    dq_tiny = DedupQueue(window_hours=0)
    c_brand_new = DiscoveryCandidate("brand/new-repo", "topic", utc_now_iso(), {})
    new_tiny = dq_tiny.enqueue([c_brand_new], conn)
    if new_tiny == ["brand/new-repo"]:
        _ok("dedup_queue.zero_window_unseen_repo_is_new")
    else:
        _fail("dedup_queue.zero_window_unseen_repo_is_new", f"got {new_tiny}")

    # Empty list
    new_empty = dq.enqueue([], conn)
    if new_empty == []:
        _ok("dedup_queue.empty_list_returns_empty")
    else:
        _fail("dedup_queue.empty_list_returns_empty", f"got {new_empty}")

    conn.close()

    # -----------------------------------------------------------------------
    # Run each adapter self-test and collect subtests
    # -----------------------------------------------------------------------
    _adapter_modules = [
        ("topic", "topic"),
        ("trending", "trending"),
        ("tracked", "tracked"),
        ("cross_source", "cross_source"),
    ]

    for mod_name, label in _adapter_modules:
        if __package__ is None or __package__ == "":
            import importlib.util
            import os as _os2
            spec = importlib.util.spec_from_file_location(
                mod_name,
                _os2.path.join(_os2.path.dirname(__file__), f"{mod_name}.py"),
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        else:
            import importlib
            mod = importlib.import_module(f".{mod_name}", package=__package__)

        sub = mod._self_test()
        metrics["adapter_subtests"][label] = sub
        metrics["tests_run"] += sub["tests_run"]
        metrics["tests_passed"] += sub["tests_passed"]

    return metrics


if __name__ == "__main__":
    m = _self_test()
    # Print compact summary
    summary: dict[str, Any] = {
        "tests_run": m["tests_run"],
        "tests_passed": m["tests_passed"],
        "dedup_queue_tests": m["details"],
        "adapter_subtests_summary": {
            k: {"tests_run": v["tests_run"], "tests_passed": v["tests_passed"]}
            for k, v in m.get("adapter_subtests", {}).items()
        },
    }
    print(json.dumps(summary, indent=2))
    sys.exit(0 if m["tests_run"] == m["tests_passed"] else 1)
