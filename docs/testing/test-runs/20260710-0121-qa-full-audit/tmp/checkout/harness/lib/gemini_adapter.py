#!/usr/bin/env python3
"""Gemini CLI/SDK adapter for Solar Harness background workers."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _model_alias(value: str) -> str:
    raw = (value or "gemini").strip().lower()
    aliases = {
        "gemini": "gemini-2.5-pro",
        "gemini-pro": "gemini-2.5-pro",
        "gemini-2.5": "gemini-2.5-pro",
        "gemini-flash": "gemini-2.5-flash",
        "flash": "gemini-2.5-flash",
    }
    return aliases.get(raw, value)


def _sdk_available() -> tuple[bool, str]:
    try:
        import google.genai  # type: ignore  # noqa: F401

        return True, "google.genai"
    except Exception as exc:
        return False, f"google.genai:{type(exc).__name__}"


def _normalize_cli_auth(value: str) -> str:
    raw = (value or "subscription").strip().lower().replace("_", "-")
    aliases = {
        "": "subscription",
        "pro": "subscription",
        "oauth": "subscription",
        "oauth-personal": "subscription",
        "login": "subscription",
        "login-with-google": "subscription",
        "google": "subscription",
        "gca": "subscription",
        "api": "api-key",
        "api_key": "api-key",
        "gemini-api-key": "api-key",
    }
    return aliases.get(raw, raw)


def _oauth_creds_path() -> Path:
    return Path.home() / ".gemini" / "oauth_creds.json"


def _settings_path() -> Path:
    return Path.home() / ".gemini" / "settings.json"


def _subscription_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GOOGLE_GENAI_USE_GCA"] = "true"
    env.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    # Solar Harness uses Gemini CLI subscriptions by default. API keys are
    # intentionally removed for this child process so an expired or costly key
    # cannot override the Pro/OAuth route.
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    return env


def _cli_env(auth: str) -> dict[str, str] | None:
    mode = _normalize_cli_auth(auth)
    if mode == "subscription":
        return _subscription_env()
    if mode in {"auto", "api-key"}:
        return None
    return None


def doctor() -> dict[str, Any]:
    gemini = shutil.which("gemini")
    sdk_ok, sdk_detail = _sdk_available()
    default_auth = _normalize_cli_auth(os.environ.get("SOLAR_GEMINI_CLI_AUTH", "subscription"))
    oauth_creds = _oauth_creds_path().exists()
    api_key_env = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if default_auth == "subscription":
        cli_ready = bool(gemini) and oauth_creds
        cli_warning = "" if cli_ready else "subscription OAuth cache missing; run interactive Gemini CLI login once"
    elif default_auth == "api-key":
        cli_ready = bool(gemini) and bool(os.environ.get("GEMINI_API_KEY"))
        cli_warning = "" if cli_ready else "api-key mode requires GEMINI_API_KEY"
    else:
        cli_ready = bool(gemini)
        cli_warning = ""
    return {
        "ok": bool(gemini) or sdk_ok,
        "cli": {
            "ok": bool(gemini),
            "ready": cli_ready,
            "path": gemini or "",
            "default_auth": default_auth,
            "oauth_creds": oauth_creds,
            "settings": _settings_path().exists(),
            "api_key_env_present": api_key_env,
            "warning": cli_warning,
        },
        "sdk": {
            "ok": sdk_ok,
            "detail": sdk_detail,
        },
        "auth_hints": {
            "cli": "Default is subscription/OAuth. API-key mode requires --auth api-key or SOLAR_GEMINI_CLI_AUTH=api-key.",
            "sdk": "Set GOOGLE_API_KEY or use Application Default Credentials before selecting gemini-sdk.",
        },
    }


def run_cli(prompt: str, model: str, approval_mode: str, output_format: str, auth: str) -> int:
    gemini = shutil.which("gemini")
    if not gemini:
        print("ERROR: gemini CLI not found", file=sys.stderr)
        return 127
    auth_mode = _normalize_cli_auth(auth)
    cmd = [
        gemini,
        "--model",
        _model_alias(model),
        "--approval-mode",
        approval_mode or "auto_edit",
        "--output-format",
        output_format or "text",
        "--prompt",
        prompt,
    ]
    if auth_mode not in {"subscription", "api-key", "auto"}:
        print(f"ERROR: unsupported Gemini CLI auth mode: {auth}", file=sys.stderr)
        return 64
    return subprocess.call(cmd, env=_cli_env(auth_mode))


def run_sdk(prompt: str, model: str) -> int:
    try:
        from google import genai  # type: ignore
    except Exception as exc:
        print(f"ERROR: google-genai SDK not available: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 127
    try:
        client = genai.Client()
        result = client.models.generate_content(model=_model_alias(model), contents=prompt)
        text = getattr(result, "text", None)
        if text:
            print(text)
        else:
            print(result)
        return 0
    except Exception as exc:
        print(f"ERROR: gemini SDK call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gemini_adapter.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    run = sub.add_parser("run")
    run.add_argument("--backend", choices=["cli", "sdk"], default="cli")
    run.add_argument("--model", default="gemini")
    run.add_argument("--prompt-file", required=True)
    run.add_argument("--approval-mode", default="auto_edit")
    run.add_argument("--output-format", default="text")
    run.add_argument("--auth", default=os.environ.get("SOLAR_GEMINI_CLI_AUTH", "subscription"),
                     choices=["subscription", "oauth", "oauth-personal", "api-key", "auto"],
                     help="Gemini CLI auth route. Default subscription uses Google login/Pro, not API keys.")
    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        return 0 if doctor().get("ok") else 1

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    if args.backend == "sdk":
        return run_sdk(prompt, args.model)
    return run_cli(prompt, args.model, args.approval_mode, args.output_format, args.auth)


if __name__ == "__main__":
    raise SystemExit(main())
