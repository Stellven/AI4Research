#!/usr/bin/env python3
"""Thin CLI: end-to-end smoke for the influence pipeline.

With ``--dry-run`` it runs the full Statement->assets chain over the frozen
fixtures (no live Knowledge writes) and reports asset counts — this is the smoke
test referenced by S1-design §7. Delegates to lib.influence.run_pipeline.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS_ROOT))

from lib.influence import insight_compiler, run_pipeline, store  # noqa: E402
from lib.influence.models import InfluenceEvidencePacket, Statement  # noqa: E402

FIXTURES = HARNESS_ROOT / "tests" / "influence" / "fixtures"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render 8 output assets per evidence packet")
    ap.add_argument("--knowledge-root", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="run full pipeline over fixtures without writing to Knowledge")
    args = ap.parse_args(argv)

    if args.dry_run:
        stmt = Statement.from_dict(json.loads((FIXTURES / "sample_statement.json").read_text()))
        result = run_pipeline([stmt])
        total_assets = sum(len(a) for a in result["assets"].values())
        print(f"dry-run: {len(result['packets'])} packets, {total_assets} assets")
        return 0

    packet_dir = store.extracted_dir("mapped_evidence_packets", args.knowledge_root)
    count = 0
    if packet_dir.exists():
        for jf in sorted(packet_dir.rglob("*.json")):
            packet = InfluenceEvidencePacket.from_dict(store.read_json(jf))
            assets = insight_compiler.build_assets(packet)
            for asset_type, asset in assets.items():
                bucket = {
                    "cross_source_resonance_seed": "resonance_seeds",
                    "ai_influence_topic": "topic_cards",
                    "open_source_project_brief": "project_briefs",
                }.get(asset_type, "topic_cards")
                store.persist(bucket, f"{packet.packet_id}-{asset_type}", asset, args.knowledge_root)
            count += 1
    print(f"{count} packets rendered into output assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
