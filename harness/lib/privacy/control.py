"""Fail-closed, sandbox-scoped controls for local personal data.

This module intentionally does not claim control of hosted accounts, provider
credentials, or external messaging platforms.  Callers must provide an
absolute product home; every read and write remains below that root.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from privacy.lifecycle import redact_text, under_root

SCHEMA_VERSION = "solar.privacy-control.v1"
SENSITIVE_KEYS = ("password", "secret", "token", "credential", "api_key", "apikey")
DATA_SURFACES: dict[str, tuple[str, ...]] = {
    "settings": ("config", "config.env"),
    "supplied_data": ("primary/supplied", "db"),
    "derived_data": ("cache", "index", "derived"),
    "activity_logs": ("logs",),
    "backups": ("backups",),
    "exports": ("exports",),
}
RETENTION_CATEGORIES = ("derived_data", "activity_logs")
CONSENT_SOURCES = ("message", "apple_notes", "local_input")


class PrivacyControlError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def explicit_home(value: str | Path) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raise PrivacyControlError("absolute_home_required", "--home must be an explicit absolute path")
    root = raw.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _control_path(root: Path) -> Path:
    return root / "primary" / "privacy-control.json"


def _empty_control() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "retention": {category: 30 for category in RETENTION_CATEGORIES},
        "consents": {},
    }


def _load_control(root: Path) -> dict[str, Any]:
    path = _control_path(root)
    if not path.exists():
        return _empty_control()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrivacyControlError("invalid_control_store", "privacy control store is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("consents", {}), dict):
        raise PrivacyControlError("invalid_control_store", "privacy control store has an invalid structure")
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("retention", {category: 30 for category in RETENTION_CATEGORIES})
    return payload


def _save_control(root: Path, payload: dict[str, Any]) -> None:
    path = _control_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _safe_surface(root: Path, relative: str) -> Path:
    candidate = root / relative
    try:
        resolved = under_root(candidate, root)
    except ValueError as exc:
        raise PrivacyControlError("path_escape", "personal-data surface escapes the explicit home") from exc
    if candidate.is_symlink() and resolved != candidate.absolute():
        raise PrivacyControlError("unsafe_symlink", f"refusing linked personal-data surface: {relative}")
    return resolved


def _files(root: Path, categories: Iterable[str]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for category in categories:
        if category not in DATA_SURFACES:
            raise PrivacyControlError("invalid_category", f"unsupported personal-data category: {category}")
        for relative in DATA_SURFACES[category]:
            surface = _safe_surface(root, relative)
            if not surface.exists():
                continue
            candidates = [surface] if surface.is_file() else sorted(surface.rglob("*"))
            for candidate in candidates:
                if candidate.is_symlink():
                    target = candidate.resolve(strict=False)
                    try:
                        target.relative_to(root)
                    except ValueError as exc:
                        raise PrivacyControlError("unsafe_symlink", "refusing a personal-data symlink outside the explicit home") from exc
                    raise PrivacyControlError("unsafe_symlink", "personal-data symlinks are not exported or deleted")
                if candidate.is_file():
                    under_root(candidate, root)
                    found.append((category, candidate))
    return found


def inventory(root: Path) -> dict[str, Any]:
    control = _load_control(root)
    surfaces: dict[str, Any] = {}
    for category in DATA_SURFACES:
        files = _files(root, (category,))
        surfaces[category] = {
            "files": len(files),
            "bytes": sum(path.stat().st_size for _, path in files),
            "locations": list(DATA_SURFACES[category]),
        }
    states = {"granted": 0, "revoked": 0}
    for item in control["consents"].values():
        state = str(item.get("state", ""))
        if state in states:
            states[state] += 1
    return {
        "scope": "local_only",
        "surfaces": surfaces,
        "retention_days": control["retention"],
        "consent_states": states,
        "unsupported_external_controls": [
            "hosted_account_deletion",
            "provider_account_revocation",
            "discord_or_wechat_platform_deletion",
        ],
    }


def _redact_value(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, str):
        redacted = redact_text(value)
        # Text configuration files are not parsed as JSON, so redact values
        # assigned to secret-bearing keys before they enter an export.
        return re.sub(
            r"(?im)^(\s*[^=\r\n]*(?:password|secret|token|credential|api_key|apikey)[^=\r\n]*=).*$",
            r"\1[REDACTED]",
            redacted,
        )
    return value


def export_data(root: Path, destination: Path, categories: Iterable[str]) -> dict[str, Any]:
    selected = tuple(dict.fromkeys(categories))
    if not selected:
        raise PrivacyControlError("category_required", "at least one export category is required")
    target = under_root(destination, root)
    exports_root = _safe_surface(root, "exports")
    try:
        target.relative_to(exports_root)
    except ValueError as exc:
        raise PrivacyControlError("invalid_export_path", "exports must be written below <home>/exports") from exc
    if target == _control_path(root):
        raise PrivacyControlError("invalid_export_path", "export cannot overwrite the control store")
    records: list[dict[str, Any]] = []
    for category, path in _files(root, selected):
        raw = path.read_bytes()
        if len(raw) > 1_000_000:
            records.append({"category": category, "path": path.relative_to(root).as_posix(), "content": "[OMITTED_TOO_LARGE]"})
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            records.append({"category": category, "path": path.relative_to(root).as_posix(), "content": "[OMITTED_BINARY]"})
            continue
        try:
            content = _redact_value(json.loads(text))
        except json.JSONDecodeError:
            content = _redact_value(text)
        records.append({"category": category, "path": path.relative_to(root).as_posix(), "content": content})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "scope": "local_only",
        "categories": list(selected),
        "records": records,
        "redacted": True,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"out": str(target), "records": len(records), "redacted": True}


def set_retention(root: Path, category: str, days: int) -> dict[str, Any]:
    if category not in RETENTION_CATEGORIES:
        raise PrivacyControlError("invalid_retention_category", "retention is limited to derived_data and activity_logs")
    if days < 1 or days > 3650:
        raise PrivacyControlError("invalid_retention_days", "retention days must be between 1 and 3650")
    control = _load_control(root)
    control["retention"][category] = days
    _save_control(root, control)
    return {"category": category, "days": days, "state": "scheduled"}


def apply_retention(root: Path, now: float | None = None) -> dict[str, Any]:
    control = _load_control(root)
    current = time.time() if now is None else now
    removed: list[str] = []
    for category in RETENTION_CATEGORIES:
        cutoff = current - int(control["retention"].get(category, 30)) * 86400
        for _, path in _files(root, (category,)):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path.relative_to(root).as_posix())
    return {"state": "applied", "removed": sorted(removed), "removed_count": len(removed)}


def delete_category(root: Path, category: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise PrivacyControlError("confirmation_required", "selective deletion requires --yes")
    if category not in DATA_SURFACES:
        raise PrivacyControlError("invalid_category", f"unsupported personal-data category: {category}")
    if category == "exports":
        # The current command may be invoked from an export location; paths are still bounded.
        pass
    removed: list[str] = []
    for relative in DATA_SURFACES[category]:
        surface = _safe_surface(root, relative)
        if not surface.exists():
            continue
        _files(root, (category,))  # fail closed before the first mutation if a symlink exists
        if surface.is_dir():
            shutil.rmtree(surface)
        else:
            surface.unlink()
        removed.append(relative)
    return {"state": "deleted", "category": category, "removed_surfaces": removed}


def record_consent(root: Path, source: str, purpose: str, message_ref: str) -> dict[str, Any]:
    if source not in CONSENT_SOURCES:
        raise PrivacyControlError("invalid_consent_source", "unsupported local consent source")
    if not purpose.strip() or not message_ref.strip():
        raise PrivacyControlError("invalid_consent", "purpose and message reference are required")
    control = _load_control(root)
    consent_id = uuid.uuid4().hex
    now = int(time.time())
    control["consents"][consent_id] = {
        "consent_id": consent_id,
        "source": source,
        "purpose": purpose.strip()[:200],
        "message_ref_sha256": hashlib.sha256(message_ref.encode()).hexdigest(),
        "state": "granted",
        "granted_at": now,
        "revoked_at": None,
    }
    _save_control(root, control)
    return {"consent_id": consent_id, "state": "granted", "scope": "local_message_derived_data"}


def revoke_consent(root: Path, consent_id: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise PrivacyControlError("confirmation_required", "consent revocation requires --yes")
    control = _load_control(root)
    item = control["consents"].get(consent_id)
    if not item:
        raise PrivacyControlError("consent_not_found", "local consent record was not found")
    # Inspect every derived JSON document before mutating anything. Unknown or
    # malformed records are retained rather than pretending revocation is complete.
    matched: list[Path] = []
    for category, path in _files(root, ("derived_data",)):
        del category
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("consent_id") == consent_id:
            matched.append(path)
    for path in matched:
        path.unlink()
    item["state"] = "revoked"
    item["revoked_at"] = int(time.time())
    _save_control(root, control)
    return {
        "consent_id": consent_id,
        "state": "revoked",
        "removed_derived": sorted(path.relative_to(root).as_posix() for path in matched),
        "external_revocation": "not_available",
    }
