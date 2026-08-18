#!/usr/bin/env python3
"""CLI for explicit-home local personal-data and consent controls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from privacy.control import (
        DATA_SURFACES,
        CONSENT_SOURCES,
        PrivacyControlError,
        apply_retention,
        delete_category,
        explicit_home,
        export_data,
        inventory,
        record_consent,
        revoke_consent,
        set_retention,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
    from privacy.control import (  # type: ignore[no-redef]
        DATA_SURFACES, CONSENT_SOURCES, PrivacyControlError, apply_retention,
        delete_category, explicit_home, export_data, inventory, record_consent,
        revoke_consent, set_retention,
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="privacy-control")
    root.add_argument("--home", required=True, help="absolute local Solar data root")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    export = sub.add_parser("export")
    export.add_argument("--out", required=True)
    export.add_argument("--category", action="append", choices=sorted(DATA_SURFACES), required=True)
    retention = sub.add_parser("retention-set")
    retention.add_argument("--category", choices=("derived_data", "activity_logs"), required=True)
    retention.add_argument("--days", type=int, required=True)
    apply = sub.add_parser("retention-apply")
    apply.add_argument("--now-epoch", type=float)
    delete = sub.add_parser("delete")
    delete.add_argument("--category", choices=sorted(DATA_SURFACES), required=True)
    delete.add_argument("--yes", action="store_true")
    consent = sub.add_parser("consent-record")
    consent.add_argument("--source", choices=CONSENT_SOURCES, required=True)
    consent.add_argument("--purpose", required=True)
    consent.add_argument("--message-ref", required=True)
    revoke = sub.add_parser("consent-revoke")
    revoke.add_argument("--consent-id", required=True)
    revoke.add_argument("--yes", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        home = explicit_home(args.home)
        if args.command == "inventory": result = inventory(home)
        elif args.command == "export": result = export_data(home, Path(args.out), args.category)
        elif args.command == "retention-set": result = set_retention(home, args.category, args.days)
        elif args.command == "retention-apply": result = apply_retention(home, args.now_epoch)
        elif args.command == "delete": result = delete_category(home, args.category, args.yes)
        elif args.command == "consent-record": result = record_consent(home, args.source, args.purpose, args.message_ref)
        elif args.command == "consent-revoke": result = revoke_consent(home, args.consent_id, args.yes)
        else: raise AssertionError(args.command)
    except (PrivacyControlError, ValueError) as exc:
        code = getattr(exc, "code", "invalid_request")
        print(json.dumps({"ok": False, "error": code, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
