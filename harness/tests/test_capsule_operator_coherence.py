#!/usr/bin/env python3
"""Stable capsule/operator bindings must agree with the shipped operator catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import capability_capsules as caps  # noqa: E402


def _write_fixture(
    root: Path,
    *,
    status: str = "stable",
    default_operator_profile: str = "builder",
    preferred: list[str] | None = None,
) -> tuple[Path, Path]:
    manifest_path = root / "capsule.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "capability_capsule_id": "cap.fixture",
                "operator_compatibility": {
                    "preferred": list(preferred or []),
                    "forbidden": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry_path = root / "registry.yaml"
    registry_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "capsules": {
                    "capability": [
                        {
                            "capability_capsule_id": "cap.fixture",
                            "version": "0.1.0",
                            "capsule_kind": "capability",
                            "status": status,
                            "schema_ref": "unused.json",
                            "manifest_path": str(manifest_path),
                            "tags": [],
                            "owner": "test",
                            "default_operator_profile": default_operator_profile,
                        }
                    ],
                    "guard": [],
                    "resource": [],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    operators_path = root / "physical-operators.json"
    operators_path.write_text(
        json.dumps(
            {
                "version": 1,
                "operators": {
                    "active-builder": {
                        "profile": "builder",
                        "role": "builder",
                        "enabled": True,
                        "available": True,
                        "deprecated": False,
                        "health_status": "ok",
                    },
                    "retired-builder": {
                        "profile": "builder",
                        "role": "builder",
                        "enabled": False,
                        "available": True,
                        "deprecated": True,
                        "health_status": "ok",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return registry_path, operators_path


def test_default_operator_profile_may_resolve_an_active_profile(tmp_path: Path):
    registry_path, operators_path = _write_fixture(tmp_path)

    issues = caps.audit_stable_capsule_operator_bindings(
        registry_path=registry_path,
        operators_path=operators_path,
    )

    assert issues == []


def test_exact_inactive_and_missing_operator_references_do_not_silently_fallback(tmp_path: Path):
    registry_path, operators_path = _write_fixture(
        tmp_path,
        default_operator_profile="retired-builder",
        preferred=["missing-builder"],
    )

    issues = caps.audit_stable_capsule_operator_bindings(
        registry_path=registry_path,
        operators_path=operators_path,
    )

    assert {(item["field"], item["reference"], item["reason"]) for item in issues} == {
        ("default_operator_profile", "retired-builder", "operator_not_selectable"),
        ("operator_compatibility.preferred", "missing-builder", "operator_not_found"),
    }


def test_draft_capsules_do_not_block_the_stable_release_surface(tmp_path: Path):
    registry_path, operators_path = _write_fixture(
        tmp_path,
        status="draft",
        default_operator_profile="missing-builder",
        preferred=["missing-builder"],
    )

    issues = caps.audit_stable_capsule_operator_bindings(
        registry_path=registry_path,
        operators_path=operators_path,
    )

    assert issues == []


def test_shipped_stable_capsules_reference_selectable_operators():
    issues = caps.audit_stable_capsule_operator_bindings(
        registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
        operators_path=ROOT / "config" / "physical-operators.json",
    )

    assert issues == []
