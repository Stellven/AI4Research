#!/usr/bin/env python3
"""Fetch bounded Wikipedia evidence for AutoSci prefill.

The command returns JSON for all outcomes. Exit code 2 means page not found;
exit code 3 means the network/provider call failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


SCHEMA = "autosci_wikipedia_fetch.v1"
API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
PARSE_API = "https://en.wikipedia.org/w/api.php"


def emit(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


def fetch_json(url: str, *, timeout: float) -> tuple[dict[str, Any] | None, int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenSolar-AutoSci/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}, status, ""
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, 404, "page_not_found"
        return None, exc.code, str(exc)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, 0, str(exc)


def cmd_summary(args: argparse.Namespace) -> int:
    title = str(args.title).strip()
    url = API.format(title=urllib.parse.quote(title.replace(" ", "_"), safe=""))
    data, status, error = fetch_json(url, timeout=float(args.timeout))
    if status == 404:
        return emit({"schema": SCHEMA, "command": "summary", "status": "page_not_found", "title": title, "url": url}, 2)
    if data is None:
        return emit({"schema": SCHEMA, "command": "summary", "status": "fetch_failed", "title": title, "url": url, "error": error}, 3)
    return emit(
        {
            "schema": SCHEMA,
            "command": "summary",
            "status": "completed",
            "title": str(data.get("title") or title),
            "source_url": str(data.get("content_urls", {}).get("desktop", {}).get("page") or data.get("canonicalurl") or ""),
            "summary": str(data.get("extract") or ""),
            "raw_status": status,
        }
    )


def parse_query(title: str, *, prop: str, section: int | None = None) -> str:
    params: dict[str, str] = {
        "action": "parse",
        "format": "json",
        "page": title,
        "prop": prop,
        "redirects": "1",
    }
    if section is not None:
        params["section"] = str(section)
    return PARSE_API + "?" + urllib.parse.urlencode(params)


def cmd_sections(args: argparse.Namespace) -> int:
    title = str(args.title).strip()
    data, status, error = fetch_json(parse_query(title, prop="sections"), timeout=float(args.timeout))
    if status == 404 or (data and data.get("error", {}).get("code") == "missingtitle"):
        return emit({"schema": SCHEMA, "command": "sections", "status": "page_not_found", "title": title}, 2)
    if data is None or data.get("error"):
        return emit({"schema": SCHEMA, "command": "sections", "status": "fetch_failed", "title": title, "error": error or data.get("error")}, 3)
    sections = data.get("parse", {}).get("sections") if isinstance(data.get("parse"), dict) else []
    return emit({"schema": SCHEMA, "command": "sections", "status": "completed", "title": title, "sections": sections if isinstance(sections, list) else []})


def cmd_section(args: argparse.Namespace) -> int:
    title = str(args.title).strip()
    index = getattr(args, "index", None)
    data, status, error = fetch_json(parse_query(title, prop="wikitext", section=index), timeout=float(args.timeout))
    if status == 404 or (data and data.get("error", {}).get("code") == "missingtitle"):
        payload = {"schema": SCHEMA, "command": args.command, "status": "page_not_found", "title": title}
        if index is not None:
            payload["index"] = index
        return emit(payload, 2)
    if data is None or data.get("error"):
        payload = {"schema": SCHEMA, "command": args.command, "status": "fetch_failed", "title": title, "error": error or data.get("error")}
        if index is not None:
            payload["index"] = index
        return emit(payload, 3)
    text = str(data.get("parse", {}).get("wikitext", {}).get("*") or "")
    payload = {"schema": SCHEMA, "command": args.command, "status": "completed", "title": title, "content": text[: int(args.max_chars)]}
    if index is not None:
        payload["index"] = index
    return emit(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15.0)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("summary", cmd_summary), ("sections", cmd_sections), ("wikitext", cmd_section)):
        command = sub.add_parser(name)
        command.add_argument("title")
        command.add_argument("--max-chars", type=int, default=8000)
        command.set_defaults(func=func)
    section = sub.add_parser("section")
    section.add_argument("title")
    section.add_argument("--index", type=int, required=True)
    section.add_argument("--max-chars", type=int, default=8000)
    section.set_defaults(func=cmd_section)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
