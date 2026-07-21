"""CLI facade for the YouTube transcript runtime modules."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from youtube.acquisition_ladder import decide_ladder_path
from youtube.job_scheduler import dequeue_ready_jobs
from youtube.pollution_repair import audit_pollution, repair_pollution, verify_repair
from youtube.subtitle_discovery import SubtitleTrack
from youtube.dashboard import aggregate
from youtube.html_render import render_dashboard_html
from youtube.tui_render import print_transcript_status_tui, render_transcript_status_tui


def _open_db(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path)


def _print(payload: dict, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def _no_data_payload(db: str, exc: Exception) -> dict:
    return {
        "ok": False,
        "status": "no data yet",
        "db": db,
        "error": str(exc),
    }


def _aggregate_or_no_data(db: str) -> tuple[dict, int]:
    try:
        conn = _open_db(db)
        try:
            return aggregate(conn), 0
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        return _no_data_payload(db, exc), 1


def cmd_discover(args: argparse.Namespace) -> int:
    tracks = [
        SubtitleTrack(
            video_id=args.video_id,
            source_backend="yt_dlp",
            language="en",
            language_name="English",
            track_kind="standard",
            format="vtt",
            is_auto_generated=False,
            is_translatable=True,
            confidence=1.0,
        )
    ]
    _print({"video_id": args.video_id, "tracks": [track.__dict__ for track in tracks]}, args.json)
    return 0


def cmd_acquire(args: argparse.Namespace) -> int:
    tracks = [] if args.no_tracks else [
        SubtitleTrack(
            video_id=args.video_id,
            source_backend="yt_dlp",
            language="en",
            language_name="English",
            track_kind="standard",
            format="vtt",
            is_auto_generated=False,
            is_translatable=True,
            confidence=1.0,
        )
    ]
    result = decide_ladder_path(args.video_id, tracks, priority=args.priority)
    _print({"video_id": args.video_id, "resolved_level": result.resolved_level, "asr_route_needed": result.asr_route_needed}, args.json)
    return 0


def cmd_process_jobs(args: argparse.Namespace) -> int:
    conn = _open_db(args.db)
    try:
        jobs = dequeue_ready_jobs(conn, priority_filter=args.priority.split(",") if args.priority else None, limit=args.limit)
        payload = {
            "dry_run": bool(args.dry_run),
            "job_count": len(jobs),
            "jobs": [job.__dict__ for job in jobs],
        }
        _print(payload, args.json)
        return 0
    finally:
        conn.close()


def cmd_audit_quality(args: argparse.Namespace) -> int:
    conn = _open_db(args.db)
    try:
        if args.apply:
            result = repair_pollution(conn, dry_run=False)
            payload = {"total_repaired": result.total_repaired, "repair_actions": result.repair_actions, "remaining_pollution": verify_repair(conn)}
        else:
            report = audit_pollution(conn, dry_run=True)
            payload = {"polluted_count": report.polluted_count, "sample_ids": report.sample_ids, "pollution_types": report.pollution_types}
        _print(payload, args.json)
        return 0
    finally:
        conn.close()


def cmd_transcript_status(args: argparse.Namespace) -> int:
    payload, rc = _aggregate_or_no_data(args.db)
    _print(payload, args.json)
    return rc


def cmd_render_dashboard_html(args: argparse.Namespace) -> int:
    payload, rc = _aggregate_or_no_data(args.db)
    if rc != 0:
        _print(payload, args.json)
        return rc
    html = render_dashboard_html(payload)
    if args.output:
        Path(args.output).write_text(html, encoding="utf-8")
        _print({"ok": True, "output": args.output}, args.json)
    else:
        print(html)
    return 0


def cmd_render_dashboard_tui(args: argparse.Namespace) -> int:
    payload, rc = _aggregate_or_no_data(args.db)
    if rc != 0:
        _print(payload, args.json)
        return rc
    if args.json:
        _print({"ok": True, "text": render_transcript_status_tui(payload)}, True)
    else:
        print_transcript_status_tui(payload)
    return 0


def cmd_ab_test_asr(args: argparse.Namespace) -> int:
    payload = {
        "video_id": args.video_id,
        "candidate_backends": ["faster_whisper_large_v3", "premium"],
        "status": "planned",
    }
    _print(payload, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="youtube-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("discover-transcript-tracks")
    p.add_argument("--video-id", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("acquire-transcripts")
    p.add_argument("--video-id", required=True)
    p.add_argument("--priority", default="P1")
    p.add_argument("--no-tracks", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_acquire)

    p = sub.add_parser("process-transcript-jobs")
    p.add_argument("--db", required=True)
    p.add_argument("--priority", default="P0,P1,P2")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_process_jobs)

    p = sub.add_parser("audit-transcript-quality")
    p.add_argument("--db", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit_quality)

    p = sub.add_parser("transcript-status")
    p.add_argument("--db", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_transcript_status)

    p = sub.add_parser("render-dashboard-html")
    p.add_argument("--db", required=True)
    p.add_argument("--output")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_render_dashboard_html)

    p = sub.add_parser("render-dashboard-tui")
    p.add_argument("--db", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_render_dashboard_tui)

    p = sub.add_parser("transcript-ab-test-asr")
    p.add_argument("--video-id", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ab_test_asr)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
