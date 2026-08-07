"""The generic research-retrieval capsule exposes the evaluator wire format."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import capability_capsules as cc  # noqa: E402
import plan_validator as pv  # noqa: E402
import workflow_contract as wc  # noqa: E402

CONFIG_DIR = _HARNESS / "config"
MANIFEST_PATH = CONFIG_DIR / "capability-capsules" / "cap.research-retrieval.yaml"
REGISTRY_PATH = CONFIG_DIR / "capability-capsules.registry.yaml"
CAPSULE_ID = "cap.research-retrieval"


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_retrieval_capsule_is_registered_and_valid(monkeypatch):
    registry = wc.load_capsule_registry(CONFIG_DIR)
    assert registry[CAPSULE_ID]["task_type_in"] == ["knowledge-extraction", "research"]
    assert registry[CAPSULE_ID]["produces_patch"] is False
    assert cc.validate_capability_capsule(_manifest()) == []

    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")
    assert f"- {CAPSULE_ID}:" in pv.planner_compile_policy_block(config_dir=CONFIG_DIR)


def test_retrieval_capsule_declares_shape_free_guarded_pack_contract():
    manifest = _manifest()
    required = {row["name"] for row in manifest["contract"]["outputs"]["required"]}
    assert required == {"sources_jsonl", "evidence_jsonl", "extracts_dir"}
    assert manifest["composition"].get("requires_after") in (None, [])
    assert "guard.secret-leak-guard" in manifest["bindings"]["required_guard_capsules"]

    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = {
        row["capability_capsule_id"]: row
        for row in registry["capsules"]["capability"]
    }
    assert entries[CAPSULE_ID]["status"] == "stable"
