#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import actor_registry as ar  # noqa: E402
import harness_paths as hp  # noqa: E402
import multi_task_status as mts  # noqa: E402


def test_resolve_runtime_harness_dir_prefers_env(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime-harness"
    runtime_root.mkdir()
    monkeypatch.setenv("HARNESS_DIR", str(runtime_root))
    monkeypatch.setattr(hp, "DEFAULT_RUNTIME_HARNESS_DIR", tmp_path / "other-default")
    assert hp.resolve_runtime_harness_dir() == runtime_root.resolve()


def test_resolve_runtime_harness_dir_prefers_canonical_runtime(monkeypatch, tmp_path):
    runtime_root = tmp_path / "canonical-harness"
    runtime_root.mkdir()
    monkeypatch.delenv("HARNESS_DIR", raising=False)
    monkeypatch.delenv("SOLAR_HARNESS_DIR", raising=False)
    monkeypatch.setattr(hp, "DEFAULT_RUNTIME_HARNESS_DIR", runtime_root)
    monkeypatch.setattr(hp, "SOURCE_HARNESS_DIR", tmp_path / "repo-harness")
    assert hp.resolve_runtime_harness_dir() == runtime_root.resolve()


def test_load_actor_registry_derives_from_physical_and_applies_override(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "actor-hosts.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": {
                    "mini": {"host_id": "mini", "host_type": "mac_mini"},
                },
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "physical-operators.json").write_text(
        json.dumps(
            {
                "version": 1,
                "operators": {
                    "mini-test-builder": {
                        "display_name": "Mini Test Builder",
                        "pane": "solar-harness-multi-task:*",
                        "role": "builder",
                        "persona": "builder",
                        "backend": "command",
                        "cost_tier": "medium",
                        "quota_cycle": "daily",
                        "preferred_for": ["implementation"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "agent-actors.json").write_text(
        json.dumps(
            {
                "version": 1,
                "actors": {
                    "mini-test-builder": {
                        "actor_id": "mini-test-builder",
                        "host_id": "mini",
                        "display_meta": {"display_name": "Override Builder"},
                        "evidence": {"last_smoke_result": "override-smoke"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    registry = ar.load_actor_registry(config_dir / "agent-actors.json")
    actor = registry["actors"]["mini-test-builder"]
    assert actor["operator_alias"] == "mini-test-builder"
    assert actor["role"] == "builder"
    assert actor["display_meta"]["display_name"] == "Override Builder"
    assert actor["mailbox"]["inbox"] == "actors/mini-test-builder/inbox"
    assert actor["evidence"]["last_smoke_result"] == "override-smoke"


def test_multi_task_status_load_actors_uses_sibling_physical_registry(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "actor-hosts.json").write_text(
        json.dumps({"version": 1, "hosts": {"mini": {"host_id": "mini", "host_type": "mac_mini"}}}),
        encoding="utf-8",
    )
    (config_dir / "physical-operators.json").write_text(
        json.dumps(
            {
                "version": 1,
                "operators": {
                    "mini-derived-planner": {
                        "display_name": "Derived Planner",
                        "pane": "solar-harness-multi-task:*",
                        "role": "planner",
                        "persona": "planner",
                        "backend": "claude-cli",
                        "cost_tier": "high",
                        "quota_cycle": "monthly",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "agent-actors.json").write_text(json.dumps({"version": 1, "actors": {}}), encoding="utf-8")

    actors = mts.load_actors(config_dir / "agent-actors.json")
    assert "mini-derived-planner" in actors
    assert actors["mini-derived-planner"]["role"] == "planner"
