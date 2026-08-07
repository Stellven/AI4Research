#!/usr/bin/env python3
"""Production local service for identity, privacy, and controlled channels.

It only accepts an explicit ``--home`` supplied by the caller.  This keeps all
state under a test/deployment sandbox and prevents accidental use of a real
user home.  Authentication material is never written to audit logs or returned
after issuance; only hashes and bounded fingerprints are persisted.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from channels.adapter import PROVIDER_CONTRACTS, deliver
    from privacy.lifecycle import redact_text, remove_personal_data_surfaces, under_root, write_redacted_export
except ImportError:  # direct execution from the repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from channels.adapter import PROVIDER_CONTRACTS, deliver
    from privacy.lifecycle import redact_text, remove_personal_data_surfaces, under_root, write_redacted_export


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _hash(value: str, salt: bytes | None = None) -> dict[str, Any]:
    salt = salt or secrets.token_bytes(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, rounds)
    return {"algorithm": "pbkdf2_sha256", "rounds": rounds,
            "salt": base64.b64encode(salt).decode(), "digest": base64.b64encode(digest).decode()}


def _matches(value: str, encoded: dict[str, Any]) -> bool:
    actual = _hash(value, base64.b64decode(encoded["salt"]))["digest"]
    return hmac.compare_digest(actual, str(encoded["digest"]))


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


class Store:
    def __init__(self, home: Path):
        self.home = home.resolve(strict=False)
        self.path = self.home / "primary" / "identity-store.json"
        self.lock = threading.RLock()
        self.data: dict[str, Any] = {"schema_version": 1, "accounts": {}, "sessions": {}, "credentials": {}, "deliveries": {}}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        for name in ("primary", "cache", "index", "logs", "derived", "backups"):
            (self.home / name).mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    def audit(self, username: str, event: str, detail: dict[str, Any] | None = None) -> None:
        # Event details are constructed by callers and must never contain a secret or session token.
        record = {"at": int(time.time()), "username": username, "event": event, "detail": detail or {}}
        with (self.home / "logs" / "audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def issue_session(self, username: str, ttl: int = 900) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        session_id = secrets.token_hex(12)
        self.data["sessions"][session_id] = {"username": username, "token_hash": _hash(token), "expires_at": int(time.time()) + ttl, "revoked": False}
        self.save(); self.audit(username, "session.issued", {"session_id": session_id, "ttl": ttl})
        return {"token": token, "expires_at": int(time.time()) + ttl}

    def authenticate(self, token: str) -> str:
        now = int(time.time())
        for session in self.data["sessions"].values():
            if not session["revoked"] and session["expires_at"] > now and _matches(token, session["token_hash"]):
                return str(session["username"])
        raise ServiceError(HTTPStatus.UNAUTHORIZED, "invalid_session", "session is missing, revoked, or stale")

    def verify_credential(self, username: str, credential_id: str, secret: str, provider: str) -> None:
        item = self.data["credentials"].get(credential_id)
        if not item or item["username"] != username or item["provider"] != provider:
            raise ServiceError(HTTPStatus.FORBIDDEN, "invalid_credential", "credential is not available to this account")
        if item["revoked"]:
            raise ServiceError(HTTPStatus.FORBIDDEN, "revoked_credential", "credential has been revoked")
        if not _matches(secret, item["secret_hash"]):
            raise ServiceError(HTTPStatus.FORBIDDEN, "invalid_credential", "credential verification failed")


def _public_account(username: str, account: dict[str, Any]) -> dict[str, Any]:
    return {"username": username, "display_name": account.get("display_name", ""), "profile": account.get("profile", {}), "scope": "local_only"}


class Handler(BaseHTTPRequestHandler):
    store: Store
    server_version = "OpenSolarIdentity/1"

    def log_message(self, _format: str, *_args: Any) -> None:
        # BaseHTTPRequestHandler would log paths/headers.  Keep token-bearing input out of artifacts.
        return

    def json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise ServiceError(HTTPStatus.BAD_REQUEST, "invalid_json", "body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ServiceError(HTTPStatus.BAD_REQUEST, "invalid_json", "body must be an object")
        return body

    def token_user(self, body: dict[str, Any]) -> str:
        token = str(self.headers.get("Authorization", "")).removeprefix("Bearer ")
        token = token or str(body.pop("session_token", ""))
        return self.store.authenticate(token)

    def reply(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def dispatch(self) -> tuple[int, dict[str, Any]]:
        path = self.path.split("?", 1)[0]
        if self.command == "GET" and path == "/v1/contracts":
            return 200, {"repo_owned": ["registration", "session", "profile", "credential_revocation", "privacy_lifecycle", "controlled_channel_adapter"], "external_platforms": {key: spec["external_status"] for key, spec in PROVIDER_CONTRACTS.items()}}
        body = self.json_body() if self.command == "POST" else {}
        if self.command == "POST" and path == "/v1/accounts/register":
            if body.get("mode") == "hosted":
                raise ServiceError(HTTPStatus.NOT_IMPLEMENTED, "hosted_account_not_available", "hosted accounts are not implemented by this repository")
            username, password = str(body.get("username", "")), str(body.get("password", ""))
            if not username or len(password) < 12 or username in self.store.data["accounts"]:
                raise ServiceError(HTTPStatus.BAD_REQUEST, "invalid_registration", "unique username and a 12-character password are required")
            self.store.data["accounts"][username] = {"password_hash": _hash(password), "display_name": str(body.get("display_name", "")), "profile": {}}
            self.store.save(); self.store.audit(username, "account.registered")
            ttl = int(body.get("ttl_seconds", 900))
            if ttl < 1 or ttl > 86_400: raise ServiceError(400, "invalid_ttl", "ttl_seconds must be between 1 and 86400")
            return 201, {"account": _public_account(username, self.store.data["accounts"][username]), "session": self.store.issue_session(username, ttl)}
        if self.command == "POST" and path == "/v1/accounts/login":
            username, password = str(body.get("username", "")), str(body.get("password", "")); account = self.store.data["accounts"].get(username)
            if not account or not _matches(password, account["password_hash"]):
                raise ServiceError(HTTPStatus.UNAUTHORIZED, "invalid_login", "invalid username or password")
            ttl = int(body.get("ttl_seconds", 900))
            if ttl < 1 or ttl > 86_400: raise ServiceError(400, "invalid_ttl", "ttl_seconds must be between 1 and 86400")
            return 200, {"session": self.store.issue_session(username, ttl)}
        if self.command == "POST" and path == "/v1/accounts/logout":
            user = self.token_user(body)
            token = str(self.headers.get("Authorization", "")).removeprefix("Bearer ") or str(body.get("session_token", ""))
            for session in self.store.data["sessions"].values():
                if session["username"] == user and _matches(token, session["token_hash"]): session["revoked"] = True
            self.store.save(); self.store.audit(user, "session.logged_out"); return 200, {"state": "logged_out"}
        if path.startswith("/v1/profiles/"):
            user = self.token_user(body); requested = path.rsplit("/", 1)[-1]
            if requested != user: raise ServiceError(HTTPStatus.FORBIDDEN, "cross_account_access", "profiles are owner-only")
            account = self.store.data["accounts"].get(user)
            if self.command == "GET": return 200, {"account": _public_account(user, account)}
            if self.command == "POST":
                profile = body.get("profile");
                if not isinstance(profile, dict): raise ServiceError(400, "invalid_profile", "profile must be an object")
                account["profile"] = profile; self.store.save(); self.store.audit(user, "profile.updated", {"fields": sorted(profile)})
                return 200, {"profile_updated": True, "account": _public_account(user, account)}
        if self.command == "POST" and path == "/v1/credentials":
            user = self.token_user(body); provider, secret = str(body.get("provider", "")), str(body.get("secret", ""))
            if provider not in PROVIDER_CONTRACTS or not secret: raise ServiceError(400, "invalid_credential", "supported provider and secret are required")
            credential_id = secrets.token_hex(12); self.store.data["credentials"][credential_id] = {"username": user, "provider": provider, "secret_hash": _hash(secret), "fingerprint": _fingerprint(secret), "revoked": False}
            self.store.save(); self.store.audit(user, "credential.added", {"provider": provider, "credential_id": credential_id})
            return 201, {"credential_id": credential_id, "provider": provider, "fingerprint": _fingerprint(secret)}
        if self.command == "POST" and path.startswith("/v1/credentials/") and path.endswith("/revoke"):
            user = self.token_user(body); credential_id = path.split("/")[3]; item = self.store.data["credentials"].get(credential_id)
            if not item or item["username"] != user: raise ServiceError(404, "credential_not_found", "credential not found")
            item["revoked"] = True; self.store.save(); self.store.audit(user, "credential.revoked", {"credential_id": credential_id}); return 200, {"state": "revoked"}
        if self.command == "POST" and path == "/v1/channels/deliver":
            user = self.token_user(body)
            try: result = deliver(self.store, user, str(body["provider"]), str(body["credential_id"]), str(body["credential_secret"]), str(body["delivery_id"]), str(body["body"]), bool(body.get("transient_fail_once")))
            except KeyError as exc: raise ServiceError(400, "invalid_delivery", "missing delivery field") from exc
            return 200, result
        if self.command == "POST" and path == "/v1/privacy/redact":
            user = self.token_user(body); self.store.audit(user, "privacy.redacted")
            return 200, {"text": redact_text(str(body.get("text", ""))), "redacted": True}
        if self.command == "POST" and path == "/v1/privacy/export":
            user = self.token_user(body); destination = under_root(Path(str(body.get("out", ""))), self.store.home)
            account = self.store.data["accounts"][user]; written = write_redacted_export(self.store.home, destination, {"account": _public_account(user, account), "audit_scope": "redacted"})
            self.store.audit(user, "privacy.exported", {"out": str(written.relative_to(self.store.home))}); return 200, {"out": str(written), "redacted": True}
        if self.command == "POST" and path == "/v1/privacy/backup":
            user = self.token_user(body); destination = under_root(Path(str(body.get("out", ""))), self.store.home)
            account = self.store.data["accounts"][user]; written = write_redacted_export(self.store.home, destination, {"backup": _public_account(user, account)})
            self.store.audit(user, "privacy.backed_up", {"out": str(written.relative_to(self.store.home))}); return 200, {"out": str(written), "redacted": True}
        if self.command == "POST" and path == "/v1/privacy/delete":
            user = self.token_user(body); self.store.data["accounts"].pop(user, None)
            for session in self.store.data["sessions"].values():
                if session["username"] == user: session["revoked"] = True
            for item in self.store.data["credentials"].values():
                if item["username"] == user: item["revoked"] = True
            self.store.save(); removed = remove_personal_data_surfaces(self.store.home)
            return 200, {"state": "deleted", "removed_surfaces": removed}
        if self.command == "POST" and path == "/v1/privacy/uninstall":
            user = self.token_user(body); self.store.audit(user, "privacy.uninstall_requested")
            removed = remove_personal_data_surfaces(self.store.home); return 200, {"state": "uninstalled", "removed_surfaces": removed}
        raise ServiceError(404, "not_found", "route not found")

    def do_GET(self) -> None: self._serve()
    def do_POST(self) -> None: self._serve()
    def _serve(self) -> None:
        try:
            with self.store.lock: status, payload = self.dispatch()
            self.reply(status, payload)
        except ServiceError as exc: self.reply(int(exc.status), {"error": exc.code, "message": exc.message})
        except ValueError as exc: self.reply(400, {"error": "invalid_request", "message": str(exc)})
        except PermissionError as exc: self.reply(403, {"error": "forbidden", "message": str(exc)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--home", required=True); parser.add_argument("--port", type=int, default=0); parser.add_argument("--ready-file")
    args = parser.parse_args(argv); home = Path(args.home)
    if not home.is_absolute(): parser.error("--home must be an explicit absolute sandbox path")
    Handler.store = Store(home); server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    if args.ready_file:
        Path(args.ready_file).write_text(json.dumps({"port": server.server_port}), encoding="utf-8")
    server.serve_forever()
    return 0


if __name__ == "__main__": raise SystemExit(main())
