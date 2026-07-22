#!/usr/bin/env python3
"""Fail when a stable capsule names an unselectable physical operator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from capability_capsules import audit_stable_capsule_operator_bindings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--capsules",
        type=Path,
        default=HARNESS_ROOT / "config" / "capability-capsules.registry.yaml",
    )
    parser.add_argument(
        "--operators",
        type=Path,
        default=HARNESS_ROOT / "config" / "physical-operators.json",
    )
    args = parser.parse_args()
    issues = audit_stable_capsule_operator_bindings(
        registry_path=args.capsules,
        operators_path=args.operators,
    )
    if issues:
        print(json.dumps({"ok": False, "issues": issues}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "issues": [], "stable_capsule_operator_bindings": "coherent"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
