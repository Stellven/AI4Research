#!/usr/bin/env python3
"""Validate that stable artifact adapters are runtime-admissible capsules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def _entries(payload: Any, key: str) -> list[dict[str, Any]]:
    value = payload.get(key, []) if isinstance(payload, dict) else []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def validate_artifact_adapter_registry(
    artifact_registry_path: Path, capability_registry_path: Path
) -> list[str]:
    """Return deterministic errors for adapter/runtime registry drift."""
    errors: list[str] = []
    try:
        artifact = yaml.safe_load(artifact_registry_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"artifact registry unreadable: {exc}"]
    try:
        capability = yaml.safe_load(capability_registry_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"capability registry unreadable: {exc}"]

    adapters = _entries(artifact, "adapters")
    groups = capability.get("capsules", {}) if isinstance(capability, dict) else {}
    runtime = [item for item in _entries(groups, "capability")]
    by_id: dict[str, list[dict[str, Any]]] = {}
    for item in runtime:
        by_id.setdefault(str(item.get("capability_capsule_id") or ""), []).append(item)

    adapter_ids: set[str] = set()
    for entry in adapters:
        adapter_id = str(entry.get("adapter_capsule_id") or "").strip()
        status = str(entry.get("status") or "").strip().lower()
        if not adapter_id:
            errors.append("artifact adapter entry missing adapter_capsule_id")
            continue
        if adapter_id in adapter_ids:
            errors.append(f"duplicate artifact adapter id: {adapter_id}")
            continue
        adapter_ids.add(adapter_id)
        if status != "stable":
            continue
        manifest_ref = str(entry.get("manifest_path") or "").strip()
        manifest_path = artifact_registry_path.parent / manifest_ref
        if not manifest_ref or not manifest_path.is_file():
            errors.append(f"{adapter_id}: stable manifest missing: {manifest_ref or '<empty>'}")
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            errors.append(f"{adapter_id}: manifest unreadable: {exc}")
            continue
        if str(manifest.get("capability_capsule_id") or "").strip() != adapter_id:
            errors.append(f"{adapter_id}: manifest capability_capsule_id mismatch")
        if manifest.get("capsule_kind") != "capability":
            errors.append(f"{adapter_id}: manifest capsule_kind must be capability")
        matches = by_id.get(adapter_id, [])
        if not matches:
            errors.append(f"{adapter_id}: stable adapter absent from runtime capability registry")
        elif len(matches) > 1:
            errors.append(f"{adapter_id}: duplicate runtime capability registry entries")
        else:
            runtime_entry = matches[0]
            runtime_status = str(runtime_entry.get("status") or "").strip().lower()
            if runtime_status != "stable":
                errors.append(f"{adapter_id}: runtime registry status is {runtime_status or '<empty>'}, expected stable")
            if runtime_entry.get("capsule_kind", "capability") != "capability":
                errors.append(f"{adapter_id}: runtime registry capsule_kind must be capability")
    return sorted(errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--artifact-registry", type=Path, default=root / "config/artifact-adapter-capsules.registry.yaml")
    parser.add_argument("--capability-registry", type=Path, default=root / "config/capability-capsules.registry.yaml")
    args = parser.parse_args()
    issues = validate_artifact_adapter_registry(args.artifact_registry, args.capability_registry)
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
