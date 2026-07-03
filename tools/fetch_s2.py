#!/usr/bin/env python3
"""Semantic Scholar fetch helper for AutoSci-compatible source evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "harness"
sys.path.insert(0, str(HARNESS))

from plugins.autosci.backends import literature_discover as lit  # noqa: E402
from autosci_runtime_proof import maybe_write_provider_proof  # noqa: E402


def network_allowed(args: argparse.Namespace) -> bool:
    if args.no_network_fetch:
        return False
    return os.environ.get("AUTOSCI_DISABLE_NETWORK_FETCH", "").lower() not in {"1", "true", "yes"}


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
    out = {"schema": "autosci_fetch_s2_cli.v1", "command": command, "status": status, "ok": ok, **payload}
    if proof_args is not None:
        out = maybe_write_provider_proof(
            out,
            evidence_out=proof_args.evidence_out,
            runtime_proof_out=proof_args.runtime_proof_out,
            native_skill=proof_args.native_skill,
            categories=proof_categories(proof_args),
            collection_mode=proof_args.proof_collection_mode,
            source="semantic_scholar",
            artifact_kind=f"{command}_response",
            command=" ".join(sys.argv),
            description=f"Completed Semantic Scholar {command} provider source fetch.",
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


def normalize(raw: dict[str, Any], source: str, anchor: str = "") -> dict[str, Any]:
    return lit._candidate_from_raw(raw, source=source, anchor=anchor)  # noqa: SLF001


def require_network_allowed() -> None:
    if os.environ.get("AUTOSCI_DISABLE_NETWORK_FETCH", "").lower() in {"1", "true", "yes"}:
        raise RuntimeError("Network fetch disabled; no Semantic Scholar request was made.")


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Semantic Scholar search API expected by native AutoSci discover.py."""
    require_network_allowed()
    return lit._s2_search(query, limit)  # noqa: SLF001


def paper(arxiv_id: str) -> dict[str, Any]:
    """Fetch one paper by arXiv ID using the native AutoSci helper shape."""
    require_network_allowed()
    return lit._s2_request(  # noqa: SLF001
        "GET",
        f"{lit.S2_BASE_URL}/paper/ARXIV:{lit._bare_arxiv_id(arxiv_id)}",  # noqa: SLF001
        params={"fields": lit.S2_FIELDS},
    )


def citations(arxiv_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return papers citing the requested arXiv ID."""
    require_network_allowed()
    return lit._s2_citations(arxiv_id, limit)  # noqa: SLF001


def references(arxiv_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return papers referenced by the requested arXiv ID."""
    require_network_allowed()
    return lit._s2_references(arxiv_id, limit)  # noqa: SLF001


def recommend(
    positive_ids: list[str],
    negative_ids: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return Semantic Scholar recommendations for native discover.py."""
    require_network_allowed()
    return lit._s2_recommend(positive_ids, negative_ids or [], limit)  # noqa: SLF001


def fetch_or_inconclusive(
    args: argparse.Namespace,
    *,
    command: str,
    fetcher: Callable[[], list[dict[str, Any]]],
    source: str,
    anchor: str = "",
) -> int:
    if not network_allowed(args):
        return emit(
            command,
            "inconclusive",
            {"items": [], "limitations": ["Network fetch disabled; no Semantic Scholar request was made."]},
            proof_args=args,
        )
    try:
        raw_items = fetcher()
    except Exception as exc:  # noqa: BLE001 - provider failures are evidence, not substitutions.
        return emit(
            command,
            "inconclusive",
            {"items": [], "limitations": [f"Semantic Scholar request failed: {exc}"]},
            proof_args=args,
        )
    items = [item for item in (normalize(raw, source, anchor) for raw in raw_items) if item]
    return emit(
        command,
        "completed" if items else "inconclusive",
        {"items": items, "count": len(items), "limitations": []},
        ok=bool(items),
        proof_args=args,
    )


def cmd_search(args: argparse.Namespace) -> int:
    return fetch_or_inconclusive(
        args,
        command="search",
        fetcher=lambda: lit._s2_search(args.query, args.limit),  # noqa: SLF001
        source="search_s2",
    )


def cmd_references(args: argparse.Namespace) -> int:
    return fetch_or_inconclusive(
        args,
        command="references",
        fetcher=lambda: lit._s2_references(args.paper_id, args.limit),  # noqa: SLF001
        source="references",
        anchor=args.paper_id,
    )


def cmd_citations(args: argparse.Namespace) -> int:
    return fetch_or_inconclusive(
        args,
        command="citations",
        fetcher=lambda: lit._s2_citations(args.paper_id, args.limit),  # noqa: SLF001
        source="citations",
        anchor=args.paper_id,
    )


def add_common(command: argparse.ArgumentParser) -> None:
    command.add_argument("--limit", type=int, default=10)
    command.add_argument("--no-network-fetch", action="store_true")
    command.add_argument("--evidence-out", default="")
    command.add_argument("--runtime-proof-out", default="")
    command.add_argument("--native-skill", default="")
    command.add_argument("--proof-category", action="append", default=[])
    command.add_argument("--proof-collection-mode", default="live_provider")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("search")
    command.add_argument("query")
    add_common(command)
    command.set_defaults(func=cmd_search)

    command = sub.add_parser("references")
    command.add_argument("paper_id")
    add_common(command)
    command.set_defaults(func=cmd_references)

    command = sub.add_parser("citations")
    command.add_argument("paper_id")
    add_common(command)
    command.set_defaults(func=cmd_citations)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
