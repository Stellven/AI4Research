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
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == request_hash == archive["request_sha256"]
    serialized = json.dumps(archive).lower()
    assert "authorization" not in serialized.replace("authorization_header_not_archived", "")
    assert "api_key" not in serialized

