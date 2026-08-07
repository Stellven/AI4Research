#!/usr/bin/env python3
"""Message channel adapter contracts with explicit live-provider gates."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any


class ChannelAdapterError(Exception):
    def __init__(self, code: str, message: str, status: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class AdapterStatus:
    provider: str
    adapter_id: str
    live_status: str
    implemented_scope: str
    missing_prereqs: list[str]
    unsupported_live_claims: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "adapter_id": self.adapter_id,
            "live_status": self.live_status,
            "implemented_scope": self.implemented_scope,
            "missing_prereqs": self.missing_prereqs,
            "unsupported_live_claims": self.unsupported_live_claims,
        }


class MessageChannelAdapter:
    provider = ""
    adapter_id = ""
    implemented_scope = ""
    required_env: tuple[str, ...] = ()
    unsupported_live_claims: tuple[str, ...] = ()

    def status(self) -> AdapterStatus:
        missing = [name for name in self.required_env if not os.environ.get(name)]
        live_status = "ready" if not missing else "provider_gated"
        return AdapterStatus(
            provider=self.provider,
            adapter_id=self.adapter_id,
            live_status=live_status,
            implemented_scope=self.implemented_scope,
            missing_prereqs=missing,
            unsupported_live_claims=list(self.unsupported_live_claims),
        )

    def route(self, raw_input: str) -> dict[str, Any]:
        raise NotImplementedError


class WechatAppleNotesAdapter(MessageChannelAdapter):
    provider = "wechat"
    adapter_id = "wechat.apple_notes_intake.v1"
    implemented_scope = "Authorized Apple Notes content containing WeChat article URLs."
    required_env: tuple[str, ...] = ()
    unsupported_live_claims = (
        "WeChat account login",
        "Mini Program connector",
        "bot/webhook transport",
        "general clipboard or arbitrary channel intake",
    )
    _WECHAT_URL_RE = re.compile(r"^https?://mp\.weixin\.qq\.com/", re.I)

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            provider=self.provider,
            adapter_id=self.adapter_id,
            live_status="local_bridge_available",
            implemented_scope=self.implemented_scope,
            missing_prereqs=[],
            unsupported_live_claims=list(self.unsupported_live_claims),
        )

    def route(self, raw_input: str) -> dict[str, Any]:
        value = str(raw_input or "").strip()
        if not self._WECHAT_URL_RE.match(value):
            raise ChannelAdapterError(
                "unsupported_wechat_input",
                "WeChat intake only accepts mp.weixin.qq.com article URLs through the Apple Notes bridge",
                2,
            )
        return {
            "ok": True,
            "provider": self.provider,
            "adapter_id": self.adapter_id,
            "route": "apple_notes_ingest",
            "input_type": "wechat_article_url",
            "live_status": "local_bridge_available",
        }


class DiscordAdapter(MessageChannelAdapter):
    provider = "discord"
    adapter_id = "discord.provider_gate.v1"
    implemented_scope = "Contract and safe refusal only; no live Discord connector is implemented."
    required_env = ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID", "DISCORD_CHANNEL_ALLOWLIST")
    unsupported_live_claims = (
        "OAuth/bot authorization",
        "message ingestion",
        "outbound notifications",
        "credential revocation against Discord",
    )

    def route(self, raw_input: str) -> dict[str, Any]:
        missing = self.status().missing_prereqs
        raise ChannelAdapterError(
            "provider_gated",
            "Discord live routing requires a real connector and configured provider credentials",
            3 if missing else 2,
        )


ADAPTERS: dict[str, MessageChannelAdapter] = {
    "wechat": WechatAppleNotesAdapter(),
    "discord": DiscordAdapter(),
}


def _adapter(provider: str) -> MessageChannelAdapter:
    key = str(provider or "").strip().lower()
    if key not in ADAPTERS:
        raise ChannelAdapterError("unknown_provider", "unknown channel provider", 2)
    return ADAPTERS[key]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solar channel")
    sub = parser.add_subparsers(dest="verb", required=True)
    status = sub.add_parser("status")
    status.add_argument("--provider", required=True)
    status.set_defaults(func=_cmd_status)
    route = sub.add_parser("route")
    route.add_argument("--provider", required=True)
    route.add_argument("--input", required=True)
    route.set_defaults(func=_cmd_route)
    return parser


def _cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    return {"ok": True, "status": _adapter(args.provider).status().to_dict()}


def _cmd_route(args: argparse.Namespace) -> dict[str, Any]:
    return _adapter(args.provider).route(args.input)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except ChannelAdapterError as exc:
        print(
            json.dumps({"ok": False, "error": exc.code, "message": exc.message}, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return exc.status


if __name__ == "__main__":
    raise SystemExit(main())
