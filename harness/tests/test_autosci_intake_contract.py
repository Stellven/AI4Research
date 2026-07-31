from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
GATEWAY = LIB / "intent_gateway.py"
CONSUMER = LIB / "intent_consumer.py"
EPIC = LIB / "epic_decomposer.py"

if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
os.environ.setdefault("HARNESS_DIR", str(ROOT))

from apo_plan_compiler import compile_execution_plan_for_node  # noqa: E402
from autosci_intake_contract import (  # noqa: E402
    WORKFLOW_CONTRACT_ID,
    WORKFLOW_CONTRACT_VERSION,
    build_autosci_task_graph,
    is_autosci_research_intake_text,
)
from plan_validator import check_planner_graph_dispatchable, compile_planner_graph  # noqa: E402


AUTOSCI_REQUEST = (
    "Official full-runtime AutoSci integration test through normal solar intake. "
    "Do not call a manual autosci shim. The workflow must ingest papers, extract claims, "
    "generate ideas, run exp-design, exp-run, exp-eval, and produce a report so we can "
    "verify whether AutoSci autonomously participates in the runtime."
)


def _env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(ROOT)
    env["SOLAR_HARNESS_DIR"] = str(ROOT)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(tmp_path / "intents")
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(tmp_path / "sprints")
    env["SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT"] = str(tmp_path / "workspace")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _capture(env: dict[str, str], text: str) -> str:
    proc = subprocess.run(
        [
            sys.executable,
            str(GATEWAY),
            "capture",
            "--text",
            text,
            "--source-channel",
            "pm_dispatch",
            "--source-trust",
            "pm_dispatch",
            "--json",
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=True,
    )
    return str(json.loads(proc.stdout)["intent_id"])


def test_autosci_contract_detection_is_explicit() -> None:
    assert is_autosci_research_intake_text(AUTOSCI_REQUEST)
    assert is_autosci_research_intake_text("请用 AutoSci 从论文 ingest 到 ideate 再到 exp-eval 全流程验证。")
    assert not is_autosci_research_intake_text("Add a dashboard filter and update the README.")


def test_autosci_contract_task_graph_selects_autosci_physical_workers() -> None:
    graph = build_autosci_task_graph(
        sprint_id="sprint-test-autosci-contract",
        title="AutoSci contract",
        request_text=AUTOSCI_REQUEST,
        harness_dir=ROOT,
    )
    assert graph["workflow_contract"] == WORKFLOW_CONTRACT_ID
    assert graph["workflow_contract_id"] == WORKFLOW_CONTRACT_ID
    assert graph["workflow_contract_version"] == WORKFLOW_CONTRACT_VERSION
    assert graph["plan_compile_required"] is True
    assert graph["strict_role_boundaries"] is True
    assert graph["planner_stage"] == {
        "node_id": "N0",
        "role": "planner",
        "status": "required",
        "next_role": "builder",
        "spillover_allowed": False,
    }
    assert "planner_bypass_reason" not in graph["intake_contract"]
    assert "plan_certificate" not in graph
    assert graph["research_mode"] is True
    assert len(graph["nodes"]) >= 19

    selected: dict[str, str] = {}
    for node in graph["nodes"]:
        plan = compile_execution_plan_for_node(
            node,
            request_type="research",
            lane_hint="research",
            registry_path=ROOT / "config" / "capability-capsules.registry.yaml",
            operators_path=ROOT / "config" / "physical-operators.json",
        )
        assert plan["capsule_plan"]["selected"] is True
        assert str(plan["capsule_plan"]["capability_capsule_id"]).startswith("cap.research-")
        operator_id = str(plan["physical_plan"]["selected_operator_id"])
        assert operator_id.startswith("autosci-")
        selected[str(node["id"])] = operator_id

    assert selected["paper_ingest"] == "autosci-paper-ingest-worker"
    assert selected["paper_analyze"] == "autosci-paper-analyze-worker"
    assert selected["idea_generate"] == "autosci-idea-worker"
    assert selected["claim_verify"] == "autosci-claim-verify-worker"


def test_autosci_builder_dispatch_requires_planner_artifacts_and_certificate(tmp_path: Path) -> None:
    sid = "sprint-test-autosci-governance"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph = build_autosci_task_graph(
        sprint_id=sid,
        title="AutoSci governance",
        request_text=AUTOSCI_REQUEST,
        harness_dir=ROOT,
    )
    (sprints / f"{sid}.task_graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (sprints / f"{sid}.status.json").write_text(
        json.dumps({"id": sid, "sprint_id": sid, "plan_compile_required": True}),
        encoding="utf-8",
    )

    missing_artifacts = compile_planner_graph(sprints, sid)
    assert missing_artifacts["ok"] is False
    assert {
        error["code"] for error in missing_artifacts["errors"]
    } == {"AUTOSCI_PLANNER_ARTIFACT_MISSING"}

    design_path = sprints / f"{sid}.design.md"
    plan_path = sprints / f"{sid}.plan.md"
    design_path.write_text("# Planner Design\n\nReviewed AutoSci topology.\n", encoding="utf-8")
    plan_path.write_text("# Planner Plan\n\nPreserve bounded Planner/Builder/Evaluator calls.\n", encoding="utf-8")

    compiled = compile_planner_graph(sprints, sid)
    assert compiled["ok"] is True
    assert compiled["stamped"] is True
    certified = json.loads((sprints / f"{sid}.task_graph.json").read_text(encoding="utf-8"))
    assert certified["plan_certificate"]["verdict"] == "PASS"
    assert certified["planner_stage"]["status"] == "reviewed"
    assert check_planner_graph_dispatchable(certified, sprints_dir=sprints, sid=sid)["ok"] is True

    plan_path.write_text("# Tampered after certification\n", encoding="utf-8")
    tampered = check_planner_graph_dispatchable(certified, sprints_dir=sprints, sid=sid)
    assert tampered["ok"] is False
    assert tampered["errors"][0]["code"] == "AUTOSCI_PLANNER_ARTIFACT_HASH_MISMATCH"


def test_rawintent_consumer_compiles_autosci_request_to_graph_ready_package(tmp_path: Path) -> None:
    env = _env(tmp_path)
    intent_id = _capture(env, AUTOSCI_REQUEST)

    proc = subprocess.run(
        [sys.executable, str(CONSUMER), "consume", "--intent-id", intent_id, "--json"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=True,
    )
    result = json.loads(proc.stdout)["results"][0]
    sprint_id = result["sprint_id"]

    graph = json.loads((tmp_path / "sprints" / f"{sprint_id}.task_graph.json").read_text(encoding="utf-8"))
    status = json.loads((tmp_path / "sprints" / f"{sprint_id}.status.json").read_text(encoding="utf-8"))
    capsule_plan = json.loads((tmp_path / "sprints" / f"{sprint_id}.capsule_plan.json").read_text(encoding="utf-8"))

    assert result["status"] == "consumed"
    assert graph["workflow_contract"] == WORKFLOW_CONTRACT_ID
    assert graph["research_mode"] is True
    assert {node["logical_operator"] for node in graph["nodes"] if str(node["logical_operator"]).startswith("Scientific")}
    assert status["status"] == "drafting"
    assert status["phase"] == "prd_ready"
    assert status["handoff_to"] == "planner"
    assert status["plan_compile_required"] is True
    assert not (tmp_path / "sprints" / f"{sprint_id}.plan.md").exists()
    assert not (tmp_path / "sprints" / f"{sprint_id}.design.md").exists()
    refusal = check_planner_graph_dispatchable(
        graph,
        sprints_dir=tmp_path / "sprints",
        sid=sprint_id,
    )
    assert refusal["ok"] is False
    assert any(error["code"] == "PLAN_CERTIFICATE_MISSING" for error in refusal["errors"])
    assert all(str(node.get("capability_capsule_id", "")).startswith("cap.research-") for node in capsule_plan["nodes"])


def test_epic_decomposer_binds_long_autosci_intake_to_autosci_child_graph(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(ROOT)
    env["SPRINTS_DIR"] = str(tmp_path / "sprints")
    long_request = AUTOSCI_REQUEST + "\n" + "\n".join(
        f"- requirement {idx}: keep AutoSci autonomous and evidence-backed." for idx in range(8)
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(EPIC),
            "create",
            "--title",
            "Official full-runtime AutoSci integration test",
            "--request",
            long_request,
            "--activate-ready",
            "--json",
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    child = payload["children"][0]
    sid = child["sid"]

    graph = json.loads((tmp_path / "sprints" / f"{sid}.task_graph.json").read_text(encoding="utf-8"))
    status = json.loads((tmp_path / "sprints" / f"{sid}.status.json").read_text(encoding="utf-8"))
    parent = json.loads((tmp_path / "sprints" / f"{payload['epic_id']}.task_graph.json").read_text(encoding="utf-8"))

    assert payload["workflow_contract"] == WORKFLOW_CONTRACT_ID
    assert graph["workflow_contract"] == WORKFLOW_CONTRACT_ID
    assert parent["workflow_contract"] == WORKFLOW_CONTRACT_ID
    assert status["status"] == "drafting"
    assert status["phase"] == "prd_ready"
    assert status["handoff_to"] == "planner"
    assert status["plan_compile_required"] is True
    assert not (tmp_path / "sprints" / f"{sid}.plan.md").exists()
    assert not (tmp_path / "sprints" / f"{sid}.design.md").exists()
