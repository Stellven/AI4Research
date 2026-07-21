"""Rich/TUI renderer for YouTube transcript acquisition health."""
from __future__ import annotations

from typing import Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except Exception:  # pragma: no cover - fallback for minimal environments
    Console = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]


def _sum_values(data: dict[str, Any]) -> int:
    return sum(int(v or 0) for v in data.values())


def render_transcript_status_tui(payload: dict[str, Any]) -> str:
    """Return a terminal-friendly dashboard string; use Rich when available."""
    pending = payload.get("pending_by_priority") or {}
    failures = payload.get("failed_by_error_code") or {}
    tiers = payload.get("accepted_by_source_tier_breakdown") or {}
    lines = [
        "youtube_transcript status",
        f"report_eligible={payload.get('report_eligible_count', 0)}",
        f"model_success_rate={payload.get('model_success_rate', 0)}",
        f"pending_total={_sum_values(pending)}",
        f"failure_total={_sum_values(failures)}",
        f"tiers={tiers}",
        f"pending={pending}",
        f"failures={failures}",
    ]
    return "\n".join(lines)


def print_transcript_status_tui(payload: dict[str, Any]) -> None:
    """Print transcript health using a Rich panel/table if Rich is installed."""
    if Console is None or Panel is None or Table is None:
        print(render_transcript_status_tui(payload))
        return

    console = Console()
    table = Table(title="youtube_transcript", show_header=True, header_style="bold cyan")
    table.add_column("Group")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("summary", "report_eligible", str(payload.get("report_eligible_count", 0)))
    table.add_row("summary", "model_success_rate", str(payload.get("model_success_rate", 0)))
    table.add_row("summary", "premium_cost_today", str(payload.get("premium_cost_today", 0)))
    for key, value in (payload.get("accepted_by_source_tier_breakdown") or {}).items():
        table.add_row("quality_tier", str(key), str(value))
    for key, value in (payload.get("pending_by_priority") or {}).items():
        table.add_row("pending", str(key), str(value))
    for key, value in (payload.get("failed_by_error_code") or {}).items():
        table.add_row("failure", str(key), str(value))

    console.print(Panel(table, title="AI Influence Transcript Runtime", border_style="cyan"))
