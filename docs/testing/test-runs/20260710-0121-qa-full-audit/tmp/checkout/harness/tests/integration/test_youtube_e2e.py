import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "migrations"))

from tech_hotspot_radar._youtube_cli_wrapper import legacy_process_transcripts
from youtube.dashboard import aggregate
from youtube_001_subtitle_tracks import up as m001
from youtube_002_transcripts import up as m002
from youtube_004_asr_runs import up as m004
from youtube_005_transcript_jobs import up as m005
from youtube_010_premium_asr_calls import up as m010


def test_legacy_wrapper_and_dashboard_end_to_end(tmp_path):
    db = tmp_path / "youtube_e2e.db"
    conn = sqlite3.connect(db)
    for migration in (m001, m002, m004, m005, m010):
        migration(conn)
    conn.execute("""INSERT INTO youtube_transcript_jobs
        (job_id, video_id, job_type, priority, status)
        VALUES ('job-e2e', 'vid-e2e', 'asr', 'P0', 'pending')""")
    conn.execute("""INSERT INTO youtube_transcripts
        (transcript_id, video_id, source, quality_score, quality_tier)
        VALUES ('t-e2e', 'vid-e2e', 'premium', 0.88, 'T0')""")
    conn.execute("""INSERT INTO youtube_premium_asr_calls
        (call_id, transcript_id, provider, model, cost_usd, budget_day, status)
        VALUES ('call-e2e', 't-e2e', 'openai', 'gpt-4o-transcribe', 0.6, '2026-05-28', 'completed')""")
    conn.commit()
    conn.close()

    assert legacy_process_transcripts(str(db), dry_run=True) == 0

    conn = sqlite3.connect(db)
    payload = aggregate(conn)
    conn.close()
    assert payload["pending_by_priority"]["P0"] == 1
    assert payload["premium_cost_today"] == 0.6
