#!/usr/bin/env python3
"""AI Influence Status Page — generates /ai-influence status view.

This module reads operator metadata from the reports directory and generates
an HTML status page showing the current state of all AI Influence operators.

Usage:
    python -m lib.ai_influence_status_page generate > status.html
    python -m lib.ai_influence_status_page serve --port 8080
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# Default paths
HARNESS_ROOT = Path(os.environ.get("HARNESS_ROOT", Path.home() / ".solar" / "harness"))
DEFAULT_REPORTS_DIR = HARNESS_ROOT / "reports"
DEFAULT_TEMPLATE_DIR = HARNESS_ROOT / "templates"
DEFAULT_METADATA_FILE = DEFAULT_TEMPLATE_DIR / "ai_influence_metadata.json"


class RunStatus(str, Enum):
    """Valid run status values."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class OperatorCard:
    """Data for a single operator status card."""
    operator_id: str
    display_name: str
    icon: str
    run_status: RunStatus
    last_run: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    schedule_type: str = "daily"

    # Computed properties
    has_errors: bool = False
    duration_display: str = ""
    processed_ratio: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "operator_id": self.operator_id,
            "display_name": self.display_name,
            "icon": self.icon,
            "run_status": self.run_status.value if isinstance(self.run_status, RunStatus) else self.run_status,
            "last_run": self.last_run,
            "artifacts": self.artifacts,
            "stats": self.stats,
            "errors": self.errors,
            "schedule_type": self.schedule_type,
            "has_errors": self.has_errors,
            "duration_display": self.duration_display,
            "processed_ratio": self.processed_ratio,
        }


# Operator definitions
OPERATORS = {
    "x_social": {
        "display_name": "X / Twitter",
        "icon": "𝕏",
        "output_dir": "x-social",
        "schedule": "daily",
    },
    "github_new": {
        "display_name": "GitHub Trends (New)",
        "icon": "🐙",
        "output_dir": "github",
        "schedule": "daily",
    },
    "github_legacy": {
        "display_name": "GitHub Trends (Legacy)",
        "icon": "📜",
        "output_dir": "github",
        "schedule": "daily",
    },
    "hf_papers": {
        "display_name": "HF Papers",
        "icon": "🤗",
        "output_dir": "hf-papers",
        "schedule": "daily",
    },
    "youtube": {
        "display_name": "YouTube Influence",
        "icon": "📺",
        "output_dir": "youtube",
        "schedule": "daily",
    },
    "gemini": {
        "display_name": "Gemini Deep Research",
        "icon": "💎",
        "output_dir": "gemini",
        "schedule": "on_demand",
    },
}


def esc(value: Any) -> str:
    """HTML escape a value."""
    return html.escape(str(value if value is not None else "N/A"), quote=True)


def format_duration(seconds: float | None) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def format_timestamp(ts: str | None) -> str:
    """Format ISO timestamp to display string."""
    if not ts:
        return "N/A"
    try:
        dt_obj = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt_obj.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, AttributeError):
        return ts


def load_metadata(reports_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all metadata.json files from reports directory.

    Returns a dict mapping operator_id to metadata dict.
    """
    metadata: dict[str, dict[str, Any]] = {}

    for op_id, op_def in OPERATORS.items():
        output_dir = reports_dir / op_def["output_dir"]
        metadata_path = output_dir / "metadata.json"

        if not metadata_path.exists():
            # No metadata yet - create default no_data entry
            metadata[op_id] = {
                "operator": op_id,
                "run_status": "no_data",
                "last_run": None,
                "artifacts": {},
                "stats": {},
                "errors": [],
                "schedule_type": op_def["schedule"],
            }
            continue

        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata[op_id] = data
        except (json.JSONDecodeError, OSError) as e:
            metadata[op_id] = {
                "operator": op_id,
                "run_status": "error",
                "last_run": None,
                "artifacts": {},
                "stats": {},
                "errors": [{"message": f"Failed to load metadata: {e}"}],
                "schedule_type": op_def["schedule"],
            }

    return metadata


def build_cards(reports_dir: Path) -> list[OperatorCard]:
    """Build operator status cards from metadata.

    Args:
        reports_dir: Base reports directory.

    Returns:
        List of OperatorCard objects.
    """
    metadata = load_metadata(reports_dir)
    cards: list[OperatorCard] = []

    for op_id, op_def in OPERATORS.items():
        meta = metadata.get(op_id, {})

        # Determine run status
        run_status_str = meta.get("run_status", "no_data")
        try:
            run_status = RunStatus(run_status_str) if run_status_str in RunStatus._value2member_map_ else RunStatus.PENDING
        except ValueError:
            run_status = RunStatus.PENDING

        # Get last run timestamp
        last_run = meta.get("started_at") or meta.get("last_run")

        # Build artifacts dict
        artifacts = meta.get("artifacts", {})

        # Build stats
        stats = meta.get("stats", {})

        # Build errors
        errors = meta.get("errors", [])

        # Calculate derived properties
        duration = meta.get("duration_seconds")
        source_count = meta.get("source_count")
        processed_count = meta.get("processed_count")

        processed_ratio = ""
        if source_count and processed_count is not None:
            ratio = processed_count / source_count if source_count > 0 else 0
            processed_ratio = f"{processed_count}/{source_count} ({ratio:.0%})"

        card = OperatorCard(
            operator_id=op_id,
            display_name=op_def["display_name"],
            icon=op_def["icon"],
            run_status=run_status,
            last_run=last_run,
            artifacts=artifacts,
            stats=stats,
            errors=errors,
            schedule_type=meta.get("schedule_type", op_def["schedule"]),
            has_errors=bool(errors),
            duration_display=format_duration(duration),
            processed_ratio=processed_ratio,
        )

        cards.append(card)

    return cards


def render_html(cards: list[OperatorCard]) -> str:
    """Render the status page as HTML.

    Args:
        cards: List of OperatorCard objects.

    Returns:
        Complete HTML document as string.
    """
    template_path = HARNESS_ROOT / "templates" / "ai_influence.html"

    # Load template
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        # Fallback inline template
        template = get_fallback_template()

    # Build cards HTML
    cards_html = "\n".join(_render_card(card) for card in cards)

    # Build summary
    total = len(cards)
    succeeded = sum(1 for c in cards if c.run_status == RunStatus.SUCCEEDED)
    failed = sum(1 for c in cards if c.run_status == RunStatus.FAILED)
    running = sum(1 for c in cards if c.run_status == RunStatus.RUNNING)
    no_data = sum(1 for c in cards if c.run_status == RunStatus.PENDING or str(c.run_status) == "no_data")

    # Generate timestamp
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Fill template
    html_content = template.replace("{{CARDS}}", cards_html)
    html_content = html_content.replace("{{TOTAL}}", str(total))
    html_content = html_content.replace("{{SUCCEEDED}}", str(succeeded))
    html_content = html_content.replace("{{FAILED}}", str(failed))
    html_content = html_content.replace("{{RUNNING}}", str(running))
    html_content = html_content.replace("{{NO_DATA}}", str(no_data))
    html_content = html_content.replace("{{GENERATED_AT}}", generated_at)

    return html_content


def _render_card(card: OperatorCard) -> str:
    """Render a single operator card as HTML."""
    status_color = {
        RunStatus.SUCCEEDED: "good",
        RunStatus.FAILED: "bad",
        RunStatus.RUNNING: "warn",
        RunStatus.PENDING: "muted",
        RunStatus.CANCELLED: "muted",
        RunStatus.TIMEOUT: "bad",
    }.get(card.run_status, "muted")

    if str(card.run_status) == "no_data":
        status_color = "muted"

    # Build artifacts list
    artifacts_html = ""
    if card.artifacts:
        artifacts_items = []
        for name, path in card.artifacts.items():
            artifacts_items.append(f'<li><code>{esc(name)}</code>: {esc(path)}</li>')
        artifacts_html = f'<ul class="artifacts-list">{"".join(artifacts_items)}</ul>'
    else:
        artifacts_html = '<p class="muted">No artifacts</p>'

    # Build stats list
    stats_items = []
    if card.processed_ratio:
        stats_items.append(f'<li>Processed: {esc(card.processed_ratio)}</li>')
    if card.duration_display:
        stats_items.append(f'<li>Duration: {esc(card.duration_display)}</li>')
    for key, value in card.stats.items():
        if key not in {"processed", "duration"}:
            stats_items.append(f'<li>{esc(key)}: {esc(value)}</li>')

    stats_html = f'<ul class="stats-list">{"".join(stats_items)}</ul>' if stats_items else '<p class="muted">No stats</p>'

    # Build errors list
    errors_html = ""
    if card.errors:
        error_items = []
        for err in card.errors[:3]:  # Show max 3 errors
            msg = err.get("message", str(err))
            error_items.append(f'<li class="error-item">{esc(msg)}</li>')
        if len(card.errors) > 3:
            error_items.append(f'<li class="error-item">+ {len(card.errors) - 3} more errors</li>')
        errors_html = f'<ul class="errors-list">{"".join(error_items)}</ul>'
    elif card.run_status == RunStatus.FAILED:
        errors_html = '<p class="muted">Failed (no error details)</p>'

    # Build schedule badge
    schedule_badge = f'<span class="badge schedule">{esc(card.schedule_type)}</span>'

    return f"""
    <div class="operator-card" data-operator="{esc(card.operator_id)}">
      <div class="card-header">
        <span class="card-icon">{card.icon}</span>
        <h3 class="card-title">{esc(card.display_name)}</h3>
        <span class="status-indicator {status_color}" data-status="{esc(str(card.run_status))}"></span>
      </div>
      <div class="card-meta">
        {schedule_badge}
        <span class="last-run">Last run: {esc(format_timestamp(card.last_run))}</span>
      </div>
      <div class="card-section">
        <h4>Artifacts</h4>
        {artifacts_html}
      </div>
      <div class="card-section">
        <h4>Stats</h4>
        {stats_html}
      </div>
      {f'<div class="card-section card-errors"><h4>Errors</h4>{errors_html}</div>' if errors_html else ''}
    </div>
    """


def get_fallback_template() -> str:
    """Get a minimal fallback HTML template."""
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Influence Status</title>
  <style>
    :root{
      --bg:#0f1320;
      --panel:#1a1f33;
      --panel-2:#20253b;
      --border:#2c3350;
      --text:#e6eaf3;
      --muted:#9aa3bf;
      --accent:#6cc4ff;
      --good:#7ee787;
      --warn:#f0b86e;
      --bad:#ff8585;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:var(--bg);
      color:var(--text);
      line-height:1.6;
    }
    .wrap{max-width:1200px;margin:0 auto;padding:32px 28px 80px}
    header{
      background:linear-gradient(135deg,#1c2444 0%,#2a1f4a 100%);
      border:1px solid var(--border);
      border-radius:14px;
      padding:24px 28px;
      margin-bottom:28px;
    }
    h1{margin:0 0 6px 0;font-size:26px;color:#fff}
    .meta{color:var(--muted);font-size:13px;margin-top:8px}
    .summary{
      display:flex;gap:16px;margin-top:12px;flex-wrap:wrap
    }
    .summary-item{
      background:var(--panel-2);
      padding:8px 14px;
      border-radius:8px;
      font-size:13px;
    }
    .summary-item strong{color:var(--accent)}
    .cards-grid{
      display:grid;
      grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
      gap:18px;
    }
    .operator-card{
      background:var(--panel);
      border:1px solid var(--border);
      border-radius:12px;
      padding:18px;
    }
    .card-header{
      display:flex;
      align-items:center;
      gap:10px;
      margin-bottom:12px;
    }
    .card-icon{font-size:24px}
    .card-title{margin:0;font-size:16px;color:#fff;flex:1}
    .status-indicator{
      width:10px;height:10px;
      border-radius:50%;
    }
    .status-indicator.good{background:var(--good)}
    .status-indicator.bad{background:var(--bad)}
    .status-indicator.warn{background:var(--warn)}
    .status-indicator.muted{background:var(--muted)}
    .card-meta{
      display:flex;gap:10px;margin-bottom:14px;font-size:12px;color:var(--muted)
    }
    .badge{
      background:var(--panel-2);
      padding:3px 8px;
      border-radius:4px;
      border:1px solid var(--border);
    }
    .card-section{margin-top:14px}
    .card-section h4{margin:0 0 6px 0;font-size:13px;color:var(--accent)}
    .artifacts-list,.stats-list,.errors-list{
      margin:0;padding-left:18px;font-size:12px
    }
    .artifacts-list li,.stats-list li{margin:3px 0}
    .errors-list li{margin:4px 0;color:var(--bad)}
    .error-item{color:var(--bad)}
    .card-errors{border-top:1px solid var(--border);padding-top:12px;margin-top:12px}
    code{background:var(--panel-2);padding:1px 5px;border-radius:3px;font-size:11px}
    @media (max-width:700px){
      .cards-grid{grid-template-columns:1fr}
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>AI Influence Operator Status</h1>
      <div class="meta">Generated: {{GENERATED_AT}}</div>
      <div class="summary">
        <div class="summary-item"><strong>{{TOTAL}}</strong> Total</div>
        <div class="summary-item"><strong>{{SUCCEEDED}}</strong> Succeeded</div>
        <div class="summary-item"><strong>{{RUNNING}}</strong> Running</div>
        <div class="summary-item"><strong>{{FAILED}}</strong> Failed</div>
        <div class="summary-item"><strong>{{NO_DATA}}</strong> No Data</div>
      </div>
    </header>
    <div class="cards-grid">
      {{CARDS}}
    </div>
  </div>
</body>
</html>"""


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate the status page HTML to stdout."""
    reports_dir = Path(args.reports_dir).expanduser() if args.reports_dir else DEFAULT_REPORTS_DIR

    cards = build_cards(reports_dir)
    html = render_html(cards)

    print(html)
    return 0


def cmd_json(args: argparse.Namespace) -> int:
    """Output status as JSON to stdout."""
    reports_dir = Path(args.reports_dir).expanduser() if args.reports_dir else DEFAULT_REPORTS_DIR

    cards = build_cards(reports_dir)

    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cards": [card.to_dict() for card in cards],
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check metadata validity and output report."""
    reports_dir = Path(args.reports_dir).expanduser() if args.reports_dir else DEFAULT_REPORTS_DIR

    cards = build_cards(reports_dir)

    issues = []
    for card in cards:
        if card.run_status == RunStatus.FAILED or card.has_errors:
            issues.append({
                "operator": card.operator_id,
                "status": str(card.run_status),
                "errors": card.errors,
            })

    if issues:
        print(f"Found {len(issues)} operators with issues:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue['operator']}: {issue['status']}", file=sys.stderr)
        return 1

    print("All operators OK")
    return 0


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="AI Influence Status Page Generator")
    parser.add_argument("--reports-dir", help=f"Base reports directory (default: {DEFAULT_REPORTS_DIR})")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("generate", help="Generate HTML status page to stdout")
    sub.add_parser("json", help="Output status as JSON to stdout")
    sub.add_parser("check", help="Check operator status and report issues")

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.cmd == "generate":
        return cmd_generate(args)
    elif args.cmd == "json":
        return cmd_json(args)
    elif args.cmd == "check":
        return cmd_check(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
