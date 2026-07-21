#!/usr/bin/env python3
"""Thin CLI: adapt legacy digest raw outputs -> canonical Statement JSON.

Delegates to lib.influence.statement_collector (read-only over the _raw tree).
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS_ROOT))

from lib.influence import statement_collector, statement_normalizer, store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect canonical Statements from legacy digests")
    ap.add_argument("--source", choices=["x_backend", "youtube_transcript"], required=True)
    ap.add_argument("--knowledge-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    statements = statement_collector.collect_from_dir(args.source, args.knowledge_root)
    statements = statement_normalizer.normalize_batch(statements)
    for s in statements:
        if args.dry_run:
            print(s.statement_id)
        else:
            store.persist("statements", s.statement_id, s.to_dict(), args.knowledge_root)
    print(f"{len(statements)} statements collected from {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
