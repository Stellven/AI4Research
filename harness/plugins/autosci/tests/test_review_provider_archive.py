from __future__ import annotations

import hashlib
import json

from harness.plugins.autosci.backends.artifact_review import _archive_provider_payload


def test_provider_archive_retains_recomputable_nonsecret_request(tmp_path):
    request = {"model": "local-test", "messages": [{"role": "user", "content": "bounded review"}]}
    path, request_hash, _ = _archive_provider_payload(
        workspace_root=tmp_path,
        provider="openai_compatible",
        request_payload=request,
        response_payload={"choices": []},
        model_payload={"schema": "artifact_review.v1"},
    )
    assert path is not None
    archive = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(archive["request_body_redacted"], ensure_ascii=False, sort_keys=True)
    assert request_hash == archive["request_sha256"]
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == archive["redacted_archive_request_sha256"]
    serialized = json.dumps(archive).lower()
    assert "authorization" not in serialized.replace("authorization_header_not_archived", "")
    assert "api_key" not in serialized


def test_provider_archive_redacts_nested_and_inline_secrets_from_all_archived_bytes(tmp_path):
    secret = "SUPERSECRET-attack-value"
    request = {
        "api_key": secret,
        "messages": [{"content": f"artifact says api_key={secret}; Authorization: Bearer bearer-token-123456"}],
        "nested": {"password": secret, "note": "token: token-value-123456"},
        "private": "-----BEGIN PRIVATE KEY-----\nSUPERSECRET\n-----END PRIVATE KEY-----",
    }
    path, original_hash, _ = _archive_provider_payload(
        workspace_root=tmp_path,
        provider="openai_compatible",
        request_payload=request,
        response_payload={"echo": f"Bearer {secret}", "client_secret": secret},
        model_payload={"finding": f"password={secret}"},
    )
    assert path is not None
    archive_bytes = path.read_bytes()
    for forbidden in (b"SUPERSECRET", b"bearer-token-123456", b"token-value-123456", b"BEGIN PRIVATE KEY"):
        assert forbidden not in archive_bytes
    archive = json.loads(archive_bytes)
    assert archive["request_sha256"] == original_hash
    canonical = json.dumps(archive["request_body_redacted"], ensure_ascii=False, sort_keys=True)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == archive["redacted_archive_request_sha256"]
