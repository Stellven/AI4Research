#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from youtube.acceptance_suite import (
    SPRINT_ID,
    auto_closeout_s03_runtime,
    generate_acceptance_reports,
    generate_traceability_and_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="~/Solar/harness")
    parser.add_argument("--runtime-root", default="~/.solar/harness")
    parser.add_argument("--knowledge-context", default="solar-harness context inject used")
    args = parser.parse_args()

    root = Path(args.root)
    runtime_root = Path(args.runtime_root)
    reports = generate_acceptance_reports(root, runtime_root / "reports" / "youtube" / "s03-acceptance")
    traceability_path, handoff_path = generate_traceability_and_handoff(
        sprint_root=runtime_root / "sprints",
        report_dir=runtime_root / "reports" / "youtube" / "s03-acceptance",
        reports=reports,
        knowledge_context=args.knowledge_context,
    )
    closeout = auto_closeout_s03_runtime(
        root=root,
        runtime_root=runtime_root,
        report_dir=runtime_root / "reports" / "youtube" / "s03-acceptance",
        traceability_path=traceability_path,
        handoff_path=handoff_path,
        reports=reports,
    )
    if not closeout.get("ok"):
        print(json.dumps(closeout, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(f"ok: generated acceptance suite for {SPRINT_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
