"""Replay entrypoint for the migration test fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapter import AI4ResearchPhase0ArtifactAdapter
from .schemas import to_dict


def replay_fixture(path: str | Path) -> dict:
    bundle = AI4ResearchPhase0ArtifactAdapter().load_fixture(path)
    return {
        "summary": to_dict(bundle.summary),
        "benchmark_run_result": bundle.benchmark_run_result,
        "counts": {
            "claims": len(bundle.claims),
            "contracts": len(bundle.contracts),
            "observed_metrics": len(bundle.observed_metrics),
            "comparisons": len(bundle.comparisons),
            "evidence_maps": len(bundle.evidence_maps),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a Phase 0 migration fixture.")
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay_fixture(args.fixture), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

