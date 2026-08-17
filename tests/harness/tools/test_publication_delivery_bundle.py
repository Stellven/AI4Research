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
    with pytest.raises(ValueError, match="local-only/not-requested or approved external_email"):
        construct(request, tmp_path / "approved-bundle", tmp_path)

    outside = tmp_path.parent / "outside-publication-delivery.txt"
    outside.write_text("outside", encoding="utf-8")
    payload["permissions"]["approval_state"] = "not_requested"
    payload["files"][0]["source_path"] = str(outside)
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes source root"):
        construct(request, tmp_path / "escape-bundle", tmp_path)


def test_delivery_bundle_accepts_approved_external_email_audit(tmp_path: Path) -> None:
    request = _request(tmp_path)
    audit = tmp_path / "external-delivery-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_external_delivery_audit.v1",
                "action": "send_email",
                "status": "completed",
                "provider": "gmail_connector",
                "channel": "gmail",
                "approval_ref": "approval-phase22-email",
                "to": "reader@example.com",
                "subject": "Phase 22 handoff",
                "delivered": True,
                "message_id_sha256": "a" * 64,
                "thread_id_sha256": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["permissions"] = {
        "distribution_scope": "external_email",
        "approval_required": True,
        "approval_state": "approved",
        "approval_ref": "approval-phase22-email",
        "approved_by": "phase22-user",
        "approved_at": "2026-08-12T00:00:00Z",
    }
    payload["external_delivery"] = {
        "channel": "gmail",
        "recipient": "reader@example.com",
        "runtime_evidence_path": str(audit),
        "recipient_acceptance_required": False,
    }
    request.write_text(json.dumps(payload), encoding="utf-8")

    manifest_path = construct(request, tmp_path / "external-bundle", tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert verify(tmp_path / "external-bundle").is_file()
    assert manifest["permissions"]["distribution_scope"] == "external_email"
    assert manifest["external_delivery"]["delivered"] is True
    assert manifest["external_delivery"]["recipient"] == "reader@example.com"
    assert any(item["file_id"] == "external-delivery-runtime-evidence" for item in manifest["files"])


def test_delivery_bundle_rejects_external_email_recipient_mismatch(tmp_path: Path) -> None:
    request = _request(tmp_path)
    audit = tmp_path / "external-delivery-audit.json"
    audit.write_text(
        json.dumps(
            {
                "schema": "autosci_external_delivery_audit.v1",
                "action": "send_email",
                "status": "completed",
                "provider": "gmail_connector",
                "approval_ref": "approval-phase22-email",
                "to": "wrong@example.com",
                "delivered": True,
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["permissions"] = {
        "distribution_scope": "external_email",
        "approval_required": True,
        "approval_state": "approved",
        "approval_ref": "approval-phase22-email",
        "approved_by": "phase22-user",
    }
    payload["external_delivery"] = {
        "channel": "gmail",
        "recipient": "reader@example.com",
        "runtime_evidence_path": str(audit),
    }
    request.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="recipient mismatch"):
        construct(request, tmp_path / "mismatch-bundle", tmp_path)
