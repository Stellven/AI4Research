from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import capability_capsules as caps


def test_autosci_manifest_research_capsules_are_registered_and_resolvable():
    manifest = yaml.safe_load((ROOT / "plugins/autosci/manifest.yaml").read_text(encoding="utf-8"))
    manifest_caps = set(manifest["capabilities"])
    registry = caps.load_capability_capsule_registry(
        path=ROOT / "config/capability-capsules.registry.yaml"
    )
    entries = {
        str(entry["capability_capsule_id"]): entry
        for entry in registry["entries"]
        if str(entry["capability_capsule_id"]).startswith("cap.research-")
    }

    assert manifest_caps == set(entries)

    for capsule_id, entry in entries.items():
        manifest_path = Path(entry["manifest_path"])
        assert manifest_path.exists(), capsule_id
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert payload["capability_capsule_id"] == capsule_id
        assert entry["status"] == "stable"
        assert entry["default_operator_profile"] in {
            "codex-builder",
            "codex-planner",
            "codex-evaluator",
        }


def test_no_autosci_research_capsule_file_is_left_unregistered():
    registry = caps.load_capability_capsule_registry(
        path=ROOT / "config/capability-capsules.registry.yaml"
    )
    registered = {str(entry["capability_capsule_id"]) for entry in registry["entries"]}
    capsule_files = sorted((ROOT / "capability-capsules").glob("cap.research-*.yaml"))

    assert capsule_files
    assert {path.stem for path in capsule_files} <= registered
