#!/usr/bin/env python3
"""
ThunderOMLX Cache Advisor Report — read-only warm path metrics snapshot.

Collects (all read-only, zero mutations):
  - hot_cache size and paged-SSD cache paths from running process args
  - unsafe feature guard status (partial-block cache, approx-skip, full-skip)
  - hit evidence from recent omlx log (Cache HIT lines + hit-ratio lines)
  - cached_tokens / TTFT / total_time from latest prewarm JSON report
  - RAID0 cache directory sizes
  - DB-backed warm-path metrics via CacheTuningAdvisor.generate_warm_path_report()

Writes: monitor-reports/thunderomlx-cache-advisor-<TS>.json
        monitor-reports/thunderomlx-cache-advisor-<TS>.md
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
LOG_PATH = Path.home() / "ThunderOMLX" / "omlx-8002.log"
MONITOR_DIR = Path.home() / ".solar" / "harness" / "monitor-reports"
ADVISOR_DB = Path.home() / ".cache" / "thunderomlx" / "adaptive_cache.db"
THUNDEROMLX_SRC = Path.home() / "ThunderOMLX" / "src"

RAID0_CACHE_ROOT = Path("/Volumes/RAID0-Main/omlx-cache")
LOG_TAIL_LINES = 2000


# ── helpers ────────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""


def _ps_omlx_args() -> str:
    """Return the full command line of the running omlx serve process."""
    out = _run(["ps", "aux"])
    for line in out.splitlines():
        if "omlx serve" in line and "grep" not in line:
            return line
    return ""


def collect_process_info() -> dict:
    """Extract hot_cache size, SSD cache dir, and feature flags from process args."""
    cmdline = _ps_omlx_args()
    if not cmdline:
        return {"status": "not_running"}

    hot_cache = "unknown"
    ssd_cache_dir = "unknown"
    ssd_cache_max = "unknown"

    m = re.search(r"--hot-cache-max-size\s+(\S+)", cmdline)
    if m:
        hot_cache = m.group(1)

    m = re.search(r"--paged-ssd-cache-dir\s+(\S+)", cmdline)
    if m:
        ssd_cache_dir = m.group(1)

    m = re.search(r"--paged-ssd-cache-max-size\s+(\S+)", cmdline)
    if m:
        ssd_cache_max = m.group(1)

    return {
        "status": "running",
        "hot_cache_max_size": hot_cache,
        "paged_ssd_cache_dir": ssd_cache_dir,
        "paged_ssd_cache_max_size": ssd_cache_max,
    }


def collect_unsafe_feature_guards() -> dict:
    """
    Detect whether unsafe warm-path features are enabled or disabled.

    Sources: recent log lines (authoritative for runtime state).
    Features: approximate-skip, partial-block cache, full-skip.
    """
    if not LOG_PATH.exists():
        return {"status": "log_unavailable"}

    tail = _run(["tail", "-n", str(LOG_TAIL_LINES), str(LOG_PATH)])

    approx_skip_disabled = "APPROXIMATE SKIP disabled" in tail
    approx_skip_enabled = "APPROXIMATE SKIP:" in tail and "disabled" not in _last_match(
        tail, r"APPROXIMATE SKIP[^\n]*"
    )
    partial_block_disabled = "Skipping partial block cache" in tail
    full_skip_active = "FULL SKIP" in tail and "disabled" not in tail

    return {
        "approximate_skip": "disabled" if approx_skip_disabled else (
            "enabled" if approx_skip_enabled else "not_observed"
        ),
        "partial_block_cache": "disabled" if partial_block_disabled else "not_observed",
        "full_skip": "enabled" if full_skip_active else "disabled",
        "guard_summary": (
            "ALL unsafe features disabled ✓"
            if (approx_skip_disabled and partial_block_disabled and not full_skip_active)
            else "WARNING: one or more unsafe features may be active"
        ),
    }


def _last_match(text: str, pattern: str) -> str:
    matches = re.findall(pattern, text)
    return matches[-1] if matches else ""


def collect_log_hit_evidence() -> dict:
    """Parse recent log for Cache HIT lines and hit-ratio lines."""
    if not LOG_PATH.exists():
        return {"status": "log_unavailable"}

    tail = _run(["tail", "-n", str(LOG_TAIL_LINES), str(LOG_PATH)])

    # Count HIT/MISS events
    hit_lines = [l for l in tail.splitlines() if "Cache HIT at block" in l]
    miss_lines = [l for l in tail.splitlines() if "Cache MISS" in l]
    ssd_io_lines = [l for l in tail.splitlines() if "blocks need SSD I/O" in l]
    hot_cache_lines = [l for l in tail.splitlines() if "found in hot cache" in l]

    # Extract last seen hit_ratio percentage
    ratios = re.findall(r"cache_hit_ratio=(\d+\.\d+)%", tail)
    last_ratio = float(ratios[-1]) if ratios else None

    # max cached_tokens seen from HIT lines
    token_counts = re.findall(r"cached_tokens=(\d+)", tail)
    max_cached = max(int(t) for t in token_counts) if token_counts else 0

    # Batch load stats: extract "X blocks need SSD I/O"
    ssd_io_needed = []
    for line in ssd_io_lines:
        m = re.search(r"(\d+) blocks need SSD I/O", line)
        if m:
            ssd_io_needed.append(int(m.group(1)))

    hot_cache_hits = []
    for line in hot_cache_lines:
        m = re.search(r"All (\d+) blocks found in hot cache", line)
        if m:
            hot_cache_hits.append(int(m.group(1)))

    return {
        "hit_line_count": len(hit_lines),
        "miss_line_count": len(miss_lines),
        "last_hit_ratio_pct": last_ratio,
        "max_cached_tokens_seen": max_cached,
        "hot_cache_hits": len(hot_cache_hits),
        "hot_cache_blocks_served": sum(hot_cache_hits),
        "ssd_io_events": len(ssd_io_needed),
        "ssd_blocks_fetched": sum(ssd_io_needed),
        "hit_evidence": "confirmed" if hit_lines else "none_in_window",
    }


def collect_prewarm_metrics() -> dict:
    """Read the latest prewarm JSON report and extract per-pane metrics."""
    jsons = sorted(MONITOR_DIR.glob("thunderomlx-four-pane-prewarm-*.json"))
    if not jsons:
        return {"status": "no_prewarm_report"}

    latest = jsons[-1]
    try:
        data = json.loads(latest.read_text())
    except Exception as e:
        return {"status": "error", "error": str(e)}

    panes = data.get("panes", [])
    summary: list[dict] = []
    for p in panes:
        entry = {
            "pane_index": p.get("pane_index"),
            "prompt_hash": p.get("prompt_hash"),
            "prompt_chars": p.get("prompt_chars"),
            "status": p.get("status"),
        }
        for phase in ("warm", "verify"):
            ph = p.get(phase, {})
            entry[f"{phase}_cached_tokens"] = ph.get("cached_tokens")
            entry[f"{phase}_ttft_s"] = ph.get("prompt_eval_duration")
            entry[f"{phase}_total_s"] = ph.get("total_time")
        summary.append(entry)

    return {
        "source_file": latest.name,
        "started_at": data.get("started_at"),
        "pane_count": len(panes),
        "panes": summary,
    }


def collect_cache_dir_sizes() -> dict:
    """Measure RAID0 cache directory sizes (du -sm, non-mutating)."""
    result: dict = {"raid0_root": str(RAID0_CACHE_ROOT)}
    if not RAID0_CACHE_ROOT.exists():
        result["status"] = "not_mounted"
        return result

    subdirs: dict[str, int] = {}
    for child in sorted(RAID0_CACHE_ROOT.iterdir()):
        if child.is_dir():
            out = _run(["du", "-sm", str(child)])
            m = re.match(r"(\d+)\s", out)
            subdirs[child.name] = int(m.group(1)) if m else 0

    out = _run(["du", "-sm", str(RAID0_CACHE_ROOT)])
    m = re.match(r"(\d+)\s", out)
    total_mb = int(m.group(1)) if m else 0

    result.update({
        "status": "ok",
        "subdirs_mb": subdirs,
        "total_mb": total_mb,
        "total_gb": round(total_mb / 1024, 2),
    })
    return result


def collect_db_warm_path() -> dict:
    """Call CacheTuningAdvisor.generate_warm_path_report() (read-only DB query).

    Uses importlib.util to load cache_tuning_advisor.py directly from its file path,
    bypassing omlx/__init__.py.  That __init__ eagerly imports scheduler.py →
    mlx_lm.generate → transformers → torch → torch's bundled libomp.dylib, which
    conflicts with numpy's already-loaded /opt/homebrew/Cellar/libomp/.../libomp.dylib
    and causes OMP Error #15 / Abort trap: 6 on macOS.

    cache_tuning_advisor.py itself only uses stdlib (sqlite3, threading, time,
    logging, pathlib, typing, random), so direct file loading is safe.
    """
    if not ADVISOR_DB.exists():
        return {"status": "db_not_found", "path": str(ADVISOR_DB)}

    import importlib.util

    advisor_module_path = THUNDEROMLX_SRC / "omlx" / "cache_tuning_advisor.py"
    if not advisor_module_path.exists():
        return {
            "status": "error",
            "error": f"cache_tuning_advisor.py not found at {advisor_module_path}",
            "db_path": str(ADVISOR_DB),
        }

    try:
        spec = importlib.util.spec_from_file_location(
            "cache_tuning_advisor_isolated",
            str(advisor_module_path),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        CacheTuningAdvisor = mod.CacheTuningAdvisor

        advisor = CacheTuningAdvisor(str(ADVISOR_DB))
        report = advisor.generate_warm_path_report(agent_id=None, last_n_requests=100)
        report["db_path"] = str(ADVISOR_DB)
        return report
    except Exception as e:
        return {"status": "error", "error": str(e), "db_path": str(ADVISOR_DB)}


def generate_recommendation(report: dict) -> dict:
    """Derive a human-readable recommendation from the collected data."""
    proc = report.get("process", {})
    guards = report.get("unsafe_feature_guards", {})
    db = report.get("db_warm_path", {})
    log_ev = report.get("log_hit_evidence", {})

    items: list[str] = []
    status = "ok"

    # 1. Unsafe features
    guard_ok = guards.get("guard_summary", "").startswith("ALL unsafe features disabled")
    if not guard_ok:
        items.append("⚠️  Unsafe features may be active — review guard_summary before enabling any warm-path feature.")
        status = "warning"
    else:
        items.append("✅ All unsafe features confirmed disabled. Safe to continue normal operation.")

    # 2. Hot cache / SSD path
    hot = proc.get("hot_cache_max_size", "unknown")
    ssd = proc.get("paged_ssd_cache_dir", "unknown")
    if proc.get("status") == "running":
        items.append(f"✅ Server running — hot_cache={hot}, SSD cache dir={ssd}.")
    else:
        items.append("ℹ️  omlx serve process not detected. Start the server to collect live cache metrics.")

    # 3. DB warm path stats
    if db.get("status") == "ok":
        avg_hit = db.get("cache_hit", {}).get("avg", 0.0)
        sample_n = db.get("sample_count", 0)
        if avg_hit >= 0.80:
            items.append(
                f"✅ DB warm-path: avg cache_hit_ratio={avg_hit:.1%} over {sample_n} samples — "
                f"cache warm path is healthy."
            )
        elif avg_hit >= 0.50:
            items.append(
                f"⚠️  DB warm-path: avg cache_hit_ratio={avg_hit:.1%} over {sample_n} samples — "
                f"consider increasing --hot-cache-max-size or reviewing prompt stability."
            )
            status = "warning"
        else:
            items.append(
                f"⚠️  DB warm-path: avg cache_hit_ratio={avg_hit:.1%} over {sample_n} samples — "
                f"low hit ratio; cache may not be primed. Run prewarm before heavy inference."
            )
            status = "warning"
    elif db.get("status") == "no_data":
        items.append("ℹ️  No inference samples in advisor DB yet — cache hit analysis not available.")
    else:
        items.append(f"ℹ️  Advisor DB status: {db.get('status')} — {db.get('error', '')}.")

    # 4. Log evidence
    hit_ev = log_ev.get("hit_evidence", "none_in_window")
    if hit_ev == "confirmed":
        items.append(
            f"✅ Log evidence: {log_ev.get('hit_line_count', 0)} Cache HIT lines found in last "
            f"{LOG_TAIL_LINES} log lines."
        )
    else:
        items.append(
            "ℹ️  No Cache HIT lines in recent log window. Warm the cache with the prewarm script "
            "before expecting hit evidence."
        )

    return {"status": status, "items": items}


# ── report assembly ────────────────────────────────────────────────────────

def build_report() -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report: dict = {
        "report_type": "cache_advisor_warm_path",
        "generated_at": ts,
        "process": collect_process_info(),
        "unsafe_feature_guards": collect_unsafe_feature_guards(),
        "log_hit_evidence": collect_log_hit_evidence(),
        "prewarm_metrics": collect_prewarm_metrics(),
        "cache_dir_sizes": collect_cache_dir_sizes(),
        "db_warm_path": collect_db_warm_path(),
        "note": (
            "Read-only report. No server parameters, cache config, "
            "or DB rows were mutated by this script."
        ),
    }
    report["recommendation"] = generate_recommendation(report)
    return report


def render_md(report: dict) -> str:
    ts = report["generated_at"]
    proc = report["process"]
    guards = report["unsafe_feature_guards"]
    log_ev = report["log_hit_evidence"]
    prewarm = report["prewarm_metrics"]
    dirs = report["cache_dir_sizes"]
    db = report["db_warm_path"]

    lines: list[str] = [
        f"# ThunderOMLX Cache Advisor — Warm Path Report",
        f"",
        f"Generated: `{ts}` | Read-only snapshot, zero mutations.",
        f"",
        f"---",
        f"",
        f"## 1. Process Config",
        f"",
        f"| Key | Value |",
        f"|-----|-------|",
        f"| Status | `{proc.get('status', 'unknown')}` |",
        f"| hot_cache_max_size | `{proc.get('hot_cache_max_size', 'N/A')}` |",
        f"| paged_ssd_cache_dir | `{proc.get('paged_ssd_cache_dir', 'N/A')}` |",
        f"| paged_ssd_cache_max_size | `{proc.get('paged_ssd_cache_max_size', 'N/A')}` |",
        f"",
        f"---",
        f"",
        f"## 2. Unsafe Feature Guard Status",
        f"",
        f"| Feature | Status |",
        f"|---------|--------|",
        f"| approximate_skip | `{guards.get('approximate_skip', 'N/A')}` |",
        f"| partial_block_cache | `{guards.get('partial_block_cache', 'N/A')}` |",
        f"| full_skip | `{guards.get('full_skip', 'N/A')}` |",
        f"",
        f"**Guard summary:** {guards.get('guard_summary', 'N/A')}",
        f"",
        f"---",
        f"",
        f"## 3. Log Hit Evidence (last {LOG_TAIL_LINES} lines)",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| hit_evidence | `{log_ev.get('hit_evidence', 'N/A')}` |",
        f"| hit_line_count | `{log_ev.get('hit_line_count', 0)}` |",
        f"| last_hit_ratio_pct | `{log_ev.get('last_hit_ratio_pct', 'N/A')}%` |",
        f"| max_cached_tokens_seen | `{log_ev.get('max_cached_tokens_seen', 0)}` |",
        f"| hot_cache_hits (batch loads) | `{log_ev.get('hot_cache_hits', 0)}` |",
        f"| hot_cache_blocks_served | `{log_ev.get('hot_cache_blocks_served', 0)}` |",
        f"| ssd_io_events | `{log_ev.get('ssd_io_events', 0)}` |",
        f"| ssd_blocks_fetched | `{log_ev.get('ssd_blocks_fetched', 0)}` |",
        f"",
        f"---",
        f"",
        f"## 4. Prewarm Metrics (latest run: `{prewarm.get('source_file', 'N/A')}`)",
        f"",
    ]

    panes = prewarm.get("panes", [])
    if panes:
        lines += [
            f"| Pane | Prompt Hash | Warm cached_tokens | Warm TTFT s | Warm total s"
            f" | Verify cached_tokens | Verify TTFT s |",
            f"|------|-------------|-------------------|-------------|-------------|"
            f"---------------------|---------------|",
        ]
        for p in panes:
            lines.append(
                f"| {p['pane_index']} | `{p.get('prompt_hash','?')}` "
                f"| {p.get('warm_cached_tokens','N/A')} "
                f"| {p.get('warm_ttft_s','N/A')} "
                f"| {p.get('warm_total_s','N/A')} "
                f"| {p.get('verify_cached_tokens','N/A')} "
                f"| {p.get('verify_ttft_s','N/A')} |"
            )
    else:
        lines.append("_No prewarm data available._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 5. Cache Directory Sizes (RAID0)",
        f"",
        f"Root: `{dirs.get('raid0_root', 'N/A')}` — status: `{dirs.get('status', 'N/A')}`",
        f"",
    ]

    subdirs = dirs.get("subdirs_mb", {})
    if subdirs:
        lines += [
            f"| Directory | Size (MB) |",
            f"|-----------|-----------|",
        ]
        for name, mb in subdirs.items():
            lines.append(f"| `{name}` | {mb} MB |")
        lines.append(f"| **Total** | **{dirs.get('total_mb', 0)} MB "
                     f"({dirs.get('total_gb', 0)} GB)** |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 6. DB-Backed Warm Path Stats (CacheTuningAdvisor — read-only)",
        f"",
    ]

    if db.get("status") == "ok":
        ch = db.get("cache_hit", {})
        tm = db.get("timing_ms", {})
        sl = db.get("skip_logic_usage", {})
        lines += [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| sample_count | `{db.get('sample_count', 0)}` |",
            f"| avg_cache_hit_ratio | `{ch.get('avg', 0):.1%}` |",
            f"| min / max cache_hit_ratio | `{ch.get('min', 0):.1%}` / `{ch.get('max', 0):.1%}` |",
            f"| warm_hit_count (≥80%) | `{ch.get('warm_hit_count', 0)}` / `{db.get('sample_count', 0)}` |",
            f"| warm_hit_pct | `{ch.get('warm_hit_pct', 0)}%` |",
            f"| avg_ttft_ms | `{tm.get('avg_ttft', 0):.1f} ms` |",
            f"| avg_total_time_ms | `{tm.get('avg_total', 0):.1f} ms` |",
            f"| avg_cached_tokens | `{db.get('avg_cached_tokens', 0)}` |",
            f"| avg_padding_pct | `{db.get('avg_padding_pct', 0)}%` |",
            f"",
            f"Skip logic breakdown: {sl}",
        ]
    else:
        lines.append(f"DB status: `{db.get('status', 'unknown')}` — {db.get('error', '')}")

    rec = report.get("recommendation", {})
    lines += [
        f"",
        f"---",
        f"",
        f"## 7. Recommendation",
        f"",
        f"**Overall status:** `{rec.get('status', 'unknown')}`",
        f"",
    ]
    for item in rec.get("items", []):
        lines.append(f"- {item}")

    lines += [
        f"",
        f"---",
        f"",
        f"_{report['note']}_",
    ]
    return "\n".join(lines)


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    MONITOR_DIR.mkdir(parents=True, exist_ok=True)

    report = build_report()
    ts = report["generated_at"]

    json_path = MONITOR_DIR / f"thunderomlx-cache-advisor-{ts}.json"
    md_path = MONITOR_DIR / f"thunderomlx-cache-advisor-{ts}.md"
    # Fixed-name file for harness runner and sprint acceptance checks
    fixed_md_path = MONITOR_DIR / "thunderomlx-cache-advisor-report.md"

    md_content = render_md(report)
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(md_content)
    fixed_md_path.write_text(md_content)

    print(f"Report written:")
    print(f"  JSON:  {json_path}")
    print(f"  MD:    {md_path}")
    print(f"  Fixed: {fixed_md_path}")

    # Quick acceptance summary to stdout
    proc = report["process"]
    guards = report["unsafe_feature_guards"]
    dirs = report["cache_dir_sizes"]
    log_ev = report["log_hit_evidence"]

    print(f"\n=== Acceptance check ===")
    print(f"hot_cache_max_size : {proc.get('hot_cache_max_size', 'unknown')}")
    print(f"paged_ssd_cache_dir: {proc.get('paged_ssd_cache_dir', 'unknown')}")
    print(f"RAID0 total        : {dirs.get('total_gb', '?')} GB ({dirs.get('total_mb', '?')} MB)")
    print(f"Unsafe features    : {guards.get('guard_summary', 'unknown')}")
    print(f"Hit evidence       : {log_ev.get('hit_evidence', 'unknown')} "
          f"({log_ev.get('hit_line_count', 0)} HIT lines, "
          f"last ratio {log_ev.get('last_hit_ratio_pct', 'N/A')}%)")
    print(f"No mutations       : confirmed (read-only script)")


if __name__ == "__main__":
    main()
