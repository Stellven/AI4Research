"""G4 blocker 2 — legacy uncontracted graphs are grandfathered, not governed.

Owner decision (2026-07-10): default-on with grandfathering. Under
default-on, `_generic_graph_kind`'s old rule (non-epic + no
workflow_contract_id -> "generic") would demand a plan certificate from
EVERY legacy flow that never passes the planner-compile seam —
hand-authored task graphs, direct multi-task CLI usage, old chain flows —
refusing them non-terminally forever (G4 spec §6 blocker 2).

Fix under test (spec option b, per owner): intake-born sprints are marked
at birth — the requirement compiler stamps `plan_compile_required: true`
on every template graph skeleton and the runtime-owned sprint status. The
validator restores it from status if a planner replaces the graph. Classification:

- graph CLAIMS pm.generic.v1  -> "generic" (governed; claiming the contract
  is never a free pass — pre-existing rule, pinned here)
- uncontracted + birth marker -> "generic" (governed; the intake path —
  cert demanded exactly as in G3 runs)
- uncontracted, no marker     -> "legacy_uncontracted" (guards skip;
  byte-identical legacy behavior — the grandfather clause)
- epics                       -> "epic_graph" (unchanged)

Defense in depth: the coordinator compile-first seam still compiles+stamps
any sprint with planner artifacts independent of this classification.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
for _p in (str(_HARNESS / "lib"), str(_HARNESS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import plan_validator as pv  # noqa: E402


def _uncontracted_graph(**top) -> dict:
    graph = {
        "sprint_id": "sprint-g4-legacy",
        "nodes": [
            {"id": "S1", "goal": "hand-authored legacy node", "depends_on": []},
        ],
    }
    graph.update(top)
    return graph


@pytest.fixture(autouse=True)
def _validator_on(monkeypatch):
    monkeypatch.setenv("SOLAR_PLAN_VALIDATOR", "1")


class TestLegacyClassification:
    def test_unmarked_uncontracted_graph_is_legacy(self):
        graph = _uncontracted_graph()
        assert pv._generic_graph_kind(graph) == "legacy_uncontracted"

    def test_unmarked_uncontracted_graph_skips_dispatch_guard(self):
        """The blocker-2 shape itself: a hand-authored graph must NOT be
        refused for a missing certificate."""
        verdict = pv.check_planner_graph_dispatchable(_uncontracted_graph())
        assert verdict.get("ok") is True, verdict
        assert verdict.get("skipped_reason") == "legacy_uncontracted", verdict

    def test_birth_marked_graph_is_governed(self):
        """The intake path: the requirement-compiler template carries the
        marker, so the guard demands the certificate exactly as in G3."""
        graph = _uncontracted_graph(plan_compile_required=True)
        assert pv._generic_graph_kind(graph) == "generic"
        verdict = pv.check_planner_graph_dispatchable(graph)
        assert verdict.get("ok") is False, verdict
        codes = [e.get("code") for e in verdict.get("errors") or []]
        assert any("CERTIFICATE" in str(c) for c in codes), verdict

    def test_claiming_generic_contract_is_never_a_free_pass(self):
        """Pre-existing rule pinned: a graph that CLAIMS pm.generic.v1 is
        governed regardless of the marker."""
        graph = _uncontracted_graph(workflow_contract_id="pm.generic.v1")
        assert pv._generic_graph_kind(graph) == "generic"
        verdict = pv.check_planner_graph_dispatchable(graph)
        assert verdict.get("ok") is False, verdict

    def test_epic_graph_classification_unchanged(self):
        graph = _uncontracted_graph(epic=True, plan_compile_required=True)
        if pv._is_epic_graph(graph):
            assert pv._generic_graph_kind(graph) == "epic_graph"
        else:
            pytest.skip("fixture does not match the epic detector shape")

    def test_compile_seam_skips_unmarked_legacy_graph(self, tmp_path):
        """compile_planner_graph must not bounce/terminalize a hand-authored
        legacy sprint (grandfather clause at the compile seam too)."""
        import json
        sid = "sprint-g4-legacy-compile"
        (tmp_path / f"{sid}.task_graph.json").write_text(
            json.dumps(_uncontracted_graph(sprint_id=sid)), encoding="utf-8"
        )
        result = pv.compile_planner_graph(tmp_path, sid)
        assert result.get("skipped_reason") == "legacy_uncontracted", result
        assert not (tmp_path / f"{sid}{pv.ERRORS_ARTIFACT_SUFFIX}").exists()


class TestRequirementCompilerBirthMarker:
    @pytest.mark.parametrize("request_type,lane", [
        ("short_impl", ""),
        ("standard", ""),
        ("research", ""),
    ])
    def test_template_skeletons_carry_the_birth_marker(self, request_type, lane):
        import codex_pm_router as router
        known_types = {
            getattr(router, "SHORT_IMPL", "short_impl"),
            getattr(router, "RESEARCH", "research"),
        }
        rt = request_type if request_type in known_types or request_type == "standard" else "standard"
        graph = router.build_task_graph_skeleton(rt, lane, "build a small tool")
        assert graph.get("plan_compile_required") is True, (
            f"template skeleton for {rt!r} must carry the intake birth marker"
        )
