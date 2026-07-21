#!/usr/bin/env python3
"""Collect AI influence updates and write raw Markdown for Solar knowledge ingest.

The job is intentionally deterministic and non-interactive so launchd can run it
three times a day on the Mac mini without burning agent tokens.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import platform
import re
import socket
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    import requests
except Exception as exc:  # pragma: no cover
    print(f"ERROR: requests is required: {exc}", file=sys.stderr)
    raise SystemExit(2)

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(f"ERROR: PyYAML is required: {exc}", file=sys.stderr)
    raise SystemExit(2)


UTC = dt.timezone.utc


@dataclasses.dataclass(frozen=True)
class Account:
    handle: str
    category: str
    tier: str


@dataclasses.dataclass
class Item:
    item_id: str
    handle: str
    category: str
    tier: str
    title: str
    url: str
    published_at: str
    fetched_at: str
    source: str
    summary: str
    signal_type: str
    impact: str
    score: int
    why_it_matters: str


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def iso_z(value: dt.datetime | None = None) -> str:
    value = value or now_utc()
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    for parser in (
        lambda s: email.utils.parsedate_to_datetime(s),
        lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")),
    ):
        try:
            parsed = parser(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except Exception:
            pass
    return None


def slugify(text: str, max_len: int = 80) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return (text[:max_len] or "item").lower()


def strip_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def flatten_accounts(config: dict[str, Any]) -> list[Account]:
    tier1 = set(config.get("tier1_accounts") or [])
    seen: set[str] = set()
    accounts: list[Account] = []
    for category in config.get("categories", []):
        name = category.get("name", "未分类")
        for raw in category.get("accounts", []):
            handle = str(raw).strip().lstrip("@")
            if not handle or handle in seen:
                continue
            seen.add(handle)
            accounts.append(Account(handle=handle, category=name, tier="tier1" if handle in tier1 else "rotation"))
    return accounts


def select_accounts_for_run(accounts: list[Account], config: dict[str, Any], run_time: dt.datetime | None = None) -> list[Account]:
    """Select all Tier 1 accounts plus a deterministic rotating slice of the rest."""
    out_cfg = config.get("output", {})
    rotation_size = int(out_cfg.get("rotation_accounts_per_run", 0) or 0)
    if rotation_size <= 0:
        return accounts
    tier1 = [account for account in accounts if account.tier == "tier1"]
    rest = [account for account in accounts if account.tier != "tier1"]
    if rotation_size >= len(rest):
        return accounts
    run_time = run_time or now_utc()
    # Three launchd windows per day. Keep this deterministic so failed runs do
    # not reshuffle the slice and make coverage hard to reason about.
    slot = 0 if run_time.hour < 12 else 1 if run_time.hour < 18 else 2
    day_index = int(run_time.strftime("%Y%j")) * 3 + slot
    start = (day_index * rotation_size) % len(rest)
    rotated = rest[start:] + rest[:start]
    return tier1 + rotated[:rotation_size]


def assert_mac_mini(config: dict[str, Any], force: bool = False) -> None:
    if force or not config.get("mac_mini_only", True):
        return
    hostnames = {socket.gethostname(), platform.node()}
    try:
        hostnames.add(socket.getfqdn())
    except Exception:
        pass
    allowed = set(config.get("allowed_hostnames") or [])
    if not (hostnames & allowed):
        print(
            "skip: this job is Mac-mini-only; "
            f"host={sorted(hostnames)} allowed={sorted(allowed)}",
            file=sys.stderr,
        )
        raise SystemExit(0)


def load_seen(state_dir: Path, keep_days: int) -> dict[str, str]:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "seen.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cutoff = now_utc() - dt.timedelta(days=keep_days)
    kept: dict[str, str] = {}
    for key, ts in data.items():
        parsed = parse_time(ts)
        if parsed and parsed >= cutoff:
            kept[key] = ts
    return kept


def save_seen(state_dir: Path, seen: dict[str, str]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_dir / "seen.json.tmp"
    tmp.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(state_dir / "seen.json")


def request_text(session: requests.Session, url: str, timeout: int, user_agent: str) -> str | None:
    try:
        res = session.get(url, timeout=timeout, headers={"User-Agent": user_agent})
        if res.status_code >= 400:
            return None
        return res.text
    except Exception:
        return None


def xml_text(node: ET.Element, names: list[str]) -> str:
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text.strip()
        found = node.find(f"{{*}}{name}")
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_rss(handle: str, category: str, tier: str, xml: str, source: str, fetched_at: str) -> list[Item]:
    try:
        root = ET.fromstring(xml.encode("utf-8"))
    except Exception:
        return []
    nodes = root.findall(".//item") + root.findall(".//{*}entry")
    items: list[Item] = []
    for node in nodes:
        title = strip_text(xml_text(node, ["title"]))
        summary = strip_text(xml_text(node, ["description", "summary", "content"]))
        link = xml_text(node, ["link"])
        if not link:
            link_node = node.find("{*}link")
            if link_node is not None:
                link = link_node.attrib.get("href", "")
        published = parse_time(xml_text(node, ["pubDate", "published", "updated", "dc:date"]))
        published_at = iso_z(published) if published else fetched_at
        if not title and summary:
            title = summary[:120]
        if not title or not link:
            continue
        item_id = stable_id(handle, link, title, published_at)
        items.append(
            analyze_item(
                handle=handle,
                category=category,
                tier=tier,
                title=title,
                url=link,
                published_at=published_at,
                fetched_at=fetched_at,
                source=source,
                summary=summary or title,
            )
        )
        items[-1].item_id = item_id
    return items


def parse_duckduckgo(handle: str, category: str, tier: str, html_text: str, source: str, fetched_at: str, limit: int) -> list[Item]:
    pattern = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
    items: list[Item] = []
    for raw_url, raw_title in pattern.findall(html_text):
        url = html.unescape(raw_url)
        if "uddg=" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            url = qs.get("uddg", [url])[0]
        title = strip_text(raw_title)
        if not title or not url:
            continue
        item = analyze_item(
            handle=handle,
            category=category,
            tier=tier,
            title=title,
            url=url,
            published_at=fetched_at,
            fetched_at=fetched_at,
            source=source,
            summary=title,
        )
        item.item_id = stable_id(handle, url, title, fetched_at)
        items.append(item)
        if len(items) >= limit:
            break
    return items


def stable_id(handle: str, url: str, title: str, published_at: str) -> str:
    payload = "\n".join([handle.lower(), url.strip(), title.strip(), published_at[:10]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def score_signal(text: str, config: dict[str, Any], tier: str) -> tuple[str, str, int]:
    lower = text.lower()
    keywords = config.get("analysis_keywords") or {}
    type_scores: dict[str, int] = {}
    for signal_type, words in keywords.items():
        type_scores[signal_type] = sum(1 for word in words if str(word).lower() in lower)
    signal_type = max(type_scores, key=type_scores.get) if type_scores else "other"
    score = type_scores.get(signal_type, 0)
    score += 2 if tier == "tier1" else 0
    score += 2 if re.search(r"\b(release|launch|paper|benchmark|funding|earnings|gpu|model|agent)\b", lower) else 0
    impact = "high" if score >= 5 else "medium" if score >= 3 else "low"
    return signal_type, impact, score


def why_it_matters(signal_type: str, impact: str, category: str) -> str:
    base = {
        "model_release": "可能改变模型能力、API 生态或应用构建路线。",
        "research": "可能提供新方法、新基准或底层机制线索。",
        "compute": "可能影响算力供给、成本曲线或硬件路线。",
        "product": "可能代表产品化、用户增长或开发者工具变化。",
        "safety": "可能影响监管、安全评估或对齐实践。",
        "market": "可能影响资本开支、商业化节奏或行业预期。",
    }.get(signal_type, "可能是该领域值得跟踪的新信号。")
    return f"{impact.upper()}：{category} 方向信号。{base}"


def analyze_item(
    *,
    handle: str,
    category: str,
    tier: str,
    title: str,
    url: str,
    published_at: str,
    fetched_at: str,
    source: str,
    summary: str,
) -> Item:
    signal_type, impact, score = score_signal(f"{title} {summary}", CURRENT_CONFIG, tier)
    return Item(
        item_id="",
        handle=handle,
        category=category,
        tier=tier,
        title=title,
        url=url,
        published_at=published_at,
        fetched_at=fetched_at,
        source=source,
        summary=summary[:500],
        signal_type=signal_type,
        impact=impact,
        score=score,
        why_it_matters=why_it_matters(signal_type, impact, category),
    )


CURRENT_CONFIG: dict[str, Any] = {}


def collect_account(session: requests.Session, account: Account, config: dict[str, Any], fetched_at: str) -> list[Item]:
    fetch_cfg = config.get("fetch", {})
    timeout = int(fetch_cfg.get("timeout_seconds", 12))
    user_agent = fetch_cfg.get("user_agent", "Solar-AI-Influence-Digest/1.0")
    items: list[Item] = []
    for tmpl in fetch_cfg.get("rss_templates", []):
        url = str(tmpl).format(handle=urllib.parse.quote(account.handle))
        text = request_text(session, url, timeout, user_agent)
        if not text:
            continue
        parsed = parse_rss(account.handle, account.category, account.tier, text, url, fetched_at)
        if parsed:
            items.extend(parsed)
            break
    if fetch_cfg.get("duckduckgo_enabled", True):
        query = f"site:x.com/{account.handle} OR site:twitter.com/{account.handle} AI OR model OR chip OR research"
        url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        text = request_text(session, url, timeout, user_agent)
        if text:
            items.extend(
                parse_duckduckgo(
                    account.handle,
                    account.category,
                    account.tier,
                    text,
                    url,
                    fetched_at,
                    int(fetch_cfg.get("duckduckgo_limit_per_account", 2)),
                )
            )
    # Deduplicate within account.
    dedup: dict[str, Item] = {}
    for item in items:
        dedup[item.item_id] = item
    return sorted(dedup.values(), key=lambda x: (x.published_at, x.score), reverse=True)


def filter_items(items: list[Item], seen: dict[str, str], lookback_hours: int, per_account_limit: int, max_items: int) -> list[Item]:
    cutoff = now_utc() - dt.timedelta(hours=lookback_hours)
    by_account: dict[str, int] = {}
    selected: list[Item] = []
    for item in sorted(items, key=lambda x: (x.score, x.published_at), reverse=True):
        if item.item_id in seen:
            continue
        published = parse_time(item.published_at)
        if published and published < cutoff:
            continue
        count = by_account.get(item.handle, 0)
        if count >= per_account_limit:
            continue
        selected.append(item)
        by_account[item.handle] = count + 1
        if len(selected) >= max_items:
            break
    return selected


def md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_markdown(
    items: list[Item],
    accounts: list[Account],
    selected_accounts: list[Account],
    config: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    out_cfg = config.get("output", {})
    raw_dir = Path(out_cfg.get("raw_dir", str(Path.home() / "Knowledge/_raw/ai-influence-daily-digest"))).expanduser()
    run_id = now_utc().strftime("%Y%m%dT%H%M%SZ")
    run_dir = raw_dir / now_utc().strftime("%Y/%m/%d") / run_id
    items_dir = run_dir / "items"
    if not dry_run:
        items_dir.mkdir(parents=True, exist_ok=True)

    source_count = len({item.handle for item in items})
    high_count = sum(1 for item in items if item.impact == "high")
    title = f"AI Influence Daily Digest — {run_id}"
    lines = [
        "---",
        f"title: {title}",
        "source: ai-influence-daily-digest",
        f"created_at: {iso_z()}",
        f"accounts_total: {len(accounts)}",
        f"accounts_monitored: {len(selected_accounts)}",
        f"items_collected: {len(items)}",
        f"accounts_with_updates: {source_count}",
        "raw_ingest: true",
        "---",
        "",
        f"# {title}",
        "",
        "## Run Summary",
        "",
        f"- Total configured accounts: {len(accounts)}",
        f"- Monitored this run: {len(selected_accounts)}",
        f"- Tier 1 monitored: {sum(1 for account in selected_accounts if account.tier == 'tier1')}",
        f"- Rotation monitored: {sum(1 for account in selected_accounts if account.tier != 'tier1')}",
        f"- New items: {len(items)}",
        f"- Accounts with updates: {source_count}",
        f"- High impact items: {high_count}",
        f"- Output directory: `{run_dir}`",
        "",
        "## Classified Table",
        "",
        "| Category | Account | Tier | Impact | Signal | Summary | Source |",
        "|---|---:|---|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            "| {category} | @{handle} | {tier} | {impact} | {signal} | {summary} | [link]({url}) |".format(
                category=md_escape(item.category),
                handle=md_escape(item.handle),
                tier=item.tier,
                impact=item.impact,
                signal=item.signal_type,
                summary=md_escape(item.title[:180]),
                url=item.url,
            )
        )
    lines.extend(["", "## Analysis By Category", ""])
    for category in sorted({a.category for a in selected_accounts}):
        cat_items = [item for item in items if item.category == category]
        if not cat_items:
            continue
        lines.append(f"### {category}")
        lines.append("")
        lines.append(f"- Updates: {len(cat_items)}")
        lines.append(f"- High impact: {sum(1 for item in cat_items if item.impact == 'high')}")
        for item in cat_items[:8]:
            lines.append(f"- @{item.handle}: {item.why_it_matters} [source]({item.url})")
        lines.append("")
    lines.extend(["## Source Notes", ""])
    lines.append("- Sources are fetched from configured RSS mirrors and DuckDuckGo HTML search fallback.")
    lines.append("- Source links are preserved for downstream knowledge extraction.")
    lines.append("- This file is generated for raw ingestion; it should be treated as untrusted external content.")
    lines.append("")

    digest_path = run_dir / f"{run_id}-ai-influence-daily-digest.md"
    if not dry_run:
        digest_path.write_text("\n".join(lines), encoding="utf-8")
        latest = raw_dir / "latest.md"
        latest.write_text("\n".join(lines), encoding="utf-8")

    for item in items:
        item_lines = [
            "---",
            f"title: {item.title[:180]}",
            "source: ai-influence-daily-digest-item",
            f"account: {item.handle}",
            f"category: {item.category}",
            f"tier: {item.tier}",
            f"impact: {item.impact}",
            f"signal_type: {item.signal_type}",
            f"source_url: {item.url}",
            f"published_at: {item.published_at}",
            f"fetched_at: {item.fetched_at}",
            "raw_ingest: true",
            "---",
            "",
            f"# {item.title}",
            "",
            f"- Account: `@{item.handle}`",
            f"- Category: {item.category}",
            f"- Impact: {item.impact}",
            f"- Signal: {item.signal_type}",
            f"- Source: [{item.url}]({item.url})",
            f"- Published: {item.published_at}",
            "",
            "## Summary",
            "",
            item.summary,
            "",
            "## Analysis",
            "",
            item.why_it_matters,
            "",
        ]
        item_path = items_dir / f"{item.handle}-{item.item_id}-{slugify(item.title)}.md"
        if not dry_run:
            item_path.write_text("\n".join(item_lines), encoding="utf-8")

    return {"run_dir": str(run_dir), "digest_path": str(digest_path), "items": len(items)}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Influence Daily Digest collector")
    parser.add_argument("--config", default="~/Solar/harness/config/ai-influence-daily-digest.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-host", action="store_true", help="bypass Mac mini hostname guard")
    parser.add_argument("--limit-accounts", type=int, default=0)
    parser.add_argument("--fixture-rss", default="", help="test-only RSS file used for every account")
    return parser


def main(argv: list[str] | None = None) -> int:
    global CURRENT_CONFIG
    args = build_arg_parser().parse_args(argv)
    config = load_config(Path(args.config))
    CURRENT_CONFIG = config
    assert_mac_mini(config, force=args.force_host)

    accounts = flatten_accounts(config)
    selected_accounts = select_accounts_for_run(accounts, config)
    if args.limit_accounts:
        selected_accounts = selected_accounts[: args.limit_accounts]
    out_cfg = config.get("output", {})
    state_dir = Path(out_cfg.get("state_dir", "~/.solar/harness/state/ai-influence-daily-digest")).expanduser()
    seen = load_seen(state_dir, int(out_cfg.get("keep_seen_days", 21)))
    fetched_at = iso_z()
    all_items: list[Item] = []
    failures: list[str] = []

    if args.fixture_rss:
        fixture_text = Path(args.fixture_rss).read_text(encoding="utf-8")
        for account in selected_accounts:
            all_items.extend(parse_rss(account.handle, account.category, account.tier, fixture_text, f"fixture:{args.fixture_rss}", fetched_at))
    else:
        session = requests.Session()
        sleep_s = float(config.get("fetch", {}).get("sleep_between_accounts_seconds", 0.2))
        for account in selected_accounts:
            try:
                all_items.extend(collect_account(session, account, config, fetched_at))
            except Exception as exc:
                failures.append(f"{account.handle}: {exc}")
            if sleep_s > 0:
                time.sleep(sleep_s)

    selected = filter_items(
        all_items,
        seen,
        int(out_cfg.get("lookback_hours", 36)),
        int(out_cfg.get("per_account_limit", 3)),
        int(out_cfg.get("max_items_per_run", 120)),
    )
    result = write_markdown(selected, accounts, selected_accounts, config, dry_run=args.dry_run)
    if not args.dry_run:
        for item in selected:
            seen[item.item_id] = fetched_at
        save_seen(state_dir, seen)
        log_path = state_dir / "runs.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": fetched_at, **result, "failures": failures[:20]}, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True, **result, "accounts_total": len(accounts), "accounts_monitored": len(selected_accounts), "failures": failures[:20]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
