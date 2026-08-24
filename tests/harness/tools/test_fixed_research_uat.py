"""Deterministic checks for the shipped fixed-research UAT driver.

These checks exercise preflight and durable-policy validation only.  They do
not claim a live Codex research run or fabricate provider output.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import urllib.error
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "harness"
SPEC = importlib.util.spec_from_file_location("fixed_research_uat", HARNESS / "tools/fixed_research_uat.py")
assert SPEC and SPEC.loader
uat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uat)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_uat_lock_rejects_a_live_owner(tmp_path: Path) -> None:
    lock = uat._acquire_lock(tmp_path)
    try:
        with pytest.raises(uat.UATError, match="already locked"):
            uat._acquire_lock(tmp_path)
    finally:
        lock.unlink(missing_ok=True)


def test_uat_lock_reclaims_a_dead_legacy_owner_after_restart(tmp_path: Path) -> None:
    lock = tmp_path / ".fixed-research-uat.lock"
    lock.write_text("pid=999999999 created_at=2000-01-01T00:00:00Z\n", encoding="utf-8")

    acquired = uat._acquire_lock(tmp_path)
    try:
        recorded = uat._parse_lock(acquired)
        assert recorded["pid"] == str(os.getpid())
        assert recorded["boot_id"]
        assert recorded["pid_namespace"].startswith("pid:")
        assert recorded["start_ticks"].isdigit()
    finally:
        acquired.unlink(missing_ok=True)


def test_uat_lock_reclaims_reused_pid_identity(tmp_path: Path) -> None:
    identity = uat._process_lock_identity(os.getpid())
    lock = tmp_path / ".fixed-research-uat.lock"
    lock.write_text(
        " ".join(
            [
                f"pid={identity['pid']}",
                "created_at=2000-01-01T00:00:00Z",
                f"boot_id={identity['boot_id']}",
                f"pid_namespace={identity['pid_namespace']}",
                f"start_ticks={int(identity['start_ticks']) + 1}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    acquired = uat._acquire_lock(tmp_path)
    try:
        assert uat._parse_lock(acquired)["start_ticks"] == identity["start_ticks"]
    finally:
        acquired.unlink(missing_ok=True)


def test_runtime_environment_records_explicit_policy_without_ambient_api_keys(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    source_pack = tmp_path / "source-pack"
    authority = tmp_path / "authority"
    codex_home = tmp_path / "codex"
    env = uat._runtime_env(
        runtime_harness=runtime,
        evidence_root=tmp_path / "evidence",
        workspace_root=tmp_path / "workspace",
        source_pack=source_pack,
        authority_root=authority,
        codex_home=codex_home,
        experiment_policy="evidence_lineage_integrity_v1",
        policy_actor="user",
        policy_statement="no need to pause at B4 no pauses",
    )
    assert env["SOLAR_RESEARCH_EXECUTION_PROFILE"] == "part_a_plus_poc"
    assert env["SOLAR_RESEARCH_EXPERIMENT_POLICY"] == "evidence_lineage_integrity_v1"
    assert env["SOLAR_RESEARCH_EXPERIMENT_POLICY_ACTOR"] == "user"
    assert env["SOLAR_RESEARCH_EXPERIMENT_POLICY_STATEMENT"] == "no need to pause at B4 no pauses"
    assert all(key not in env for key in uat.SECRET_ENV_KEYS)


def test_driver_rehashes_and_rejects_changed_one_shot_policy(tmp_path: Path) -> None:
    sid = "fixed-driver-policy"
    sprints = tmp_path / "sprints"
    graph_path = sprints / f"{sid}.task_graph.json"
    policy_path = (
        sprints
        / sid
        / "workdir/artifacts/research_evidence_to_poc/poc/approval/experiment_policy_authorization.json"
    )
    policy_path.parent.mkdir(parents=True)
    policy = {
        "schema": "solar.fixed_research.experiment_policy_authorization.v1",
        "policy_id": "evidence_lineage_integrity_v1",
        "sprint_id": sid,
        "actor": "user",
        "statement": "no need to pause at B4 no pauses",
        "benchmark_policy": {
            "benchmark_id": "evidence-lineage-integrity-v1",
            "runner": "harness/tools/fixed_research_benchmark.py",
            "network": "none",
            "timeout_max_seconds": 60,
            "capabilities": ["execute:fixed_evidence_lineage_benchmark", "network:none"],
        },
    }
    policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
    graph = {
        "sprint_id": sid,
        "experiment_policy": {
            "mode": "policy_preauthorized",
            "policy_id": "evidence_lineage_integrity_v1",
            "path": str(policy_path.relative_to(sprints / sid / "workdir")),
            "sha256": _sha(policy_path.read_bytes()),
        },
    }
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph) + "\n", encoding="utf-8")
    accepted = uat._one_shot_policy(
        graph_path,
        graph,
        actor="user",
        statement="no need to pause at B4 no pauses",
    )
    assert accepted["sha256"] == graph["experiment_policy"]["sha256"]

    policy["benchmark_policy"]["network"] = "any"
    policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
    with pytest.raises(uat.UATError, match="hash binding"):
        uat._one_shot_policy(
            graph_path,
            graph,
            actor="user",
            statement="no need to pause at B4 no pauses",
        )


def test_driver_public_command_is_solar_harness_graph_dispatch() -> None:
    assert uat._shell_command("graph-dispatch", "dispatch-ready", "--max-parallel", "1") == [
        "bash",
        str(HARNESS / "solar-harness.sh"),
        "graph-dispatch",
        "dispatch-ready",
        "--max-parallel",
        "1",
    ]


def test_codex_preflight_resolves_normal_package_manager_symlink_and_hashes_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "lib/codex.js"
    target.parent.mkdir(parents=True)
    target.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    target.chmod(0o755)
    launcher = tmp_path / "bin/codex"
    launcher.parent.mkdir()
    try:
        launcher.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth = codex_home / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)

    result = uat._codex_preflight(launcher, codex_home)

    assert result["launcher"] == str(launcher)
    assert result["binary"] == str(target.resolve())
    assert result["binary_sha256"] == _sha(target.read_bytes())
    assert result["credential_contents_recorded"] is False


def test_dashboard_driver_waits_for_attributed_fixed_graph_without_calling_intake(tmp_path: Path) -> None:
    request_id = "dashboard-request-001"
    sid = "dashboard-fixed-sprint"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph_path = sprints / f"{sid}.task_graph.json"
    graph_path.write_text(json.dumps({
        "sprint_id": sid,
        "workflow_contract_id": uat.WORKFLOW_ID,
        "execution_profile": {"kind": "part_a_plus_poc", "part_b": "enabled"},
        "execution_mode": "single_threaded",
        "codex_execution": {"max_parallel": 1},
        "nodes": [{"id": node_id} for node_id in (*uat.PART_A_NODE_IDS, *uat.PART_B_NODE_IDS)],
    }), encoding="utf-8")
    (sprints / f"{sid}.status.json").write_text(json.dumps({
        "sprint_id": sid,
        "request_id": request_id,
    }), encoding="utf-8")

    observed = uat._wait_for_dashboard_graph(
        sprints=sprints,
        request_id=request_id,
        timeout_seconds=1,
        poll_seconds=0.01,
    )

    assert observed == graph_path


def test_dashboard_driver_rejects_wrong_workflow_attribution(tmp_path: Path) -> None:
    request_id = "dashboard-request-wrong"
    sid = "dashboard-wrong-sprint"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    (sprints / f"{sid}.task_graph.json").write_text(json.dumps({
        "sprint_id": sid,
        "workflow_contract_id": "research.autosci.v1",
        "execution_profile": {"kind": "part_a_plus_poc", "part_b": "enabled"},
        "execution_mode": "single_threaded",
        "codex_execution": {"max_parallel": 1},
        "nodes": [{"id": node_id} for node_id in (*uat.PART_A_NODE_IDS, *uat.PART_B_NODE_IDS)],
    }), encoding="utf-8")
    (sprints / f"{sid}.status.json").write_text(json.dumps({
        "sprint_id": sid,
        "request_id": request_id,
    }), encoding="utf-8")

    with pytest.raises(uat.UATError, match="exact fixed research workflow"):
        uat._wait_for_dashboard_graph(
            sprints=sprints,
            request_id=request_id,
            timeout_seconds=1,
            poll_seconds=0.01,
        )


def test_dashboard_surface_capture_retries_a_transient_deliverables_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int]] = []
    observed_tokens: list[str | None] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return b'{"ok":true}'

    def urlopen(request, *, timeout: int):
        url = request.full_url
        calls.append((url, timeout))
        observed_tokens.append(request.get_header("X-solar-token"))
        if url.endswith("/deliverables") and sum(item[0] == url for item in calls) == 1:
            raise TimeoutError("slow deliverables scan")
        return Response()

    monkeypatch.setattr(uat.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(uat.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("SOLAR_AUTH_TOKEN", "runtime-container-token")

    rows = uat._capture_dashboard_surfaces(
        base_url="http://127.0.0.1:8765",
        sprint_id="fixed-dashboard-sprint",
        output_dir=tmp_path / "dashboard",
    )

    assert [row["label"] for row in rows] == ["projection", "events", "deliverables"]
    assert len([url for url, _timeout in calls if url.endswith("/deliverables")]) == 2
    assert {timeout for _url, timeout in calls} == {uat.DASHBOARD_CAPTURE_TIMEOUT_SECONDS}
    assert set(observed_tokens) == {"runtime-container-token"}


def test_dashboard_surface_capture_fails_closed_after_bounded_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(_request, *, timeout: int):
        assert timeout == uat.DASHBOARD_CAPTURE_TIMEOUT_SECONDS
        raise urllib.error.URLError("dashboard unavailable")

    monkeypatch.setattr(uat.urllib.request, "urlopen", unavailable)
    monkeypatch.setattr(uat.time, "sleep", lambda _seconds: None)

    with pytest.raises(uat.UATError, match="projection.*after 2 attempts"):
        uat._capture_dashboard_surfaces(
            base_url="http://127.0.0.1:8765",
            sprint_id="fixed-dashboard-sprint",
            output_dir=tmp_path / "dashboard",
        )


def test_real_intake_output_is_attributable_by_the_real_dashboard_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seam check: the producer of the attribution and its consumer must agree.

    The two tests above construct ``status.json`` by hand, so they pass even if
    nothing ever writes ``request_id``.  That is how a real dashboard run could
    reach ``dashboard-to-final`` and poll until timeout: the status server
    exported ``SOLAR_INTAKE_REQUEST_ID`` and no downstream component consumed
    it.  This check runs the real intake and feeds its real output to the real
    reader, so the seam cannot silently come apart again.
    """
    import sys

    harness_lib = str(HARNESS / "lib")
    if harness_lib not in sys.path:
        sys.path.insert(0, harness_lib)
    import workflow_intake as wi

    request_id = "webapp-intake-6f1c0a72-seam"
    monkeypatch.setenv("SOLAR_INTAKE_REQUEST_ID", request_id)
    created = wi.create_contract_sprint(
        workflow_id=uat.WORKFLOW_ID,
        request="Research RAG evaluation methods, then design and run the PoC benchmark.",
        workspace_root=str(tmp_path / "ws"),
        inputs={
            "execution_profile": "part_a_plus_poc",
            "acquisition_mode": "live_search",
            "retrieval_policy": "public_bibliographic_no_key_v1",
        },
        sprints_dir=tmp_path / "sprints",
        workflows_dir=HARNESS / "config" / "workflows",
    )

    observed = uat._wait_for_dashboard_graph(
        sprints=tmp_path / "sprints",
        request_id=request_id,
        timeout_seconds=1,
        poll_seconds=0.01,
    )

    assert observed == tmp_path / "sprints" / f"{created['sprint_id']}.task_graph.json"


def test_real_intake_is_not_attributable_to_a_different_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    harness_lib = str(HARNESS / "lib")
    if harness_lib not in sys.path:
        sys.path.insert(0, harness_lib)
    import workflow_intake as wi

    monkeypatch.setenv("SOLAR_INTAKE_REQUEST_ID", "webapp-intake-owner")
    wi.create_contract_sprint(
        workflow_id=uat.WORKFLOW_ID,
        request="Research RAG evaluation methods, then design and run the PoC benchmark.",
        workspace_root=str(tmp_path / "ws"),
        inputs={
            "execution_profile": "part_a_plus_poc",
            "acquisition_mode": "live_search",
            "retrieval_policy": "public_bibliographic_no_key_v1",
        },
        sprints_dir=tmp_path / "sprints",
        workflows_dir=HARNESS / "config" / "workflows",
    )

    with pytest.raises(uat.UATError, match="timed out waiting for dashboard request"):
        uat._wait_for_dashboard_graph(
            sprints=tmp_path / "sprints",
            request_id="webapp-intake-someone-else",
            timeout_seconds=1,
            poll_seconds=0.01,
        )


def test_dashboard_runtime_env_scopes_the_intent_gateway_to_the_run(tmp_path: Path) -> None:
    """The dispatch-time specialization guard resolves the expected binding
    manifest from SOLAR_INTENT_GATEWAY_DIR.  A dashboard-created sprint is
    bound under the run's own gateway root, so omitting this variable makes
    the guard read the default installed gateway and reject a valid binding
    as fixed_research_intent_binding_evidence_invalid.
    """
    evidence_root = tmp_path / "evidence"
    env = uat._dashboard_runtime_env(
        runtime_harness=tmp_path / "harness",
        evidence_root=evidence_root,
        sprints=evidence_root / "sprints",
        codex_home=tmp_path / "codex",
    )

    assert env["SOLAR_INTENT_GATEWAY_DIR"] == str(evidence_root / "intents")
    assert env["HARNESS_SPRINTS_DIR"] == str(evidence_root / "sprints")
    assert env["SOLAR_HARNESS_SPRINTS_DIR"] == str(evidence_root / "sprints")
    assert env["SOLAR_CODEX_OPERATOR_STATE_ROOT"] == str(evidence_root / "runtime/codex-state")


def test_dashboard_runtime_env_drops_ambient_api_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in sorted(uat.SECRET_ENV_KEYS):
        monkeypatch.setenv(key, "must-not-propagate")
    env = uat._dashboard_runtime_env(
        runtime_harness=tmp_path / "harness",
        evidence_root=tmp_path / "evidence",
        sprints=tmp_path / "evidence" / "sprints",
        codex_home=tmp_path / "codex",
    )
    for key in uat.SECRET_ENV_KEYS:
        assert key not in env


def test_dashboard_runtime_env_omits_intake_only_variables(tmp_path: Path) -> None:
    """Intake already ran inside the status server.  Re-supplying the intake
    source-pack authority here would let the driver appear to choose inputs it
    must not choose."""
    env = uat._dashboard_runtime_env(
        runtime_harness=tmp_path / "harness",
        evidence_root=tmp_path / "evidence",
        sprints=tmp_path / "evidence" / "sprints",
        codex_home=tmp_path / "codex",
    )
    for key in (
        "SOLAR_RESEARCH_SOURCE_PACK",
        "SOLAR_RESEARCH_SOURCE_PACK_ROOT",
        "SOLAR_INTAKE_WORKFLOW_ID",
    ):
        assert key not in env


def test_waiting_for_builder_eval_tick_is_treated_as_transient() -> None:
    """`graph-dispatch` exits 2 whenever its payload carries ok=false, and in a
    single-threaded run the eval pass routinely finds its only candidate still
    waiting on the builder that produces the artifacts it grades.  Treating that
    tick as fatal aborts a healthy run partway through Part A."""
    payload = json.dumps({
        "ok": False,
        "sprint_id": "sprint-x",
        "dispatched": [],
        "skipped": [{"node": "source_validation", "reason": "deterministic_gate_waiting_for_builder", "gate_kind": "none"}],
        "terminalized": [],
    })
    assert uat._is_transient_dispatch_noop(payload) is True


def test_specialization_guard_rejection_is_never_transient() -> None:
    """The real r2 failure payload.  A guard rejection must keep aborting the
    run; tolerating it would let a mis-bound graph run to a false pass."""
    payload = json.dumps({
        "ok": False,
        "reason": "fixed_research_specialization_guard_failed",
        "errors": ["fixed_research_intent_binding_evidence_invalid"],
        "graph": "/tmp/x.task_graph.json",
        "enqueue": {},
        "drain": {},
    })
    assert uat._is_transient_dispatch_noop(payload) is False


def test_unknown_skip_reason_is_never_transient() -> None:
    """The allowlist is deliberately narrow: a skip reason nobody has classified
    must surface rather than be polled over silently."""
    payload = json.dumps({
        "ok": False,
        "dispatched": [],
        "skipped": [{"node": "experiment_run", "reason": "some_new_unclassified_reason"}],
        "terminalized": [],
    })
    assert uat._is_transient_dispatch_noop(payload) is False


def test_tick_that_moved_the_graph_is_never_transient() -> None:
    payload = json.dumps({
        "ok": False,
        "dispatched": ["source_validation"],
        "skipped": [{"node": "x", "reason": "deterministic_gate_waiting_for_builder"}],
        "terminalized": [],
    })
    assert uat._is_transient_dispatch_noop(payload) is False

    terminalized = json.dumps({
        "ok": False,
        "dispatched": [],
        "skipped": [{"node": "x", "reason": "deterministic_gate_waiting_for_builder"}],
        "terminalized": ["final_delivery"],
    })
    assert uat._is_transient_dispatch_noop(terminalized) is False


def test_empty_or_unparseable_dispatch_output_is_never_transient() -> None:
    for payload in ("", "   ", "not json", json.dumps({"ok": False, "skipped": []}), json.dumps({"ok": True})):
        assert uat._is_transient_dispatch_noop(payload) is False


def test_graph_node_statuses_read_the_runtime_state_plane(tmp_path, monkeypatch):
    """The boundary detector must see statuses the dispatcher persists.

    save_graph writes a spec-only graph and keeps per-node status in a state
    sidecar that load_graph re-attaches. Reading the raw JSON reports every
    node pending forever, which made start-to-final poll to its own timeout
    after a 15/15 completion.
    """
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(
        "graph_scheduler", uat.SOURCE_HARNESS / "lib" / "graph_scheduler.py"
    )
    gs = _ilu.module_from_spec(spec)
    import sys as _sys
    _sys.modules.setdefault("graph_scheduler", gs)
    spec.loader.exec_module(gs)

    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph_path = sprints / "uat-runtime-status-test.task_graph.json"
    graph = {
        "sprint_id": "uat-runtime-status-test",
        "nodes": [
            {"id": "seed_fetch", "status": "passed", "depends_on": []},
            {"id": "source_discovery", "status": "pending", "depends_on": ["seed_fetch"]},
        ],
        # The dispatcher records status here; save_graph moves it into the
        # state sidecar and strips it from the persisted spec payload.
        "node_results": {"seed_fetch": {"status": "passed"}},
    }
    gs.save_graph(graph_path, graph)
    raw = uat._read_json(graph_path)
    # The spec-only payload must not carry status, or this test is vacuous.
    assert all("status" not in node for node in raw["nodes"])
    statuses = uat._graph_node_statuses(graph_path, raw)
    assert statuses["seed_fetch"] == "passed"
    assert statuses["source_discovery"] == "pending"


def test_final_boundary_reads_the_contracts_delivery_paths(tmp_path):
    """_final_reached must look where final_delivery actually writes.

    The stale poc/final spelling was dead code while the boundary detector
    could not see completed graphs; the first run that reached the boundary
    failed on a path B7 never wrote to. The expected path comes from the
    contract's declared outputs, so the two cannot drift silently again.
    """
    import inspect
    contract = json.loads(
        (uat.SOURCE_HARNESS / "config/workflows/research.evidence_to_poc.v1.workflow.json").read_text(encoding="utf-8")
    )
    stage = next(item for item in contract["stages"] if item["id"] == "final_delivery")
    declared_json = next(
        str(item["path"]) for item in stage["outputs"] if str(item["path"]).endswith("final_delivery.json")
    )
    source = inspect.getsource(uat._final_reached)
    declared_dir = declared_json.rsplit("/", 1)[0]
    assert f'"workdir/{declared_dir}"' in source
    code_lines = [line for line in source.splitlines() if not line.strip().startswith("#")]
    assert not any("poc/final" in line for line in code_lines)
