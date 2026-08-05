#!/usr/bin/env python3
"""Research runtime readiness doctor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from research_orchestration.runtime_readiness import (  # noqa: E402
    BLOCKED,
    READY,
    READY_WITH_LIMITATIONS,
    check_research_runtime,
)


EXIT_CODES = {
    READY: 0,
    READY_WITH_LIMITATIONS: 2,
    BLOCKED: 3,
}


class DoctorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse calls sys.exit
        payload = {
            "schema": "research_runtime_doctor_error.v1",
            "status": "invalid_invocation",
            "error": message,
        }
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        raise SystemExit(4)


def build_parser() -> argparse.ArgumentParser:
    parser = DoctorArgumentParser(description="Research runtime readiness doctor")
    parser.add_argument("--json", action="store_true", help="Emit deterministic JSON")
    parser.add_argument("--offline", action="store_true", help="Skip network probe unless network is required")
    parser.add_argument("--require-network", action="store_true", help="Block when DNS/network probing fails")
    parser.add_argument("--require-provider", action="append", default=[], metavar="NAME", help="Require provider env var NAME")
    parser.add_argument("--require-tmux", action="store_true", help="Block when tmux is unavailable")
    parser.add_argument("--require-sandbox", action="store_true", help="Block when sandbox root/bwrap requirements fail")
    parser.add_argument("--sandbox-root", default=os.environ.get("SOLAR_RESEARCH_SANDBOX_ROOT", ""), help="Sandbox root to check")
    parser.add_argument("--approval-ref", default=os.environ.get("SOLAR_LIVE_PROVIDER_APPROVAL_REF", ""), help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 4)

    require_provider = args.require_provider[-1] if args.require_provider else None
    provider_names = tuple(args.require_provider)
    try:
        report = check_research_runtime(
            source_env=os.environ,
            allowed_provider_env_names=provider_names,
            require_provider=require_provider,
            live_provider_approval_ref=args.approval_ref,
            offline=bool(args.offline),
            require_network=bool(args.require_network),
            require_tmux=bool(args.require_tmux),
            require_sandbox=bool(args.require_sandbox),
            use_sandbox=bool(args.require_sandbox),
            sandbox_root=args.sandbox_root or None,
        )
    except ValueError as exc:
        payload = {
            "schema": "research_runtime_doctor_error.v1",
            "status": "invalid_invocation",
            "error": str(exc),
        }
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"research runtime: {report['status']}")
        for blocker in report.get("blockers", []):
            print(f"blocker: {blocker['check']} {blocker['reason']}")
        for limitation in report.get("limitations", []):
            print(f"limitation: {limitation}")
    return EXIT_CODES.get(str(report.get("status")), 3)


if __name__ == "__main__":
    sys.exit(main())
