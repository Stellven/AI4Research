"""Black-box E2E evidence for the local identity/privacy/channel service."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
SERVICE = REPO / "harness" / "lib" / "identity" / "service.py"


class LocalService:
    def __init__(self, home: Path):
        self.home, self.ready = home, home.parent / (home.name + ".identity-ready.json")
        self.proc = subprocess.Popen([sys.executable, str(SERVICE), "--home", str(home), "--ready-file", str(self.ready)], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(50):
            if self.ready.exists():
                self.url = "http://127.0.0.1:%s" % json.loads(self.ready.read_text())["port"]
                return
            time.sleep(0.05)
        self.proc.kill()
        raise AssertionError("service did not become ready")

    def close(self) -> None:
        self.proc.terminate(); self.proc.wait(timeout=5)

    def request(self, method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        raw = json.dumps(body or {}).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token: headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(self.url + path, raw, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())


@pytest.fixture
def service(tmp_path: Path):
    app = LocalService(tmp_path / "explicit-sandbox-home")
    yield app
    app.close()


def register(app: LocalService, username: str, password: str = "safe-password-more-than-twelve") -> str:
    status, payload = app.request("POST", "/v1/accounts/register", {"username": username, "password": password, "display_name": username})
    assert status == 201, payload
    return payload["session"]["token"]


def test_account_session_profile_lifecycle_and_cross_account_isolation(service: LocalService) -> None:
    owner_token = register(service, "owner")
    other_token = register(service, "other")
    status, hosted = service.request("POST", "/v1/accounts/register", {"mode": "hosted", "username": "hosted", "password": "safe-password-more-than-twelve"})
    assert (status, hosted["error"]) == (501, "hosted_account_not_available")
    status, updated = service.request("POST", "/v1/profiles/owner", {"profile": {"email": "owner@example.invalid", "name": "Owner"}}, owner_token)
    assert status == 200 and updated["account"]["profile"]["name"] == "Owner"
    status, denied = service.request("GET", "/v1/profiles/owner", token=other_token)
    assert (status, denied["error"]) == (403, "cross_account_access")
    status, stale = service.request("POST", "/v1/accounts/login", {"username": "owner", "password": "safe-password-more-than-twelve", "ttl_seconds": 1})
    assert status == 200
    time.sleep(1.1)
    status, expired = service.request("GET", "/v1/profiles/owner", token=stale["session"]["token"])
    assert (status, expired["error"]) == (401, "invalid_session")
    assert service.request("POST", "/v1/accounts/logout", {}, owner_token)[0] == 200
    status, logged_out = service.request("GET", "/v1/profiles/owner", token=owner_token)
    assert (status, logged_out["error"]) == (401, "invalid_session")


def test_controlled_channel_auth_retry_dedup_and_revocation(service: LocalService) -> None:
    token = register(service, "channel-owner")
    provider_secret = "credential-secret-never-written-to-artifacts"
    status, credential = service.request("POST", "/v1/credentials", {"provider": "discord", "secret": provider_secret}, token)
    assert status == 201 and provider_secret not in json.dumps(credential)
    delivery = {"provider": "discord", "credential_id": credential["credential_id"], "credential_secret": provider_secret, "delivery_id": "delivery-001", "body": "controlled delivery", "transient_fail_once": True}
    status, first = service.request("POST", "/v1/channels/deliver", delivery, token)
    assert status == 200 and first["attempts"] == 2 and not first["deduplicated"]
    status, duplicate = service.request("POST", "/v1/channels/deliver", delivery, token)
    assert status == 200 and duplicate["deduplicated"] and duplicate["attempts"] == 2
    assert service.request("POST", f"/v1/credentials/{credential['credential_id']}/revoke", {}, token)[0] == 200
    status, revoked = service.request("POST", "/v1/channels/deliver", delivery, token)
    assert (status, revoked["error"]) == (403, "revoked_credential")
    status, contract = service.request("GET", "/v1/contracts")
    assert status == 200 and contract["external_platforms"] == {"discord": "ENVIRONMENT_BLOCKED", "wechat": "ENVIRONMENT_BLOCKED"}
    logs = (service.home / "logs" / "audit.jsonl").read_text(encoding="utf-8")
    assert provider_secret not in logs and token not in logs


def test_sandbox_privacy_export_backup_redaction_delete_and_uninstall(service: LocalService) -> None:
    token = register(service, "privacy-owner")
    profile = {"email": "privacy-owner@example.invalid", "phone": "+14165550123", "api_token": "Bearer LONG-PROTECTED-TOKEN-123456789"}
    assert service.request("POST", "/v1/profiles/privacy-owner", {"profile": profile}, token)[0] == 200
    export = service.home / "derived" / "export.json"; backup = service.home / "backups" / "backup.json"
    for endpoint, output in (("export", export), ("backup", backup)):
        status, payload = service.request("POST", f"/v1/privacy/{endpoint}", {"out": str(output)}, token)
        assert status == 200 and payload["redacted"] and "privacy-owner@example.invalid" not in output.read_text()
    status, redacted = service.request("POST", "/v1/privacy/redact", {"text": "privacy-owner@example.invalid +14165550123 Bearer LONG-PROTECTED-TOKEN-123456789"}, token)
    assert status == 200 and "privacy-owner@example.invalid" not in redacted["text"] and "[REDACTED]" in redacted["text"]
    status, deleted = service.request("POST", "/v1/privacy/delete", {}, token)
    assert status == 200 and set(deleted["removed_surfaces"]) == {"primary", "cache", "index", "logs", "derived", "backups"}
    assert not any((service.home / name).exists() for name in ("primary", "cache", "index", "logs", "derived", "backups"))
    # A fresh sandbox proves uninstall has the same all-surfaces deletion contract.
    fresh = LocalService(service.home.parent / "uninstall-sandbox")
    try:
        fresh_token = register(fresh, "uninstall-owner")
        status, removed = fresh.request("POST", "/v1/privacy/uninstall", {}, fresh_token)
        assert status == 200 and set(removed["removed_surfaces"]) == {"primary", "cache", "index", "logs", "derived", "backups"}
        assert not any((fresh.home / name).exists() for name in ("primary", "cache", "index", "logs", "derived", "backups"))
    finally:
        fresh.close()
