"""SnapshotCollector — fetch and persist HF paper snapshots per window type.

Per interfaces.md §1: daily/weekly/monthly snapshot collection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol

from schema import PaperSnapshot, WindowType, _gen_id, _utc_now


class StoreProto(Protocol):
    def upsert(self, entity: object) -> None: ...


class SourceProto(Protocol):
    def fetch_papers(self, window_type: str, window_start: str, window_end: str) -> list[dict]: ...


def _window_bounds(window_type: WindowType, observed_at: Optional[str] = None,
                   window_start: Optional[str] = None, window_end: Optional[str] = None) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    if window_type == WindowType.daily:
        day = observed_at or _utc_now()[:10]
        return f"{day}T00:00:00Z", f"{day}T23:59:59Z"
    elif window_type == WindowType.weekly:
        if window_start and window_end:
            return window_start, window_end
        week_start = (now - __import__("datetime").timedelta(days=now.weekday())).strftime("%Y-%m-%dT00:00:00Z")
        week_end = (now + __import__("datetime").timedelta(days=6 - now.weekday())).strftime("%Y-%m-%dT23:59:59Z")
        return week_start, week_end
    else:
        if window_start and window_end:
            return window_start, window_end
        month_start = now.strftime("%Y-%m-01T00:00:00Z")
        if now.month == 12:
            month_end = f"{now.year + 1}-01-01T00:00:00Z"
        else:
            month_end = f"{now.year}-{now.month + 1:02d}-01T00:00:00Z"
        return month_start, month_end


class SnapshotCollector:
    def __init__(self, source: SourceProto) -> None:
        self._source = source

    def fetch_daily_snapshot(self, *, observed_at: Optional[str] = None) -> list[PaperSnapshot]:
        ws, we = _window_bounds(WindowType.daily, observed_at=observed_at)
        raw = self._source.fetch_papers("daily", ws, we)
        return self._to_snapshots(raw, WindowType.daily, ws, we)

    def fetch_weekly_snapshot(self, *, window_start: str, window_end: str) -> list[PaperSnapshot]:
        ws, we = _window_bounds(WindowType.weekly, window_start=window_start, window_end=window_end)
        raw = self._source.fetch_papers("weekly", ws, we)
        return self._to_snapshots(raw, WindowType.weekly, ws, we)

    def fetch_monthly_snapshot(self, *, window_start: str, window_end: str) -> list[PaperSnapshot]:
        ws, we = _window_bounds(WindowType.monthly, window_start=window_start, window_end=window_end)
        raw = self._source.fetch_papers("monthly", ws, we)
        return self._to_snapshots(raw, WindowType.monthly, ws, we)

    def persist_snapshot_batch(self, snapshots: list[PaperSnapshot], store: StoreProto) -> int:
        count = 0
        for snap in snapshots:
            store.upsert(snap)
            count += 1
        return count

    def _to_snapshots(self, raw_list: list[dict], wt: WindowType, ws: str, we: str) -> list[PaperSnapshot]:
        snapshots = []
        for i, item in enumerate(raw_list):
            snapshots.append(PaperSnapshot(
                snapshot_id=_gen_id("snap-"),
                window_type=wt,
                window_start=ws,
                window_end=we,
                source=item.get("source", "huggingface_papers"),
                paper_id=item.get("paper_id", item.get("id", "")),
                rank=item.get("rank", i + 1),
                upvotes=item.get("upvotes", 0),
                hf_url=item.get("hf_url", f"https://huggingface.co/papers/{item.get('paper_id', item.get('id', ''))}"),
                observed_at=_utc_now(),
                first_seen_in_window=item.get("first_seen_in_window", 1),
            ))
        return snapshots
