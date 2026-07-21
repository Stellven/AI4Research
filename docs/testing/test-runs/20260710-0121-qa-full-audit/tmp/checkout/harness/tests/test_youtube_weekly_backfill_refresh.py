from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import youtube_weekly_backfill as ywb


def test_parse_refresh_before_date_today():
    today = dt.date.today()
    assert ywb.parse_refresh_before_date("today") == today


def test_status_collected_date_prefers_completed_at(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"status": "ok", "completed_at": "2026-05-29T10:00:00Z"}), encoding="utf-8")
    assert ywb.status_collected_date(path) == dt.date(2026, 5, 29)
