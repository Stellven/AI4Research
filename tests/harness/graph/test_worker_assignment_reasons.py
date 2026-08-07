"""Regression tests for graph worker assignment queue reasons."""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = (Path(__file__).resolve().parents[3] / 'harness')
os.environ["HARNESS_DIR"] = str(ROOT)
for _env in ("SOLAR_HARNESS_DIR", "HARNESS_SPRINTS_DIR"):
    os.environ.pop(_env, None)
sys.path.insert(0, str(ROOT / "lib"))
for _module in ("graph_scheduler", "capability_inference", "apo_plan_compiler"):
    sys.modules.pop(_module, None)

import graph_scheduler as gs  # noqa: E402
from graph_scheduler import assign_workers, enqueue_ready  # noqa: E402


def _worker(pane: str, *, busy: bool = False) -> dict:
    return {
        "pane": pane,
        "models": ["glm"],
        "skills": ["python", "pytest", "stub-llm"],
        "capabilities": ["harness.context_preflight", "harness.dag"],
        "busy": busy,
    }


def _node(node_id: str) -> dict:
    return {
        "id": node_id,
        "preferred_model": "sonnet",
        "required_skills": ["python", "pytest", "stub-llm"],
        "required_capabilities": ["harness.context_preflight", "harness.dag"],
    }


def test_queue_reason_distinguishes_capacity_from_no_matching_worker() -> None:
    result = assign_workers([_node("N1"), _node("N2")], [_worker("pane-a")])
    assert [item["node"] for item in result["assigned"]] == ["N1"]
    assert result["queued"][0]["node"] == "N2"
    assert result["queued"][0]["reason"] == "worker_capacity_exhausted"
    assert "details" in result["queued"][0]


def test_skill_short_worker_is_assignable_but_capability_short_strands() -> None:
    # graph_scheduler design: required SKILLS are a PREFERENCE (Layer-3 relaxed net) so a node never
    # permanently strands on a free-form/unregistered skill string, while a required CAPABILITY stays
    # the HARD gate. So a capability-qualified worker that is merely skill-short is still dispatched,
    # but a worker missing a genuinely-unsatisfiable required capability strands as no_matching_worker.

    # Skill-short (missing pytest/stub-llm) but capabilities satisfied -> assigned (skills are not a gate).
    skill_short = _worker("pane-a")
    skill_short["skills"] = ["python"]
    relaxed = assign_workers([_node("N1")], [skill_short])
    assert relaxed["queued"] == []
    assert relaxed["assigned"][0]["node"] == "N1"

    # GUARDRAIL (the real gate is kept): a genuinely-unsatisfiable required capability strands honestly.
    cap_short = _worker("pane-b")
    cap_node = {
        "id": "N2",
        "preferred_model": "sonnet",
        "required_skills": [],
        "required_capabilities": ["fake.capability.xyz"],
    }
    stranded = assign_workers([cap_node], [cap_short])
    assert stranded["assigned"] == []
    assert stranded["queued"][0]["node"] == "N2"
    assert stranded["queued"][0]["reason"] == "no_matching_worker"
    assert "fake.capability.xyz" in stranded["queued"][0]["details"]["missing_capabilities"]


def test_busy_matching_worker_is_queued_instead_of_assigned() -> None:
    result = assign_workers([_node("N1")], [_worker("pane-a", busy=True)])
    assert result["assigned"] == []
    assert result["queued"][0]["node"] == "N1"
    assert result["queued"][0]["reason"] == "worker_capacity_exhausted"


def test_queue_reason_runtime_not_running_when_matching_worker_is_shell_residue() -> None:
    worker = _worker("pane-a")
    worker["busy"] = True
    worker["unavailable_reason"] = "worker_runtime_not_running"
    result = assign_workers([_node("N1")], [worker])
    assert result["assigned"] == []
    assert result["queued"][0]["node"] == "N1"
    assert result["queued"][0]["reason"] == "worker_runtime_not_running"


def test_unavailable_matching_worker_is_not_assigned_even_when_not_busy() -> None:
    worker = _worker("solar-harness-multi-task:0.0")
    worker["busy"] = False
    worker["unavailable_reason"] = "multi_task_shell_not_direct_worker"
    result = assign_workers([_node("N1")], [worker])
    assert result["assigned"] == []
    assert result["queued"][0]["node"] == "N1"
    assert result["queued"][0]["reason"] == "multi_task_shell_not_direct_worker"
    assert result["queued"][0]["details"]["unavailable_reasons"] == [
        "multi_task_shell_not_direct_worker"
    ]


def test_enriched_dag_capabilities_are_assignable() -> None:
    worker = _worker("pane-a")
    worker["capabilities"] = [
        "harness.context_preflight",
        "harness.dag",
        "dag.validate",
        "dag.ready_nodes",
        "dag.join_gate",
    ]
    node = _node("N1")
    node["required_capabilities"] = [
        "harness.context_preflight",
        "harness.dag",
        "dag.validate",
        "dag.ready_nodes",
        "dag.join_gate",
    ]
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_skill_labels_can_satisfy_required_capabilities() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "pytest", "stub-llm", "cli"]
    worker["capabilities"] = ["harness.context_preflight", "harness.dag"]
    node = _node("N1")
    node["required_capabilities"] = ["harness.context_preflight", "cli"]
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_control_plane_aliases_can_bind_specialized_builder_nodes() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "workflow.planning", "technical-writing", "algorithm"]
    worker["capabilities"] = ["documentation", "governance"]
    node = {
        "id": "N1",
        "preferred_model": "sonnet",
        "required_skills": ["python", "solar-harness-control-plane", "architecture-writing"],
        "required_capabilities": ["algorithm_design", "documentation"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_product_analytics_nodes_bind_general_builder_workers() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "product.requirements", "planning", "analytics"]
    worker["capabilities"] = ["product.requirements", "analytics"]
    node = {
        "id": "N1",
        "preferred_model": "glm-5.1",
        "required_skills": ["analytics", "product.requirements"],
        "required_capabilities": ["analytics", "product.requirements"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_rag_reporting_nodes_bind_general_builder_workers() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "docs", "harness.knowledge", "technical-writing"]
    worker["capabilities"] = ["harness.model_routing", "harness.reporting"]
    node = {
        "id": "N1",
        "preferred_model": None,
        "required_skills": ["ai-rag-pipeline", "reporting"],
        "required_capabilities": ["model.routing", "reporting"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_social_signal_nodes_bind_browser_collector_workers() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "browser", "collector", "social"]
    worker["capabilities"] = ["browser.automation", "web.capture", "social.signal", "link.extract"]
    node = {
        "id": "N1",
        "preferred_model": None,
        "required_skills": [],
        "required_capabilities": ["browser.browse", "social_links", "entity.extract"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_sqlite_alias_nodes_bind_sqlite3_workers() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "sqlite3"]
    worker["capabilities"] = ["python"]
    node = {
        "id": "N1",
        "preferred_model": "sonnet",
        "required_skills": ["python", "sqlite"],
        "required_capabilities": [],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_observability_skill_nodes_bind_observability_builders() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "observability"]
    worker["capabilities"] = ["observability"]
    node = {
        "id": "N1",
        "preferred_model": None,
        "required_skills": ["python", "observability"],
        "required_capabilities": [],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_capability_match_accepts_any_alias_per_required_label() -> None:
    worker = _worker("pane-a")
    worker["capabilities"] = ["harness.model_routing"]
    node = {
        "id": "N1",
        "preferred_model": None,
        "required_skills": [],
        "required_capabilities": ["model.routing"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_code_impl_and_test_generation_aliases_bind_general_builder_workers() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "pytest", "refactor", "ImplementationWorker"]
    worker["capabilities"] = ["testing"]
    node = {
        "id": "N1",
        "preferred_model": "glm-5.1",
        "required_skills": [],
        "required_capabilities": ["code_impl", "test_generation"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"


def test_capability_alias_groups_do_not_bridge_unrelated_requirements() -> None:
    worker = {
        "skills": ["python"],
        "capabilities": ["python"],
    }

    # Direct synonyms in one declared group remain equivalent.
    assert gs._capabilities_match(worker, ["code_impl"])
    # Overlap between the algorithm and API groups must not make every Python
    # worker an algorithm-design worker through api-design -> python.
    assert not gs._capabilities_match(worker, ["algorithm_design"])


def test_repo_workspace_is_dispatch_provisioned_not_worker_advertised() -> None:
    worker = _worker("pane-a")
    worker["skills"] = ["python", "pytest", "ImplementationWorker"]
    worker["capabilities"] = ["code_impl"]
    node = {
        "id": "N1",
        "preferred_model": "glm-5.1",
        "logical_operator": "ImplementationWorker",
        "required_skills": ["python", "testing"],
        "required_capabilities": ["repo-workspace", "python-cli-implementation"],
    }
    result = assign_workers([node], [worker])
    assert result["queued"] == []
    assert result["assigned"][0]["node"] == "N1"
    assert result["assigned"][0]["required_capabilities"] == ["python-cli-implementation"]


def test_enqueue_ready_marks_no_matching_worker_nodes_as_worker_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path / "sprints")
    graph = {
        "sprint_id": "sid",
        "nodes": [
            {
                "id": "N1",
                "depends_on": [],
                "required_skills": ["python", "solar-harness-control-plane"],
                "required_capabilities": ["algorithm_design"],
            }
        ],
    }
    graph_path = tmp_path / "sid.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("task_queue.enqueue", lambda *a, **kw: {"ok": True, "id": "q-1"})
    result = enqueue_ready(
        graph,
        str(graph_path),
        [{"pane": "pane-a", "models": ["sonnet"], "skills": ["python"], "capabilities": ["python"]}],
        lease=False,
        dry_run=False,
    )
    assert result["queued"][0]["reason"] == "no_matching_worker"
    assert result["worker_blocked"][0]["node"] == "N1"
    assert graph["nodes"][0]["status"] == "worker_blocked"
    assert graph["node_results"]["N1"]["blocking_reason"] == "no_matching_worker"


def test_worker_blocked_nodes_are_retryable_after_capability_fix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path / "sprints")
    graph = {
        "sprint_id": "sid",
        "nodes": [
            {
                "id": "N1",
                "depends_on": [],
                "status": "worker_blocked",
                "required_skills": [],
                "required_capabilities": ["code_impl", "test_generation"],
                "preferred_model": "glm-5.1",
            }
        ],
    }
    graph_path = tmp_path / "sid.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("task_queue.enqueue", lambda *a, **kw: {"ok": True, "id": "q-2"})
    result = enqueue_ready(
        graph,
        str(graph_path),
        [{
            "pane": "pane-a",
            "models": ["glm-5.1"],
            "skills": ["python", "pytest", "ImplementationWorker"],
            "capabilities": ["testing"],
            "busy": False,
        }],
        lease=False,
        dry_run=False,
    )
    assert result["enqueued"][0]["node"] == "N1"
    assert result["queued"] == []
    assert graph["nodes"][0]["status"] == "assigned"


def test_worker_blocked_node_becomes_queued_when_matching_worker_is_pane_busy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gs, "SPRINTS_DIR", tmp_path / "sprints")
    graph = {
        "sprint_id": "sid",
        "nodes": [
            {
                "id": "N1",
                "depends_on": [],
                "status": "worker_blocked",
                "required_skills": ["python", "sqlite"],
                "required_capabilities": [],
            }
        ],
    }
    graph_path = tmp_path / "sid.task_graph.json"
    graph_path.write_text("{}", encoding="utf-8")

    def fake_acquire(*_args, **_kwargs):
        return {"acquired": False, "reason": "pane_busy"}

    monkeypatch.setattr("pane_lease.acquire", fake_acquire)
    result = enqueue_ready(
        graph,
        str(graph_path),
        [{
            "pane": "pane-a",
            "models": ["sonnet"],
            "skills": ["python", "sqlite3"],
            "capabilities": ["python"],
            "busy": False,
        }],
        lease=True,
        dry_run=False,
    )
    assert result["queued"][0]["reason"] == "pane_busy"
    assert result["worker_blocked"] == []
    assert graph["nodes"][0]["status"] == "queued"
    assert graph["node_results"]["N1"]["blocking_reason"] == "pane_busy"
