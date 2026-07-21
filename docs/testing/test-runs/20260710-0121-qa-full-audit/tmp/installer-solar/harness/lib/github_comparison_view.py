"""GitHub dual-run comparison view for the /ai-influence status page.

Loads GitHub New and Legacy operator metadata from reports/github/ and
renders a side-by-side comparison with >= 4 dimensions:
  items_processed, report_quality, error_rate, duration_s

Gracefully degrades to New-only when Legacy data is absent.

Usage:
    from lib.github_comparison_view import build_comparison, render_comparison_html
    data = build_comparison(reports_dir)
    html = render_comparison_html(data)

Integration:
    Called by ai_influence_status_page.py to inject the GitHub comparison
    block via the {{GITHUB_COMPARISON}} template placeholder.
"""
from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HARNESS_ROOT = Path(os.environ.get("HARNESS_ROOT", Path.home() / ".solar" / "harness"))
DEFAULT_REPORTS_DIR = HARNESS_ROOT / "reports"

# Sub-directories within reports/github/ for each variant
_NEW_SUBDIR = "new"
_LEGACY_SUBDIR = "legacy"


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else "N/A"), quote=True)


@dataclass
class GitHubRunMetrics:
    """Normalised metrics for one GitHub operator run."""

    variant: str  # "new" | "legacy"
    run_status: str = "no_data"
    items_processed: int | None = None
    items_attempted: int | None = None
    report_quality: float | None = None   # 0.0–1.0
    error_rate: float | None = None       # errors / attempted, 0.0–1.0
    duration_s: float | None = None
    last_run: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GitHubComparisonData:
    """Comparison data for both GitHub variants."""

    new_run: GitHubRunMetrics
    legacy_run: GitHubRunMetrics | None  # None → degrade to New-only


# ── metadata loading ──────────────────────────────────────────────────────────


def _load_metadata(path: Path) -> dict[str, Any] | None:
    """Load a metadata.json; return None if absent or unreadable."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _derive_metrics(variant: str, meta: dict[str, Any] | None) -> GitHubRunMetrics:
    """Convert raw metadata dict to GitHubRunMetrics."""
    if meta is None:
        return GitHubRunMetrics(variant=variant)

    run_status = meta.get("run_status", "no_data")
    items_processed = meta.get("items_processed") or meta.get("processed_count")
    items_attempted = meta.get("items_attempted") or meta.get("source_count") or items_processed
    errors = meta.get("errors", [])

    # report_quality: 1.0 if succeeded + artifacts present, scales down otherwise
    has_artifacts = bool(meta.get("artifacts"))
    if run_status == "succeeded" and has_artifacts:
        quality = 1.0
    elif run_status == "succeeded":
        quality = 0.8
    elif run_status in ("failed", "timeout"):
        quality = 0.0
    elif run_status == "running":
        quality = None
    else:
        quality = None

    # error_rate
    error_rate: float | None = None
    if items_attempted and items_attempted > 0:
        error_count = len(errors) if errors else meta.get("error_count", 0)
        error_rate = round(error_count / items_attempted, 4)
    elif run_status in ("failed", "timeout"):
        error_rate = 1.0

    duration_s = meta.get("duration_seconds") or meta.get("duration_s")
    last_run = meta.get("started_at") or meta.get("last_run")

    return GitHubRunMetrics(
        variant=variant,
        run_status=run_status,
        items_processed=items_processed,
        items_attempted=items_attempted,
        report_quality=quality,
        error_rate=error_rate,
        duration_s=duration_s,
        last_run=last_run,
        artifacts=meta.get("artifacts", {}),
        errors=errors,
        raw_metadata=meta,
    )


def build_comparison(reports_dir: Path | None = None) -> GitHubComparisonData:
    """Build comparison data from the reports directory.

    Looks for:
        reports/github/new/metadata.json   → New variant
        reports/github/legacy/metadata.json → Legacy variant
        reports/github/metadata.json        → fallback (treated as New)

    Args:
        reports_dir: Base reports directory. Defaults to HARNESS_ROOT/reports.

    Returns:
        GitHubComparisonData with new_run and optional legacy_run.
    """
    base = reports_dir if reports_dir is not None else DEFAULT_REPORTS_DIR
    github_dir = base / "github"

    # Try structured new/legacy sub-dirs first, then flat fallback
    new_meta = (
        _load_metadata(github_dir / _NEW_SUBDIR / "metadata.json")
        or _load_metadata(github_dir / "metadata.json")
    )
    legacy_meta = _load_metadata(github_dir / _LEGACY_SUBDIR / "metadata.json")

    new_run = _derive_metrics("new", new_meta)
    legacy_run = _derive_metrics("legacy", legacy_meta) if legacy_meta is not None else None

    return GitHubComparisonData(new_run=new_run, legacy_run=legacy_run)


# ── HTML rendering ────────────────────────────────────────────────────────────

_COMPARISON_DIMENSIONS = [
    ("items_processed", "Items Processed", lambda m: str(m.items_processed) if m.items_processed is not None else "—"),
    ("report_quality",  "Report Quality",  lambda m: f"{m.report_quality:.0%}" if m.report_quality is not None else "—"),
    ("error_rate",      "Error Rate",      lambda m: f"{m.error_rate:.1%}" if m.error_rate is not None else "—"),
    ("duration_s",      "Run Duration",    lambda m: _fmt_duration(m.duration_s)),
]


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _status_class(run_status: str) -> str:
    return {
        "succeeded": "good",
        "running": "warn",
        "failed": "bad",
        "timeout": "bad",
        "cancelled": "muted",
    }.get(run_status, "muted")


def _render_run_column(metrics: GitHubRunMetrics, label: str) -> str:
    """Render a single run column (New or Legacy)."""
    status_cls = _status_class(metrics.run_status)
    last_run = esc(metrics.last_run or "Never")

    rows = ""
    for dim_id, dim_label, getter in _COMPARISON_DIMENSIONS:
        value = getter(metrics)
        # Highlight bad error_rate
        cell_cls = ""
        if dim_id == "error_rate" and metrics.error_rate is not None and metrics.error_rate > 0.1:
            cell_cls = ' class="bad"'
        elif dim_id == "report_quality" and metrics.report_quality is not None and metrics.report_quality < 0.5:
            cell_cls = ' class="bad"'
        rows += f'<tr><td class="dim-label">{esc(dim_label)}</td><td{cell_cls}>{esc(value)}</td></tr>'

    errors_html = ""
    if metrics.errors:
        items = "".join(
            f'<li>{esc(e.get("message", str(e)))}</li>'
            for e in metrics.errors[:3]
        )
        if len(metrics.errors) > 3:
            items += f'<li>+{len(metrics.errors) - 3} more</li>'
        errors_html = f'<ul class="cmp-errors">{items}</ul>'

    return f"""
    <div class="cmp-col" data-variant="{esc(metrics.variant)}">
      <div class="cmp-col-header">
        <span class="cmp-label">{esc(label)}</span>
        <span class="status-dot {status_cls}" title="{esc(metrics.run_status)}"></span>
        <span class="cmp-status-text">{esc(metrics.run_status)}</span>
      </div>
      <div class="cmp-meta">Last run: {last_run}</div>
      <table class="cmp-table">
        <tbody>{rows}</tbody>
      </table>
      {f'<div class="cmp-error-section"><span class="cmp-error-label">Errors</span>{errors_html}</div>' if errors_html else ''}
    </div>"""


def render_comparison_html(data: GitHubComparisonData) -> str:
    """Render the GitHub comparison block as an HTML fragment.

    When legacy_run is None, renders a degraded single-column view.

    Args:
        data: GitHubComparisonData from build_comparison().

    Returns:
        HTML fragment (no outer <html>/<body> tags).
    """
    new_col = _render_run_column(data.new_run, "GitHub New")

    if data.legacy_run is None:
        # Degraded: Legacy absent
        legacy_col = """
    <div class="cmp-col cmp-col--absent" data-variant="legacy">
      <div class="cmp-col-header">
        <span class="cmp-label">GitHub Legacy</span>
        <span class="status-dot muted"></span>
        <span class="cmp-status-text muted">not available</span>
      </div>
      <div class="cmp-meta cmp-absent-note">Legacy data not present. Showing New only.</div>
    </div>"""
        layout_cls = "cmp-layout--degraded"
    else:
        legacy_col = _render_run_column(data.legacy_run, "GitHub Legacy")
        layout_cls = ""

    return f"""<div class="github-comparison">
  <h3 class="cmp-title">🐙 GitHub Dual-Run Comparison</h3>
  <div class="cmp-layout {layout_cls}">
    {new_col}
    {legacy_col}
  </div>
</div>
<style>
.github-comparison{{margin:18px 0}}
.cmp-title{{font-size:15px;color:var(--accent,#6cc4ff);margin:0 0 10px 0}}
.cmp-layout{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.cmp-layout--degraded{{grid-template-columns:1fr 1fr}}
.cmp-col{{background:var(--panel-2,#20253b);border:1px solid var(--border,#2c3350);border-radius:10px;padding:14px}}
.cmp-col--absent{{opacity:.55}}
.cmp-col-header{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.cmp-label{{font-weight:600;font-size:14px;color:#fff}}
.status-dot{{width:9px;height:9px;border-radius:50%;flex-shrink:0}}
.status-dot.good{{background:var(--good,#7ee787)}}
.status-dot.bad{{background:var(--bad,#ff8585)}}
.status-dot.warn{{background:var(--warn,#f0b86e)}}
.status-dot.muted{{background:var(--muted,#9aa3bf)}}
.cmp-status-text{{font-size:12px;color:var(--muted,#9aa3bf)}}
.cmp-status-text.muted{{color:var(--muted,#9aa3bf)}}
.cmp-meta{{font-size:12px;color:var(--muted,#9aa3bf);margin-bottom:10px}}
.cmp-absent-note{{font-style:italic}}
.cmp-table{{width:100%;border-collapse:collapse;font-size:12px}}
.cmp-table td{{padding:4px 6px;border-bottom:1px solid var(--border,#2c3350)}}
.cmp-table td.dim-label{{color:var(--muted,#9aa3bf);white-space:nowrap;width:50%}}
.cmp-table td.bad{{color:var(--bad,#ff8585)}}
.cmp-error-section{{margin-top:10px;font-size:12px}}
.cmp-error-label{{color:var(--bad,#ff8585);font-weight:600}}
.cmp-errors{{margin:4px 0 0 0;padding-left:16px;color:var(--bad,#ff8585)}}
@media(max-width:600px){{.cmp-layout{{grid-template-columns:1fr}}}}
</style>"""


# ── convenience: update status page template ─────────────────────────────────


def inject_into_status_html(status_html: str, reports_dir: Path | None = None) -> str:
    """Replace {{GITHUB_COMPARISON}} placeholder in status page HTML.

    If the placeholder is absent, appends the block before </body>.

    Args:
        status_html: Full HTML string from ai_influence_status_page.render_html().
        reports_dir: Passed to build_comparison().

    Returns:
        HTML string with comparison block injected.
    """
    data = build_comparison(reports_dir)
    block = render_comparison_html(data)

    if "{{GITHUB_COMPARISON}}" in status_html:
        return status_html.replace("{{GITHUB_COMPARISON}}", block)

    # Fallback: insert before </body>
    return status_html.replace("</body>", f"{block}\n</body>", 1)
