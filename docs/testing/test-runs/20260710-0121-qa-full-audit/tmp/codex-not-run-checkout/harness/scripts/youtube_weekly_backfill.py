#!/usr/bin/env python3
"""YouTube AI Influence Weekly Backfill Runner.

Discovers historical AI-influence videos (Jan 1 → last week) per channel via
yt-dlp, groups them by ISO week, and extracts transcripts using the
browser-agent operator.  Fully resumable — re-running skips videos whose
status.json already says 'ok' or 'skipped'.

Output structure:
  {state_dir}/backfill/weeks/{YYYY-WNN}/{video_id}/
    metadata.json     — video title, channel, url, publish date, iso_week
    transcript.txt    — timestamped transcript (browser-agent)
    digest.md         — structured digest with signal analysis
    status.json       — {status: ok|failed|skipped, ts, …}
    browser-task/     — raw browser-agent artifacts (screenshots, page.json …)

Usage examples:
  # Full run (discovery + extraction), W20-2026 → W01-2026
  python3 youtube_weekly_backfill.py

  # Skip yt-dlp discovery (reuse cached discovery-cache.json)
  python3 youtube_weekly_backfill.py --skip-discovery

  # Process only one week (useful for testing)
  python3 youtube_weekly_backfill.py --skip-discovery --only-week 2026-W18

  # Dry run (no downloads, no browser)
  python3 youtube_weekly_backfill.py --dry-run --skip-discovery

  # Custom range
  python3 youtube_weekly_backfill.py --start-week 2026-W15 --end-week 2026-W10
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Extend sys.path so harness lib/tools are importable
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_HARNESS_ROOT = _SCRIPTS_DIR.parent
for _p in (_HARNESS_ROOT / "lib", _HARNESS_ROOT / "tools"):
    _p_str = str(_p)
    if _p_str not in sys.path:
        sys.path.insert(0, _p_str)
del _p, _p_str

try:
    import yaml  # type: ignore
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    raise SystemExit(2)

try:
    import youtube_transcript_operator as _yto
except ImportError as _e:
    print(
        f"ERROR: youtube_transcript_operator not importable: {_e}\n"
        "Ensure harness/tools is on sys.path and browser-use is installed.",
        file=sys.stderr,
    )
    raise SystemExit(2)

UTC = dt.timezone.utc

DEFAULT_CONFIG = "~/Solar/harness/config/youtube-influence-digest.yaml"

# ---------------------------------------------------------------------------
# Date / ISO week helpers
# ---------------------------------------------------------------------------

def iso_z(ts: dt.datetime | None = None) -> str:
    ts = ts or dt.datetime.now(UTC).replace(microsecond=0)
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_to_iso_week(d: dt.date) -> str:
    """Return 'YYYY-WNN' label for a date."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def iso_week_to_monday(week_label: str) -> dt.date:
    """Parse 'YYYY-WNN' → the Monday of that week."""
    year_str, week_str = week_label.split("-W")
    return dt.date.fromisocalendar(int(year_str), int(week_str), 1)


def weeks_newest_first(start_label: str, end_label: str) -> list[str]:
    """Return ISO week labels from start_label (newest) down to end_label (oldest), inclusive."""
    start_mon = iso_week_to_monday(start_label)
    end_mon = iso_week_to_monday(end_label)
    weeks: list[str] = []
    d = start_mon
    while d >= end_mon:
        weeks.append(date_to_iso_week(d))
        d -= dt.timedelta(weeks=1)
    return weeks


def parse_isoish_datetime(value: str | None) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def status_collected_date(status_path: Path, payload: dict[str, Any] | None = None) -> dt.date | None:
    data = payload
    if data is None:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    for key in ("completed_at", "failed_at", "started_at", "ts", "updated_at"):
        parsed = parse_isoish_datetime(str(data.get(key) or ""))
        if parsed is not None:
            return parsed.date()
    try:
        return dt.datetime.fromtimestamp(status_path.stat().st_mtime, tz=UTC).date()
    except OSError:
        return None


def parse_refresh_before_date(raw: str) -> dt.date | None:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value == "today":
        return dt.date.today()
    return dt.date.fromisoformat(value)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def find_binary(name: str, hint: str = "") -> str:
    import shutil
    if hint:
        p = Path(hint).expanduser()
        if p.exists():
            return str(p)
    found = shutil.which(name)
    return found or ""


# ---------------------------------------------------------------------------
# yt-dlp video discovery
# ---------------------------------------------------------------------------

def _parse_upload_date(info: dict[str, Any]) -> dt.date | None:
    """Extract upload date from yt-dlp flat-playlist entry."""
    raw = str(info.get("upload_date") or "").strip()
    if len(raw) == 8 and raw.isdigit():
        try:
            return dt.date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            pass
    # Fallback: epoch timestamp
    ts = info.get("timestamp") or info.get("release_timestamp")
    if ts:
        try:
            return dt.datetime.fromtimestamp(float(ts), tz=UTC).date()
        except (ValueError, OSError):
            pass
    return None


def discover_channel_videos(
    channel_id: str,
    channel_name: str,
    channel_priority: str,
    category: str,
    yt_dlp_bin: str,
    date_after: dt.date,
    date_before: dt.date,
    timeout: int = 300,
) -> list[dict[str, Any]]:
    """Discover videos for one channel in [date_after, date_before] via yt-dlp.

    NOTE: YouTube flat-playlist entries have null upload_date/timestamp fields,
    so we use full yt-dlp mode (no --flat-playlist) which fetches individual
    video pages to get accurate upload_date.

    --break-per-url causes yt-dlp to stop processing as soon as it encounters
    a video older than --dateafter (since YouTube lists newest-first).

    Returns list of video metadata dicts.
    """
    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
    cmd = [
        yt_dlp_bin,
        # Full mode — fetches individual video pages for accurate dates.
        # No --flat-playlist because flat entries have null upload_date.
        "--dump-json",
        "--no-warnings",
        "--quiet",
        "--skip-download",
        # Date filters: yt-dlp stops early (newest-first) when hitting --dateafter
        "--dateafter",  date_after.strftime("%Y%m%d"),
        "--datebefore", date_before.strftime("%Y%m%d"),
        # Stop processing the channel playlist as soon as a video is out of date range
        "--break-on-reject",
        # Safety cap in case break-on-reject doesn't fire
        "--max-downloads", "150",
        # Reduce rate-limit risk
        "--sleep-requests", "1",
        "--retries", "2",
        channel_url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"  WARNING: yt-dlp timed out for {channel_name} ({channel_id})", flush=True)
        return []

    videos: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            info = json.loads(line)
        except json.JSONDecodeError:
            continue

        video_id = str(info.get("id") or "").strip()
        if not video_id:
            continue

        upload_date = _parse_upload_date(info)
        if upload_date is None:
            # Full mode should always have upload_date; if missing, skip.
            continue
        # Enforce our own date bounds (redundant but safe)
        if upload_date < date_after or upload_date > date_before:
            continue

        iso_week = date_to_iso_week(upload_date)
        title = str(info.get("title") or "").strip()
        channel_nm = str(info.get("channel") or info.get("uploader") or channel_name).strip()

        videos.append({
            "video_id": video_id,
            "title": title,
            "upload_date": upload_date.isoformat(),
            "iso_week": iso_week,
            "channel_id": channel_id,
            "channel_name": channel_nm,
            "channel_priority": channel_priority,
            "category": category,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return videos


def run_discovery(
    channels: list[dict[str, Any]],
    yt_dlp_bin: str,
    date_after: dt.date,
    date_before: dt.date,
    cache_path: Path,
    sleep_between_channels: float = 5.0,
) -> dict[str, list[dict[str, Any]]]:
    """Discover all channel videos in the date range.

    Saves to cache_path (JSON).  Returns week_label → [video_meta_list] dict.
    """
    print(f"\n{'='*60}", flush=True)
    print(f"DISCOVERY PHASE", flush=True)
    print(f"  Channels : {len(channels)}", flush=True)
    print(f"  Date range: {date_after} → {date_before}", flush=True)
    print(f"{'='*60}\n", flush=True)

    all_videos: list[dict[str, Any]] = []

    for i, channel in enumerate(channels):
        cid = channel.get("channel_id", "")
        name = channel.get("name", cid)
        priority = channel.get("priority", "rotation")
        category = channel.get("category", "")
        prefix = f"[{i+1:02d}/{len(channels)}]"
        print(f"{prefix} {name} ({cid})", end="  →  ", flush=True)

        try:
            videos = discover_channel_videos(
                channel_id=cid,
                channel_name=name,
                channel_priority=priority,
                category=category,
                yt_dlp_bin=yt_dlp_bin,
                date_after=date_after,
                date_before=date_before,
            )
            all_videos.extend(videos)
            print(f"{len(videos)} videos found", flush=True)
        except Exception as exc:
            print(f"ERROR: {exc}", flush=True)

        if sleep_between_channels > 0 and i < len(channels) - 1:
            time.sleep(sleep_between_channels)

    print(f"\nTotal discovered: {len(all_videos)} videos across {len(set(v['iso_week'] for v in all_videos))} weeks", flush=True)

    # Group by ISO week, sort within each week: tier1 first, then by channel, then newest first
    week_map: dict[str, list[dict[str, Any]]] = {}
    for v in all_videos:
        week = v.get("iso_week", "unknown")
        week_map.setdefault(week, []).append(v)

    _PRIORITY_RANK = {"tier1": 0, "must_scan": 0, "high": 0, "rotation": 1}

    def _sort_key(v: dict) -> tuple:
        rank = _PRIORITY_RANK.get(str(v.get("channel_priority") or ""), 1)
        date_neg = -(int(v.get("upload_date", "1970-01-01").replace("-", "")) if v.get("upload_date") else 0)
        return (rank, v.get("channel_id", ""), date_neg)

    for week in week_map:
        week_map[week].sort(key=_sort_key)

    # Save cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "discovered_at": iso_z(),
        "date_after": date_after.isoformat(),
        "date_before": date_before.isoformat(),
        "total_videos": len(all_videos),
        "weeks": week_map,
    }
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nDiscovery cache saved → {cache_path}", flush=True)
    return week_map


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------

def _score_signal(text: str, config: dict[str, Any]) -> tuple[str, str, int]:
    lower = (text or "").lower()
    keywords: dict[str, list] = config.get("analysis_keywords") or {}
    type_scores: dict[str, int] = {}
    for signal_type, words in keywords.items():
        type_scores[signal_type] = sum(1 for w in words if str(w).lower() in lower)
    signal_type = max(type_scores, key=type_scores.get) if type_scores else "other"
    score = type_scores.get(signal_type, 0)
    score += 2 if re.search(r"\b(release|launch|paper|benchmark|agent|model|gpu|tutorial|demo)\b", lower) else 0
    impact = "high" if score >= 6 else "medium" if score >= 3 else "low"
    return signal_type, impact, score


def _build_digest_md(
    video_meta: dict[str, Any],
    transcript_text: str,
    signal_type: str,
    impact: str,
    score: int,
) -> str:
    video_id = video_meta["video_id"]
    title = video_meta.get("title", "")
    channel = video_meta.get("channel_name", "")
    url = video_meta.get("url", "")
    iso_week = video_meta.get("iso_week", "")
    upload_date = video_meta.get("upload_date", "")
    category = video_meta.get("category", "")

    lines = [
        "---",
        f"title: {title[:180]}",
        "source: youtube-weekly-backfill",
        f"week: {iso_week}",
        f"video_id: {video_id}",
        f"channel: {channel}",
        f"category: {category}",
        f"upload_date: {upload_date}",
        f"impact: {impact}",
        f"signal_type: {signal_type}",
        f"signal_score: {score}",
        f"source_url: {url}",
        "raw_ingest: true",
        "---",
        "",
        f"# {title}",
        "",
        f"- **Channel**: {channel}",
        f"- **ISO Week**: {iso_week}",
        f"- **Upload Date**: {upload_date}",
        f"- **Impact**: {impact}  |  **Signal**: {signal_type}  |  **Score**: {score}",
        f"- **Source**: [{url}]({url})",
        "",
        "## Transcript",
        "",
        (transcript_text[:60000] if transcript_text else "N/A"),
        "",
    ]
    return "\n".join(lines)


def process_video(
    video_meta: dict[str, Any],
    video_dir: Path,
    config: dict[str, Any],
    browser_op_timeout: int = 300,
) -> dict[str, Any]:
    """Extract transcript and write all artifacts for one video.

    Returns status dict with keys: status, text_length, signal_type, impact, score.
    Raises on unrecoverable failure.
    """
    video_dir.mkdir(parents=True, exist_ok=True)

    # Save metadata
    (video_dir / "metadata.json").write_text(
        json.dumps(video_meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    task_dir = video_dir / "browser-task"
    task_dir.mkdir(parents=True, exist_ok=True)

    # Build request and run via browser-agent operator
    request = _yto.build_request(
        {
            "youtube_url": video_meta["url"],
            "timeout_seconds": browser_op_timeout,
            "output_format": "timestamped",
        },
        task_dir=task_dir,
    )
    result = _yto.run_request(request, task_dir=task_dir)

    text = str(result.get("text") or "").strip()
    if not text:
        raise RuntimeError("browser-agent returned an empty transcript")

    # Save transcript
    (video_dir / "transcript.txt").write_text(text + "\n", encoding="utf-8")

    # Signal analysis
    signal_type, impact, score = _score_signal(text, config)

    # Build and save digest
    digest_md = _build_digest_md(video_meta, text, signal_type, impact, score)
    (video_dir / "digest.md").write_text(digest_md, encoding="utf-8")

    return {
        "status": "ok",
        "text_length": len(text),
        "signal_type": signal_type,
        "impact": impact,
        "score": score,
    }


# ---------------------------------------------------------------------------
# Per-week runner
# ---------------------------------------------------------------------------

def _apply_per_channel_limit(
    videos: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for v in videos:
        cid = v.get("channel_id", "")
        if seen.get(cid, 0) < limit:
            result.append(v)
            seen[cid] = seen.get(cid, 0) + 1
    return result


def process_week(
    week_label: str,
    week_videos: list[dict[str, Any]],
    backfill_dir: Path,
    config: dict[str, Any],
    dry_run: bool,
    per_channel_limit: int,
    max_videos_per_week: int,
    sleep_between_videos: float,
    browser_op_timeout: int,
    refresh_before_date: dt.date | None = None,
) -> dict[str, Any]:
    """Process all selected videos for a single week. Returns stats."""
    week_dir = backfill_dir / "weeks" / week_label
    if not dry_run:
        week_dir.mkdir(parents=True, exist_ok=True)

    # Apply limits
    candidates = _apply_per_channel_limit(week_videos, per_channel_limit)[:max_videos_per_week]

    stats: dict[str, Any] = {
        "week": week_label,
        "discovered": len(week_videos),
        "candidates": len(candidates),
        "ok": 0,
        "skipped": 0,
        "failed": 0,
    }

    for idx, video_meta in enumerate(candidates):
        video_id = video_meta["video_id"]
        title = video_meta.get("title", "")[:70]
        video_dir = week_dir / video_id
        status_path = video_dir / "status.json"

        # Resume: skip already-done videos
        if status_path.exists():
            try:
                prior = json.loads(status_path.read_text(encoding="utf-8"))
                if prior.get("status") in {"ok", "skipped"}:
                    collected_date = status_collected_date(status_path, prior)
                    should_refresh = bool(
                        refresh_before_date is not None and (
                            collected_date is None or collected_date < refresh_before_date
                        )
                    )
                    if should_refresh:
                        print(
                            f"  [{idx+1}/{len(candidates)}] REFRESH {video_id}  "
                            f"({prior['status']} from {collected_date or 'unknown'})",
                            flush=True,
                        )
                    else:
                        stats["skipped"] += 1
                        print(
                            f"  [{idx+1}/{len(candidates)}] SKIP {video_id}  ({prior['status']})",
                            flush=True,
                        )
                        continue
            except Exception:
                pass

        ch = video_meta.get("channel_name", "")
        dt_str = video_meta.get("upload_date", "")
        print(
            f"  [{idx+1}/{len(candidates)}] {video_id}  [{ch}]  {dt_str}",
            flush=True,
        )
        print(f"    Title: {title}", flush=True)

        if dry_run:
            print(f"    [dry-run] would extract transcript", flush=True)
            stats["skipped"] += 1
            continue

        start_ts = iso_z()
        try:
            result_data = process_video(
                video_meta=video_meta,
                video_dir=video_dir,
                config=config,
                browser_op_timeout=browser_op_timeout,
            )
            (video_dir / "status.json").write_text(
                json.dumps({**result_data, "started_at": start_ts, "completed_at": iso_z()},
                           ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            stats["ok"] += 1
            print(
                f"    ✓ {result_data['text_length']} chars  "
                f"signal={result_data['signal_type']}/{result_data['impact']}",
                flush=True,
            )
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            print(f"    ✗ FAILED: {err_msg}", file=sys.stderr, flush=True)
            try:
                video_dir.mkdir(parents=True, exist_ok=True)
                (video_dir / "status.json").write_text(
                    json.dumps({
                        "status": "failed",
                        "started_at": start_ts,
                        "failed_at": iso_z(),
                        "error": err_msg,
                    }, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                # Save metadata even on failure so we know what was tried
                if not (video_dir / "metadata.json").exists():
                    (video_dir / "metadata.json").write_text(
                        json.dumps(video_meta, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass
            stats["failed"] += 1

        # Sleep between videos (not after the last one)
        if sleep_between_videos > 0 and idx < len(candidates) - 1:
            time.sleep(sleep_between_videos)

    return stats


def recount_backfill_week(backfill_dir: Path, week_label: str) -> dict[str, Any]:
    """Recount real per-week results from persisted status files.

    This normalizes summary generation against interrupted/rerun sessions so the
    final summary reflects what is actually on disk instead of only in-memory
    loop counters from the current invocation.
    """
    week_dir = backfill_dir / "weeks" / week_label
    if not week_dir.exists():
        return {
            "week": week_label,
            "discovered": 0,
            "candidates": 0,
            "ok": 0,
            "skipped": 0,
            "failed": 0,
        }

    discovered = 0
    cache_path = backfill_dir / "discovery-cache.json"
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            discovered = len((cache.get("weeks") or {}).get(week_label) or [])
        except Exception:
            discovered = 0

    ok = skipped = failed = 0
    candidates = 0
    for video_dir in sorted(week_dir.iterdir()):
        if not video_dir.is_dir():
            continue
        candidates += 1
        status_path = video_dir / "status.json"
        if not status_path.exists():
            continue
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            failed += 1
            continue
        status = str(payload.get("status") or "").strip().lower()
        if status == "ok":
            ok += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

    return {
        "week": week_label,
        "discovered": discovered,
        "candidates": candidates,
        "ok": ok,
        "skipped": skipped,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="YouTube AI Influence Weekly Backfill Runner")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--dry-run", action="store_true", help="no downloads, no browser")
    # Week range
    p.add_argument("--start-week", default="", help="e.g. 2026-W20 (default: last ISO week)")
    p.add_argument("--end-week", default="2026-W01", help="earliest week to collect (default: 2026-W01)")
    p.add_argument("--only-week", default="", help="process only this one week")
    # Discovery
    p.add_argument("--skip-discovery", action="store_true", help="reuse cached discovery-cache.json")
    # Limits
    p.add_argument("--max-videos-per-week", type=int, default=24)
    p.add_argument("--per-channel-limit", type=int, default=2)
    # Timing
    p.add_argument("--sleep-between-videos", type=float, default=30.0)
    p.add_argument("--sleep-between-weeks", type=float, default=10.0)
    p.add_argument("--sleep-between-channels", type=float, default=5.0)
    p.add_argument("--browser-op-timeout", type=int, default=300)
    p.add_argument(
        "--refresh-before-date",
        default="",
        help="recollect videos whose prior status was last collected before this UTC date (YYYY-MM-DD) or 'today'",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = load_config(Path(args.config))
    refresh_before_date = parse_refresh_before_date(args.refresh_before_date)

    asr_cfg: dict = config.get("asr") or {}
    out_cfg: dict = config.get("output") or {}
    backfill_cfg: dict = config.get("backfill") or {}

    yt_dlp_bin = find_binary("yt-dlp", str(asr_cfg.get("yt_dlp_bin") or ""))
    if not yt_dlp_bin:
        print("ERROR: yt-dlp binary not found. Set asr.yt_dlp_bin in config.", file=sys.stderr)
        return 1

    state_dir = Path(
        out_cfg.get("state_dir", "~/.solar/harness/state/youtube-influence-digest")
    ).expanduser()
    backfill_dir = state_dir / "backfill"
    backfill_dir.mkdir(parents=True, exist_ok=True)

    # ---- Compute week range ----
    today = dt.date.today()
    # "last week" = the week that ended last Sunday (today's Monday - 7 days)
    days_since_monday = today.weekday()  # Mon=0 … Sun=6
    this_week_monday = today - dt.timedelta(days=days_since_monday)
    last_week_monday = this_week_monday - dt.timedelta(weeks=1)

    start_week = args.start_week or date_to_iso_week(last_week_monday)
    end_week = args.end_week  # default 2026-W01

    all_weeks = [args.only_week] if args.only_week else weeks_newest_first(start_week, end_week)

    # Date bounds for discovery
    discovery_date_after = iso_week_to_monday(end_week)                          # Monday of earliest week
    discovery_date_before = iso_week_to_monday(start_week) + dt.timedelta(days=6) # Sunday of newest week

    channels: list[dict] = config.get("channels") or []

    # ---- Print plan ----
    print(f"\n{'='*60}", flush=True)
    print(f"YouTube AI Influence Weekly Backfill", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Week range : {end_week}  →  {start_week}  ({len(all_weeks)} weeks)", flush=True)
    print(f"  Date range : {discovery_date_after}  →  {discovery_date_before}", flush=True)
    print(f"  Backfill dir: {backfill_dir}", flush=True)
    print(f"  Channels   : {len(channels)}", flush=True)
    print(f"  Max/week   : {args.max_videos_per_week}  (per-channel limit: {args.per_channel_limit})", flush=True)
    print(f"  Dry run    : {args.dry_run}", flush=True)
    if args.only_week:
        print(f"  Only week  : {args.only_week}", flush=True)
    print(flush=True)

    # ---- Discovery ----
    discovery_cache_path = backfill_dir / "discovery-cache.json"

    if args.skip_discovery and discovery_cache_path.exists():
        print(f"Loading discovery cache: {discovery_cache_path}", flush=True)
        cache = json.loads(discovery_cache_path.read_text(encoding="utf-8"))
        week_map: dict[str, list] = cache.get("weeks") or {}
        total = sum(len(v) for v in week_map.values())
        print(f"  {total} videos across {len(week_map)} weeks.", flush=True)
    else:
        if args.skip_discovery:
            print("WARNING: --skip-discovery specified but no cache found. Running discovery.", flush=True)
        week_map = run_discovery(
            channels=channels,
            yt_dlp_bin=yt_dlp_bin,
            date_after=discovery_date_after,
            date_before=discovery_date_before,
            cache_path=discovery_cache_path,
            sleep_between_channels=args.sleep_between_channels,
        )

    # ---- Extraction phase ----
    print(f"\n{'='*60}", flush=True)
    print(f"EXTRACTION PHASE  ({len(all_weeks)} weeks)", flush=True)
    print(f"{'='*60}", flush=True)

    all_stats: list[dict[str, Any]] = []

    for week_idx, week_label in enumerate(all_weeks):
        week_videos = week_map.get(week_label) or []
        monday = iso_week_to_monday(week_label)
        sunday = monday + dt.timedelta(days=6)

        print(
            f"\n--- Week {week_idx+1}/{len(all_weeks)}: {week_label}  "
            f"({monday} – {sunday})  "
            f"[{len(week_videos)} discovered] ---",
            flush=True,
        )

        if not week_videos:
            print("  (no videos discovered for this week)", flush=True)
            all_stats.append({"week": week_label, "discovered": 0, "candidates": 0,
                               "ok": 0, "skipped": 0, "failed": 0})
            continue

        stats = process_week(
            week_label=week_label,
            week_videos=week_videos,
            backfill_dir=backfill_dir,
            config=config,
            dry_run=args.dry_run,
            per_channel_limit=args.per_channel_limit,
            max_videos_per_week=args.max_videos_per_week,
            sleep_between_videos=args.sleep_between_videos,
            browser_op_timeout=args.browser_op_timeout,
            refresh_before_date=refresh_before_date,
        )
        all_stats.append(stats)

        print(
            f"  → Week {week_label}: ok={stats['ok']}  "
            f"skipped={stats['skipped']}  failed={stats['failed']}",
            flush=True,
        )

        if args.sleep_between_weeks > 0 and week_idx < len(all_weeks) - 1:
            time.sleep(args.sleep_between_weeks)

    # ---- Summary ----
    real_stats = [recount_backfill_week(backfill_dir, s["week"]) for s in all_stats]
    total_ok = sum(s.get("ok", 0) for s in real_stats)
    total_failed = sum(s.get("failed", 0) for s in real_stats)
    total_skipped = sum(s.get("skipped", 0) for s in real_stats)

    summary: dict[str, Any] = {
        "schema": "youtube-weekly-backfill-summary-v1",
        "completed_at": iso_z(),
        "week_range": f"{end_week} — {start_week}",
        "weeks_processed": len(real_stats),
        "total_ok": total_ok,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "per_week": real_stats,
    }

    summary_path = backfill_dir / "backfill-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n{'='*60}", flush=True)
    print(f"BACKFILL COMPLETE", flush=True)
    print(f"  ok={total_ok}  failed={total_failed}  skipped={total_skipped}", flush=True)
    print(f"  Output : {backfill_dir}/weeks/", flush=True)
    print(f"  Summary: {summary_path}", flush=True)
    print(f"{'='*60}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
