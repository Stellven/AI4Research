#!/usr/bin/env python3
"""CLI for browser profile registry / lease / recovery inspection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from browser.auth_policy import browser_auth_policy  # noqa: E402
from browser.contracts import browser_profile_ref  # noqa: E402
from browser.login_recovery import build_login_recovery_report, select_executor  # noqa: E402
from browser.profile_lease import ProfileLease  # noqa: E402
from browser.profile_registry import ProfileRegistry  # noqa: E402
from browser.verifiers.profile_login_verifier import verify_profile_login  # noqa: E402


def _json_dump(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _profile_id(service: str, profile: str) -> str:
    clean_service = str(service or "").strip().lower()
    clean_profile = str(profile or "").strip()
    if not clean_service or not clean_profile:
        raise RuntimeError("service/profile are required")
    return clean_profile if "/" in clean_profile else f"{clean_service}/{clean_profile}"


def _doctor(_: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    lease = ProfileLease()
    active = lease.list_active()
    payload = {
        "ok": True,
        "registry_root": str(registry.root),
        "lease_root": str(lease.root),
        "active_lease_count": len(active),
        "active_leases": active,
    }
    _json_dump(payload)
    return 0


def _init(args: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    profile_id = _profile_id(args.service, args.profile)
    meta = registry.write_meta(
        profile_id,
        {
            "schema_version": 1,
            "service": args.service,
            "profile_id": profile_id,
            "account_label": args.profile,
            "allowed_account_identifiers": [args.account] if args.account else [],
            "runtime_owner": "browser-use",
            "headless_default": True,
            "headed_required_for_first_login": bool(args.headed),
            "status": "initialized",
            "concurrency_policy": "exclusive",
            "never_log_cookie_values": True,
        },
    )
    policy = browser_auth_policy(
        service=args.service,
        profile_id=profile_id,
        allowed_accounts=[args.account] if args.account else [],
    )
    payload = {
        "ok": True,
        "profile_id": profile_id,
        "meta": meta,
        "auth_policy": policy,
    }
    _json_dump(payload)
    return 0


def _verify(args: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    profile_id = _profile_id(args.service, args.profile)
    meta = registry.read_meta(profile_id)
    health = registry.read_health(profile_id)
    request_dir = Path(args.request_dir).expanduser() if args.request_dir else None
    profile_ref = browser_profile_ref(
        profile_id=profile_id,
        storage_state_ref=meta.get("storage_state_ref"),
        allowed_account_identifiers=meta.get("allowed_account_identifiers"),
    )
    report = {}
    if request_dir and (request_dir / "login-recovery-report.json").exists():
        report = json.loads((request_dir / "login-recovery-report.json").read_text(encoding="utf-8"))
    verification = verify_profile_login(
        profile_ref=profile_ref,
        login_recovery_report=report if report else None,
        account_identifier=args.account,
    )
    payload = {
        "ok": verification.get("ok", False),
        "profile_id": profile_id,
        "meta": meta,
        "health": health,
        "verification": verification,
    }
    _json_dump(payload)
    return 0 if verification.get("ok") else 1


def _recover(args: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    profile_id = _profile_id(args.service, args.profile)
    meta = registry.read_meta(profile_id)
    allowlist = meta.get("allowed_account_identifiers") if isinstance(meta.get("allowed_account_identifiers"), list) else []
    profile_ref = browser_profile_ref(
        profile_id=profile_id,
        storage_state_ref=meta.get("storage_state_ref"),
        allowed_account_identifiers=allowlist,
    )
    executor = select_executor(
        runtime_owner="browser_use",
        wrapper_kind=args.wrapper,
        requires_precise_page_control=args.executor == "playwright_cdp" or args.precise,
        task_operator="webwright" if args.executor == "webwright_bridge" else None,
    )
    report = build_login_recovery_report(
        service=args.service,
        profile_ref=profile_ref,
        runtime_owner="browser_use",
        wrapper_kind=args.wrapper,
        error_text=args.reason,
        account_identifier=args.account,
        allowlist=allowlist,
        requires_precise_page_control=args.executor == "playwright_cdp" or args.precise,
        lease_released=True,
        logged_in_state_verified=False,
        details={
            "requested_executor": args.executor,
            "selected_executor": executor,
            "note": "This command prepares/records recovery policy and does not bypass password/OTP/CAPTCHA gates.",
        },
    )
    verification = verify_profile_login(
        profile_ref=profile_ref,
        login_recovery_report=report,
        account_identifier=args.account,
    )
    payload = {
        "ok": True,
        "profile_id": profile_id,
        "report": report,
        "verification": verification,
    }
    _json_dump(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solar-harness browser", description="Browser profile control plane")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=_doctor)

    init = sub.add_parser("profile-init")
    init.add_argument("--service", required=True)
    init.add_argument("--profile", required=True)
    init.add_argument("--account", default="")
    init.add_argument("--headed", action="store_true")
    init.set_defaults(func=_init)

    verify = sub.add_parser("profile-verify")
    verify.add_argument("--service", required=True)
    verify.add_argument("--profile", required=True)
    verify.add_argument("--account", default="")
    verify.add_argument("--request-dir", default="")
    verify.set_defaults(func=_verify)

    recover = sub.add_parser("profile-recover")
    recover.add_argument("--service", required=True)
    recover.add_argument("--profile", required=True)
    recover.add_argument("--account", default="")
    recover.add_argument("--reason", default="")
    recover.add_argument("--wrapper", default="")
    recover.add_argument("--executor", choices=["auto", "browser_use_dom", "playwright_cdp", "webwright_bridge"], default="auto")
    recover.add_argument("--precise", action="store_true")
    recover.set_defaults(func=_recover)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
