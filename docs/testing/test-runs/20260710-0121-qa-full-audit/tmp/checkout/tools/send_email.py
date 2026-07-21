#!/usr/bin/env python3
"""Email draft/send helper with approval-gated delivery."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from email.message import EmailMessage
import json
import os
from pathlib import Path
import smtplib
import ssl
from typing import Any


def emit(command: str, status: str, payload: dict[str, Any], *, ok: bool = False) -> int:
    out = {"schema": "autosci_send_email_cli.v1", "command": command, "status": status, "ok": ok, **payload}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if status == "failed" else 0


class ConfigError(ValueError):
    """Raised when required SMTP configuration is missing or invalid."""


def split_recipients(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def load_env_config(args: argparse.Namespace) -> dict[str, Any]:
    host = (getattr(args, "smtp_host", "") or os.environ.get("SMTP_HOST", "")).strip()
    arg_port = getattr(args, "smtp_port", "")
    env_port = os.environ.get("SMTP_PORT", "").strip()
    raw_port = str(env_port if env_port and arg_port in ("", None, 25) else (arg_port or env_port or "587")).strip()
    username = (getattr(args, "smtp_user", "") or os.environ.get("SMTP_USER", "")).strip()
    password = getattr(args, "smtp_password", "") or os.environ.get("SMTP_PASSWORD", "")
    from_addr = (getattr(args, "from_addr", "") or os.environ.get("SMTP_FROM") or "").strip()
    to_raw = getattr(args, "to", "") or os.environ.get("DAILY_ARXIV_EMAIL_TO", "")
    to_addrs = split_recipients(to_raw)
    missing: list[str] = []
    for name, value in (
        ("SMTP_HOST", host),
        ("SMTP_USER", username),
        ("SMTP_PASSWORD", password),
        ("SMTP_FROM", from_addr),
        ("DAILY_ARXIV_EMAIL_TO", ",".join(to_addrs)),
    ):
        if not value:
            missing.append(name)
    if missing:
        raise ConfigError("Missing SMTP configuration: " + ", ".join(missing))
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ConfigError("SMTP_PORT must be an integer") from exc
    use_ssl = bool_env("SMTP_SSL", port == 465)
    use_starttls = bool_env("SMTP_STARTTLS", not use_ssl)
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_addr": from_addr,
        "to_addrs": to_addrs,
        "use_ssl": use_ssl,
        "use_starttls": use_starttls,
    }


def body_from_args(args: argparse.Namespace) -> str:
    body_file = getattr(args, "body_file", None)
    if body_file:
        return body_file.read_text(encoding="utf-8")
    return str(getattr(args, "body", "") or "")


def apply_env_config(args: argparse.Namespace, config: dict[str, Any]) -> None:
    args.smtp_host = str(config["host"])
    args.smtp_port = int(config["port"])
    args.smtp_user = str(config["username"])
    args.smtp_password = str(config["password"])
    args.from_addr = str(config["from_addr"])
    args.to = ", ".join(config["to_addrs"])
    args.tls = bool(config["use_starttls"]) and not bool(config["use_ssl"])


def cmd_check_config(args: argparse.Namespace) -> int:
    try:
        config = load_env_config(args)
    except ConfigError as exc:
        return emit("check-config", "inconclusive", {"reason": str(exc), "limitations": ["SMTP configuration is incomplete."]})
    return emit(
        "check-config",
        "completed",
        {
            "smtp_host": config["host"],
            "smtp_port": config["port"],
            "recipient_count": len(config["to_addrs"]),
            "use_ssl": bool(config["use_ssl"]),
            "use_starttls": bool(config["use_starttls"]),
        },
        ok=True,
    )


def cmd_draft(args: argparse.Namespace) -> int:
    return emit("draft", "completed", {"to": args.to, "subject": args.subject, "body": body_from_args(args)}, ok=True)


def write_runtime_evidence(
    args: argparse.Namespace,
    *,
    status: str,
    exit_code: int,
    checks: list[dict[str, Any]],
    runtime_fields: dict[str, Any],
    limitations: list[str],
) -> str:
    if not args.runtime_evidence_out:
        return ""
    from_addr = args.from_addr or args.smtp_user or "autosci@localhost"
    receipt_path = None
    artifacts: list[dict[str, str]] = []
    if status == "completed":
        receipt_path = args.runtime_evidence_out + ".receipt.json"
        with open(receipt_path, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "schema": "autosci_email_delivery_receipt.v1",
                        "status": status,
                        "approval_ref": args.approval_ref,
                        "to": args.to,
                        "from": from_addr,
                        "subject": args.subject,
                        "provider": runtime_fields.get("provider", "smtp"),
                        "delivered": runtime_fields.get("delivered") is True,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
        artifacts.append({"type": "email_delivery_receipt_json", "path": receipt_path})
    payload = {
        "schema": "autosci_runtime_evidence.v1",
        "task_id": "send-email-runtime",
        "sprint_id": "send-email",
        "node_id": "node-send-email",
        "status": status,
        "inputs": {"approval_ref": args.approval_ref, "to": args.to, "subject": args.subject},
        "outputs": {
            "runtime": {
                "action": "send_email",
                "status": status,
                "approval_ref": args.approval_ref,
                "command_run": f"smtp://{args.smtp_host}:{args.smtp_port} send {from_addr} -> {args.to}",
                "exit_code": exit_code,
                "evidence_ids": [f"email:{args.approval_ref}", f"recipient:{args.to}"],
                "checks": checks,
                **runtime_fields,
            }
        },
        "artifacts": artifacts,
        "provenance": {
            "operator_id": "autosci-send-email-cli",
            "implementation_package": "tools.send_email",
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
        "limitations": limitations,
    }
    with open(args.runtime_evidence_out, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return str(args.runtime_evidence_out)


def cmd_send(args: argparse.Namespace) -> int:
    if getattr(args, "check_config", False):
        return cmd_check_config(args)
    if not args.smtp_host and os.environ.get("SMTP_HOST"):
        try:
            apply_env_config(args, load_env_config(args))
        except ConfigError:
            pass
    if not args.approval_ref:
        return emit("send", "approval_required", {"to": args.to, "subject": args.subject, "limitations": ["Email delivery requires --approval-ref and configured SMTP/provider credentials."]})
    if not args.execute_approved:
        return emit("send", "inconclusive", {"approval_ref": args.approval_ref, "limitations": ["Email delivery requires --execute-approved before contacting SMTP/provider endpoints."]})
    if not args.smtp_host:
        runtime_path = write_runtime_evidence(
            args,
            status="inconclusive",
            exit_code=1,
            checks=[{"check": "smtp_configured", "status": "error", "detail": "Missing --smtp-host."}],
            runtime_fields={"delivered": False},
            limitations=["SMTP/provider delivery did not run because no SMTP host was configured."],
        )
        return emit("send", "inconclusive", {"approval_ref": args.approval_ref, "runtime_evidence_path": runtime_path, "limitations": ["SMTP/provider delivery is not configured."]})

    from_addr = args.from_addr or args.smtp_user or "autosci@localhost"
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = args.to
    message["Subject"] = args.subject
    message.set_content(body_from_args(args))
    try:
        if getattr(args, "ssl", False):
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(args.smtp_host, int(args.smtp_port), context=context, timeout=int(args.timeout_seconds)) as smtp:
                if args.smtp_user or args.smtp_password:
                    smtp.login(args.smtp_user, args.smtp_password)
                refused = smtp.send_message(message)
        else:
            with smtplib.SMTP(args.smtp_host, int(args.smtp_port), timeout=int(args.timeout_seconds)) as smtp:
                if args.tls:
                    smtp.starttls()
                if args.smtp_user or args.smtp_password:
                    smtp.login(args.smtp_user, args.smtp_password)
                refused = smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001 - CLI must surface provider failures as evidence.
        runtime_path = write_runtime_evidence(
            args,
            status="failed",
            exit_code=1,
            checks=[
                {"check": "smtp_configured", "status": "ok", "detail": f"{args.smtp_host}:{args.smtp_port}"},
                {"check": "smtp_send", "status": "error", "detail": str(exc)[:500]},
            ],
            runtime_fields={"delivered": False, "provider": "smtp", "smtp_host": args.smtp_host, "smtp_port": int(args.smtp_port)},
            limitations=["SMTP/provider delivery failed; no successful delivery is claimed."],
        )
        return emit("send", "failed", {"approval_ref": args.approval_ref, "runtime_evidence_path": runtime_path, "error": str(exc)[:500]})

    delivered = not refused
    status = "completed" if delivered else "failed"
    runtime_path = write_runtime_evidence(
        args,
        status=status,
        exit_code=0 if delivered else 1,
        checks=[
            {"check": "smtp_configured", "status": "ok", "detail": f"{args.smtp_host}:{args.smtp_port}"},
            {"check": "smtp_send", "status": "ok" if delivered else "error", "detail": "accepted" if delivered else json.dumps(refused, sort_keys=True, default=str)},
        ],
        runtime_fields={
            "delivered": delivered,
            "provider": "smtp",
            "smtp_host": args.smtp_host,
            "smtp_port": int(args.smtp_port),
            "to": args.to,
            "from": from_addr,
            "subject": args.subject,
        },
        limitations=["Email was sent only because explicit approval and SMTP execution flags were supplied."],
    )
    return emit("send", status, {"approval_ref": args.approval_ref, "runtime_evidence_path": runtime_path, "delivered": delivered}, ok=delivered)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--to", default="")
    parser.add_argument("--from", dest="from_addr", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--approval-ref", default="")
    parser.add_argument("--execute-approved", action="store_true")
    parser.add_argument("--smtp-host", default="")
    parser.add_argument("--smtp-port", type=int, default=25)
    parser.add_argument("--smtp-user", default="")
    parser.add_argument("--smtp-password", default="")
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--ssl", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--runtime-evidence-out", default="")


def cmd_top_level(args: argparse.Namespace) -> int:
    if args.check_config or args.body_file or args.approval_ref or args.execute_approved or args.smtp_host or os.environ.get("SMTP_HOST"):
        return cmd_send(args)
    return cmd_draft(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    sub = parser.add_subparsers(dest="command")
    for name, func in (("draft", cmd_draft), ("send", cmd_send)):
        command = sub.add_parser(name)
        add_common_args(command)
        command.set_defaults(func=func)
    parser.set_defaults(func=cmd_top_level, command="draft")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
