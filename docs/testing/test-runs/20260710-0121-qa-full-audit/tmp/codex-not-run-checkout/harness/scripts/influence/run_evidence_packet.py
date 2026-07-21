#!/usr/bin/env python3
"""Thin CLI: Thesis -> InfluenceEvidencePacket JSON. Delegates to lib.influence."""
from __future__ import annotations

import argparse
import pathlib
import sys

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS_ROOT))

from lib.influence import evidence_packet_compiler, store, thesis_mapper  # noqa: E402
from lib.influence.models import Statement, Thesis  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compile InfluenceEvidencePackets from theses")
    ap.add_argument("--knowledge-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    thesis_dir = store.extracted_dir("thesis", args.knowledge_root)
    stmt_dir = store.extracted_dir("statements", args.knowledge_root)
    stmt_by_id = {}
    if stmt_dir.exists():
        for jf in stmt_dir.rglob("*.json"):
            s = Statement.from_dict(store.read_json(jf))
            stmt_by_id[s.statement_id] = s

    count = 0
    if thesis_dir.exists():
        for jf in sorted(thesis_dir.rglob("*.json")):
            thesis = Thesis.from_dict(store.read_json(jf))
            members = [stmt_by_id[sid] for sid in thesis.derived_from_statements if sid in stmt_by_id]
            mapped = thesis_mapper.map_thesis(thesis)
            packet = evidence_packet_compiler.compile_packet(thesis, members, mapped)
            if args.dry_run:
                print(packet.packet_id)
            else:
                store.persist("mapped_evidence_packets", packet.packet_id, packet.to_dict(), args.knowledge_root)
            count += 1
    print(f"{count} evidence packets compiled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
