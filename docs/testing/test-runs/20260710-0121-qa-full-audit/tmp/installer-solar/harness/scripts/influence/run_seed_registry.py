#!/usr/bin/env python3
"""Thin CLI: load seed_accounts.yaml -> InfluencerProfile JSON files.

No business logic here; delegates to lib.influence.seed_registry.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS_ROOT))

from lib.influence import seed_registry, store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build InfluencerProfile records from seed config")
    ap.add_argument("--config", default=str(HARNESS_ROOT / "config" / "influence" / "seed_accounts.yaml"))
    ap.add_argument("--knowledge-root", default=None, help="override KNOWLEDGE_ROOT")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    profiles = seed_registry.registry_from_config(args.config)
    for p in profiles:
        if args.dry_run:
            print(p.influencer_id)
        else:
            store.persist("influencer_profiles", p.influencer_id, p.to_dict(), args.knowledge_root)
    print(f"{len(profiles)} profiles processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
