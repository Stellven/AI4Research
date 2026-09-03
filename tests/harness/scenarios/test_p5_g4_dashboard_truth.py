"""G4 spec §3 — the dashboard surfaces generic-path governance truthfully.

The runtime facts (G4 spec table) and their surfaces:
- graph stamped (pm.generic.v1 + plan_certificate PASS)  -> state "certified"
- plan_compile_bounces > 0                               -> bounce counter +
  latest compile error codes (from <sid>.plan-compile-errors.json)
- terminal failed/plan_compile_failed                    -> truthful terminal
- terminal failed/plan_certificate_invalid               -> truthful terminal
- graph present but unstamped (planner in flight)        -> NEUTRAL
  "compiling" state — not an error, never "template"
- fixed contracts -> "contracted"; legacy uncontracted -> "legacy" (both
  outside the generic-path governance story; no invented projections)

Everything derives from files the runtime actually writes (status.json,
task_graph.json, the errors artifact) — failure class 14's rule: dashboard
surfaces contract truth, never heuristics.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')

SID = "sprint-20260710-g4-dash-truth"


def _load_routes(harness_dir: Path):
    routes_path = _HARNESS / "status-server" / "routes" / "orchestration_routes.py"
    spec = importlib.util.spec_from_file_location("p5_g4_dash_truth_routes", str(routes_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    lib_path = str(_HARNESS / "lib")
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    spec.loader.exec_module(mod)
    mod.HARNESS_DIR = harness_dir
    mod.SPRINTS_DIR = harness_dir / "sprints"
    mod.SESSIONS_DIR = harness_dir / "sessions"
    mod.STATE_DIR = harness_dir / "state"
    return mod


def _write_fixture(
    harness_dir: Path,
    *,
    graph_top: dict,
    status_extra: dict | None = None,
    compile_errors: list[dict] | None = None,
) -> None:
    sprints = harness_dir / "sprints"
    for sub in ("sprints", "sessions", "state", "config", "events"):
        (harness_dir / sub).mkdir(parents=True, exist_ok=True)
    status = {
        "sprint_id": SID,
        "title": "linecount",
        "status": "active",
        "phase": "building",
    }
    status.update(status_extra or {})
    (sprints / f"{SID}.status.json").write_text(json.dumps(status), encoding="utf-8")
    graph = {
        "sprint_id": SID,
        "nodes": [
            {"id": "N1", "goal": "build", "status": "pending", "depends_on": []},
        ],
    }
    graph.update(graph_top)
    (sprints / f"{SID}.task_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    if compile_errors is not None:
        (sprints / f"{SID}.plan-compile-errors.json").write_text(
            json.dumps({"errors": compile_errors, "bounce_count": (status_extra or {}).get("plan_compile_bounces", 0)}),
            encoding="utf-8",
        )


def _governance(mod) -> dict:
    payload, _degraded = mod.build_dashboard_payload(SID)
    gov = payload.get("plan_governance")
    assert isinstance(gov, dict), payload.keys()
    return gov


CERT = {"schema": "solar.plan_certificate.v1", "verdict": "PASS",
        "graph_hash": "abc123def4567890", "validated_at": "2026-07-10T00:00:00Z"}


class TestPlanGovernanceStates:
    def test_certified_generic(self, tmp_path):
        _write_fixture(tmp_path, graph_top={
            "workflow_contract_id": "pm.generic.v1",
            "workflow_contract_version": "1",
            "plan_certificate": CERT,
            "plan_compile_required": True,
        })
        gov = _governance(_load_routes(tmp_path))
        assert gov["state"] == "certified", gov
        assert gov["certificate"]["verdict"] == "PASS"
        assert gov["certificate"]["present"] is True

    def test_unstamped_intake_graph_is_neutral_compiling(self, tmp_path):
        """Planner in flight / template on disk: NOT an error, NOT 'template'."""
        _write_fixture(tmp_path, graph_top={"plan_compile_required": True})
        gov = _governance(_load_routes(tmp_path))
        assert gov["state"] == "compiling", gov
        assert gov["certificate"]["present"] is False

    def test_bounce_counter_and_error_codes(self, tmp_path):
        _write_fixture(
            tmp_path,
            graph_top={"plan_compile_required": True},
            status_extra={"plan_compile_bounces": 2},
            compile_errors=[{"code": "PLAN_GATE_PATH_DENIED", "node_id": "S2", "message": "x"}],
        )
        gov = _governance(_load_routes(tmp_path))
        assert gov["plan_compile_bounces"] == 2, gov
        assert "PLAN_GATE_PATH_DENIED" in gov["compile_error_codes"], gov

    def test_completed_repair_record_survives_finalized_projection(self, tmp_path):
        _write_fixture(
            tmp_path,
            graph_top={
                "workflow_contract_id": "pm.generic.v1",
                "plan_certificate": CERT,
                "plan_compile_required": True,
            },
            status_extra={"status": "passed", "phase": "finalized"},
        )
        repair_path = (
            tmp_path
            / "sprints"
            / SID
            / "planning"
            / "semantic"
            / "repair_record.json"
        )
        repair_path.parent.mkdir(parents=True, exist_ok=True)
        repair_path.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "generation": 1,
                    "defects": [
                        {"code": "DISCOVERY_NON_SCOPE_OWNERSHIP"},
                        {"code": "REQUIREMENT_VERIFIER_MISSING"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        gov = _governance(_load_routes(tmp_path))

        assert gov["plan_compile_bounces"] == 1, gov
        assert gov["compile_error_codes"] == [
            "DISCOVERY_NON_SCOPE_OWNERSHIP",
            "REQUIREMENT_VERIFIER_MISSING",
        ], gov

    def test_terminal_plan_compile_failed(self, tmp_path):
        _write_fixture(
            tmp_path,
            graph_top={"plan_compile_required": True},
            status_extra={"status": "failed", "phase": "plan_compile_failed", "plan_compile_bounces": 3},
        )
        gov = _governance(_load_routes(tmp_path))
        assert gov["state"] == "plan_compile_failed", gov
        assert gov["plan_compile_bounces"] == 3

    def test_terminal_plan_certificate_invalid(self, tmp_path):
        _write_fixture(
            tmp_path,
            graph_top={
                "workflow_contract_id": "pm.generic.v1",
                "plan_certificate": CERT,
                "plan_compile_required": True,
            },
            status_extra={"status": "failed", "phase": "plan_certificate_invalid"},
        )
        gov = _governance(_load_routes(tmp_path))
        assert gov["state"] == "plan_certificate_invalid", gov

    def test_fixed_contract_is_contracted(self, tmp_path):
        _write_fixture(tmp_path, graph_top={
            "workflow_contract_id": "code.cli_smoke",
            "workflow_contract_version": "1",
        })
        gov = _governance(_load_routes(tmp_path))
        assert gov["state"] == "contracted", gov

    def test_legacy_uncontracted_is_legacy(self, tmp_path):
        _write_fixture(tmp_path, graph_top={})
        gov = _governance(_load_routes(tmp_path))
        assert gov["state"] == "legacy", gov

    def test_projection_carries_the_same_block(self, tmp_path):
        _write_fixture(tmp_path, graph_top={
            "workflow_contract_id": "pm.generic.v1",
            "plan_certificate": CERT,
            "plan_compile_required": True,
        })
        mod = _load_routes(tmp_path)
        projection, _deg = mod.build_projection_payload(SID, mode="fast")
        gov = projection.get("plan_governance")
        assert isinstance(gov, dict) and gov.get("state") == "certified", projection.keys()


class TestNoFalseDecisionCardOnGovernedPath:
    """G4 UI-rung run 6: six 'YOUR DECISION — Review the plan' sightings
    during 'Plan compiling…' with ZERO plan verdicts in the ledger — the P4
    class-14 bug resurfacing on the GENERIC path. P4's guard keyed on
    workflow_contract_id, which the pre-planner template does not carry yet;
    the governed generic path (birth marker -> plan_governance states) never
    waits on a human plan review — autopilot advances pm->planner->builder
    and the certificate is the plan gate. Legacy uncontracted sprints keep
    the human plan-review card (pinned)."""

    def _stage(self, tmp_path, *, governed: bool):
        graph_top = {"plan_compile_required": True} if governed else {}
        _write_fixture(tmp_path, graph_top=graph_top,
                       status_extra={"status": "active", "phase": "planning_complete"})
        sprints = tmp_path / "sprints"
        (sprints / f"{SID}.design.md").write_text("# design\n", encoding="utf-8")
        (sprints / f"{SID}.plan.md").write_text("# plan\n", encoding="utf-8")

    def test_governed_compiling_never_advertises_plan_review(self, tmp_path):
        self._stage(tmp_path, governed=True)
        mod = _load_routes(tmp_path)
        projection, _deg = mod.build_projection_payload(SID, mode="fast")
        action = projection.get("human_action_required") or {}
        assert action.get("type") != "plan_review", action

    def test_governed_compiling_is_not_reported_as_a_stall(self, tmp_path):
        """The normal compiler/certificate interval is progress, not a pause."""
        self._stage(tmp_path, governed=True)
        mod = _load_routes(tmp_path)
        projection, _deg = mod.build_projection_payload(SID, mode="fast")
        governance = projection.get("plan_governance") or {}
        stall = (projection.get("dispatch") or {}).get("stall") or {}
        action = projection.get("human_action_required") or {}

        assert governance.get("state") == "compiling", governance
        assert stall.get("is_stalled") is False, stall
        assert action.get("type") not in {"stall_review", "capability_mismatch"}, action

    def test_certified_pending_dispatch_handoff_is_not_reported_as_a_stall(self, tmp_path):
        """A pending node is not blocked evidence during the scheduler handoff.

        The live rc.9 fixture received its PASS certificate, then briefly had
        no active node before the first builder dispatch.  That normal state
        must remain flowing unless routing records a real blocker or the event
        stream proves a repeated no-progress loop.
        """
        _write_fixture(
            tmp_path,
            graph_top={
                "workflow_contract_id": "pm.generic.v1",
                "workflow_contract_version": "1",
                "plan_certificate": CERT,
                "plan_compile_required": True,
            },
            status_extra={"status": "active", "phase": "planning_complete"},
        )
        mod = _load_routes(tmp_path)
        projection, _deg = mod.build_projection_payload(SID, mode="fast")
        governance = projection.get("plan_governance") or {}
        stall = (projection.get("dispatch") or {}).get("stall") or {}
        action = projection.get("human_action_required") or {}

        assert governance.get("state") == "certified", governance
        assert stall.get("is_stalled") is False, stall
        assert action.get("type") not in {"stall_review", "capability_mismatch"}, action

    def test_legacy_uncontracted_keeps_the_plan_review_card(self, tmp_path):
        self._stage(tmp_path, governed=False)
        mod = _load_routes(tmp_path)
        projection, _deg = mod.build_projection_payload(SID, mode="fast")
        action = projection.get("human_action_required") or {}
        assert action.get("type") == "plan_review", action
