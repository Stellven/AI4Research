#!/usr/bin/env python3
"""DeepXiv fetch helper for AutoSci-compatible source evidence.

The repository does not bundle a DeepXiv provider implementation.  This CLI
therefore only performs a live request when DEEPXIV_API_URL is configured and
otherwise emits explicit unavailable evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any

from autosci_runtime_proof import maybe_write_provider_proof


def proof_categories(args: argparse.Namespace) -> list[str]:
    categories = [str(item).strip() for item in (args.proof_category or []) if str(item).strip()]
    if categories:
        return categories
    if args.proof_collection_mode == "live_provider":
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
    out = {"schema": "autosci_fetch_deepxiv_cli.v1", "command": command, "status": status, "ok": ok, **payload}
    if proof_args is not None:
        out = maybe_write_provider_proof(
            out,
            evidence_out=proof_args.evidence_out,
            runtime_proof_out=proof_args.runtime_proof_out,
            native_skill=proof_args.native_skill,
            categories=proof_categories(proof_args),
            collection_mode=proof_args.proof_collection_mode,
            source="deepxiv",
            artifact_kind=f"{command}_response",
            command=" ".join(sys.argv),
            description=f"Completed DeepXiv {command} provider source fetch.",
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


def provider_url() -> str:
    return os.environ.get("DEEPXIV_API_URL", "").strip()


def network_allowed(args: argparse.Namespace) -> bool:
    if args.no_network_fetch:
        return False
    return os.environ.get("AUTOSCI_DISABLE_NETWORK_FETCH", "").lower() not in {"1", "true", "yes"}


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "").strip()
    if not title:
        return {}
    return {
        "candidate_id": str(item.get("id") or item.get("paper_id") or item.get("url") or title),
        "title": title,
        "abstract": str(item.get("abstract") or item.get("summary") or ""),
        "url": str(item.get("url") or item.get("source_ref") or ""),
        "source_channels": ["deepxiv"],
        "source_ref": str(item.get("url") or item.get("source_ref") or ""),
        "fetch_status": "fetched",
    }


def _request_payload(params: dict[str, Any]) -> Any:
    if os.environ.get("AUTOSCI_DISABLE_NETWORK_FETCH", "").lower() in {"1", "true", "yes"}:
        raise RuntimeError("Network fetch disabled; no DeepXiv request was made.")
    base_url = provider_url()
    if not base_url:
        raise RuntimeError("DEEPXIV_API_URL is not configured; DeepXiv live evidence is unavailable.")
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{query}"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _payload_items(payload: Any) -> list[dict[str, Any]]:
    raw_items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise RuntimeError("DeepXiv response must be a JSON list or object with data list.")
    return [item for item in raw_items if isinstance(item, dict)]


def search(query: str, mode: str = "hybrid", limit: int = 10, **_: Any) -> list[dict[str, Any]]:
    """DeepXiv search API expected by native AutoSci discover.py."""
    return _payload_items(_request_payload({"q": query, "mode": mode, "limit": limit}))


def brief(arxiv_id: str) -> dict[str, Any]:
    """DeepXiv brief API expected by native AutoSci daily_arxiv.py."""
    payload = _request_payload({"arxiv_id": arxiv_id, "view": "brief"})
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if isinstance(data, dict):
            return data
    raise RuntimeError("DeepXiv brief response must be a JSON object.")


def trending(days: int = 7, limit: int = 30) -> list[dict[str, Any]]:
    """DeepXiv trending API expected by native AutoSci daily_arxiv.py."""
    return _payload_items(_request_payload({"view": "trending", "days": days, "limit": limit}))


def cmd_search(args: argparse.Namespace) -> int:
    if not network_allowed(args):
        return emit(
            "search",
            "inconclusive",
            {"items": [], "limitations": ["Network fetch disabled; no DeepXiv request was made."]},
            proof_args=args,
        )
    base_url = provider_url()
    if not base_url:
        return emit(
            "search",
            "inconclusive",
            {"items": [], "limitations": ["DEEPXIV_API_URL is not configured; DeepXiv live evidence is unavailable."]},
            proof_args=args,
        )
    query = urllib.parse.urlencode({"q": args.query, "limit": args.limit})
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{query}"
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - provider failures are explicit evidence.
        return emit(
            "search",
            "inconclusive",
            {"items": [], "limitations": [f"DeepXiv request failed: {exc}"]},
            proof_args=args,
        )
    raw_items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        return emit(
            "search",
            "failed",
            {"items": [], "limitations": ["DeepXiv response must be a JSON list or object with data list."]},
            proof_args=args,
        )
    items = [item for item in (normalize_item(raw) for raw in raw_items if isinstance(raw, dict)) if item]
    return emit(
        "search",
        "completed" if items else "inconclusive",
        {"items": items, "count": len(items), "limitations": []},
        ok=bool(items),
        proof_args=args,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("search")
    command.add_argument("query")
    command.add_argument("--limit", type=int, default=10)
    command.add_argument("--timeout", type=int, default=30)
    command.add_argument("--no-network-fetch", action="store_true")
    command.add_argument("--evidence-out", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.add_argument("--native-skill", default="")
    command.add_argument("--proof-category", action="append", default=[])
    command.add_argument("--proof-collection-mode", default="live_provider")
    command.set_defaults(func=cmd_search)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
