#!/usr/bin/env python3
"""Thin CLI: normalized Statements -> Thesis JSON. Delegates to lib.influence."""
from __future__ import annotations

import argparse
import pathlib
import sys

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS_ROOT))

from lib.influence import store, thesis_extractor  # noqa: E402
from lib.influence.models import Statement  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract Thesis objects from collected Statements")
    ap.add_argument("--knowledge-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    statements_dir = store.extracted_dir("statements", args.knowledge_root)
    statements = []
    if statements_dir.exists():
        for jf in sorted(statements_dir.rglob("*.json")):
            statements.append(Statement.from_dict(store.read_json(jf)))
    theses = thesis_extractor.extract_theses(statements)
    for t in theses:
        if args.dry_run:
            print(t.thesis_id)
        else:
            store.persist("thesis", t.thesis_id, t.to_dict(), args.knowledge_root)
    print(f"{len(theses)} theses extracted from {len(statements)} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
