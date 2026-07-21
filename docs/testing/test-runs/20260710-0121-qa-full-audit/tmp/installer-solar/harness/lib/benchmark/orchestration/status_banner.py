"""AP-3: main-status banner for benchmark run summary.

S04 N3: render_banner() reads latest-terminal-bench-2.json and returns
a one-line summary string <=80 chars.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _latest_json_path() -> Path:
    """Return path to the latest benchmark run JSON."""
    env = os.environ.get("SOLAR_BENCH_REPORTS_DIR")
    if env:
        base = Path(env)
    else:
        base = Path.home() / ".solar" / "harness" / "reports" / "benchmark"
    return base / "latest-terminal-bench-2.json"


def render_banner() -> str:
    """Return a one-line benchmark summary for main-status display.

    With run:   'Benchmark: verdict=ok score=0.83 5/6 tasks passed (2026-05-21)'
    Without run: 'Benchmark: no recent benchmark run'
    """
    latest = _latest_json_path()
    if not latest.is_file():
        return "Benchmark: no recent benchmark run"

    try:
        with latest.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return "Benchmark: no recent benchmark run"

    verdict = data.get("verdict", "unknown")
    score = data.get("score")
    pass_count = data.get("pass_count", 0)
    fail_count = data.get("fail_count", 0)
    total = pass_count + fail_count
    started = data.get("started_at", "")

    # Extract date portion from started_at (e.g. "2026-05-21T06:00:00Z" → "2026-05-21")
    date_str = started[:10] if len(started) >= 10 else started

    score_str = f"{score:.2f}" if score is not None else "N/A"
    line = f"Benchmark: verdict={verdict} score={score_str} {pass_count}/{total} tasks passed ({date_str})"

    # Truncate to 80 chars if needed
    if len(line) > 80:
        line = line[:77] + "..."

    return line


if __name__ == "__main__":
    print(render_banner())
