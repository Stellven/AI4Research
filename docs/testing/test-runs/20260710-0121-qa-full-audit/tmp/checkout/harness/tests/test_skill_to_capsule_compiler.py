#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import skill_to_capsule_compiler as compiler  # noqa: E402


def test_discover_plugins_finds_understand_anything():
    plugins = compiler.discover_plugins(ROOT, plugin_id="understand-anything")
    assert len(plugins) == 1
    assert plugins[0].plugin_id == "understand-anything"


def test_compile_draft_produces_valid_yaml():
    plugin = compiler.discover_plugins(ROOT, plugin_id="understand-anything")[0]
    capability = compiler.normalize_capabilities(plugin)[0]
    draft = compiler.compile_capsule_draft(plugin.plugin_id, capability)
    rendered = yaml.safe_dump(draft, sort_keys=False)
    assert "semantic_backend: ThunderOMLX" in rendered
    assert draft["capability_capsule_id"] == "cap.understand-anything-knowledge-graph-builder"


def test_derive_physical_operator_knowledge_graph():
    assert compiler.derive_physical_operator("understand-anything.knowledge_graph") == "mini-understand-anything-pane-bridge"


def test_batch_compile_dry_run_no_writes():
    report = compiler.batch_compile(dry_run=True, plugin_id="understand-anything", harness_dir=ROOT)
    assert report["ok"] is True
    assert report["capsule_count"] >= 1


def test_batch_compile_registers_in_capsule_registry(tmp_path):
    harness_root = tmp_path / "harness"
    (harness_root / "plugins" / "understand-anything").mkdir(parents=True, exist_ok=True)
    (harness_root / "config" / "capability-capsules").mkdir(parents=True, exist_ok=True)
    (harness_root / "plugins" / "understand-anything" / "manifest.yaml").write_text(
        (ROOT / "plugins" / "understand-anything" / "manifest.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (harness_root / "config" / "capability-capsules.registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "capsules": {"capability": [], "guard": [], "resource": []}}, sort_keys=False),
        encoding="utf-8",
    )
    report = compiler.batch_compile(dry_run=False, plugin_id="understand-anything", harness_dir=harness_root)
    assert report["ok"] is True
    registry = yaml.safe_load((harness_root / "config" / "capability-capsules.registry.yaml").read_text(encoding="utf-8"))
    ids = [item["capability_capsule_id"] for item in registry["capsules"]["capability"]]
    assert "cap.understand-anything-knowledge-graph-builder" in ids
    assert (harness_root / "config" / "capability-capsules" / "cap.understand-anything-knowledge-graph-builder.yaml").exists()
