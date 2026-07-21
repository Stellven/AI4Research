#!/usr/bin/env python3
"""Generate backlog-aware autoscaling snapshot for Solar Harness."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
sys.path.insert(0, str(HARNESS_DIR / "lib"))

import backlog_autoscaler as autoscaler  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh backlog-aware autoscaling snapshot.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = autoscaler.refresh_snapshot()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        metrics = payload.get("metrics", {})
        globals_ = payload.get("global_limits", {})
        print(
            "backlog_autoscaler "
            f"drafting_spec={metrics.get('drafting_spec', 0)} "
            f"prd_ready={metrics.get('active_prd_ready', 0)} "
            f"planning_complete={metrics.get('active_planning_complete', 0)} "
            f"reviewing={metrics.get('reviewing_handoff_ready', 0)} "
            f"max_workers={globals_.get('max_workers', 'N/A')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

