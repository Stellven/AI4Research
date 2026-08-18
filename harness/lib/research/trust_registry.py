"""Policy-pinned trust registry checks for Phase 22 research evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HEX = set("0123456789abcdef")
SCHEMA = "solar.trust_anchor_registry.v1"
APPROVED_REGISTRY_SHA256S = {
    "a84808e8f64888b567628acd6636c1a61b558f3d8f7f582a7eae8c68cf590edc",
    # P22-047 prospective live follow-up registry (arXiv + OpenAlex holdouts).
    "57fd7773eec381734414e2d04ed93ec19b386237031d1da099be7e5f53db2a3f",
}


class TrustRegistryError(ValueError):
    pass


def _text(value: Any) -> str:
    return value.strip() if type(value) is str else ""


def _sha(value: Any) -> str:
    text = _text(value).lower()
    return text if len(text) == 64 and set(text) <= HEX else ""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _safe_https_uri(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.netloc)
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _instant(value: Any) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def load_registry(path: str | Path, trusted_registry_sha256: str = "") -> dict[str, Any]:
    registry_path = Path(path)
    expected = _sha(trusted_registry_sha256)
    if not expected:
        raise TrustRegistryError("trust_registry_sha256_required")
    if expected not in APPROVED_REGISTRY_SHA256S:
        raise TrustRegistryError("trust_registry_sha256_not_policy_approved")
    try:
        raw = registry_path.read_bytes()
        actual = sha256_bytes(raw)
        if actual != expected:
            raise TrustRegistryError("trust_registry_sha256_mismatch")
        registry = json.loads(raw.decode("utf-8"))
    except TrustRegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrustRegistryError(f"trust_registry_unreadable:{exc}") from exc
    if not isinstance(registry, dict):
        raise TrustRegistryError("trust_registry_not_object")
    if registry.get("schema") != SCHEMA:
        raise TrustRegistryError("trust_registry_schema_invalid")
    anchors = registry.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        raise TrustRegistryError("trust_registry_anchors_missing")
    return registry


def _anchor(registry: dict[str, Any], anchor_id: str, purpose: str) -> dict[str, Any]:
    anchors = registry.get("anchors")
    if not isinstance(anchors, list):
        raise TrustRegistryError("trust_registry_anchors_missing")
    for item in anchors:
        if not isinstance(item, dict):
            continue
        allowed = item.get("allowed_purposes")
        if (
            _text(item.get("anchor_id")) == anchor_id
            and _safe_https_uri(item.get("identity_uri"))
            and _sha(item.get("public_key_sha256"))
            and isinstance(allowed, list)
            and purpose in {_text(value) for value in allowed}
        ):
            return item
    raise TrustRegistryError(f"trust_anchor_not_authorized:{anchor_id}:{purpose}")


def trusted_artifact(
    registry: dict[str, Any],
    *,
    purpose: str,
    sha256: str,
    artifact_id: str = "",
) -> dict[str, Any]:
    """Return the exact out-of-band artifact pin, or raise."""
    digest = _sha(sha256)
    if not digest or not purpose:
        raise TrustRegistryError("trusted_artifact_arguments_invalid")
    artifacts = registry.get("trusted_artifacts")
    if not isinstance(artifacts, list):
        raise TrustRegistryError("trusted_artifacts_missing")
    matches = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if _text(item.get("purpose")) != purpose or _sha(item.get("sha256")) != digest:
            continue
        if artifact_id and _text(item.get("artifact_id")) != artifact_id:
            continue
        anchor_id = _text(item.get("anchor_id"))
        _anchor(registry, anchor_id, purpose)
        if not _instant(item.get("registered_at")):
            raise TrustRegistryError("trusted_artifact_registered_at_invalid")
        if not _sha(item.get("signature_sha256")):
            raise TrustRegistryError("trusted_artifact_signature_missing")
        matches.append(item)
    if len(matches) != 1:
        raise TrustRegistryError(f"trusted_artifact_pin_not_exactly_once:{purpose}:{artifact_id or digest}")
    return matches[0]


def trusted_site_identity(
    registry: dict[str, Any],
    *,
    site_id: str,
    organization_id: str,
    collection_protocol_id: str,
    evidence_sha256: str,
) -> dict[str, Any]:
    """Validate a site identity against a registry-owned evidence hash pin."""
    site_id = _text(site_id)
    organization_id = _text(organization_id)
    collection_protocol_id = _text(collection_protocol_id)
    digest = _sha(evidence_sha256)
    if not all((site_id, organization_id, collection_protocol_id, digest)):
        raise TrustRegistryError("site_identity_arguments_invalid")
    sites = registry.get("site_identities")
    if not isinstance(sites, list):
        raise TrustRegistryError("site_identities_missing")
    matches = []
    for item in sites:
        if not isinstance(item, dict):
            continue
        evidence_hashes = item.get("evidence_sha256s")
        if not isinstance(evidence_hashes, list):
            continue
        if (
            _text(item.get("site_id")) == site_id
            and _text(item.get("organization_id")) == organization_id
            and _text(item.get("collection_protocol_id")) == collection_protocol_id
            and digest in {_sha(value) for value in evidence_hashes}
        ):
            anchor_id = _text(item.get("anchor_id"))
            _anchor(registry, anchor_id, "external_site_identity")
            if not _safe_https_uri(item.get("identity_uri")):
                raise TrustRegistryError("site_identity_uri_invalid")
            if not _sha(item.get("signature_sha256")):
                raise TrustRegistryError("site_identity_signature_missing")
            matches.append(item)
    if len(matches) != 1:
        raise TrustRegistryError(f"site_identity_pin_not_exactly_once:{site_id}")
    return matches[0]
