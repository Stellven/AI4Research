#!/usr/bin/env python3
"""Paper Copilot paper-list fetch helper for AutoSci-compatible source evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from autosci_runtime_proof import maybe_write_provider_proof


def proof_categories(args: argparse.Namespace) -> list[str]:
    categories = [str(item).strip() for item in (args.proof_category or []) if str(item).strip()]
    if categories:
        return categories
    if args.proof_collection_mode == "live_provider" and not str(args.url or "").startswith("file://"):
        return ["provider_source_evidence", "external_runtime_evidence"]
    return ["provider_source_evidence"]


def emit(
    command: str,
    status: str,
    payload: dict[str, Any],
    *,
    ok: bool = False,
    proof_args: argparse.Namespace | None = None,
) -> int:
    out = {"schema": "autosci_fetch_paper_copilot_cli.v1", "command": command, "status": status, "ok": ok, **payload}
    if proof_args is not None:
        out = maybe_write_provider_proof(
            out,
            evidence_out=proof_args.evidence_out,
            runtime_proof_out=proof_args.runtime_proof_out,
            native_skill=proof_args.native_skill,
            categories=proof_categories(proof_args),
            collection_mode=proof_args.proof_collection_mode,
            source="paper_copilot",
            artifact_kind=f"{command}_response",
            command=" ".join(sys.argv),
            description=f"Completed Paper Copilot {command} provider source fetch.",
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


def network_allowed(args: argparse.Namespace, url: str) -> bool:
    if url.startswith("file://"):
        return True
    if args.no_network_fetch:
        return False
    return os.environ.get("AUTOSCI_DISABLE_NETWORK_FETCH", "").lower() not in {"1", "true", "yes"}


def paper_copilot_url(venue: str, year: int) -> str:
    canonical = {"neurips": "nips"}.get(str(venue).lower(), str(venue).lower())
    base = os.environ.get("PAPER_COPILOT_BASE_URL", "https://raw.githubusercontent.com/papercopilot/paperlists/main").rstrip("/")
    return f"{base}/{canonical}/{canonical}{year}.json"


def load_json(url: str, timeout: int) -> Any:
    if url.startswith("file://"):
        parsed = urllib.parse.urlparse(url)
        path_text = urllib.request.url2pathname(parsed.path)
        if parsed.netloc:
            path_text = f"//{parsed.netloc}{path_text}"
        path = Path(path_text)
        return json.loads(path.read_text(encoding="utf-8"))
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8", errors="replace"))


def source_url(item: dict[str, Any]) -> str:
    for key in ("url", "paper_url", "pdf_url", "openreview_url", "arxiv_url"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def normalize_item(item: dict[str, Any], *, venue: str, year: int, index: int) -> dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        return {}
    url = source_url(item)
    return {
        "candidate_id": str(item.get("id") or item.get("paper_id") or url or f"paper-copilot-{index:03d}"),
        "title": title,
        "abstract": str(item.get("abstract") or item.get("summary") or ""),
        "venue": venue,
        "year": year,
        "provider": "paper_copilot",
        "source_channels": ["paper_copilot"],
        "source_ref": url,
        "url": url,
        "fetch_status": "fetched",
    }


def raw_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "papers", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def cmd_venue(args: argparse.Namespace) -> int:
    url = args.url or paper_copilot_url(args.venue, args.year)
    if not network_allowed(args, url):
        return emit(
            "venue",
            "inconclusive",
            {
                "items": [],
                "count": 0,
                "provider_status": {"provider": "paper_copilot", "status": "unavailable", "url": url},
                "limitations": ["Network fetch disabled; no Paper Copilot request was made."],
            },
            proof_args=args,
        )
    try:
        payload = load_json(url, args.timeout)
    except Exception as exc:  # noqa: BLE001 - provider failures are evidence, not substitutions.
        return emit(
            "venue",
            "inconclusive",
            {
                "items": [],
                "count": 0,
                "provider_status": {"provider": "paper_copilot", "status": "failed", "url": url, "reason": str(exc)},
                "limitations": [f"Paper Copilot request failed: {exc}"],
            },
            proof_args=args,
        )
    items = [
        item
        for index, raw in enumerate(raw_items(payload)[: max(args.limit, 0)], start=1)
        if (item := normalize_item(raw, venue=args.venue, year=args.year, index=index))
    ]
    status = "completed" if items else "inconclusive"
    return emit(
        "venue",
        status,
        {
            "items": items,
            "count": len(items),
            "provider_status": {
                "provider": "paper_copilot",
                "status": status,
                "url": url,
                "source_count": len(items),
            },
            "limitations": [] if items else ["Paper Copilot response contained no usable paper records."],
        },
        ok=bool(items),
        proof_args=args,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("venue")
    command.add_argument("venue")
    command.add_argument("year", type=int)
    command.add_argument("--limit", type=int, default=50)
    command.add_argument("--timeout", type=int, default=30)
    command.add_argument("--url", default="")
    command.add_argument("--no-network-fetch", action="store_true")
    command.add_argument("--evidence-out", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.add_argument("--native-skill", default="")
    command.add_argument("--proof-category", action="append", default=[])
    command.add_argument("--proof-collection-mode", default="live_provider")
    command.set_defaults(func=cmd_venue)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
