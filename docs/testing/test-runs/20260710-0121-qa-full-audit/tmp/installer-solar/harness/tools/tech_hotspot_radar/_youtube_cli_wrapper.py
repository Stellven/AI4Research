"""Legacy wrapper for `process-transcripts` command."""
from __future__ import annotations

from youtube.cli import main as youtube_cli_main


def legacy_process_transcripts(db_path: str, *, dry_run: bool = False) -> int:
    argv = [
        "process-transcript-jobs",
        "--db",
        db_path,
        "--priority",
        "P0,P1,P2",
    ]
    if dry_run:
        argv.append("--dry-run")
    return youtube_cli_main(argv)
