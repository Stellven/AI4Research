#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import skill_operator_registry as reg  # noqa: E402


def test_load_bindings_returns_empty_for_missing_file(tmp_path):
    assert reg.load_bindings(tmp_path / "missing.yaml") == []


def test_lookup_and_merge_bindings(tmp_path):
    path = tmp_path / "bindings.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "skill_operator_bindings": [
                    {
                        "skill_id": "understand-anything.knowledge_graph",
                        "logical_operator": "KnowledgeGraphBuilder",
                        "physical_operator": "mini-understand-anything-pane-bridge",
                        "capsule_id": "cap.understand-anything-knowledge-graph-builder",
                        "actor": "codex",
                        "semantic_backend": "ThunderOMLX",
                    }
                ],
                "defaults": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    binding = reg.lookup_by_skill("understand-anything.knowledge_graph", path=path)
    assert binding is not None
    assert binding.logical_operator == "KnowledgeGraphBuilder"
    merged = reg.merge_with_defaults({"DeepArchitect": "cap.requirement-compiler-planner"}, path=path)
    assert merged["KnowledgeGraphBuilder"] == "cap.understand-anything-knowledge-graph-builder"
    assert merged["DeepArchitect"] == "cap.requirement-compiler-planner"


def test_register_binding_persists_yaml(tmp_path):
    path = tmp_path / "bindings.yaml"
    reg.register_binding(
        reg.SkillOperatorBinding(
            skill_id="understand-anything.chat",
            logical_operator="CodebaseChatBuilder",
            physical_operator="mini-understand-anything-pane-bridge",
            capsule_id="cap.understand-anything-chat-builder",
        ),
        path=path,
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["skill_operator_bindings"][0]["logical_operator"] == "CodebaseChatBuilder"
