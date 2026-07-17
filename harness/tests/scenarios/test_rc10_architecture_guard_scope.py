"""Live-run regression: ArchitectureGuard must govern architecture work only.

The first isolated deep-research run classified a retrieval node as a new
feature because its goal contained ``sources``/``research``.  Its evaluator
also enforced architecture-exploration alternatives even though the guard's
own classifier did not identify an exploration node.  That caused a needless
repair cycle on valid research output.
"""
from __future__ import annotations

import sys
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS / "lib"))

import architecture_guard as guard  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


def _retrieval_node() -> dict:
    return {
        "id": "R2",
        "goal": "Explore and retrieve current official sources for pricing, privacy, and workflow fit",
        "description": "Write a provenance-complete research source pack.",
        "capability_capsule_id": "cap.research-retrieval",
        "required_capabilities": ["research.web", "source.provenance"],
        "write_scope": ["workspace/research/source-pack/"],
        "evaluation_plan": {
            "review_mode": "single",
            "required_evaluators": 1,
            "evidence_requirements": ["handoff_md"],
        },
    }


def test_runtime_retrieval_is_not_an_architecture_change() -> None:
    node = _retrieval_node()

    assessed = guard.assess_graph({"nodes": [node]}, strict=True)

    assert assessed["ok"] is True, assessed
    report = assessed["nodes"][0]
    assert report["feature_node"] is False
    assert report["exploration_node"] is False
    block = guard.dispatch_policy_block(node)
    assert "feature_node: `false`" in block
    assert "exploration_node: `false`" in block
    assert "retrieval/search/network activity alone is not architecture exploration" in block


def test_explicit_architecture_exploration_keeps_its_guard_obligations() -> None:
    node = {
        "id": "A1",
        "goal": "Explore candidate plugin architectures for a new connector",
        "write_scope": ["plugins/example-connector/"],
        "architecture_policy": {
            "package_boundary": "plugins/example-connector",
            "online_exploration": True,
            "exploration_alternatives": ["adapter", "sidecar"],
            "kill_criteria": "Reject any direction that mutates the coordinator loop.",
        },
    }

    assessed = guard.assess_graph({"nodes": [node]}, strict=True)

    assert assessed["ok"] is True, assessed
    assert assessed["nodes"][0]["exploration_node"] is True
    block = guard.dispatch_policy_block(node)
    assert "exploration_node: `true`" in block
    assert "exploration_requirement: `required`" in block


def test_architecture_exploration_is_inferred_only_with_architecture_context() -> None:
    node = {
        "id": "A2",
        "goal": "Explore alternative architecture approaches for the runtime scheduler",
        "write_scope": ["workspace/design/runtime-scheduler.md"],
    }

    assessed = guard.assess_graph({"nodes": [node]}, strict=False)

    assert assessed["nodes"][0]["exploration_node"] is True
    assert any("exploration_alternatives" in warning for warning in assessed["warnings"])
    assert any("kill_criteria" in warning for warning in assessed["warnings"])


def test_evaluator_consumes_guard_classification_instead_of_reinferring_it(
    tmp_path, monkeypatch
) -> None:
    sid = "sprint-runtime-retrieval"
    node = _retrieval_node()
    handoff = tmp_path / f"{sid}.R2-handoff.md"
    dispatch = tmp_path / f"{sid}.R2-dispatch.md"
    monkeypatch.setattr(gnd, "_existing_node_handoff", lambda _sid, _node, _graph: handoff)
    monkeypatch.setattr(gnd, "_node_handoff_candidates", lambda _sid, _node, _graph: [handoff])
    monkeypatch.setattr(gnd, "_eval_md_file", lambda _sid, _node_id: tmp_path / "R2-eval.md")
    monkeypatch.setattr(gnd, "_eval_json_file", lambda _sid, _node_id: tmp_path / "R2-eval.json")
    monkeypatch.setattr(gnd, "_dispatch_file", lambda _sid, _node_id: dispatch)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path)
    (tmp_path / f"{sid}.contract.md").write_text("# contract\n", encoding="utf-8")

    text = gnd.build_eval_dispatch_text(
        {"sprint_id": sid},
        str(tmp_path / f"{sid}.task_graph.json"),
        node,
        "solar-test:evaluator.0",
        "dispatch-1",
    )

    assert "exploration_node: `false`" in text
    assert "ONLY when Architecture Guard says `feature_node: true`" in text
    assert "ONLY when Architecture Guard says `exploration_node: true`" in text
    assert "retrieval/search/network activity alone is not architecture exploration" in text
    assert "涉及 online exploration 的 node 必须验证" not in text
