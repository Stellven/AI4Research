"""HTML dashboard renderer for YouTube transcript acquisition health.

The ``visual-template`` marker is intentionally kept as a stable verifier
anchor for S05 release checks.
"""
from __future__ import annotations

import html
from typing import Any


VISUAL_TEMPLATE_ID = "youtube-transcript-dashboard.visual-template.v1"


def _status_class(value: float, *, warn: float, error: float, invert: bool = False) -> str:
    if invert:
        if value <= error:
            return "ok"
        if value <= warn:
            return "warn"
        return "error"
    if value >= warn:
        return "ok"
    if value >= error:
        return "warn"
    return "error"


def _metric_card(label: str, value: Any, status: str = "ok", hint: str = "") -> str:
    safe_label = html.escape(str(label))
    safe_value = html.escape(str(value))
    safe_hint = html.escape(str(hint))
    return (
        f'<article class="metric metric-{status}">'
        f"<span>{safe_label}</span>"
        f"<strong>{safe_value}</strong>"
        f"<small>{safe_hint}</small>"
        "</article>"
    )


def _kv_rows(data: dict[str, Any]) -> str:
    rows = []
    for key, value in data.items():
        rows.append(
            "<tr>"
            f"<th>{html.escape(str(key))}</th>"
            f"<td>{html.escape(str(value))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_dashboard_html(payload: dict[str, Any]) -> str:
    """Render transcript runtime health as a self-contained HTML fragment."""
    pending = payload.get("pending_by_priority") or {}
    failures = payload.get("failed_by_error_code") or {}
    tiers = payload.get("accepted_by_source_tier_breakdown") or {}
    dist = payload.get("quality_score_distribution") or {}
    total_pending = sum(int(v or 0) for v in pending.values())
    total_failures = sum(int(v or 0) for v in failures.values())
    report_eligible = int(payload.get("report_eligible_count") or 0)
    browser_capture_success = float(payload.get("browser_capture_success_rate") or 0.0)
    low_quality = int(dist.get("lt_0_50") or 0)

    quality_status = _status_class(browser_capture_success, warn=0.70, error=0.50)
    pending_status = _status_class(total_pending, warn=50, error=10, invert=True)
    failure_status = _status_class(total_failures, warn=10, error=3, invert=True)
    low_quality_status = _status_class(low_quality, warn=10, error=3, invert=True)

    cards = "\n".join(
        [
            _metric_card("Report eligible", report_eligible, "ok", "T0/T1/T2 可进入报告池"),
            _metric_card("Browser capture success", f"{browser_capture_success:.1%}", quality_status, "Browser Agent transcript capture"),
            _metric_card("Pending backlog", total_pending, pending_status, "按 P0/P1/P2/P3 调度"),
            _metric_card("Failed jobs", total_failures, failure_status, "bot/no_caption/transcript/timeout"),
            _metric_card("Low quality", low_quality, low_quality_status, "T3 不允许进核心报告"),
            _metric_card("Premium cost today", f"${float(payload.get('premium_cost_today') or 0.0):.2f}", "ok", "disabled"),
        ]
    )

    return f"""<!doctype html>
<html lang="zh-CN" data-template="{VISUAL_TEMPLATE_ID}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Influence YouTube Transcript Dashboard</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --ink: #e5e7eb;
      --muted: #94a3b8;
      --ok: #22c55e;
      --warn: #f59e0b;
      --error: #ef4444;
      --line: rgba(148, 163, 184, .28);
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 15% 5%, #1e3a8a 0, transparent 32rem), var(--bg);
      color: var(--ink);
      font: 15px/1.55 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 24px 48px;
    }}
    header {{
      border: 1px solid var(--line);
      background: rgba(17, 24, 39, .76);
      border-radius: 24px;
      padding: 24px;
      box-shadow: 0 24px 80px rgba(0, 0, 0, .28);
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    p {{ color: var(--muted); margin: 0; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin: 20px 0;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-left: 5px solid var(--ok);
      border-radius: 18px;
      padding: 16px;
      background: rgba(15, 23, 42, .76);
    }}
    .metric-warn {{ border-left-color: var(--warn); }}
    .metric-error {{ border-left-color: var(--error); }}
    .metric span, .metric small {{ display: block; color: var(--muted); }}
    .metric strong {{ display: block; margin: 6px 0; font-size: 26px; }}
    section {{
      margin-top: 18px;
      border: 1px solid var(--line);
      border-radius: 20px;
      overflow: hidden;
      background: rgba(17, 24, 39, .7);
    }}
    h2 {{ margin: 0; padding: 16px 18px; border-bottom: 1px solid var(--line); font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 12px 18px; border-bottom: 1px solid rgba(148, 163, 184, .16); text-align: left; }}
    th {{ width: 42%; color: var(--muted); font-weight: 600; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>AI Influence YouTube Transcript Dashboard</h1>
    <p>Transcript ladder / Browser Agent capture / quality gate 的运行态总览。</p>
  </header>
  <div class="grid">{cards}</div>
  <section><h2>Quality Tiers</h2><table>{_kv_rows(tiers)}</table></section>
  <section><h2>Pending By Priority</h2><table>{_kv_rows(pending)}</table></section>
  <section><h2>Failed By Error Code</h2><table>{_kv_rows(failures)}</table></section>
</main>
</body>
</html>
"""
