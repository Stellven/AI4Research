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

    def test_falls_back_to_legacy_on_submit_value_error(
        self,
        tmp_harness,
        sample_node,
        profile_with_operator,
        sample_graph,
        monkeypatch,
    ):
        """ValueError from submit (e.g. unknown operator) → falls back to legacy."""
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

        assert result["operator_submit_fallback"] == "legacy"
        mock_tmux.assert_called_once()


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
