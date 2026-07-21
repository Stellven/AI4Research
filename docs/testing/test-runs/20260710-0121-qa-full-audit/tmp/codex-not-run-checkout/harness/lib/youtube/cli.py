"""CLI facade for the YouTube transcript runtime modules."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from youtube.acquisition_ladder import decide_ladder_path
from youtube.job_scheduler import dequeue_ready_jobs, handle_job_failure, apply_job_update
from youtube.pollution_repair import audit_pollution, repair_pollution, verify_repair
from youtube.subtitle_discovery import SubtitleTrack, discover_subtitle_tracks
from youtube.dashboard import aggregate
from youtube.quality_gate import evaluate_quality, persist_quality_check
from ai_influence_youtube_report.browser_agent import YoutubeTranscriptExtractor


def _open_db(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path)


def _print(payload: dict, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def cmd_discover(args: argparse.Namespace) -> int:
    tracks = discover_subtitle_tracks(args.video_id, timeout=args.timeout)
    if args.db:
        conn = _open_db(args.db)
        try:
            _ensure_subtitle_url_column(conn)
            for track in tracks:
                _persist_subtitle_track(conn, track)
            conn.commit()
        finally:
            conn.close()
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
    _print(
        {
            "video_id": args.video_id,
            "resolved_level": result.resolved_level,
            "browser_capture_needed": result.resolved_level == "L2_browser_capture",
        },
        args.json,
    )
    return 0


def cmd_process_jobs(args: argparse.Namespace) -> int:
    conn = _open_db(args.db)
    try:
        dequeue_limit = max(args.limit, 1000) if args.job_type else args.limit
        jobs = dequeue_ready_jobs(conn, priority_filter=args.priority.split(",") if args.priority else None, limit=dequeue_limit)
        if args.job_type:
            wanted = {value.strip() for value in args.job_type.split(",") if value.strip()}
            jobs = [job for job in jobs if job.job_type in wanted][:args.limit]
        if not args.dry_run:
            _ensure_subtitle_url_column(conn)
            for job in jobs:
                if job.job_type in {"asr", "premium_asr"}:
                    conn.execute(
                        """UPDATE youtube_transcript_jobs
                           SET status='metadata_only', error_code='max_attempts',
                               error_message='local/premium ASR disabled; use browser_capture or metadata_only',
                               finished_at=?
                           WHERE job_id=?""",
                        (_now(), job.job_id),
                    )
                    conn.commit()
                    continue
                if job.job_type == "caption_discovery":
                    _run_caption_discovery_job(conn, job, timeout=args.timeout)
                elif job.job_type == "subtitle_download":
                    _run_subtitle_download_job(conn, job, state_dir=Path(args.state_dir).expanduser())
                elif job.job_type == "browser_capture":
                    _run_browser_capture_job(
                        conn,
                        job,
                        state_dir=Path(args.state_dir).expanduser(),
                        timeout=args.timeout,
                    )
                else:
                    continue
        payload = {
            "dry_run": bool(args.dry_run),
            "job_count": len(jobs),
            "jobs": [job.__dict__ for job in jobs],
            "processed": 0 if args.dry_run else len(jobs),
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
    conn = _open_db(args.db)
    try:
        payload = aggregate(conn)
        _print(payload, args.json)
        return 0
    finally:
        conn.close()


def cmd_ab_test_asr(args: argparse.Namespace) -> int:
    payload = {
        "video_id": args.video_id,
        "candidate_backends": [],
        "status": "disabled",
        "reason": "local/premium ASR is disabled; use subtitle-first or browser_capture",
    }
    _print(payload, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="youtube-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("discover-transcript-tracks")
    p.add_argument("--video-id", required=True)
    p.add_argument("--db", default="")
    p.add_argument("--timeout", type=int, default=30)
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
    p.add_argument("--job-type", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--state-dir", default=str(Path.home() / ".solar/harness/state/tech-hotspot-radar"))
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

    p = sub.add_parser("transcript-ab-test-asr", help="Disabled: local/premium ASR is not used by the YouTube pipeline")
    p.add_argument("--video-id", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ab_test_asr)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def _ensure_subtitle_url_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(youtube_subtitle_tracks)")}
    if "url" not in columns:
        conn.execute("ALTER TABLE youtube_subtitle_tracks ADD COLUMN url TEXT")


def _persist_subtitle_track(conn: sqlite3.Connection, track: SubtitleTrack) -> None:
    conn.execute(
        """INSERT INTO youtube_subtitle_tracks
           (track_id, video_id, source_backend, language, language_name, track_kind,
            format, is_auto_generated, is_translatable, confidence, discovered_at,
            download_status, file_path, error, url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?)
           ON CONFLICT(video_id, source_backend, language, track_kind) DO UPDATE SET
             language_name=excluded.language_name,
             format=excluded.format,
             is_auto_generated=excluded.is_auto_generated,
             is_translatable=excluded.is_translatable,
             confidence=excluded.confidence,
             discovered_at=excluded.discovered_at,
             url=excluded.url,
             download_status=CASE
               WHEN youtube_subtitle_tracks.download_status='success' THEN 'success'
               ELSE 'pending'
             END""",
        (
            track.track_id,
            track.video_id,
            track.source_backend,
            track.language,
            track.language_name,
            track.track_kind,
            track.format,
            1 if track.is_auto_generated else 0,
            1 if track.is_translatable else 0,
            track.confidence,
            track.discovered_at,
            track.url,
        ),
    )


def _run_caption_discovery_job(conn: sqlite3.Connection, job, *, timeout: int) -> None:
    now = _now()
    conn.execute(
        "UPDATE youtube_transcript_jobs SET status='running', started_at=? WHERE job_id=?",
        (now, job.job_id),
    )
    try:
        tracks = discover_subtitle_tracks(job.video_id, timeout=timeout)
        for track in tracks:
            _persist_subtitle_track(conn, track)
        decision = decide_ladder_path(job.video_id, tracks, priority=job.priority)
        if decision.subtitle_track:
            download_id = _job_id(job.video_id, "subtitle_download", decision.subtitle_track.track_id)
            conn.execute(
                """INSERT INTO youtube_transcript_jobs
                   (job_id, video_id, job_type, priority, status, backend, max_attempts, error_message)
                   VALUES (?, ?, 'subtitle_download', ?, 'pending', ?, 3, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     status=CASE WHEN youtube_transcript_jobs.status IN ('succeeded','running')
                       THEN youtube_transcript_jobs.status ELSE 'pending' END,
                     priority=excluded.priority,
                     backend=excluded.backend,
                     error_message=excluded.error_message""",
                (
                    download_id,
                    job.video_id,
                    job.priority,
                    decision.subtitle_track.source_backend,
                    f"{decision.resolved_level}:{decision.subtitle_track.language}:{decision.subtitle_track.track_kind}",
                ),
            )
        else:
            _enqueue_browser_capture(
                conn,
                job.video_id,
                job.priority,
                reason="caption_unavailable",
                error_code="no_caption",
                error_message="caption unavailable after subtitle-first discovery",
            )
        conn.execute(
            "UPDATE youtube_transcript_jobs SET status='succeeded', finished_at=?, error_message=? WHERE job_id=?",
            (now, f"tracks={len(tracks)}", job.job_id),
        )
        conn.commit()
    except Exception as exc:
        update = handle_job_failure(conn, job.job_id, "timeout", job.attempt_count, job.max_attempts)
        apply_job_update(conn, update)
        conn.execute(
            "UPDATE youtube_transcript_jobs SET error_message=? WHERE job_id=?",
            (f"{type(exc).__name__}: {exc}"[:500], job.job_id),
        )
        conn.commit()


def _run_subtitle_download_job(conn: sqlite3.Connection, job, *, state_dir: Path) -> None:
    now = _now()
    conn.execute(
        "UPDATE youtube_transcript_jobs SET status='running', started_at=? WHERE job_id=?",
        (now, job.job_id),
    )
    track = _best_pending_track(conn, job.video_id)
    if not track or not track["url"]:
        _enqueue_browser_capture(
            conn,
            job.video_id,
            job.priority,
            reason="subtitle_track_url_missing",
            error_code="no_caption",
            error_message="no downloadable subtitle track url; routed to browser_capture",
        )
        conn.execute(
            """UPDATE youtube_transcript_jobs
               SET status='cancelled', next_retry_at=NULL, error_code='no_caption',
                   error_message='no downloadable subtitle track url; routed to browser_capture',
                   finished_at=?
               WHERE job_id=?""",
            (now, job.job_id),
        )
        conn.commit()
        return
    try:
        payload = _download_text(str(track["url"]))
        clean = _clean_caption_text(payload)
        if len(clean) < 200:
            raise RuntimeError("caption text too short after cleaning")
        week_dir = _transcript_week_dir(conn, job.video_id, state_dir)
        raw_path = week_dir / f"{job.video_id}.caption.{track['format'] or 'txt'}"
        clean_path = week_dir / f"{job.video_id}.txt"
        raw_path.write_text(payload, encoding="utf-8")
        clean_path.write_text(clean + "\n", encoding="utf-8")
        source = "youtube_asr_caption" if track["track_kind"] == "asr" else "standard_caption"
        transcript_id = f"t-{job.video_id}-{source}-{hashlib.sha1(clean.encode()).hexdigest()[:12]}"
        reliability = 0.75 if source == "youtube_asr_caption" else 1.0
        result = evaluate_quality(
            text=clean,
            coverage_ratio=0.85 if source == "youtube_asr_caption" else 0.95,
            hallucination_risk=0.25 if source == "youtube_asr_caption" else 0.10,
            source_reliability=reliability,
            vocab_terms=_vocab_terms(conn),
            trigger_source=source,
        )
        status = "fetched"
        conn.execute(
            """INSERT INTO youtube_transcripts
               (video_id, transcript_id, transcript_raw, transcript_clean, transcript_status,
                source, language, fetched_at, char_count, is_auto_generated, raw_path, clean_path,
                transcript_hash, quality_score, quality_tier, coverage_ratio, hallucination_risk, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 transcript_id=excluded.transcript_id,
                 transcript_raw=excluded.transcript_raw,
                 transcript_clean=excluded.transcript_clean,
                 transcript_status=excluded.transcript_status,
                 source=excluded.source,
                 language=excluded.language,
                 fetched_at=excluded.fetched_at,
                 char_count=excluded.char_count,
                 is_auto_generated=excluded.is_auto_generated,
                 raw_path=excluded.raw_path,
                 clean_path=excluded.clean_path,
                 transcript_hash=excluded.transcript_hash,
                 quality_score=excluded.quality_score,
                 quality_tier=excluded.quality_tier,
                 coverage_ratio=excluded.coverage_ratio,
                 hallucination_risk=excluded.hallucination_risk""",
            (
                job.video_id,
                transcript_id,
                payload,
                clean,
                status,
                source,
                track["language"] or "",
                now,
                len(clean),
                1 if source == "youtube_asr_caption" else 0,
                str(raw_path),
                str(clean_path),
                hashlib.sha256(clean.encode()).hexdigest(),
                result.final_score,
                result.final_tier,
                result.sub_scores.get("coverage_ratio"),
                1.0 - result.sub_scores.get("inverse_hallucination", 1.0),
                now,
            ),
        )
        persist_quality_check(conn, transcript_id=transcript_id, result=result, commit=False)
        conn.execute(
            "UPDATE youtube_subtitle_tracks SET download_status='success', file_path=?, error=NULL WHERE track_id=?",
            (str(raw_path), track["track_id"]),
        )
        conn.execute(
            "UPDATE youtube_transcript_jobs SET status='succeeded', finished_at=?, error_message=? WHERE job_id=?",
            (now, f"quality={result.final_tier}:{result.final_score}", job.job_id),
        )
        conn.commit()
    except Exception as exc:
        next_attempt = int(job.attempt_count or 0) + 1
        error_text = f"{type(exc).__name__}: {exc}"[:500]
        conn.execute(
            "UPDATE youtube_subtitle_tracks SET download_status='failed', error=? WHERE track_id=?",
            (error_text, track["track_id"]),
        )
        if next_attempt >= int(job.max_attempts or 3):
            _enqueue_browser_capture(
                conn,
                job.video_id,
                job.priority,
                reason="subtitle_download_exhausted",
                error_code="max_attempts",
                error_message=f"subtitle_download exhausted; routed to browser_capture: {error_text}",
            )
            conn.execute(
                """UPDATE youtube_transcript_jobs
                   SET status='cancelled', attempt_count=?, next_retry_at=NULL,
                       error_code='max_attempts', error_message=?, finished_at=?
                   WHERE job_id=?""",
                (next_attempt, error_text, now, job.job_id),
            )
        else:
            update = handle_job_failure(conn, job.job_id, "timeout", job.attempt_count, job.max_attempts)
            apply_job_update(conn, update)
            conn.execute(
                "UPDATE youtube_transcript_jobs SET error_message=? WHERE job_id=?",
                (error_text, job.job_id),
            )
        conn.commit()


def _run_browser_capture_job(conn: sqlite3.Connection, job, *, state_dir: Path, timeout: int) -> None:
    now = _now()
    conn.execute(
        "UPDATE youtube_transcript_jobs SET status='running', started_at=? WHERE job_id=?",
        (now, job.job_id),
    )
    run_dir = state_dir / "browser-capture-runs" / f"{job.video_id}-{now.replace(':', '').replace('.', '')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        result_payload = YoutubeTranscriptExtractor().extract(
            f"https://www.youtube.com/watch?v={job.video_id}",
            task_dir=run_dir,
            timeout_seconds=max(timeout, 300),
            max_retries=1,
            output_format="timestamped",
            headless=True,
        )
        clean = _dedupe_lines(str(result_payload.get("text") or "").splitlines())
        if len(clean) < 200:
            raise RuntimeError("browser transcript text too short after cleaning")

        week_dir = _transcript_week_dir(conn, job.video_id, state_dir)
        raw_path = week_dir / f"{job.video_id}.browser.txt"
        clean_path = week_dir / f"{job.video_id}.txt"
        raw_path.write_text(str(result_payload.get("text") or "") + "\n", encoding="utf-8")
        clean_path.write_text(clean + "\n", encoding="utf-8")
        transcript_id = f"t-{job.video_id}-browser_caption-{hashlib.sha1(clean.encode()).hexdigest()[:12]}"
        quality = evaluate_quality(
            text=clean,
            coverage_ratio=0.80,
            hallucination_risk=0.20,
            source_reliability=0.70,
            vocab_terms=_vocab_terms(conn),
            trigger_source="browser_caption",
        )
        conn.execute(
            """INSERT INTO youtube_transcripts
               (video_id, transcript_id, transcript_raw, transcript_clean, transcript_status,
                source, language, fetched_at, char_count, is_auto_generated, raw_path, clean_path,
                transcript_hash, quality_score, quality_tier, coverage_ratio, hallucination_risk, created_at)
               VALUES (?, ?, ?, ?, 'fetched', 'browser_caption', '', ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                 transcript_id=excluded.transcript_id,
                 transcript_raw=excluded.transcript_raw,
                 transcript_clean=excluded.transcript_clean,
                 transcript_status=excluded.transcript_status,
                 source=excluded.source,
                 fetched_at=excluded.fetched_at,
                 char_count=excluded.char_count,
                 is_auto_generated=excluded.is_auto_generated,
                 raw_path=excluded.raw_path,
                 clean_path=excluded.clean_path,
                 transcript_hash=excluded.transcript_hash,
                 quality_score=excluded.quality_score,
                 quality_tier=excluded.quality_tier,
                 coverage_ratio=excluded.coverage_ratio,
                 hallucination_risk=excluded.hallucination_risk""",
            (
                job.video_id,
                transcript_id,
                str(result_payload.get("text") or ""),
                clean,
                now,
                len(clean),
                str(raw_path),
                str(clean_path),
                hashlib.sha256(clean.encode()).hexdigest(),
                quality.final_score,
                quality.final_tier,
                quality.sub_scores.get("coverage_ratio"),
                1.0 - quality.sub_scores.get("inverse_hallucination", 1.0),
                now,
            ),
        )
        persist_quality_check(conn, transcript_id=transcript_id, result=quality, commit=False)
        conn.execute(
            "UPDATE youtube_transcript_jobs SET status='succeeded', finished_at=?, error_message=? WHERE job_id=?",
            (now, f"browser_caption quality={quality.final_tier}:{quality.final_score}", job.job_id),
        )
        conn.commit()
    except Exception as exc:
        next_attempt = int(job.attempt_count or 0) + 1
        full_error_text = f"{type(exc).__name__}: {exc}"
        error_text = full_error_text[:500]
        terminal_no_transcript = any(
            marker in full_error_text
            for marker in (
                "youtube_transcript_button_not_found",
                "youtube_transcript_panel_not_loaded",
                "youtube_transcript_empty",
            )
        )
        if terminal_no_transcript:
            conn.execute(
                """UPDATE youtube_transcript_jobs
                   SET status='metadata_only', attempt_count=?, next_retry_at=NULL,
                       error_code='no_caption', error_message=?, finished_at=?
                   WHERE job_id=?""",
                (next_attempt, error_text, now, job.job_id),
            )
            conn.commit()
        elif next_attempt >= int(job.max_attempts or 2):
            conn.execute(
                """UPDATE youtube_transcript_jobs
                   SET status='metadata_only', attempt_count=?, next_retry_at=NULL,
                       error_code='max_attempts', error_message=?, finished_at=?
                   WHERE job_id=?""",
                (next_attempt, error_text, now, job.job_id),
            )
            conn.commit()
        else:
            update = handle_job_failure(conn, job.job_id, "timeout", job.attempt_count, job.max_attempts)
            apply_job_update(conn, update)
            conn.execute(
                "UPDATE youtube_transcript_jobs SET error_message=? WHERE job_id=?",
                (error_text, job.job_id),
            )
            conn.commit()


def _best_pending_track(conn: sqlite3.Connection, video_id: str):
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """SELECT * FROM youtube_subtitle_tracks
           WHERE video_id=? AND download_status IN ('pending','failed','success')
           ORDER BY
             CASE track_kind WHEN 'standard' THEN 0 WHEN 'asr' THEN 1 ELSE 2 END,
             CASE language WHEN 'en' THEN 0 WHEN 'en-US' THEN 1 WHEN 'en-GB' THEN 2
                           WHEN 'zh' THEN 3 WHEN 'zh-Hans' THEN 4 WHEN 'zh-Hant' THEN 5
                           ELSE 9 END,
             confidence DESC
           LIMIT 1""",
        (video_id,),
    ).fetchone()


def _enqueue_browser_capture(
    conn: sqlite3.Connection,
    video_id: str,
    priority: str,
    *,
    reason: str,
    error_code: str,
    error_message: str,
) -> None:
    capture_id = _job_id(video_id, "browser_capture", reason)
    conn.execute(
        """INSERT INTO youtube_transcript_jobs
           (job_id, video_id, job_type, priority, status, backend, max_attempts, error_code, error_message)
           VALUES (?, ?, 'browser_capture', ?, 'pending', 'browser-agent', 2, ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
             status=CASE
               WHEN youtube_transcript_jobs.status IN ('succeeded','running','metadata_only','cancelled','quarantined')
               THEN youtube_transcript_jobs.status ELSE 'pending' END,
             priority=excluded.priority,
             backend='browser-agent',
             next_retry_at=NULL,
             error_code=excluded.error_code,
             error_message=excluded.error_message""",
        (capture_id, video_id, priority, error_code, error_message[:500]),
    )


def _download_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean_caption_text(payload: str) -> str:
    if '"events"' in payload[:500]:
        try:
            data = json.loads(payload)
            parts = []
            for event in data.get("events", []):
                segs = event.get("segs") or []
                text = "".join(str(seg.get("utf8") or "") for seg in segs)
                if text.strip():
                    parts.append(text.strip())
            return _dedupe_lines(parts)
        except Exception:
            pass
    lines: list[str] = []
    for raw in payload.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:")):
            continue
        if re.match(r"^\\d+$", line):
            continue
        if "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = line.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        if line:
            lines.append(line)
    return _dedupe_lines(lines)


def _dedupe_lines(lines: list[str]) -> str:
    out: list[str] = []
    prev = ""
    for line in lines:
        for part in str(line).replace("\\n", "\n").splitlines():
            normalized = re.sub(r"\\s+", " ", part).strip()
            if not normalized or normalized == prev:
                continue
            if len(normalized) <= 2 and out:
                continue
            out.append(normalized)
            prev = normalized
    return "\\n".join(out).strip()


def _transcript_week_dir(conn: sqlite3.Connection, video_id: str, state_dir: Path) -> Path:
    row = conn.execute("SELECT published_at FROM youtube_videos WHERE video_id=?", (video_id,)).fetchone()
    published = str(row[0] if row else "")
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    iso = dt.isocalendar()
    path = state_dir / "transcripts" / f"{iso.year}-W{iso.week:02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _vocab_terms(conn: sqlite3.Connection) -> list[str]:
    terms = [
        "MCP", "Claude Code", "Codex", "Cursor", "vLLM", "Triton", "MLX",
        "Qwen", "DeepSeek", "Kimi", "Gemini", "Gemma", "LlamaIndex",
        "LangChain", "PyTorch", "CUDA", "RAG", "context engineering",
    ]
    try:
        terms.extend(row[0] for row in conn.execute("SELECT term_corrected FROM vocab_dictionary LIMIT 200").fetchall())
    except Exception:
        pass
    return sorted({term for term in terms if term})


def _job_id(video_id: str, job_type: str, salt: str) -> str:
    return "ytj-" + hashlib.sha1(f"{video_id}:{job_type}:{salt}".encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


if __name__ == "__main__":
    raise SystemExit(main())
