import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "migrations"))

from youtube.cli import main
from youtube_005_transcript_jobs import up as m005


def test_cli_process_jobs_dry_run(tmp_path, capsys):
    db = tmp_path / "yt.db"
    conn = sqlite3.connect(db)
    m005(conn)
    conn.execute("""INSERT INTO youtube_transcript_jobs
        (job_id, video_id, job_type, priority, status)
        VALUES ('j1', 'v1', 'asr', 'P0', 'pending')""")
    conn.commit()
    conn.close()
    rc = main(["process-transcript-jobs", "--db", str(db), "--dry-run", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"job_count": 1' in out


def test_cli_legacy_acquire_no_tracks(capsys):
    rc = main(["acquire-transcripts", "--video-id", "v1", "--priority", "P1", "--no-tracks", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"browser_capture_needed": true' in out.lower()
