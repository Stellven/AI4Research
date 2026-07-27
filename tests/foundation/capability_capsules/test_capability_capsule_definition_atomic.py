"""Executable Phase 22 atomic tests for capability-capsule definition."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "harness"
sys.path.insert(0, str(HARNESS / "lib"))

import capability_capsules as caps


SCHEMA = HARNESS / "schemas" / "draft" / "capability-capsule.v1.draft.json"


def _minimal_manifest() -> dict:
    return {
        "capability_capsule_id": "cap.phase22-minimal",
        "version": "0.1.0",
        "capsule_kind": "capability",
        "metadata": {"name": "Phase 22 minimal", "description": "Minimal valid capsule"},
        "applicability": {
            "task_types": ["CODE_IMPL"],
            "positive_signals": [],
            "negative_signals": [],
        },
        "contract": {
            "inputs": {"required": [], "optional": []},
            "outputs": {"required": [], "optional": []},
            "preconditions": [{"check": "task_type_in", "values": ["CODE_IMPL"]}],
            "postconditions": [{"check": "output_present", "field": "result"}],
            "invariants": ["read-only validation"],
        },
        "composition": {
            "consumes": [],
            "produces": [],
            "compatible_with": [],
            "incompatible_with": [],
            "requires_after": [],
        },
        "effects": {
            "read": [],
            "write": [],
            "execute": [],
            "network": [],
            "cost": [],
            "risk": [],
        },
        "bindings": {
            "skills": {"required": [], "optional": []},
            "mcp_capabilities": {},
            "data_refs": [],
            "secret_refs": [],
        },
        "verification": {
            "self_check": ["result exists"],
            "external_verifier": {"required": False},
            "pass_conditions": ["result exists"],
        },
        "operator_compatibility": {"preferred": [], "forbidden": []},
        "provenance": {"owner": "phase22"},
    }


def test_atomic_capability_capsule_definition_assembly__valid_minimal_manifest() -> None:
    manifest = _minimal_manifest()
    assert caps.validate_capability_capsule(manifest, schema_path=SCHEMA) == []


def test_atomic_capability_capsule_definition_assembly__rich_manifest() -> None:
    path = HARNESS / "config" / "capability-capsules" / "cap.flashmlx-performance-debugger.yaml"
    manifest = caps.load_capability_capsule_manifest(path)
    assert manifest["bindings"]["required_resource_capsules"]
    assert manifest["verification"]["pass_conditions"]
    assert caps.validate_capability_capsule(manifest, schema_path=SCHEMA) == []


def test_atomic_capability_capsule_definition_assembly__missing_fields() -> None:
    with pytest.raises(caps.CapsuleRegistryError, match="capability_capsule_id"):
        caps.normalize_capability_capsule({})


def test_atomic_capability_capsule_definition_assembly__invalid_fields() -> None:
    manifest = deepcopy(_minimal_manifest())
    manifest["contract"]["preconditions"] = []
    errors = caps.validate_capability_capsule(manifest, schema_path=SCHEMA)
    assert any("contract.preconditions must be non-empty" in error for error in errors)


def test_atomic_capability_capsule_definition_assembly__duplicate_identity_version(tmp_path) -> None:
    entry = {
        "capability_capsule_id": "cap.phase22-duplicate",
        "version": "0.1.0",
        "capsule_kind": "capability",
        "status": "stable",
        "manifest_path": "capsule.yaml",
    }
    registry = {
        "version": 1,
        "capsules": {"capability": [entry, deepcopy(entry)], "guard": [], "resource": []},
    }
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    with pytest.raises(caps.CapsuleRegistryError, match="duplicate"):
        caps.load_capability_capsule_registry(registry_path)
