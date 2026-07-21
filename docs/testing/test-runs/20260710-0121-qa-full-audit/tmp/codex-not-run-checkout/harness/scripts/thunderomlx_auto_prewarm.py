#!/usr/bin/env python3
"""Automatic four-pane system prompt prewarm with health gate and idempotency.

Usage:
    python3 thunderomlx_auto_prewarm.py [options]

Options:
    --health-url URL      ThunderOMLX health endpoint (default: http://127.0.0.1:8002/health)
    --health-timeout SECS Seconds to wait for server ready (default: 120)
    --idle-minutes MINS   Skip if a prewarm ran within this many minutes (default: 5)
    --force               Bypass idle-minutes check and rerun unconditionally
    --session NAME        tmux session to inspect (default: solar-harness-lab:0)

This script:
  1. Skips if a prewarm already ran within --idle-minutes (idempotency).
  2. Skips if the tmux session does not exist (safe in non-harness environments).
  3. Polls /health until the server is ready or the timeout elapses.
  4. Delegates to thunderomlx_prewarm_four_pane.py for the actual prewarm.
  5. Writes a stamp file so callers know the last run time and status.
  6. Never prints or persists auth tokens.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
PREWARM_SCRIPT = SCRIPTS_DIR / "thunderomlx_prewarm_four_pane.py"
REPORT_DIR = Path.home() / ".solar" / "harness" / "monitor-reports"
STAMP_FILE = REPORT_DIR / "thunderomlx_prewarm.stamp"

DEFAULT_SESSION = "solar-harness-lab:0"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8002/health"
DEFAULT_HEALTH_TIMEOUT = 120.0  # seconds to wait for /health
DEFAULT_IDLE_MINUTES = 5.0      # skip if last run was within this window


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[auto-prewarm {ts}] {msg}", flush=True)


def _wait_for_health(url: str, timeout_s: float) -> bool:
    """Poll url until {"status":"healthy"} is returned or timeout elapses."""
    deadline = time.monotonic() + timeout_s
    poll_interval = 2.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read())
                    if body.get("status") == "healthy":
                        return True
        except Exception:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))
    return False


def _tmux_session_exists(session: str) -> bool:
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _read_stamp() -> dict:
    try:
        return json.loads(STAMP_FILE.read_text())
    except Exception:
        return {}


def _write_stamp(data: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STAMP_FILE.write_text(json.dumps(data, indent=2))


def _should_skip(idle_minutes: float) -> tuple[bool, str]:
    """Return (skip, reason). True means we should skip this run."""
    stamp = _read_stamp()
    last_run_str = stamp.get("last_run")
    if not last_run_str:
        return False, "no previous stamp"
    try:
        last_run = datetime.fromisoformat(last_run_str)
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        elapsed_minutes = (datetime.now(timezone.utc) - last_run).total_seconds() / 60.0
        if elapsed_minutes < idle_minutes:
            return True, f"last run {elapsed_minutes:.1f}m ago (< {idle_minutes:.0f}m threshold)"
    except Exception:
        pass
    return False, "previous stamp too old"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto prewarm ThunderOMLX four-pane system prompt cache"
    )
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL,
                        help="ThunderOMLX /health endpoint URL")
    parser.add_argument("--health-timeout", type=float, default=DEFAULT_HEALTH_TIMEOUT,
                        help="Seconds to wait for server readiness")
    parser.add_argument("--idle-minutes", type=float, default=DEFAULT_IDLE_MINUTES,
                        help="Skip if last run was within this many minutes (idempotency)")
    parser.add_argument("--force", action="store_true",
                        help="Bypass idle-minutes check and rerun unconditionally")
    parser.add_argument("--session", default=DEFAULT_SESSION,
                        help="tmux session whose panes hold the system prompts")
    args = parser.parse_args()

    # Gate 1: idempotency — skip if a recent run succeeded
    if not args.force:
        skip, reason = _should_skip(args.idle_minutes)
        if skip:
            _log(f"Skipping (idempotent): {reason}")
            return 0

    # Gate 2: tmux session must exist — safe no-op in non-harness environments
    if not _tmux_session_exists(args.session):
        _log(f"Skipping: tmux session '{args.session}' not found")
        return 0

    # Gate 3: wait for server health
    _log(f"Waiting for server ready at {args.health_url} (timeout {args.health_timeout:.0f}s) ...")
    if not _wait_for_health(args.health_url, args.health_timeout):
        _log(f"ERROR: Server not healthy after {args.health_timeout:.0f}s — aborting prewarm")
        _write_stamp({
            "last_run": datetime.now(timezone.utc).isoformat(),
            "status": "health_timeout",
            "session": args.session,
        })
        return 1

    _log("Server healthy. Running four-pane prewarm ...")

    # Verify the delegate script exists
    if not PREWARM_SCRIPT.exists():
        _log(f"ERROR: prewarm script not found: {PREWARM_SCRIPT}")
        return 1

    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(PREWARM_SCRIPT)],
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - start

    # Parse summary output (tokens are never in the delegate script's stdout)
    summary: dict = {}
    if result.stdout.strip():
        try:
            summary = json.loads(result.stdout)
        except json.JSONDecodeError:
            summary = {"raw_preview": result.stdout[:200]}

    stamp_data: dict = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if result.returncode == 0 else "error",
        "elapsed_s": round(elapsed, 3),
        "session": args.session,
        "json_report": summary.get("json_report"),
        "md_report": summary.get("md_report"),
    }
    _write_stamp(stamp_data)

    if result.returncode != 0:
        _log(f"ERROR: prewarm exited {result.returncode}: {result.stderr[:300]}")
        return result.returncode

    _log(f"Prewarm complete in {elapsed:.1f}s")

    # Emit per-pane summary (no tokens)
    for pane in summary.get("panes") or []:
        cached = pane.get("cached_tokens", "N/A")
        verify_s = pane.get("verify_s", "N/A")
        bad = pane.get("bad_chars", "N/A")
        phash = pane.get("prompt_hash", "")
        _log(
            f"  pane {pane.get('pane')}: status={pane.get('status')} "
            f"prompt_hash={phash} cached_tokens={cached} verify_s={verify_s} bad_chars={bad}"
        )

    if summary.get("json_report"):
        _log(f"Full report: {summary['json_report']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
