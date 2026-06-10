#!/usr/bin/env python3
"""Build and mail the unified AI Influence report.

Inputs are the already-generated daily artifacts:
- ai-influence-daily-digest/YYYY-MM-DD/digest.json
- github-trends-digest/YYYY-MM-DD/digest.json
- youtube-influence-digest/YYYY/MM/DD/*/*youtube-influence-digest.md
- youtube-influence-digest/asr/YYYY/MM/DD/**/*.md

The report intentionally separates collection from presentation. Collectors can
fail or be rate-limited independently, while this layer still emits a clear
three-chapter daily report and attaches raw YouTube transcript text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib.util
import json
import os
import re
import smtplib
import sys
from email import encoders
from email.utils import make_msgid
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
KNOWLEDGE_RAW = Path.home() / "Knowledge" / "_raw"
DEFAULT_MAIL_TO = "solar@example.com"
DEFAULT_GMAIL_USER = ""
DEFAULT_GMAIL_KEYCHAIN_SERVICE = "solar-ai-influence-gmail"


def load_ai_daily_module():
    path = SCRIPT_DIR / "ai_influence_daily.py"
    spec = importlib.util.spec_from_file_location("ai_influence_daily", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "N/A"), quote=True)


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def latest_file(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def youtube_day_dir(raw: Path, date_str: str) -> Path:
    y, m, d = date_str.split("-")
    return raw / "youtube-influence-digest" / y / m / d


def latest_youtube_digest(raw: Path, date_str: str) -> Path | None:
    day = youtube_day_dir(raw, date_str)
    if not day.exists():
        return None
    return latest_file(list(day.glob("*/*youtube-influence-digest.md")))


def youtube_asr_files(raw: Path, date_str: str) -> list[Path]:
    y, m, d = date_str.split("-")
    base = raw / "youtube-influence-digest" / "asr" / y / m / d
    files = sorted(base.glob("*/*-asr.md")) if base.exists() else []
    latest = raw / "youtube-influence-digest" / "asr" / "latest-asr.md"
    if not files and latest.exists():
        files.append(latest)
    # De-duplicate repeated ASR reruns by video id prefix; keep newest.
    by_video: dict[str, Path] = {}
    for f in files:
        video_id = f.name.split("-", 1)[0]
        prev = by_video.get(video_id)
        if prev is None or f.stat().st_mtime > prev.stat().st_mtime:
            by_video[video_id] = f
    return sorted(by_video.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta


def parse_youtube_digest(path: Path | None) -> dict[str, Any]:
    if not path:
        return {
            "path": None,
            "channels_total": 0,
            "videos_collected": 0,
            "transcripts_ok": 0,
            "asr_queued": 0,
            "top_rows": [],
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    meta = parse_frontmatter(text)
    rows = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| Category ") or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 7:
            continue
        category, channel, impact, signal, transcript, video, source = parts[:7]
        if impact.lower() not in {"high", "medium"} and len(rows) >= 8:
            continue
        href = re.search(r"\((https?://[^)]+)\)", source)
        rows.append({
            "category": category,
            "channel": channel,
            "impact": impact,
            "signal": signal,
            "transcript": transcript,
            "video": re.sub(r"\s+", " ", video),
            "url": href.group(1) if href else "",
        })
        if len(rows) >= 10:
            break
    return {
        "path": str(path),
        "channels_total": int(meta.get("channels_total", "0") or 0),
        "videos_collected": int(meta.get("videos_collected", "0") or 0),
        "transcripts_ok": int(meta.get("transcripts_ok", "0") or 0),
        "asr_queued": len(re.findall(r"\basr_queued:", text)),
        "top_rows": rows,
    }


def extract_section(text: str, heading: str, stop_headings: tuple[str, ...] = ("## ", "# ")) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    start = text.find("\n", start)
    if start < 0:
        return ""
    end = len(text)
    for stop in stop_headings:
        pos = text.find(f"\n{stop}", start + 1)
        if pos > start:
            end = min(end, pos)
    return text[start:end].strip()


def parse_asr_summary(files: list[Path]) -> list[dict[str, str]]:
    summaries = []
    for path in files[:5]:
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = parse_frontmatter(text)
        title = meta.get("title") or re.sub(r"-asr\.md$", "", path.stem)
        channel = meta.get("channel") or "N/A"
        source = meta.get("source_url") or meta.get("video_url") or ""
        summary = extract_section(text, "Corrected Summary") or extract_section(text, "Summary")
        key_points = extract_section(text, "Key Points")
        cleaned = re.sub(r"\s+", " ", summary or key_points).strip()
        summaries.append({
            "title": title,
            "channel": channel,
            "source": source,
            "summary": cleaned[:520] if cleaned else "已完成 ASR，等待上层模型摘要回填。",
        })
    return summaries


def build_transcript_attachment(files: list[Path], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    chunks = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = parse_frontmatter(text)
        title = meta.get("title") or path.name
        channel = meta.get("channel") or "N/A"
        url = meta.get("source_url") or meta.get("video_url") or "N/A"
        cleaned = extract_section(text, "Cleaned Transcript")
        raw = extract_section(text, "Raw Whisper Transcript")
        transcript = cleaned or raw or text
        chunks.append(
            "\n".join([
                "=" * 88,
                f"Title: {title}",
                f"Channel: {channel}",
                f"URL: {url}",
                f"File: {path}",
                "-" * 88,
                transcript.strip(),
                "",
            ])
        )
    if not chunks:
        chunks.append("No YouTube transcript files were completed for this report date.\n")
    out_path.write_text("\n".join(chunks), encoding="utf-8")
    return out_path


def metric_card(label: str, value: Any, hint: str) -> str:
    return f"""
      <td style="width:33%;padding:8px;">
        <div style="background:#fffdf8;border:1px solid #eadfcd;border-radius:18px;padding:16px;box-shadow:0 8px 24px rgba(49,42,31,.06);">
          <div style="font-size:27px;font-weight:800;color:#123b35;">{esc(value)}</div>
          <div style="font-size:13px;color:#66736d;">{esc(label)}</div>
          <div style="font-size:12px;color:#8a7661;margin-top:4px;">{esc(hint)}</div>
        </div>
      </td>
    """


def render_youtube_section(youtube: dict[str, Any], asr_summaries: list[dict[str, str]]) -> str:
    rows = youtube.get("top_rows") or []
    row_html = "".join(
        f"""
        <tr>
          <td>{esc(r.get('channel'))}</td>
          <td><a href="{esc(r.get('url'))}" style="color:#0f766e;text-decoration:none;">{esc(r.get('video'))}</a></td>
          <td>{esc(r.get('impact'))}</td>
          <td>{esc(r.get('signal'))}</td>
        </tr>
        """
        for r in rows
    ) or '<tr><td colspan="4">N/A</td></tr>'
    summaries = "".join(
        f"""
        <div style="background:#fbf7ef;border:1px solid #eadfcd;border-radius:14px;padding:13px;margin:10px 0;">
          <div style="font-weight:800;color:#123b35;">{esc(s['title'])}</div>
          <div style="font-size:12px;color:#66736d;">{esc(s['channel'])} · <a href="{esc(s['source'])}" style="color:#0f766e;">source</a></div>
          <p style="margin:8px 0 0;">{esc(s['summary'])}</p>
        </div>
        """
        for s in asr_summaries
    ) or '<p style="color:#66736d;">本期没有完成的 transcript 摘要，附件会说明空结果。</p>'
    return f"""
    <div style="background:#fffdf8;border:1px solid #eadfcd;border-radius:22px;padding:22px;margin:18px 0;">
      <h2 style="font-size:22px;color:#123b35;margin:0 0 12px;">一、YouTube 热点扫描</h2>
      <p style="margin:0 0 14px;color:#33423d;">扫描订阅频道的最新视频，优先标出 AI、Agent、机器人、算力、开源 infra 等方向的高信号内容；完整 transcript 以附件形式随邮件发送。</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">频道</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">视频</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">影响</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">信号</th></tr></thead>
        <tbody>{row_html}</tbody>
      </table>
      <h3 style="font-size:17px;color:#1e4b41;margin:18px 0 8px;">已完成 transcript 摘要</h3>
      {summaries}
    </div>
    """


def render_social_section(ai_digest: dict[str, Any]) -> str:
    trend_analysis = ai_digest.get("trend_analysis") or {}
    trends = trend_analysis.get("core_trends") or []
    items = ai_digest.get("items") or []
    trend_html = "".join(
        f"""
        <div style="border-left:5px solid #c9863d;padding-left:14px;margin:14px 0;">
          <div style="font-weight:800;color:#123b35;">{esc(t.get('theme'))} · {esc(t.get('impact'))} · score {esc(t.get('score'))}</div>
          <p style="margin:6px 0;color:#263832;">{esc(t.get('thesis'))}</p>
          <div style="font-size:12px;color:#66736d;">观察指标：{esc(t.get('watch_metric'))}</div>
        </div>
        """
        for t in trends[:5]
    ) or '<p style="color:#66736d;">N/A</p>'
    item_rows = "".join(
        f"""
        <tr>
          <td>{esc(i.get('handle'))}</td>
          <td><a href="{esc(i.get('tweet_url'))}" style="color:#0f766e;text-decoration:none;">{esc(i.get('title'))}</a></td>
          <td>{esc(i.get('type'))}</td>
          <td>{esc(i.get('hotness'))}</td>
        </tr>
        """
        for i in items[:8]
    ) or '<tr><td colspan="4">N/A</td></tr>'
    return f"""
    <div style="background:#fffdf8;border:1px solid #eadfcd;border-radius:22px;padding:22px;margin:18px 0;">
      <h2 style="font-size:22px;color:#123b35;margin:0 0 12px;">二、社交媒体热点监控</h2>
      <p style="margin:0 0 14px;color:#33423d;">来自 AI Influence 账号池的趋势分析，保留可操作的工具、工作流、Agent、开源 infra 和方法论信号。</p>
      {trend_html}
      <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:12px;">
        <thead><tr><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">账号</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">标题</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">类型</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">热度</th></tr></thead>
        <tbody>{item_rows}</tbody>
      </table>
    </div>
    """


def render_github_section(github_digest: dict[str, Any]) -> str:
    windows = (github_digest.get("analysis") or {}).get("windows") or {}
    labels = [("daily", "今日新热点"), ("weekly", "一周热点"), ("monthly", "一月热点")]
    blocks = []
    for key, label in labels:
        repos = windows.get(key) or []
        rows = "".join(
            f"""
            <tr>
              <td><a href="{esc(r.get('url'))}" style="color:#0f766e;text-decoration:none;">{esc(r.get('repo'))}</a></td>
              <td>{esc(r.get('category'))}</td>
              <td>{esc(r.get('language'))}</td>
              <td>{esc(r.get('stars'))}</td>
              <td>{esc(r.get('max_delta'))}</td>
            </tr>
            """
            for r in repos[:7]
        ) or '<tr><td colspan="5">N/A</td></tr>'
        blocks.append(f"""
          <h3 style="font-size:17px;color:#1e4b41;margin:16px 0 8px;">{esc(label)}</h3>
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead><tr><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">Repo</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">分类</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">语言</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">Stars</th><th style="background:#123b35;color:#fff;text-align:left;padding:10px;">增量</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        """)
    return f"""
    <div style="background:#fffdf8;border:1px solid #eadfcd;border-radius:22px;padding:22px;margin:18px 0;">
      <h2 style="font-size:22px;color:#123b35;margin:0 0 12px;">三、GitHub 热点扫描</h2>
      <p style="margin:0 0 14px;color:#33423d;">跟踪 GitHub Trending / Trendshift / Star History 等来源沉淀的开源热度，按日、周、月窗口观察 AI、大模型、Agent、Skill、训练与基础软件趋势。</p>
      {''.join(blocks)}
    </div>
    """


def render_report(date_str: str, ai_digest: dict[str, Any], github_digest: dict[str, Any], youtube: dict[str, Any], asr_summaries: list[dict[str, str]]) -> str:
    social_items = len(ai_digest.get("items") or [])
    social_trends = len((ai_digest.get("trend_analysis") or {}).get("core_trends") or [])
    github_windows = (github_digest.get("analysis") or {}).get("windows") or {}
    github_repos = len(github_windows.get("daily") or [])
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>AI Influence Unified Digest — {esc(date_str)}</title></head>
<body style="margin:0;background:#f4efe4;color:#17231f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB',sans-serif;line-height:1.7;">
  <div style="max-width:980px;margin:0 auto;padding:28px 18px 42px;">
    <div style="background:linear-gradient(135deg,#123b35,#315f4f 58%,#c9863d);color:#fff;border-radius:26px;padding:30px;">
      <div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;opacity:.82;">AI Influence Unified Digest</div>
      <h1 style="margin:10px 0 12px;font-size:31px;line-height:1.22;">三层热点扫描：YouTube、社交媒体、GitHub</h1>
      <div style="font-size:15px;opacity:.92;max-width:790px;">日报日期：{esc(date_str)}。本邮件正文只放洞察和扫描结果；YouTube transcript 原文作为附件发送，方便后续手工复核或二次加工。</div>
    </div>
    <table style="width:100%;border-collapse:separate;border-spacing:0;margin:16px 0;">
      <tr>
        {metric_card("YouTube 视频扫描", youtube.get("videos_collected", 0), f"频道 {youtube.get('channels_total', 0)} / ASR 队列 {youtube.get('asr_queued', 0)}")}
        {metric_card("社交媒体热点", social_items, f"趋势 {social_trends} 条")}
        {metric_card("GitHub 今日仓库", github_repos, "日/周/月三窗口")}
      </tr>
    </table>
    {render_youtube_section(youtube, asr_summaries)}
    {render_social_section(ai_digest)}
    {render_github_section(github_digest)}
    <div style="font-size:12px;color:#66736d;margin-top:18px;">Generated by solar-harness unified AI Influence report. Transcript 原文见附件。</div>
  </div>
</body>
</html>
"""


def send_smtp(html_content: str, subject: str, attachments: list[Path]) -> dict[str, Any]:
    ai_daily = load_ai_daily_module()
    gmail_user = os.environ.get("GMAIL_USER") or os.environ.get("AI_INFLUENCE_GMAIL_USER") or DEFAULT_GMAIL_USER
    gmail_to = os.environ.get("GMAIL_TO") or os.environ.get("MAIL_TO") or os.environ.get("AI_INFLUENCE_MAIL_TO") or DEFAULT_MAIL_TO
    recipients = [addr.strip() for addr in re.split(r"[,;]", gmail_to) if addr.strip()]
    if not recipients:
        return {"status": "warn", "backend": "gmail_smtp", "reason": "missing recipients"}
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not password:
        service = os.environ.get("GMAIL_APP_PASSWORD_KEYCHAIN_SERVICE") or DEFAULT_GMAIL_KEYCHAIN_SERVICE
        account = os.environ.get("GMAIL_APP_PASSWORD_KEYCHAIN_ACCOUNT") or gmail_user
        password = ai_daily._keychain_password(service, account)
    if not password:
        return {"status": "warn", "backend": "gmail_smtp", "reason": "missing gmail app password"}

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = ", ".join(recipients)
    message_id = make_msgid(domain="solar-harness.local")
    msg["Message-ID"] = message_id
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(alt)

    for path in attachments:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, password)
        refused = server.sendmail(gmail_user, recipients, msg.as_string())
    return {
        "status": "sent",
        "backend": "gmail_smtp",
        "from": gmail_user,
        "to": recipients,
        "message_id": message_id,
        "refused": refused,
        "attachments": [str(p) for p in attachments],
    }


def run(date_str: str, raw: Path, send: bool) -> dict[str, Any]:
    ai_path = raw / "ai-influence-daily-digest" / date_str / "digest.json"
    github_path = raw / "github-trends-digest" / date_str / "digest.json"
    youtube_path = latest_youtube_digest(raw, date_str)
    ai_digest = read_json(ai_path)
    github_digest = read_json(github_path)
    youtube = parse_youtube_digest(youtube_path)
    asr_files = youtube_asr_files(raw, date_str)
    asr_summaries = parse_asr_summary(asr_files)

    out_dir = raw / "ai-influence-daily-digest" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_attachment = build_transcript_attachment(asr_files, out_dir / f"youtube-transcripts-{date_str}.txt")
    html_content = render_report(date_str, ai_digest, github_digest, youtube, asr_summaries)
    html_path = out_dir / "unified-digest.html"
    html_path.write_text(html_content, encoding="utf-8")

    mail_result: dict[str, Any] = {"status": "skipped", "reason": "send disabled"}
    if send:
        mail_result = send_smtp(html_content, f"AI Influence Unified Digest — {date_str}", [transcript_attachment])

    result = {
        "status": "ok" if html_path.exists() and transcript_attachment.exists() else "warn",
        "date": date_str,
        "html": str(html_path),
        "attachment": str(transcript_attachment),
        "ai_digest": str(ai_path) if ai_path.exists() else None,
        "github_digest": str(github_path) if github_path.exists() else None,
        "youtube_digest": str(youtube_path) if youtube_path else None,
        "asr_files": len(asr_files),
        "mail": mail_result,
    }
    (out_dir / "unified-digest-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and optionally mail the unified AI Influence report.")
    parser.add_argument("--date", default=today_utc(), help="Report date in YYYY-MM-DD.")
    parser.add_argument("--raw", default=str(KNOWLEDGE_RAW), help="Knowledge _raw directory.")
    parser.add_argument("--send", action="store_true", help="Send the report via Gmail SMTP.")
    args = parser.parse_args(argv)

    result = run(args.date, Path(args.raw).expanduser(), args.send)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" and result.get("mail", {}).get("status") not in {"warn", "error"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
