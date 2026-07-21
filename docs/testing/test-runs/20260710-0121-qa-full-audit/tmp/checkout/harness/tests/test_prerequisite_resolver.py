"""Top-level pytest suite for ``lib/prerequisite_resolver``.

Covers the four case classes called out in
``sprints/sprint-20260524-133807.S3-dispatch.md``:

A. APO reproduction — upstream ``status == "active"`` but the prerequisite
   targets ``required_node_id`` which is ``passed`` on the upstream's graph;
   the resolver must allow (the wake-prerequisite is the node, not the
   sprint-level phase).
B. dict prerequisite with ``required_phase`` (e.g.
   ``{"sprint_id": "upstream", "required_phase": "planning_complete"}``).
C. string ``"sid"`` and ``"sid:status"`` back-compat parsing.
D. upstream missing status / missing task_graph / missing node →
   ``ok == False`` with a specific ``reason`` string.

The sibling suite at ``tests/graph/test_prerequisite_resolver.py`` covers
phase ladder + dedupe; this top-level suite covers the four acceptance
classes for ``S3``. Both suites share the same module under test via
``importlib`` (no production code coupling between them).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


LIB_PATH = Path(__file__).resolve().parents[1] / "lib" / "prerequisite_resolver.py"


@pytest.fixture(scope="module")
def pr():
    """Load ``prerequisite_resolver`` from ``lib/`` without polluting sys.path."""
    spec = importlib.util.spec_from_file_location(
        "prerequisite_resolver_under_test", LIB_PATH
    )
    assert spec is not None and spec.loader is not None, f"no spec for {LIB_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_status(
    sprints_dir: Path, sid: str, *, status: str, phase: str = ""
) -> Path:
    payload = {"id": sid, "status": status, "phase": phase}
    path = sprints_dir / f"{sid}.status.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_graph(
    sprints_dir: Path,
    sid: str,
    *,
    nodes: list[dict] | None = None,
    node_results: dict | None = None,
) -> Path:
    payload: dict = {"sprint_id": sid, "nodes": nodes or []}
    if node_results is not None:
        payload["node_results"] = node_results
    path = sprints_dir / f"{sid}.task_graph.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Case A — APO reproduction
# ---------------------------------------------------------------------------


class TestAcceptanceA_NodeStatusAllowsWhileSprintActive:
    """Upstream sprint is ``active`` but a specific upstream node is ``passed``.

    The APO foundation sprint hit exactly this: ``status.json`` carried
    ``status=active, phase=planning_complete`` while the child wake required
    ``required_node_id=N_root, required_node_status=passed``. The resolver
    must allow because the node-level requirement is independent of the
    sprint-level phase.
    """

    def test_node_passed_via_node_results_block(self, pr, tmp_path: Path) -> None:
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_root", "status": "pending"}],
            node_results={
                "N_root": {"status": "passed", "updated_at": "2026-05-24T00:00:00Z"}
            },
        )

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_root",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is True, detail
        assert detail["current_node_status"] == "passed"
        assert detail["current_status"] == "active"
        assert detail["current_phase"] == "planning_complete"
        assert "reason" not in detail

    def test_node_passed_via_inline_node_status(self, pr, tmp_path: Path) -> None:
        """If ``node_results`` is absent, the resolver falls back to the
        per-node ``status`` field embedded in ``nodes[]``."""
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_root", "status": "passed"}],
        )

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_root",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is True, detail
        assert detail["current_node_status"] == "passed"

    def test_node_passed_with_default_required_status(self, pr, tmp_path: Path) -> None:
        """When ``required_node_status`` is omitted, the resolver defaults to
        ``passed`` (per normalize_prerequisite)."""
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_root", "status": "passed"}],
        )

        ok, detail = pr.evaluate_prerequisite(
            {"sprint_id": "upstream", "required_node_id": "N_root"},
            tmp_path,
        )

        assert ok is True, detail
        assert detail["required_node_status"] == "passed"
        assert detail["current_node_status"] == "passed"

    def test_node_skipped_counts_as_passed(self, pr, tmp_path: Path) -> None:
        """The resolver treats ``skipped`` as terminal-success for nodes
        (see _node_effective_status + the ``effective in (passed, skipped)``
        check)."""
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_skip", "status": "skipped"}],
        )

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_skip",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is True, detail
        assert detail["current_node_status"] == "skipped"


# ---------------------------------------------------------------------------
# Case B — dict prerequisite with required_phase
# ---------------------------------------------------------------------------


class TestAcceptanceB_DictPrerequisiteWithRequiredPhase:
    """Dict-form prerequisite carrying ``required_phase``.

    ``required_phase`` is satisfied either when the current phase matches
    exactly, when it has progressed past the requested rank in PHASE_ORDER,
    or when current_status/phase is terminal-success.
    """

    def test_exact_phase_match_allows(self, pr, tmp_path: Path) -> None:
        _write_status(
            tmp_path, "upstream", status="active", phase="planning_complete"
        )

        ok, detail = pr.evaluate_prerequisite(
            {"sprint_id": "upstream", "required_phase": "planning_complete"},
            tmp_path,
        )

        assert ok is True, detail
        assert detail["required_phase"] == "planning_complete"
        assert detail["current_phase"] == "planning_complete"

    def test_phase_progressed_past_requirement_allows(
        self, pr, tmp_path: Path
    ) -> None:
        # planning_complete is at rank 5; build_complete (rank 7) is later
        _write_status(tmp_path, "upstream", status="active", phase="build_complete")

        ok, detail = pr.evaluate_prerequisite(
            {"sprint_id": "upstream", "required_phase": "planning_complete"},
            tmp_path,
        )

        assert ok is True, detail
        assert detail["current_phase"] == "build_complete"

    def test_phase_behind_requirement_blocks(self, pr, tmp_path: Path) -> None:
        # drafting (rank 1) is behind planning_complete (rank 5)
        _write_status(tmp_path, "upstream", status="drafting", phase="drafting")

        ok, detail = pr.evaluate_prerequisite(
            {"sprint_id": "upstream", "required_phase": "planning_complete"},
            tmp_path,
        )

        assert ok is False
        assert detail["reason"] == "status_not_satisfied"
        assert detail["required_phase"] == "planning_complete"
        assert detail["current_phase"] == "drafting"

    def test_phase_with_terminal_status_allows(self, pr, tmp_path: Path) -> None:
        """Even if the phase string is unfamiliar, a terminal status
        (``passed``) satisfies a ``required_phase`` requirement when the
        required phase is in MILESTONE_REQUIREMENTS."""
        _write_status(tmp_path, "upstream", status="passed", phase="finalized")

        ok, detail = pr.evaluate_prerequisite(
            {"sprint_id": "upstream", "required_phase": "planning_complete"},
            tmp_path,
        )

        assert ok is True, detail


# ---------------------------------------------------------------------------
# Case C — string back-compat
# ---------------------------------------------------------------------------


class TestAcceptanceC_StringBackCompat:
    """Plain-string prerequisites must continue to parse:

    - ``"sid"``         → default ``required_status == "passed"``
    - ``"sid:status"``  → ``required_status == <status>``
    """

    def test_bare_sid_string_defaults_to_passed(self, pr, tmp_path: Path) -> None:
        _write_status(tmp_path, "upstream", status="passed", phase="completed")

        ok, detail = pr.evaluate_prerequisite("upstream", tmp_path)

        assert ok is True, detail
        assert detail["sprint_id"] == "upstream"
        assert detail["required_status"] == "passed"

    def test_bare_sid_string_blocks_when_not_terminal(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="drafting", phase="drafting")

        ok, detail = pr.evaluate_prerequisite("upstream", tmp_path)

        assert ok is False
        assert detail["reason"] == "status_not_satisfied"

    def test_sid_colon_status_parses_explicit_required(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="reviewing", phase="reviewing")

        ok, detail = pr.evaluate_prerequisite("upstream:reviewing", tmp_path)

        assert ok is True, detail
        assert detail["sprint_id"] == "upstream"
        assert detail["required_status"] == "reviewing"
        assert detail["current_status"] == "reviewing"

    def test_sid_colon_status_blocks_when_status_differs(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="drafting", phase="drafting")

        ok, detail = pr.evaluate_prerequisite("upstream:reviewing", tmp_path)

        assert ok is False
        assert detail["reason"] == "status_not_satisfied"
        assert detail["required_status"] == "reviewing"

    def test_empty_string_returns_blocked_with_reason(
        self, pr, tmp_path: Path
    ) -> None:
        ok, detail = pr.evaluate_prerequisite("", tmp_path)

        assert ok is False
        assert detail["reason"] == "empty_sprint_id"

    def test_whitespace_string_returns_blocked_with_reason(
        self, pr, tmp_path: Path
    ) -> None:
        ok, detail = pr.evaluate_prerequisite("   ", tmp_path)

        assert ok is False
        assert detail["reason"] == "empty_sprint_id"


# ---------------------------------------------------------------------------
# Case D — missing artifacts → blocked with specific reason
# ---------------------------------------------------------------------------


class TestAcceptanceD_MissingArtifactsBlockWithReason:
    """When upstream artifacts are absent, evaluation must return
    ``(False, detail)`` with a precise ``reason`` token so callers (autopilot,
    workflow_guard, graph_scheduler) can route correctly."""

    def test_missing_status_file_reports_missing_status(
        self, pr, tmp_path: Path
    ) -> None:
        # no status.json written
        ok, detail = pr.evaluate_prerequisite(
            {"sprint_id": "ghost", "required_status": "passed"}, tmp_path
        )

        assert ok is False
        assert detail["reason"] == "missing_status"
        assert detail["sprint_id"] == "ghost"
        assert detail["status_path"].endswith("ghost.status.json")

    def test_missing_status_with_string_form(self, pr, tmp_path: Path) -> None:
        """Same path through the string parser."""
        ok, detail = pr.evaluate_prerequisite("ghost", tmp_path)

        assert ok is False
        assert detail["reason"] == "missing_status"

    def test_corrupt_status_reports_status_corrupt(
        self, pr, tmp_path: Path
    ) -> None:
        (tmp_path / "broken.status.json").write_text("not json", encoding="utf-8")

        ok, detail = pr.evaluate_prerequisite("broken", tmp_path)

        assert ok is False
        assert detail["reason"] == "status_corrupt"
        assert "error" in detail

    def test_missing_task_graph_when_node_id_required(
        self, pr, tmp_path: Path
    ) -> None:
        """status.json exists but task_graph.json is missing → upstream
        graph cannot be evaluated for a node-level requirement."""
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        # deliberately do NOT write task_graph.json

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_root",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is False
        assert detail["reason"] == "upstream_task_graph_missing"

    def test_corrupt_task_graph_when_node_id_required(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        (tmp_path / "upstream.task_graph.json").write_text(
            "not json", encoding="utf-8"
        )

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_root",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is False
        assert detail["reason"] == "upstream_task_graph_corrupt"
        assert "error" in detail

    def test_missing_node_in_present_task_graph(self, pr, tmp_path: Path) -> None:
        """task_graph.json exists but does not contain the requested node."""
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_other", "status": "passed"}],
        )

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_missing",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is False
        assert detail["reason"] == "upstream_node_missing:N_missing"

    def test_node_present_but_status_mismatch_reports_status_not_satisfied(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_root", "status": "pending"}],
        )

        ok, detail = pr.evaluate_prerequisite(
            {
                "sprint_id": "upstream",
                "required_node_id": "N_root",
                "required_node_status": "passed",
            },
            tmp_path,
        )

        assert ok is False
        # The node exists and was evaluable, so the failure reason is the
        # status-mismatch path, not the graph-missing path.
        assert detail["reason"] == "status_not_satisfied"
        assert detail["current_node_status"] == "pending"


# ---------------------------------------------------------------------------
# Cross-case sanity — iter_blocked walks both prerequisites and policy
# ---------------------------------------------------------------------------


class TestIterBlockedIntegration:
    """Ensures the four cases above wire correctly through ``iter_blocked``."""

    def test_iter_blocked_returns_node_level_failures(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_root", "status": "pending"}],
        )

        graph = {
            "prerequisites": [
                {
                    "sprint_id": "upstream",
                    "required_node_id": "N_root",
                    "required_node_status": "passed",
                }
            ]
        }

        blocked = pr.iter_blocked(graph, tmp_path)

        assert len(blocked) == 1
        assert blocked[0]["reason"] == "status_not_satisfied"
        assert blocked[0]["required_node_id"] == "N_root"

    def test_iter_blocked_clears_when_node_passes(
        self, pr, tmp_path: Path
    ) -> None:
        _write_status(tmp_path, "upstream", status="active", phase="planning_complete")
        _write_graph(
            tmp_path,
            "upstream",
            nodes=[{"id": "N_root", "status": "passed"}],
        )

        graph = {
            "prerequisites": [
                {
                    "sprint_id": "upstream",
                    "required_node_id": "N_root",
                    "required_node_status": "passed",
                }
            ]
        }

        assert pr.iter_blocked(graph, tmp_path) == []

    def test_iter_blocked_walks_both_prerequisites_and_blocks_until(
        self, pr, tmp_path: Path
    ) -> None:
        # upstream_a is missing entirely; upstream_b has the wrong phase
        _write_status(tmp_path, "upstream_b", status="drafting", phase="drafting")

        graph = {
            "prerequisites": ["upstream_a"],
            "dependency_policy": {
                "blocks_until": [
                    {"sprint_id": "upstream_b", "required_phase": "planning_complete"}
                ]
            },
        }

        blocked = pr.iter_blocked(graph, tmp_path)

        # one missing-status + one phase-not-satisfied
        assert len(blocked) == 2
        reasons = {b["reason"] for b in blocked}
        assert reasons == {"missing_status", "status_not_satisfied"}
