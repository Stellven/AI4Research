"""Unit tests for multi_task_runner submit path via operator_runtime.

Coverage:
- Success: envelope submitted, status.json has operator_id / lease_id / inbox_path / result_path
- Capacity/policy rejection: terminal refusal, never duplicate legacy launch
- Pre-submit configuration error: legacy compatibility fallback remains available
- Result timeout: submit succeeds but result.json never appears → status = result_timeout
- Fallback: no operator_id in profile → legacy path taken without attempting submit
- Fallback: OPERATORD_SUBMIT_ENABLED is False → legacy path taken

All dispatch in the submit path goes through the operator inbox (file-based), not
through direct keystroke injection into tmux panes.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(HARNESS_DIR / "lib"))

import multi_task_runner as mtr  # noqa: E402
import node_runstate  # noqa: E402
import operator_runtime as optime  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_harness(tmp_path, monkeypatch):
    """Redirect HARNESS_DIR, RUN_DIR, and SPRINTS_DIR into tmp_path."""
    monkeypatch.setattr(mtr, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(mtr, "RUN_DIR", tmp_path / "run" / "multi-task")
    monkeypatch.setattr(mtr, "SPRINTS_DIR", tmp_path / "sprints")
    (tmp_path / "run" / "multi-task").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sprints").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def sample_node() -> dict:
    return {
        "id": "N1",
        "goal": "Build something useful",
        "write_scope": ["lib/foo.py"],
        "read_scope": ["lib/bar.py"],
        "acceptance": ["foo passes tests"],
    }


@pytest.fixture()
def profile_with_operator() -> dict:
    return {
        "name": "builder",
        "role": "builder",
        "persona": "builder",
        "backend": "claude-cli",
        "model": "sonnet",
        "approval_mode": "bypassPermissions",
        "operator_id": "test-operator-1",
        "operator_vendor": "anthropic",
        "operator_model": "sonnet",
        "operator_pane": "N/A",
        "operator_quota_refresh_at": "N/A",
        "operator_fallback_reason": "",
    }


@pytest.fixture()
def profile_without_operator() -> dict:
    return {
        "name": "builder",
        "role": "builder",
        "persona": "builder",
        "backend": "claude-cli",
        "model": "sonnet",
        "approval_mode": "bypassPermissions",
        "operator_fallback_reason": "",
    }


@pytest.fixture()
def sample_graph() -> dict:
    return {
        "sprint_id": "sprint-test-submit-001",
        "nodes": [{"id": "N1", "status": "ready"}],
    }


@pytest.fixture()
def fake_submit_result(tmp_harness) -> dict:
    inbox_path = str(tmp_harness / "run" / "operator-inbox" / "test-operator-1" / "mt-task-1.json")
    return {
        "task_id": "mt-task-1",
        "operator_id": "test-operator-1",
        "lease_id": "test-operator-1:mt-task-1:2026-01-01T00:00:00Z",
        "inbox_path": inbox_path,
        "status": "submitted",
        "submitted_at": "2026-01-01T00:00:00Z",
    }


def _make_args() -> mock.MagicMock:
    args = mock.MagicMock()
    args.profile = ""
    args.model = ""
    args.backend = ""
    return args


def test_terminal_attribution_ignores_historical_task_for_same_node(tmp_harness) -> None:
    sid = "sprint-attribution-correlation"
    node_id = "N1"
    node_runstate.record(
        mtr.SPRINTS_DIR,
        sid,
        node_id,
        "attribution",
        {
            "dispatch_id": "task-current",
            "operator_id": "operator-current",
            "phase": "running",
            "status": "running",
            "role": "builder",
        },
    )

    mtr._finalize_terminal_attribution(
        {
            "id": "task-historical",
            "sprint_id": sid,
            "node_id": node_id,
            "status": "failed",
            "exit_code": 1,
            "operator_id": "operator-historical",
            "role": "builder",
        }
    )

    attribution = node_runstate.read_snapshot(mtr.SPRINTS_DIR, sid, node_id)["build_attribution"]
    assert attribution["dispatch_id"] == "task-current"
    assert attribution["operator_id"] == "operator-current"
    assert attribution["phase"] == "running"


def test_terminal_attribution_finalizes_only_correlated_current_task(tmp_harness) -> None:
    sid = "sprint-attribution-current"
    node_id = "N1"
    node_runstate.record(
        mtr.SPRINTS_DIR,
        sid,
        node_id,
        "attribution",
        {
            "dispatch_id": "task-current",
            "operator_id": "operator-current",
            "phase": "running",
            "status": "running",
            "role": "builder",
        },
    )

    mtr._finalize_terminal_attribution(
        {
            "id": "task-current",
            "sprint_id": sid,
            "node_id": node_id,
            "status": "completed",
            "exit_code": 0,
            "operator_id": "operator-current",
            "role": "builder",
        }
    )

    attribution = node_runstate.read_snapshot(mtr.SPRINTS_DIR, sid, node_id)["build_attribution"]
    assert attribution["dispatch_id"] == "task-current"
    assert attribution["operator_id"] == "operator-current"
    assert attribution["phase"] == "completed"
    assert attribution["status"] == "completed"
    assert attribution["exit_code"] == 0


def _base_patches(profile):
    """Return a dict of common mock.patch.object calls needed for launch_node."""
    return {
        "select_profile": mock.patch.object(mtr, "select_profile", return_value=profile),
        "capability_for_profile": mock.patch.object(
            mtr, "capability_for_profile",
            return_value={"status": "ok", "provider": "anthropic"},
        ),
        "build_dispatch_text": mock.patch.object(
            mtr, "build_dispatch_text", return_value="# dispatch"
        ),
        "set_node_status": mock.patch.object(mtr, "set_node_status"),
        "save_graph": mock.patch.object(mtr, "save_graph"),
        "set_last_launch": mock.patch.object(mtr, "set_last_launch"),
    }


# ---------------------------------------------------------------------------
# Test: success path
# ---------------------------------------------------------------------------

class TestSubmitPathSuccess:
    def test_status_json_has_required_operator_fields(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        """Successful submit must write operator_id, lease_id, inbox_path, result_path."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", return_value=fake_submit_result):

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["submit_mode"] == "operatord"
        assert result["operator_id"] == "test-operator-1"
        assert result["lease_id"] == fake_submit_result["lease_id"]
        assert result["inbox_path"] == fake_submit_result["inbox_path"]
        assert "result_path" in result
        assert result["status"] == "submitted"

    def test_status_json_written_to_disk(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        """status.json on disk must contain the operator tracking fields."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", return_value=fake_submit_result):

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        status_file = tmp_harness / "run" / "multi-task" / result["id"] / "status.json"
        assert status_file.exists(), "status.json was not written"
        on_disk = json.loads(status_file.read_text())
        assert on_disk["operator_id"] == "test-operator-1"
        assert on_disk["lease_id"] == fake_submit_result["lease_id"]
        assert on_disk["inbox_path"] == fake_submit_result["inbox_path"]
        assert "result_path" in on_disk

    def test_no_tmux_start_called_on_submit_success(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        """tmux_start must NOT be called when submit path succeeds."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", return_value=fake_submit_result), \
             mock.patch.object(mtr, "tmux_start") as mock_tmux:

            mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        mock_tmux.assert_not_called()

    def test_command_profile_propagates_command_into_envelope(
        self,
        tmp_harness,
        sample_node,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        profile = {
            "name": "knowledge-extractor",
            "role": "builder",
            "persona": "builder",
            "backend": "command",
            "model": "thunderomlx",
            "approval_mode": "default",
            "operator_id": "test-operator-1",
            "operator_vendor": "local",
            "operator_model": "thunderomlx",
            "operator_pane": "N/A",
            "operator_quota_refresh_at": "N/A",
            "operator_fallback_reason": "",
            "command": "python3 \"$HARNESS_DIR/tools/thunderomlx_knowledge_extract_agent.py\"",
        }
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"
        captured: dict = {}

        def fake_submit(envelope):
            captured["envelope"] = envelope
            return fake_submit_result

        patches = _base_patches(profile)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", side_effect=fake_submit):

            mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert captured["envelope"]["command"] == profile["command"]


# ---------------------------------------------------------------------------
# Test: submit rejection → legacy fallback
# ---------------------------------------------------------------------------

class TestSubmitPathRejection:
    def test_unknown_structured_reason_does_not_suppress_safe_fallback(self):
        """Only recognized capacity/policy reasons may disable fallback."""

        class OtherSubmitError(RuntimeError):
            reason = "invalid_request"

        assert mtr._operator_submit_rejection_reason(OtherSubmitError("bad envelope")) == ""

    def test_frozen_candidates_cannot_escape_through_legacy_quota_profile(self, monkeypatch):
        """Stale quota/profile history cannot replace the planner's ranked assignment."""
        node = {
            "id": "N1",
            "role": "builder",
            "preferred_profile": "legacy-escape",
            "quota_failure_reason": "quota_exhausted",
            "quota_fallback_from": "legacy-escape",
            "quota_blocked_profiles": ["builder"],
            "physical_candidates": [
                {"rank": 1, "operator_id": "frozen-operator"},
            ],
        }
        config = {
            "defaults": {"profile": "builder", "backend": "command"},
            "profiles": {
                "builder": {
                    "role": "builder",
                    "backend": "command",
                    "model": "base-model",
                    "operator_id": "legacy-builder-operator",
                },
                "legacy-escape": {
                    "role": "builder",
                    "backend": "command",
                    "model": "legacy-model",
                    "operator_id": "legacy-escape-operator",
                },
            },
        }
        monkeypatch.setattr(mtr, "load_profiles", lambda: config)
        select = mock.Mock(return_value=({
            "operator_id": "frozen-operator",
            "backend": "command",
            "model": "frozen-model",
            "scheduler_candidate_rank": 1,
            "scheduler_candidate_observations": [
                {"operator_id": "frozen-operator", "rank": 1, "state": "READY"},
            ],
        }, ""))
        monkeypatch.setattr(mtr, "select_operator", select)

        selected = mtr.select_profile(node)

        select.assert_called_once()
        assert selected["operator_id"] == "frozen-operator"
        assert selected["model"] == "frozen-model"
        assert selected["scheduler_candidate_rank"] == 1
        assert "quota_fallback_from" not in selected

    @pytest.mark.parametrize(
        ("submit_error", "expected_reason"),
        [
            (RuntimeError("operator not dispatchable: state=leased"), "operator_busy"),
            (RuntimeError("operator not dispatchable: state=cooldown"), "operator_unavailable"),
        ],
    )
    def test_frozen_classified_rejection_remains_retryable_by_ranked_scheduler(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
        submit_error,
        expected_reason,
    ):
        """Busy/unavailable races stay ready for the next ranked-candidate tick."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)
        sample_graph["nodes"][0]["physical_candidates"] = [
            {"rank": 1, "operator_id": "test-operator-1"},
            {"rank": 2, "operator_id": "test-operator-2"},
        ]
        graph_path = tmp_harness / "sprints" / "scheduler-runtime.json"
        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch("operator_runtime.submit", side_effect=submit_error):
            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "submit_rejected"
        assert result["operator_submit_reason"] == expected_reason
        assert "blocking_reason" not in result
        assert "operator_submit_fallback" not in result
        assert sample_graph["nodes"][0]["status"] == "ready"
        mock_tmux.assert_not_called()

    @pytest.mark.parametrize(
        ("graph_contract", "submit_error"),
        [
            ("frozen_candidates", RuntimeError("operator submit transport broke")),
            ("runtime_projection", ValueError("malformed submit response")),
        ],
    )
    def test_frozen_dispatch_fails_closed_on_unclassified_submit_error(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
        graph_contract,
        submit_error,
    ):
        """A planner-frozen node must never bypass operatord lease ownership."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)
        monkeypatch.setattr(mtr, "_plan_validator_launch_refusal", lambda *_args, **_kwargs: None)
        if graph_contract == "frozen_candidates":
            sample_graph["nodes"][0]["physical_candidates"] = [
                {"rank": 1, "operator_id": "test-operator-1"},
                {"rank": 2, "operator_id": "test-operator-2"},
            ]
        else:
            sample_graph["schema_version"] = "solar.scheduler_runtime_projection.v1"

        graph_path = tmp_harness / "sprints" / "scheduler-runtime.json"
        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["save_graph"], \
             patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch.object(mtr, "runner_script") as mock_runner, \
             mock.patch("operator_runtime.submit", side_effect=submit_error):
            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "submit_rejected"
        assert result["submit_mode"] == "operatord"
        assert result["dispatch_mode"] == "operatord"
        assert result["operator_submit_reason"] == "operator_submit_failed"
        assert result["blocking_reason"].startswith(
            f"operator_submit_failed:{type(submit_error).__name__}:"
        )
        assert "operator_submit_fallback" not in result
        assert "lease_id" not in result
        assert "inbox_path" not in result
        assert sample_graph["nodes"][0]["status"] == "needs_human_review"
        assert sample_graph["nodes"][0]["blocking_reason"] == result["blocking_reason"]
        assert sample_graph["node_results"]["N1"]["blocking_reason"] == result["blocking_reason"]
        on_disk = json.loads(
            (tmp_harness / "run" / "multi-task" / result["id"] / "status.json").read_text()
        )
        assert on_disk["blocking_reason"] == result["blocking_reason"]
        mock_tmux.assert_not_called()
        mock_runner.assert_not_called()

    def test_schedule_once_persists_frozen_candidate_preflight_queue(
        self,
        tmp_harness,
        monkeypatch,
    ):
        """Candidate exhaustion is inspectable and remains retryable."""
        graph_path = tmp_harness / "sprints" / "frozen.task_graph.json"
        node = {
            "id": "N1",
            "status": "pending",
            "physical_candidates": [
                {"rank": 1, "operator_id": "planner-primary"},
                {"rank": 2, "operator_id": "planner-fallback"},
            ],
        }
        graph = {
            "schema_version": "solar.scheduler_runtime_projection.v1",
            "sprint_id": "frozen",
            "runtime_state_filename": "frozen.task_graph_state.json",
            "nodes": [node],
        }
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        args = types.SimpleNamespace(
            graph=[str(graph_path)],
            max_workers=1,
            memory_reserve_gb=0,
            cooldown_sec=0,
            quota_backoff_sec=0,
            dry_run=False,
            profile="",
            model="",
            backend="",
        )
        monkeypatch.setattr(mtr, "AUTO_ADVANCE_ENABLED", False)
        monkeypatch.setattr(mtr, "graph_files", lambda _value: [graph_path])
        monkeypatch.setattr(mtr, "load_graph", lambda _path: graph)
        monkeypatch.setattr(mtr, "recover_quota_failed_nodes", lambda *_args: 0)
        monkeypatch.setattr(mtr, "launch_guard", lambda *_args: {"ok": True})
        monkeypatch.setattr(mtr, "active_tasks", lambda: [])
        monkeypatch.setattr(mtr, "active_parallel_counts", lambda _rows: {})
        monkeypatch.setattr(mtr, "capability_summary", lambda: {})
        monkeypatch.setattr(mtr, "status_summary_for_graph", lambda _path: {})
        monkeypatch.setattr(mtr, "ready_nodes", lambda _graph: [dict(node)])
        monkeypatch.setattr(mtr, "_plan_validator_launch_refusal", lambda *_args: None)
        monkeypatch.setattr(
            mtr,
            "select_profile",
            mock.Mock(side_effect=ValueError("frozen_physical_candidates_unavailable:planner-primary=busy")),
        )
        monkeypatch.setattr(mtr, "list_harness_panes", lambda: [])
        monkeypatch.setattr(mtr, "recent_dispatch_rows", lambda: [])

        result = mtr.schedule_once(args)

        assert result["skipped"][0]["reason"] == "frozen_scheduler_preflight_unavailable"
        assert Path(result["skipped"][0]["failure_record"]).is_file()
        state = json.loads((tmp_harness / "sprints" / "frozen.task_graph_state.json").read_text())
        queued = state["node_results"]["N1"]
        assert queued["status"] == "queued"
        assert queued["blocking_reason"].startswith("frozen_scheduler_preflight_unavailable:")

    def test_launch_persists_scheduler_input_verification_refusal(
        self,
        tmp_harness,
        sample_node,
        sample_graph,
        monkeypatch,
    ):
        graph_path = tmp_harness / "sprints" / "refused.task_graph.json"
        monkeypatch.setattr(
            mtr,
            "_plan_validator_launch_refusal",
            lambda *_args: {
                "reason": "scheduler_input_dispatch_refused",
                "errors": ["SCHEDULER_RUNTIME_PROJECTION_TAMPERED"],
            },
        )

        result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "plan_validator_dispatch_refused"
        record_path = Path(result["failure_record"])
        assert record_path.is_file()
        record = json.loads(record_path.read_text())
        assert record["reason"] == "scheduler_input_dispatch_refused"
        assert record["errors"] == ["SCHEDULER_RUNTIME_PROJECTION_TAMPERED"]

    def test_frozen_quota_recovery_retries_candidates_without_legacy_profile(
        self,
        tmp_harness,
        monkeypatch,
    ):
        graph_path = tmp_harness / "sprints" / "retry.task_graph.json"
        graph = {
            "schema_version": "solar.scheduler_runtime_projection.v1",
            "sprint_id": "retry",
            "runtime_state_filename": "retry.task_graph_state.json",
            "nodes": [{
                "id": "N1",
                "status": "failed",
                "dispatch_id": "dispatch-1",
                "preferred_profile": "legacy-escape",
                "physical_candidates": [
                    {"rank": 1, "operator_id": "planner-primary"},
                    {"rank": 2, "operator_id": "planner-fallback"},
                ],
                "failure_policy": {"max_attempts": 2, "on_exhausted": "block_dependents"},
                "execution_attempt": {"sequence": 1, "task_id": "dispatch-1"},
            }],
        }
        monkeypatch.setattr(mtr, "output_log_failure_kind", lambda _task_id: "quota_exhausted")
        monkeypatch.setattr(
            __import__("scheduler_input"),
            "verify_runtime_projection",
            lambda *_args, **_kwargs: {"ok": True, "errors": []},
        )
        monkeypatch.setattr(
            mtr,
            "load_profiles",
            mock.Mock(side_effect=AssertionError("legacy profile ladder must not be consulted")),
        )

        changed = mtr.recover_quota_failed_nodes(graph_path, graph)

        assert changed == 1
        assert graph["nodes"][0]["status"] == "pending"
        assert graph["nodes"][0]["preferred_profile"] == "legacy-escape"
        assert graph["nodes"][0]["execution_attempt"]["sequence"] == 1
        mtr.load_profiles.assert_not_called()

    def test_frozen_quota_recovery_stops_at_planner_attempt_budget(
        self,
        tmp_harness,
        monkeypatch,
    ):
        graph_path = tmp_harness / "sprints" / "exhausted.task_graph.json"
        graph = {
            "schema_version": "solar.scheduler_runtime_projection.v1",
            "sprint_id": "exhausted",
            "runtime_state_filename": "exhausted.task_graph_state.json",
            "nodes": [{
                "id": "N1",
                "status": "failed",
                "dispatch_id": "dispatch-1",
                "physical_candidates": [{"rank": 1, "operator_id": "planner-primary"}],
                "failure_policy": {"max_attempts": 1, "on_exhausted": "block_dependents"},
                "execution_attempt": {"sequence": 1, "task_id": "dispatch-1"},
            }],
        }
        monkeypatch.setattr(mtr, "output_log_failure_kind", lambda _task_id: "quota_exhausted")
        monkeypatch.setattr(
            __import__("scheduler_input"),
            "verify_runtime_projection",
            lambda *_args, **_kwargs: {"ok": True, "errors": []},
        )
        monkeypatch.setattr(
            mtr,
            "load_profiles",
            mock.Mock(side_effect=AssertionError("legacy profile ladder must not be consulted")),
        )

        changed = mtr.recover_quota_failed_nodes(graph_path, graph)

        assert changed == 1
        assert graph["nodes"][0]["status"] == "failed"
        exhausted = graph["nodes"][0]["failure_policy_exhausted"]
        assert exhausted["attempt"] == exhausted["max_attempts"] == 1
        assert exhausted["on_exhausted"] == "block_dependents"
        mtr.load_profiles.assert_not_called()

    def test_providerless_command_bridge_defaults_to_local_auth(self, monkeypatch):
        """Local Harness command bridges must not require a provider key_ref."""
        operator = {
            "operator_id": "autosci-literature-discover-worker",
            "backend": "command",
            "command": "python autosci_bridge.py run --action discover_literature",
            "enabled": True,
            "available": True,
        }
        monkeypatch.setattr(optime, "get_operator_runtime_state", lambda _operator_id: "idle")

        assert mtr.operator_dispatchable(operator) == (True, "ready")

    def test_external_provider_command_still_requires_key_ref(self, monkeypatch):
        """The local-bridge default must not admit an uncredentialed provider worker."""
        operator = {
            "operator_id": "external-provider-worker",
            "backend": "command",
            "provider": "openai",
            "command": "python provider_worker.py",
            "enabled": True,
            "available": True,
        }
        monkeypatch.setattr(optime, "get_operator_runtime_state", lambda _operator_id: "idle")

        assert mtr.operator_dispatchable(operator) == (False, "key_ref_missing")

    @pytest.mark.parametrize("state", ["leased", "running", "draining", "cooldown"])
    def test_non_dispatchable_operator_is_filtered_before_submit(self, monkeypatch, state):
        """Selection must not keep choosing a busy or cooling-down operator."""
        operator = {
            "operator_id": "test-operator-1",
            "enabled": True,
            "available": True,
            "auth_mode": "subscription",
        }
        monkeypatch.setattr(optime, "get_operator_runtime_state", lambda _operator_id: state)

        assert mtr.operator_dispatchable(operator) == (False, f"dynamic_state_{state}")

    def test_busy_operator_does_not_launch_duplicate_legacy_worker(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
    ):
        """A leased operator is pending capacity, not permission to duplicate work."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch.object(mtr, "runner_script", return_value=tmp_harness / "fake-runner.sh"), \
             mock.patch("operator_runtime.submit", side_effect=RuntimeError("operator not dispatchable: state=leased")):

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "submit_rejected"
        assert result["operator_submit_reason"] == "operator_busy"
        assert "operator_submit_fallback" not in result
        assert "operator_submit_error" in result
        assert "leased" in result["operator_submit_error"]
        mock_tmux.assert_not_called()

    def test_unknown_operator_fails_closed_without_legacy_dispatch(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
    ):
        """An admission failure cannot bypass the lease path through legacy tmux."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch.object(mtr, "runner_script", return_value=tmp_harness / "fake-runner.sh"), \
             mock.patch("operator_runtime.submit", side_effect=ValueError("Unknown operator")):

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "submit_rejected"
        assert result["operator_submit_reason"] == "operator_admission_failed"
        assert "operator_submit_fallback" not in result
        mock_tmux.assert_not_called()


# ---------------------------------------------------------------------------
# Test: result timeout
# ---------------------------------------------------------------------------

class TestSubmitPathResultTimeout:
    def test_timeout_boundary_preserves_exact_terminal_result(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        """A result landing at the timeout boundary must win over stale timeout state."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 1)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"
        result_data = {
            "task_id": fake_submit_result["task_id"],
            "operator_id": fake_submit_result["operator_id"],
            "sprint_id": sample_graph["sprint_id"],
            "node_id": sample_node["id"],
            "status": "completed",
            "exit_code": 0,
        }

        def fake_submit(envelope):
            result_data["task_id"] = envelope["task_id"]
            result_path = mtr._operator_result_path(envelope["operator_id"], envelope["task_id"])
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(result_data), encoding="utf-8")
            return fake_submit_result

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", side_effect=fake_submit), \
             mock.patch.object(mtr, "_poll_operator_result", return_value=None):
            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert result["operator_result"] == result_data

    def test_status_set_to_result_timeout_when_no_result_appears(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        """When result.json does not appear within timeout, status → result_timeout."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 1)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_POLL_INTERVAL_SEC", 0.05)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", return_value=fake_submit_result):

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "result_timeout"

    def test_completed_when_result_appears_with_exit_zero(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        fake_submit_result,
        monkeypatch,
    ):
        """When result.json appears with exit_code=0, status → completed."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 5)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_POLL_INTERVAL_SEC", 0.05)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        result_data = {
            "task_id": "mt-task-1",
            "operator_id": "test-operator-1",
            "status": "completed",
            "exit_code": 0,
        }

        def mock_submit(envelope):
            op_id = envelope["operator_id"]
            disp_id = envelope["task_id"]
            result_dir = tmp_harness / "run" / "operator-results" / op_id / disp_id
            result_dir.mkdir(parents=True, exist_ok=True)
            (result_dir / "result.json").write_text(json.dumps(result_data), encoding="utf-8")
            return fake_submit_result

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit", side_effect=mock_submit):

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        assert result["status"] == "completed"
        assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# Test: fallback when submit should not be attempted
# ---------------------------------------------------------------------------

class TestSubmitPathFallback:
    def test_command_profile_without_physical_operator_keeps_profile_attribution(
        self,
        tmp_harness,
        sample_node,
        sample_graph,
        monkeypatch,
    ):
        """Command-backed Codex profiles without operator_id must not erase attribution as N/A."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        profile = {
            "name": "codex-evaluator",
            "role": "evaluator",
            "persona": "evaluator",
            "backend": "command",
            "model": "gpt-5.5",
            "approval_mode": "default",
            "command": "python3 \"$HARNESS_DIR/tools/codex_operator.py\"",
            "operator_fallback_reason": "",
        }
        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile)
        with patches["select_profile"], \
             mock.patch.object(
                 mtr,
                 "capability_for_profile",
                 return_value={"status": "ok", "provider": "openai"},
             ), \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit") as mock_submit:

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args(), dry_run=True)

        mock_submit.assert_not_called()
        assert result["status"] == "dry_run"
        assert result["operator_id"] == "codex-evaluator"
        assert result["operator_vendor"] == "openai"
        assert result["operator_model"] == "gpt-5.5"
        assert result["dispatch_mode"] == "multi_task_command"

    def test_legacy_path_when_no_operator_id(
        self,
        tmp_harness,
        sample_node,
        profile_without_operator,
        sample_graph,
        monkeypatch,
    ):
        """No operator_id in profile → legacy path, no submit attempt."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_without_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch.object(mtr, "runner_script", return_value=tmp_harness / "fake-runner.sh"), \
             mock.patch("operator_runtime.submit") as mock_submit:

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        mock_submit.assert_not_called()
        mock_tmux.assert_called_once()
        assert result.get("submit_mode") != "operatord"

    def test_legacy_path_when_operator_id_is_N_A(
        self,
        tmp_harness,
        sample_node,
        sample_graph,
        monkeypatch,
    ):
        """operator_id='N/A' → legacy path, no submit attempt."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        profile_na = {
            "name": "builder",
            "role": "builder",
            "persona": "builder",
            "backend": "claude-cli",
            "model": "sonnet",
            "approval_mode": "bypassPermissions",
            "operator_id": "N/A",
            "operator_fallback_reason": "",
        }

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_na)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch.object(mtr, "runner_script", return_value=tmp_harness / "fake-runner.sh"), \
             mock.patch("operator_runtime.submit") as mock_submit:

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        mock_submit.assert_not_called()
        mock_tmux.assert_called_once()

    def test_legacy_path_when_feature_flag_disabled(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
    ):
        """OPERATORD_SUBMIT_ENABLED=False → legacy path even with a valid operator_id."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", False)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch.object(mtr, "tmux_start") as mock_tmux, \
             mock.patch.object(mtr, "runner_script", return_value=tmp_harness / "fake-runner.sh"), \
             mock.patch("operator_runtime.submit") as mock_submit:

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args())

        mock_submit.assert_not_called()
        mock_tmux.assert_called_once()
        assert result.get("submit_mode") != "operatord"

    def test_dry_run_skips_submit_path(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
    ):
        """dry_run=True must not attempt submit even when flag is enabled."""
        monkeypatch.setattr(mtr, "OPERATORD_SUBMIT_ENABLED", True)
        monkeypatch.setattr(mtr, "OPERATORD_RESULT_TIMEOUT_SEC", 0)

        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"

        patches = _base_patches(profile_with_operator)
        with patches["select_profile"], patches["capability_for_profile"], \
             patches["build_dispatch_text"], patches["set_node_status"], \
             patches["save_graph"], patches["set_last_launch"], \
             mock.patch("operator_runtime.submit") as mock_submit:

            result = mtr.launch_node(graph_path, sample_graph, sample_node, _make_args(), dry_run=True)

        mock_submit.assert_not_called()
        assert result["status"] == "dry_run"


class TestAutoAdvanceStatusSync:
    def test_syncs_parent_status_cache_after_reconcile(self, tmp_harness, monkeypatch):
        graph_path = tmp_harness / "sprints" / "sprint-test-submit-001.task_graph.json"
        graph = {"sprint_id": "sprint-test-submit-001", "nodes": [{"id": "N1", "status": "passed"}]}
        saved: list[tuple[str, dict]] = []
        sync_calls: list[dict] = []

        fake_gnd = types.SimpleNamespace(
            dispatch_node_evals=lambda path: {"dispatched": [], "terminalized": []},
            load_graph=lambda path: graph,
            _reconcile_existing_dispatches=lambda graph_arg, path: [
                {"node": "N1", "status": "passed", "reason": "eval_pass"}
            ],
            save_graph=lambda path, graph_arg: saved.append((path, graph_arg)),
        )

        def fake_sync_status_cache(graph_arg, path, *, actor, event):
            sync_calls.append({"graph": graph_arg, "path": path, "actor": actor, "event": event})
            return {"ok": True, "updated": True, "reason": "parent_passed"}

        fake_graph_scheduler = types.SimpleNamespace(
            sync_status_cache_from_graph=fake_sync_status_cache,
        )
        monkeypatch.setitem(sys.modules, "graph_node_dispatcher", fake_gnd)
        monkeypatch.setitem(sys.modules, "graph_scheduler", fake_graph_scheduler)

        result = mtr._advance_graph(graph_path)

        assert saved == [(str(graph_path), graph)]
        assert result["reconciled"] == [{"node": "N1", "status": "passed", "reason": "eval_pass"}]
        assert result["status_sync"] == {"ok": True, "updated": True, "reason": "parent_passed"}
        assert sync_calls == [{
            "graph": graph,
            "path": str(graph_path),
            "actor": "multi_task_runner",
            "event": "multi_task_auto_advance_reconciled",
        }]
