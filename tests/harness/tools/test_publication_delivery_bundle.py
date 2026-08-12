from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.tools.publication_delivery_bundle import construct, verify


def _request(root: Path) -> Path:
    source = root / "report.md"
    source.write_text("# Report\n\nA bounded local result.\n", encoding="utf-8")
    request = root / "request.json"
    request.write_text(
        json.dumps({
            "schema": "publication_delivery_request.v1",
            "delivery_id": "delivery-test",
            "audience": {"role": "technical_lead"},
            "delivery_format": "markdown_bundle",
            "content_scope": ["report"],
            "permissions": {"distribution_scope": "local_only", "approval_required": True, "approval_state": "not_requested"},
            "files": [{"file_id": "report", "type": "report", "source_path": str(source), "evidence_ids": ["report:test"]}],
        }),
        encoding="utf-8",
    )
    return request


def test_delivery_bundle_build_verify_and_tamper_rejection(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    construct(_request(tmp_path), bundle, tmp_path)
    assert verify(bundle).is_file()
    report = next((bundle / "files").iterdir())
    report.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify(bundle)


def test_delivery_bundle_rejects_secret_and_extra_inventory(tmp_path: Path) -> None:
    request = _request(tmp_path)
    source = tmp_path / "report.md"
    source.write_text("sk-realisticSecretToken123456789", encoding="utf-8")
    with pytest.raises(ValueError, match="secret-like"):
        construct(request, tmp_path / "secret-bundle", tmp_path)

    source.write_text("task-autosci-skill-assignment is an evidence id, not a credential", encoding="utf-8")
    bundle = tmp_path / "clean-bundle"
    construct(request, bundle, tmp_path)
    (bundle / "unlisted.txt").write_text("not in manifest", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory mismatch"):
        verify(bundle)


def test_delivery_bundle_rejects_unapproved_or_escaping_source(tmp_path: Path) -> None:
    request = _request(tmp_path)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["permissions"]["approval_state"] = "approved"
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="truthful local-only"):
        construct(request, tmp_path / "approved-bundle", tmp_path)

    outside = tmp_path.parent / "outside-publication-delivery.txt"
    outside.write_text("outside", encoding="utf-8")
    payload["permissions"]["approval_state"] = "not_requested"
    payload["files"][0]["source_path"] = str(outside)
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes source root"):
        construct(request, tmp_path / "escape-bundle", tmp_path)
