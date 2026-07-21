#!/usr/bin/env python3
"""Code Signal Plane — unified CLI entry point.

Runs the L0→L5 pipeline: Discovery → Enrichment → Scoring → Packet → Insight → Store.

Usage:
    python3 code_signal_plane.py --dry-run
    python3 code_signal_plane.py --fixture path/to/fixtures.json
    python3 code_signal_plane.py --knowledge-root /path/to/knowledge
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# Add harness/lib to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from github_intelligence.code_signal.operators.discovery import GitHubCandidateDiscoveryOperator
from github_intelligence.code_signal.operators.enrichment import RepoEnrichmentOperator
from github_intelligence.code_signal.operators.scoring import RepoSignalScoringOperator
from github_intelligence.code_signal.operators.packet_compiler import GitHubEvidencePacketCompiler
from github_intelligence.code_signal.operators.insight import GitHubHotspotInsightOperator
from github_intelligence.code_signal.operators.knowledge_store import GitHubKnowledgeStoreOperator
from github_intelligence.code_signal.resonance import stamp_packet_resonance
from github_intelligence.code_signal.models import GitHubEvidencePacket


def run_pipeline(
    trending: list[dict] | None = None,
    search_results: list[dict] | None = None,
    tracked: list[dict] | None = None,
    mention_seeds: list[dict] | None = None,
    repo_metadata: dict | None = None,
    db_path: str | None = None,
    knowledge_root: str | None = None,
    config: dict | None = None,
) -> dict:
    cfg = config or {}

    # G1: Discovery
    discovery = GitHubCandidateDiscoveryOperator(cfg.get("operators", {}).get("discovery"))
    snapshots = discovery.run(trending, search_results, tracked, mention_seeds)

    # G2: Enrichment
    enrichment_op = RepoEnrichmentOperator(cfg.get("operators", {}).get("enrichment"))
    enr_result = enrichment_op.run(snapshots, repo_metadata)

    # G3: Scoring
    scoring = RepoSignalScoringOperator(cfg.get("operators", {}).get("scoring"))
    signals = scoring.run(enr_result["filled_snapshots"], enr_result["enrichments"])

    # G4: Packet compilation
    compiler = GitHubEvidencePacketCompiler(cfg.get("operators", {}).get("packet_compiler"))
    packets: list[GitHubEvidencePacket] = []
    for i, snap in enumerate(enr_result["filled_snapshots"]):
        can = enr_result["canonicals"][i] if i < len(enr_result["canonicals"]) else None
        enr = enr_result["enrichments"][i] if i < len(enr_result["enrichments"]) else None
        sig = signals[i] if i < len(signals) else None
        pkt = compiler.run(snap, can, enr, sig)
        packets.append(pkt)

    # Stamp resonance
    for pkt in packets:
        pkt.resonance_level = stamp_packet_resonance(
            packet=pkt.to_row(),
            cross_source_refs=None,
        )

    # G5: Insight
    insight = GitHubHotspotInsightOperator(cfg.get("operators", {}).get("insight"))
    assets = insight.run(packets)

    # G6: Store
    store = GitHubKnowledgeStoreOperator(
        db_path=db_path or ":memory:",
        knowledge_root=knowledge_root,
        config=cfg.get("operators", {}).get("knowledge_store"),
    )
    store.store_snapshots(snapshots)
    store.store_canonicals(enr_result["canonicals"])
    store.store_enrichments(enr_result["enrichments"])
    store.store_signals(signals)
    store.store_packets(packets)
    store.store_assets(assets)

    return {
        "repos_discovered": len(snapshots),
        "canonicals": len(enr_result["canonicals"]),
        "enrichments": len(enr_result["enrichments"]),
        "signals": len(signals),
        "packets": len(packets),
        "assets": len(assets),
        "asset_types": list(set(a.asset_type for a in assets)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Code Signal Plane pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run with sample fixtures")
    parser.add_argument("--fixture", type=str, help="Path to fixture JSON file")
    parser.add_argument("--knowledge-root", type=str, default=None)
    parser.add_argument("--db-path", type=str, default=None)
    args = parser.parse_args()

    if args.dry_run or args.fixture:
        if args.fixture:
            fixtures = json.loads(Path(args.fixture).read_text())
        else:
            fixtures = {
                "trending": [
                    {"full_name": "example/hot-repo", "stars": 5000, "stars_delta_24h": 200, "language": "Python"},
                    {"full_name": "example/cool-repo", "stars": 100, "stars_delta_24h": 5, "language": "Rust"},
                ],
                "repo_metadata": {
                    "example/hot-repo": {
                        "stars": 5000, "forks": 300, "readme": "A hot project",
                        "readme_tags": ["ai", "ml"], "latest_release_tag": "v2.0",
                    },
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            result = run_pipeline(
                trending=fixtures.get("trending"),
                repo_metadata=fixtures.get("repo_metadata"),
                db_path=args.db_path or str(Path(tmp) / "test.db"),
                knowledge_root=args.knowledge_root or tmp,
            )
        print(json.dumps(result, indent=2))
    else:
        print("No --dry-run or --fixture provided. Use --dry-run for sample run.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
