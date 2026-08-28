from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness" / "tools"))
from check_artifact_adapter_registry import validate_artifact_adapter_registry


ROOT = Path(__file__).resolve().parents[2] / "harness"


def test_stable_artifact_adapters_are_runtime_admissible() -> None:
    assert validate_artifact_adapter_registry(
        ROOT / "config/artifact-adapter-capsules.registry.yaml",
        ROOT / "config/capability-capsules.registry.yaml",
    ) == []


def test_missing_runtime_entry_is_reported(tmp_path: Path) -> None:
    artifact = yaml.safe_load((ROOT / "config/artifact-adapter-capsules.registry.yaml").read_text())
    capability = yaml.safe_load((ROOT / "config/capability-capsules.registry.yaml").read_text())
    capability["capsules"]["capability"] = [
        item for item in capability["capsules"]["capability"]
        if item.get("capability_capsule_id") != "adapter.artifact-type-bridge"
    ]
    artifact_path = tmp_path / "artifact.yaml"
    capability_path = tmp_path / "capability.yaml"
    # Preserve manifest resolution against the repository config directory.
    artifact_path.write_text(yaml.safe_dump(artifact), encoding="utf-8")
    capability_path.write_text(yaml.safe_dump(capability), encoding="utf-8")
    issues = validate_artifact_adapter_registry(
        ROOT / "config/artifact-adapter-capsules.registry.yaml", capability_path
    )
    assert "adapter.artifact-type-bridge: stable adapter absent from runtime capability registry" in issues


def test_revoked_runtime_entry_is_not_admissible(tmp_path: Path) -> None:
    artifact = yaml.safe_load((ROOT / "config/artifact-adapter-capsules.registry.yaml").read_text())
    capability = yaml.safe_load((ROOT / "config/capability-capsules.registry.yaml").read_text())
    for item in capability["capsules"]["capability"]:
        if item.get("capability_capsule_id") == "adapter.artifact-type-bridge":
            item["status"] = "revoked"
    capability_path = tmp_path / "capability.yaml"
    capability_path.write_text(yaml.safe_dump(capability), encoding="utf-8")
    issues = validate_artifact_adapter_registry(
        ROOT / "config/artifact-adapter-capsules.registry.yaml", capability_path
    )
    assert any("runtime registry status is revoked" in issue for issue in issues)
