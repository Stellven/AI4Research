#!/usr/bin/env python3
"""Dashboard data gatherer and HTML renderer for Solar Knowledge ingest."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import knowledge_ingest_registry as registry
import knowledge_ingest_health as health


DEFAULT_PAUSE_FILE = Path.home() / "Knowledge" / "_registry" / "extract_queue.paused.json"


def gather_dashboard(db_path: Path | str) -> dict[str, Any]:
    """Gather all dashboard data: watermarks, state_counts, source_coverage, circuit_breaker, extract_metrics."""
    db = Path(db_path)
    registry.migrate(db)

    with registry.connect(db) as conn:
        # Watermarks
        watermarks = {}
        for row in conn.execute("SELECT layer, last_indexed_ts, pending_count, failed_count, last_batch_ts FROM watermarks ORDER BY layer"):
            watermarks[row["layer"]] = {
                "last_indexed_ts": row["last_indexed_ts"],
                "pending_count": row["pending_count"],
                "failed_count": row["failed_count"],
                "last_batch_ts": row["last_batch_ts"],
            }

        # State counts
        state_counts = {}
        for row in conn.execute("SELECT current_state, COUNT(*) AS n FROM documents GROUP BY current_state ORDER BY current_state"):
            state_counts[row["current_state"]] = row["n"]

        # Source coverage (per source_kind)
        source_coverage = {}
        for row in conn.execute("SELECT source_kind, current_state, COUNT(*) AS n FROM documents GROUP BY source_kind, current_state ORDER BY source_kind"):
            kind = row["source_kind"]
            if kind not in source_coverage:
                source_coverage[kind] = {"total": 0, "states": {}}
            source_coverage[kind]["total"] += row["n"]
            source_coverage[kind]["states"][row["current_state"]] = row["n"]

        # Extract metrics
        total_jobs = conn.execute("SELECT COUNT(*) FROM extract_jobs").fetchone()[0]
        completed_jobs = conn.execute("SELECT COUNT(*) FROM extract_jobs WHERE state IN ('completed', 'legacy_imported', 'DONE')").fetchone()[0]
        failed_jobs = conn.execute("SELECT COUNT(*) FROM extract_jobs WHERE state LIKE '%failed%'").fetchone()[0]
        total_outputs = conn.execute("SELECT COUNT(*) FROM extract_outputs").fetchone()[0]
        avg_repair = conn.execute("SELECT AVG(repair_count) FROM extract_jobs WHERE repair_count > 0").fetchone()[0]
        extract_metrics = {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "total_outputs": total_outputs,
            "avg_repair_count": round(avg_repair or 0, 2),
        }

    # Circuit breaker
    circuit_breaker = {"paused": False, "pause_file": str(DEFAULT_PAUSE_FILE)}
    if DEFAULT_PAUSE_FILE.exists():
        try:
            circuit_breaker["paused"] = True
            circuit_breaker["details"] = json.loads(DEFAULT_PAUSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Health audit
    try:
        audit_result = health.audit(db)
    except Exception:
        audit_result = {"ok": False, "error": "audit unavailable"}

    return {
        "ok": True,
        "watermarks": watermarks,
        "state_counts": state_counts,
        "source_coverage": source_coverage,
        "circuit_breaker": circuit_breaker,
        "extract_metrics": extract_metrics,
        "audit": audit_result,
        "generated_at": registry.now_iso(),
    }


def render_html(dashboard: dict[str, Any]) -> str:
    """Render dashboard data as a self-contained HTML page."""
    watermarks = dashboard.get("watermarks", {})
    state_counts = dashboard.get("state_counts", {})
    source_coverage = dashboard.get("source_coverage", {})
    cb = dashboard.get("circuit_breaker", {})
    metrics = dashboard.get("extract_metrics", {})
    generated = dashboard.get("generated_at", "N/A")

    def _esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Watermarks table
    wm_rows = ""
    for layer, info in watermarks.items():
        wm_rows += f"<tr><td>{_esc(layer)}</td><td>{info.get('last_indexed_ts', 'N/A')}</td><td>{info.get('pending_count', 0)}</td><td>{info.get('failed_count', 0)}</td></tr>\n"

    # State counts
    sc_rows = ""
    for state, count in state_counts.items():
        sc_rows += f"<tr><td>{_esc(state)}</td><td>{count}</td></tr>\n"

    # Source coverage
    src_rows = ""
    for kind, info in source_coverage.items():
        total = info.get("total", 0)
        states_str = ", ".join(f"{s}: {c}" for s, c in info.get("states", {}).items())
        src_rows += f"<tr><td>{_esc(kind)}</td><td>{total}</td><td>{_esc(states_str)}</td></tr>\n"

    # Circuit breaker status
    cb_status = "PAUSED" if cb.get("paused") else "OK"
    cb_color = "#e74c3c" if cb.get("paused") else "#27ae60"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Solar Knowledge Dashboard</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #1a1a2e; color: #e0e0e0; }}
h1 {{ color: #00d2ff; }}
h2 {{ color: #7fdbff; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
th, td {{ border: 1px solid #333; padding: 8px 12px; text-align: left; }}
th {{ background: #16213e; color: #00d2ff; }}
tr:nth-child(even) {{ background: #1a1a3e; }}
.badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; color: white; }}
.footer {{ margin-top: 2rem; color: #666; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>Solar Knowledge Ingest Dashboard</h1>
<p>Generated: {_esc(generated)}</p>

<h2>Circuit Breaker</h2>
<p>Status: <span class="badge" style="background: {cb_color}">{cb_status}</span></p>

<h2>3-Layer Watermarks</h2>
<table>
<tr><th>Layer</th><th>Last Indexed</th><th>Pending</th><th>Failed</th></tr>
{wm_rows}
</table>

<h2>State Distribution</h2>
<table>
<tr><th>State</th><th>Count</th></tr>
{sc_rows}
</table>

<h2>Source Coverage</h2>
<table>
<tr><th>Source Kind</th><th>Total</th><th>States</th></tr>
{src_rows}
</table>

<h2>Extract Metrics</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Jobs</td><td>{metrics.get('total_jobs', 0)}</td></tr>
<tr><td>Completed Jobs</td><td>{metrics.get('completed_jobs', 0)}</td></tr>
<tr><td>Failed Jobs</td><td>{metrics.get('failed_jobs', 0)}</td></tr>
<tr><td>Total Outputs</td><td>{metrics.get('total_outputs', 0)}</td></tr>
<tr><td>Avg Repair Count</td><td>{metrics.get('avg_repair_count', 0)}</td></tr>
</table>

<div class="footer">Solar Knowledge Ingest Dashboard</div>
</body>
</html>"""
