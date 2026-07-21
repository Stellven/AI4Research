from __future__ import annotations

import json
import sys
from pathlib import Path


HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(HARNESS_LIB))

import multi_task_runner  # noqa: E402


def test_quota_guard_ignores_recovered_fallback_hit(monkeypatch, tmp_path):
    harness = tmp_path / "harness"
    run_dir = harness / "run" / "multi-task"
    task_dir = run_dir / "mt-quota-N1"
    task_dir.mkdir(parents=True)
    (task_dir / "output.log").write_text("You've hit your org's monthly usage limit\n", encoding="utf-8")
    graph_path = tmp_path / "sprint-quota.task_graph.json"
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "id": "mt-quota-N1",
                "status": "failed",
                "profile": "gemini-builder",
                "graph": str(graph_path),
                "node_id": "N1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": "sprint-quota",
                "nodes": [
                    {
                        "id": "N1",
                        "status": "active",
                        "quota_failure_task_id": "mt-quota-N1",
                        "preferred_profile": "knowledge-extractor",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)

    assert multi_task_runner.quota_guard(3600)["ok"] is True


def test_quota_guard_ignores_late_hit_after_node_already_recovered(monkeypatch, tmp_path):
    harness = tmp_path / "harness"
    run_dir = harness / "run" / "multi-task"
    task_dir = run_dir / "mt-quota-late-N1"
    task_dir.mkdir(parents=True)
    (task_dir / "output.log").write_text("You've hit your org's monthly usage limit\n", encoding="utf-8")
    graph_path = tmp_path / "sprint-quota.task_graph.json"
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "id": "mt-quota-late-N1",
                "status": "failed",
                "profile": "gemini-builder",
                "graph": str(graph_path),
                "node_id": "N1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path.write_text(
        json.dumps(
            {
                "sprint_id": "sprint-quota",
                "nodes": [
                    {
                        "id": "N1",
                        "status": "pending",
                        "quota_failure_reason": "quota_exhausted",
                        "quota_failure_task_id": "mt-quota-earlier-N1",
                        "preferred_profile": "knowledge-extractor",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)

    assert multi_task_runner.quota_guard(3600)["ok"] is True


def test_quota_guard_ignores_hit_for_already_passed_node(monkeypatch, tmp_path):
    harness = tmp_path / "harness"
    run_dir = harness / "run" / "multi-task"
    task_dir = run_dir / "mt-quota-passed-N1"
    task_dir.mkdir(parents=True)
    (task_dir / "output.log").write_text("Antigravity quota exhausted\n", encoding="utf-8")
    graph_path = tmp_path / "sprint-quota.task_graph.json"
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "id": "mt-quota-passed-N1",
                "status": "failed",
                "profile": "antigravity-multimodal",
                "graph": str(graph_path),
                "node_id": "N1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    graph_path.write_text(
        json.dumps({"sprint_id": "sprint-quota", "nodes": [{"id": "N1", "status": "passed"}]}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)

    assert multi_task_runner.quota_guard(3600)["ok"] is True


def test_quota_recovered_knowledge_profile_is_not_overridden_by_operator_for_knowledge_task(monkeypatch):
    monkeypatch.setattr(
        multi_task_runner,
        "load_profiles",
        lambda: {
            "profiles": {
                "knowledge-extractor": {"role": "builder", "backend": "command", "model": "local"},
                "gemini-builder": {"role": "builder", "backend": "command", "model": "gemini-3.5-flash"},
            },
            "defaults": {"profile": "gemini-builder"},
        },
    )
    monkeypatch.setattr(multi_task_runner, "capability_for_profile", lambda profile, include_probe=True: {"status": "ok", "provider": "local"})
    monkeypatch.setattr(
        multi_task_runner,
        "select_operator",
        lambda node, profile: (
            {
                "operator_id": "mini-antigravity-gemini35-flash-image",
                "profile": "gemini-builder",
                "role": "builder",
                "backend": "command",
                "model": "gemini-3.5-flash",
            },
            "",
        ),
    )
    node = {
        "id": "N1",
        "role": "builder",
        "goal": "Run knowledge-extraction wiki-ingest into QMD semantic layer",
        "preferred_profile": "knowledge-extractor",
        "quota_failure_reason": "quota_exhausted",
    }

    selected = multi_task_runner.select_profile(node)

    assert selected["name"] == "knowledge-extractor"
    assert selected["model"] == "local"
    assert selected.get("operator_id") is None


def test_quota_fallback_skips_knowledge_extractor_for_code_node(monkeypatch):
    monkeypatch.setattr(
        multi_task_runner,
        "capability_for_profile",
        lambda profile, include_probe=True: {"status": "ok", "provider": profile.get("backend", "local")},
    )
    profiles = {
        "builder": {"role": "builder", "backend": "claude-cli", "model": "sonnet"},
        "gemini-builder": {"role": "builder", "backend": "gemini-cli", "model": "gemini"},
        "knowledge-extractor": {
            "role": "builder",
            "backend": "command",
            "model": "thunderomlx",
            "best_for": ["knowledge-extraction", "wiki-ingest", "qmd-indexing"],
        },
        "deepseek-builder": {"role": "builder", "backend": "claude-cli", "model": "deepseek"},
    }
    node = {
        "id": "C1_schema_contract",
        "role": "builder",
        "write_scope": ["harness/lib/github_intelligence/schema.py"],
        "required_capabilities": ["python", "testing"],
        "acceptance": "schema API unit coverage and no incompatible import changes",
        "quota_blocked_profiles": ["builder", "gemini-builder"],
    }

    selected = multi_task_runner.select_quota_fallback_profile(node, "gemini-builder", profiles)

    assert selected == "deepseek-builder"


def test_quota_recovered_unsuitable_profile_is_replaced_for_code_node(monkeypatch):
    monkeypatch.setattr(
        multi_task_runner,
        "load_profiles",
        lambda: {
            "profiles": {
                "gemini-builder": {"role": "builder", "backend": "gemini-cli", "model": "gemini"},
                "knowledge-extractor": {
                    "role": "builder",
                    "backend": "command",
                    "model": "thunderomlx",
                    "best_for": ["knowledge-extraction", "wiki-ingest", "qmd-indexing"],
                },
                "deepseek-builder": {"role": "builder", "backend": "claude-cli", "model": "deepseek"},
            },
            "defaults": {"profile": "gemini-builder"},
        },
    )
    monkeypatch.setattr(
        multi_task_runner,
        "capability_for_profile",
        lambda profile, include_probe=True: {"status": "ok", "provider": profile.get("backend", "local")},
    )
    monkeypatch.setattr(multi_task_runner, "select_operator", lambda node, profile: (None, ""))
    node = {
        "id": "C1_schema_contract",
        "role": "builder",
        "preferred_profile": "knowledge-extractor",
        "quota_failure_reason": "quota_exhausted",
        "quota_blocked_profiles": ["builder", "gemini-builder"],
        "write_scope": ["harness/lib/github_intelligence/schema.py"],
        "required_capabilities": ["python", "testing"],
        "acceptance": "schema API unit coverage",
    }

    selected = multi_task_runner.select_profile(node)

    assert selected["name"] == "deepseek-builder"
    assert node["quota_fallback_unsuitable_profile"] == "knowledge-extractor"


def test_quota_fallback_allows_knowledge_extractor_for_knowledge_node(monkeypatch):
    monkeypatch.setattr(
        multi_task_runner,
        "capability_for_profile",
        lambda profile, include_probe=True: {"status": "ok", "provider": profile.get("backend", "local")},
    )
    profiles = {
        "builder": {"role": "builder", "backend": "claude-cli", "model": "sonnet"},
        "gemini-builder": {"role": "builder", "backend": "gemini-cli", "model": "gemini"},
        "knowledge-extractor": {
            "role": "builder",
            "backend": "command",
            "model": "thunderomlx",
            "best_for": ["knowledge-extraction", "wiki-ingest", "qmd-indexing"],
        },
    }
    node = {
        "id": "K1_semantic_ingest",
        "role": "builder",
        "goal": "Run knowledge-extraction wiki-ingest into QMD semantic layer",
        "write_scope": ["semantic.md", "monitor-reports/semantic-layer.md"],
        "quota_blocked_profiles": ["builder", "gemini-builder"],
    }

    selected = multi_task_runner.select_quota_fallback_profile(node, "gemini-builder", profiles)

    assert selected == "knowledge-extractor"


def test_output_log_auth_takes_precedence_over_quota_text(monkeypatch, tmp_path):
    run_dir = tmp_path / "run" / "multi-task"
    task_dir = run_dir / "mt-auth"
    task_dir.mkdir(parents=True)
    (task_dir / "output.log").write_text(
        "ERROR: Antigravity quota exhausted; refusing empty handoff\n"
        "Error: failed to send message: no active conversation\n"
        "You are not logged into Antigravity.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)

    assert multi_task_runner.output_log_failure_kind("mt-auth") == "auth_expired"
    assert multi_task_runner.output_log_has_quota_failure("mt-auth") is False
    assert multi_task_runner.output_log_has_auth_failure("mt-auth") is True


def test_recover_auth_failed_node_sets_auth_reason_and_fallback(monkeypatch, tmp_path):
    run_dir = tmp_path / "run" / "multi-task"
    task_dir = run_dir / "mt-auth-failed"
    task_dir.mkdir(parents=True)
    (task_dir / "output.log").write_text(
        "Error: failed to send message: no active conversation\n",
        encoding="utf-8",
    )
    (task_dir / "status.json").write_text(
        json.dumps({"profile": "antigravity-multimodal"}) + "\n",
        encoding="utf-8",
    )
    graph_path = tmp_path / "graph.json"
    graph = {
        "nodes": [
            {
                "id": "N1",
                "status": "failed",
                "dispatch_id": "mt-auth-failed",
                "role": "builder",
                "write_scope": ["harness/lib/example.py"],
                "acceptance": "unit tests pass",
            }
        ]
    }
    profiles = {
        "antigravity-multimodal": {"role": "builder", "backend": "command", "model": "gemini-3.5-flash"},
        "deepseek-builder": {"role": "builder", "backend": "claude-cli", "model": "deepseek"},
    }
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)
    monkeypatch.setattr(multi_task_runner, "load_profiles", lambda: {"profiles": profiles})
    monkeypatch.setattr(
        multi_task_runner,
        "capability_for_profile",
        lambda profile, include_probe=True: {"status": "ok", "provider": profile.get("backend", "local")},
    )
    monkeypatch.setattr(multi_task_runner, "save_graph", lambda path, payload: None)
    monkeypatch.setattr(multi_task_runner, "node_status", lambda payload, node_id: payload["nodes"][0]["status"])

    changed = multi_task_runner.recover_quota_failed_nodes(graph_path, graph)

    node = graph["nodes"][0]
    assert changed == 1
    assert node["status"] == "pending"
    assert node["auth_failure_reason"] == "auth_expired"
    assert node["auth_failure_task_id"] == "mt-auth-failed"
    assert node["preferred_profile"] == "deepseek-builder"
    assert node["quota_fallback_reason"] == "auth_expired"


def test_quota_fallback_skips_profile_with_recent_auth_failure(monkeypatch, tmp_path):
    run_dir = tmp_path / "run" / "multi-task"
    task_dir = run_dir / "mt-antigravity-auth"
    task_dir.mkdir(parents=True)
    (task_dir / "status.json").write_text(
        json.dumps({"profile": "antigravity-multimodal"}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "output.log").write_text("You are not logged into Antigravity.\n", encoding="utf-8")
    profiles = {
        "builder": {"role": "builder", "backend": "claude-cli", "model": "sonnet"},
        "gemini-builder": {"role": "builder", "backend": "gemini-cli", "model": "gemini"},
        "antigravity-multimodal": {"role": "builder", "backend": "command", "model": "gemini-3.5-flash"},
        "deepseek-builder": {"role": "builder", "backend": "claude-cli", "model": "deepseek"},
    }
    node = {
        "id": "N1",
        "role": "builder",
        "write_scope": ["harness/lib/example.py"],
        "quota_blocked_profiles": ["builder", "gemini-builder"],
    }
    monkeypatch.setattr(multi_task_runner, "RUN_DIR", run_dir)
    monkeypatch.setattr(multi_task_runner, "load_profiles", lambda: {"profiles": profiles})
    monkeypatch.setattr(
        multi_task_runner,
        "capability_for_profile",
        lambda profile, include_probe=True: {"status": "ok", "provider": profile.get("backend", "local")},
    )

    selected = multi_task_runner.select_quota_fallback_profile(node, "builder", profiles)

    assert selected == "deepseek-builder"
