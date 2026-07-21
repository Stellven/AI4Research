import sqlite3
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.dashboard import aggregate
from youtube_001_subtitle_tracks import up as m001
from youtube_002_transcripts import up as m002
from youtube_004_asr_runs import up as m004
from youtube_005_transcript_jobs import up as m005
from youtube_010_premium_asr_calls import up as m010


def test_dashboard_aggregate():
    conn = sqlite3.connect(":memory:")
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    m001(conn)
    m002(conn)
    m004(conn)
    m005(conn)
    m010(conn)
    conn.execute("""INSERT INTO youtube_subtitle_tracks
        (track_id, video_id, source_backend, language, track_kind, discovered_at)
        VALUES ('trk1', 'v1', 'yt_dlp', 'en', 'standard', '2026-05-28T00:00:00Z')""")
    conn.execute("""INSERT INTO youtube_transcripts
        (transcript_id, video_id, source, quality_score, quality_tier)
        VALUES ('t1', 'v1', 'premium', 0.9, 'T0')""")
    conn.execute("""INSERT INTO youtube_asr_runs
        (asr_run_id, video_id, backend, model, quality_score)
        VALUES ('r1', 'v1', 'premium', 'gpt-4o-transcribe', 0.9)""")
    conn.execute("""INSERT INTO youtube_transcript_jobs
        (job_id, video_id, job_type, priority, status)
        VALUES ('j1', 'v1', 'asr', 'P0', 'pending')""")
    conn.execute("""INSERT INTO youtube_premium_asr_calls
        (call_id, transcript_id, provider, model, cost_usd, budget_day, status)
        VALUES ('c1', 't1', 'openai', 'gpt-4o-transcribe', 1.2, ?, 'completed')""", (today,))
    conn.commit()
    payload = aggregate(conn)
    assert payload["subtitle_tracks_count"] == 1
    assert payload["accepted_by_source_tier_breakdown"]["T0"] == 1
    assert payload["premium_cost_today"] == 1.2
