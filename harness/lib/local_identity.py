#!/usr/bin/env python3
"""Local-only identity, session, profile, and privacy controls for Solar.

This is deliberately not a Solar cloud/product account backend. It protects
local profile/privacy operations with a sandboxable account store, hashed
passwords, hashed session tokens, expiry, logout, redacted export, and delete.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "solar.local_identity.v1"
HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 260_000
DEFAULT_SESSION_TTL_SECONDS = 3600
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@+-]{3,128}$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()_-]{7,}\d)(?!\d)")
TOKEN_RE = re.compile(r"\b(?:Bearer\s+)?[A-Za-z0-9_-]{24,}\b")
SENSITIVE_KEY_PARTS = ("password", "secret", "token", "credential", "api_key", "apikey")


class IdentityError(Exception):
    def __init__(self, code: str, message: str, status: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _utc_now() -> int:
    return int(time.time())


def _iso(ts: int | None = None) -> str:
    ts = _utc_now() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _store_path() -> Path:
    override = os.environ.get("SOLAR_IDENTITY_STORE")
    if override:
        return Path(override).expanduser()
    solar_home = Path(os.environ.get("SOLAR_HOME") or Path.home() / ".solar").expanduser()
    return solar_home / "identity" / "local-accounts.json"


def _empty_store() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "accounts": {},
        "sessions": {},
        "audit": [],
    }


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_store()
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise IdentityError("invalid_store", "identity store is not a JSON object")
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("accounts", {})
    data.setdefault("sessions", {})
    data.setdefault("audit", [])
    return data


def _write_store(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _normalize_username(username: str) -> str:
    value = str(username or "").strip().lower()
    if not USERNAME_RE.fullmatch(value):
        raise IdentityError(
            "invalid_username",
            "username must be 3-128 characters using letters, numbers, . _ @ + -",
            2,
        )
    return value


def _read_password_from_stdin() -> str:
    password = sys.stdin.read()
    password = password.rstrip("\r\n")
    if len(password) < 12:
        raise IdentityError("weak_password", "password must be at least 12 characters", 2)
    return password


def _hash_password(password: str) -> dict[str, Any]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return {
        "algorithm": HASH_ALGORITHM,
        "iterations": HASH_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
    }


def _verify_password(password: str, stored: dict[str, Any]) -> bool:
    if stored.get("algorithm") != HASH_ALGORITHM:
        return False
    try:
        salt = base64.b64decode(stored["salt"])
        expected = base64.b64decode(stored["hash"])
        iterations = int(stored["iterations"])
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _purge_expired_sessions(store: dict[str, Any], now: int | None = None) -> None:
    now = _utc_now() if now is None else now
    sessions = store.get("sessions", {})
    for key in list(sessions.keys()):
        if int(sessions[key].get("expires_at", 0)) <= now:
            del sessions[key]


def _issue_session(store: dict[str, Any], username: str, ttl_seconds: int) -> dict[str, Any]:
    ttl = max(1, min(int(ttl_seconds), 30 * 24 * 3600))
    now = _utc_now()
    raw_token = secrets.token_urlsafe(32)
    account = store["accounts"][username]
    store["sessions"][_token_hash(raw_token)] = {
        "user_id": account["user_id"],
        "username": username,
        "created_at": now,
        "expires_at": now + ttl,
    }
    return {
        "token": raw_token,
        "expires_at": _iso(now + ttl),
        "ttl_seconds": ttl,
    }


def _session_for_token(store: dict[str, Any], token: str) -> dict[str, Any]:
    _purge_expired_sessions(store)
    if not token:
        raise IdentityError("missing_token", "session token is required", 2)
    session = store.get("sessions", {}).get(_token_hash(token))
    if not session:
        raise IdentityError("invalid_session", "session is invalid or expired", 3)
    username = session.get("username", "")
    account = store.get("accounts", {}).get(username)
    if not account or account.get("user_id") != session.get("user_id"):
        raise IdentityError("invalid_session", "session is invalid or expired", 3)
    return session


def _redact_text(value: str) -> str:
    value = EMAIL_RE.sub("[EMAIL]", value)
    value = PHONE_RE.sub("[PHONE]", value)
    value = TOKEN_RE.sub("[TOKEN]", value)
    return value


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in SENSITIVE_KEY_PARTS):
                out[key_text] = "[REDACTED]"
            else:
                out[key_text] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _audit(store: dict[str, Any], event: str, user_id: str) -> None:
    store.setdefault("audit", []).append(
        {
            "event": event,
            "at": _iso(),
            "user_id_hash": hashlib.sha256(user_id.encode("utf-8")).hexdigest(),
        }
    )


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "active": True,
        "username": session.get("username", ""),
        "user_id": session.get("user_id", ""),
        "created_at": _iso(int(session.get("created_at", 0))),
        "expires_at": _iso(int(session.get("expires_at", 0))),
    }


def _register(args: argparse.Namespace) -> dict[str, Any]:
    if not args.local_only:
        raise IdentityError(
            "product_account_unsupported",
            "Solar product-account registration is unsupported; pass --local-only for the local identity store",
            2,
        )
    password = _read_password_from_stdin()
    path = _store_path()
    store = _load_store(path)
    _purge_expired_sessions(store)
    username = _normalize_username(args.username)
    if username in store["accounts"]:
        raise IdentityError("account_exists", "local account already exists", 2)
    now = _utc_now()
    user_id = "local_" + secrets.token_urlsafe(18)
    store["accounts"][username] = {
        "user_id": user_id,
        "username": username,
        "account_scope": "local_only",
        "password_hash": _hash_password(password),
        "terms": {
            "accepted_version": args.terms_version or "local-identity-v1",
            "accepted_at": _iso(now),
        },
        "profile": {
            "owner_user_id": user_id,
            "data": {
                "display_name": args.display_name or username,
            },
            "updated_at": _iso(now),
        },
        "created_at": _iso(now),
    }
    session = _issue_session(store, username, args.session_ttl)
    _audit(store, "local_account_registered", user_id)
    _write_store(path, store)
    return {
        "ok": True,
        "account_scope": "local_only",
        "product_account_status": "unsupported",
        "username": username,
        "user_id": user_id,
        "session": session,
        "store": str(path),
    }


def _login(args: argparse.Namespace) -> dict[str, Any]:
    password = _read_password_from_stdin()
    path = _store_path()
    store = _load_store(path)
    _purge_expired_sessions(store)
    username = _normalize_username(args.username)
    account = store["accounts"].get(username)
    if not account or not _verify_password(password, account.get("password_hash", {})):
        raise IdentityError("invalid_credentials", "invalid username or password", 3)
    session = _issue_session(store, username, args.session_ttl)
    _audit(store, "local_session_created", account["user_id"])
    _write_store(path, store)
    return {"ok": True, "username": username, "user_id": account["user_id"], "session": session}


def _session(args: argparse.Namespace) -> dict[str, Any]:
    path = _store_path()
    store = _load_store(path)
    session = _session_for_token(store, args.token)
    _write_store(path, store)
    return {"ok": True, "session": _public_session(session)}


def _logout(args: argparse.Namespace) -> dict[str, Any]:
    path = _store_path()
    store = _load_store(path)
    token_hash = _token_hash(args.token or "")
    session = store.get("sessions", {}).pop(token_hash, None)
    if not session:
        raise IdentityError("invalid_session", "session is invalid or expired", 3)
    _audit(store, "local_session_logged_out", str(session.get("user_id", "")))
    _write_store(path, store)
    return {"ok": True, "state": "logged_out"}


def _profile_get(args: argparse.Namespace) -> dict[str, Any]:
    path = _store_path()
    store = _load_store(path)
    session = _session_for_token(store, args.token)
    account = store["accounts"][session["username"]]
    profile = copy.deepcopy(account.get("profile", {}))
    _write_store(path, store)
    return {"ok": True, "profile": profile}


def _profile_set(args: argparse.Namespace) -> dict[str, Any]:
    path = _store_path()
    store = _load_store(path)
    session = _session_for_token(store, args.token)
    try:
        data = json.loads(args.data_json)
    except json.JSONDecodeError as exc:
        raise IdentityError("invalid_profile_json", f"profile JSON parse failed: {exc}", 2)
    if not isinstance(data, dict):
        raise IdentityError("invalid_profile_json", "profile JSON must be an object", 2)
    account = store["accounts"][session["username"]]
    account["profile"] = {
        "owner_user_id": account["user_id"],
        "data": data,
        "updated_at": _iso(),
    }
    _audit(store, "local_profile_updated", account["user_id"])
    _write_store(path, store)
    return {
        "ok": True,
        "profile_updated": True,
        "owner_user_id": account["user_id"],
        "updated_at": account["profile"]["updated_at"],
    }


def _privacy_export(args: argparse.Namespace) -> dict[str, Any]:
    path = _store_path()
    store = _load_store(path)
    session = _session_for_token(store, args.token)
    account = store["accounts"][session["username"]]
    payload = {
        "schema_version": "solar.local_identity.export.v1",
        "exported_at": _iso(),
        "account_scope": "local_only",
        "username": account["username"],
        "user_id": account["user_id"],
        "terms": account.get("terms", {}),
        "profile": account.get("profile", {}),
    }
    redacted = redact_value(payload)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(redacted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    _audit(store, "local_privacy_exported", account["user_id"])
    _write_store(path, store)
    return {"ok": True, "export_path": str(out), "redacted": True}


def _privacy_delete(args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        raise IdentityError("confirmation_required", "privacy delete requires --yes", 2)
    path = _store_path()
    store = _load_store(path)
    session = _session_for_token(store, args.token)
    username = session["username"]
    user_id = session["user_id"]
    store["accounts"].pop(username, None)
    for key in list(store.get("sessions", {}).keys()):
        if store["sessions"][key].get("user_id") == user_id:
            del store["sessions"][key]
    _audit(store, "local_account_deleted", user_id)
    _write_store(path, store)
    return {"ok": True, "state": "deleted", "username": username}


def _privacy_redact(args: argparse.Namespace) -> dict[str, Any]:
    src = Path(args.input).expanduser()
    out = Path(args.out).expanduser()
    text = src.read_text(encoding="utf-8", errors="replace")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_redact_text(text), encoding="utf-8")
    return {"ok": True, "redacted": True, "out": str(out)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solar identity/privacy")
    sub = parser.add_subparsers(dest="top", required=True)

    identity = sub.add_parser("identity")
    identity_sub = identity.add_subparsers(dest="verb", required=True)

    register = identity_sub.add_parser("register")
    register.add_argument("--username", required=True)
    register.add_argument("--password-stdin", action="store_true", required=True)
    register.add_argument("--display-name", default="")
    register.add_argument("--terms-version", default="")
    register.add_argument("--local-only", action="store_true")
    register.add_argument("--session-ttl", type=int, default=DEFAULT_SESSION_TTL_SECONDS)
    register.set_defaults(func=_register)

    login = identity_sub.add_parser("login")
    login.add_argument("--username", required=True)
    login.add_argument("--password-stdin", action="store_true", required=True)
    login.add_argument("--session-ttl", type=int, default=DEFAULT_SESSION_TTL_SECONDS)
    login.set_defaults(func=_login)

    session = identity_sub.add_parser("session")
    session.add_argument("--token", required=True)
    session.set_defaults(func=_session)

    logout = identity_sub.add_parser("logout")
    logout.add_argument("--token", required=True)
    logout.set_defaults(func=_logout)

    profile = identity_sub.add_parser("profile")
    profile_sub = profile.add_subparsers(dest="profile_verb", required=True)
    profile_get = profile_sub.add_parser("get")
    profile_get.add_argument("--token", required=True)
    profile_get.set_defaults(func=_profile_get)
    profile_set = profile_sub.add_parser("set")
    profile_set.add_argument("--token", required=True)
    profile_set.add_argument("--data-json", required=True)
    profile_set.set_defaults(func=_profile_set)

    privacy = sub.add_parser("privacy")
    privacy_sub = privacy.add_subparsers(dest="verb", required=True)
    export = privacy_sub.add_parser("export")
    export.add_argument("--token", required=True)
    export.add_argument("--out", required=True)
    export.set_defaults(func=_privacy_export)
    delete = privacy_sub.add_parser("delete")
    delete.add_argument("--token", required=True)
    delete.add_argument("--yes", action="store_true")
    delete.set_defaults(func=_privacy_delete)
    redact = privacy_sub.add_parser("redact")
    redact.add_argument("--in", dest="input", required=True)
    redact.add_argument("--out", required=True)
    redact.set_defaults(func=_privacy_redact)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except IdentityError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "message": exc.message}, indent=2, sort_keys=True), file=sys.stderr)
        return exc.status


if __name__ == "__main__":
    raise SystemExit(main())
