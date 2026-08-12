from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from journey_runner import base_env, prepare_isolated_harness, python_executable


BATCH_ID = "NT-dag-trace"
L2_DAG = "Foundation :: DAG and Agent Organization (AFlow / MCTS / ADAS)"
L2_TRACE = "Foundation :: Trace Graph Management"
L2_SEARCH = "Vertical :: Execution Trace Search & Inspection"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_from_stdout(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        for line in reversed(stripped.splitlines()):
            line = line.strip()
            if line.startswith("{") or line.startswith("["):
                return json.loads(line)
    return {}


def _run_cmd(
    label: str,
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    evidence_dir: Path,
    timeout: int = 120,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    ended = datetime.now(timezone.utc).isoformat()
    command_dir = evidence_dir / "commands"
    command_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label)
    stdout_path = command_dir / f"{safe}.stdout.txt"
    stderr_path = command_dir / f"{safe}.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return {
        "label": label,
        "argv": argv,
        "command": " ".join(argv),
        "exit_code": completed.returncode,
        "started_at": started,
        "ended_at": ended,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_json": _json_from_stdout(completed.stdout),
        "stderr_tail": completed.stderr[-2000:],
    }


def _copy_artifact(src: Path, evidence_dir: Path) -> str:
    dst = evidence_dir / "artifacts" / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return str(dst)


def _copy_or_link_runtime_dep(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _scan_named_algorithm_hits(repo_root: Path) -> dict[str, list[str]]:
    roots = [repo_root / "harness" / "lib", repo_root / "harness" / "tools", repo_root / "core"]
    hits: dict[str, list[str]] = {"AFlow": [], "MCTS": [], "ADAS": []}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".py", ".ts", ".json", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in hits:
                if token.lower() in text.lower():
                    hits[token].append(str(path.relative_to(repo_root)))
    return hits


def _mark_node_with_production_scheduler(
    python: str,
    graph_path: Path,
    node_id: str,
    *,
    repo_root: Path,
    env: dict[str, str],
    evidence_dir: Path,
) -> dict[str, Any]:
    code = (
        "import json, sys; "
        "from pathlib import Path; "
        f"sys.path.insert(0, {str(repo_root / 'harness' / 'lib')!r}); "
        "import graph_scheduler as gs; "
        "p=Path(sys.argv[1]); "
        "g=gs.load_graph(p); "
        "r=gs.mark_node_result(g, sys.argv[2], 'passed', note='phase22_nt_dag_trace_verified'); "
        "gs.save_graph(p, g); "
        "print(json.dumps(r, ensure_ascii=False))"
    )
    return _run_cmd(
        f"mark-{node_id}-passed",
        [python, "-c", code, str(graph_path), node_id],
        cwd=repo_root,
        env=env,
        evidence_dir=evidence_dir,
    )


def _start_status_server(python: str, status_server: Path, env: dict[str, str], evidence_dir: Path) -> subprocess.Popen:
    code = (
        "import importlib.util, sys; "
        "from pathlib import Path; "
        "p=Path(sys.argv[1]); "
        "spec=importlib.util.spec_from_file_location('phase22_status_server', p); "
        "m=importlib.util.module_from_spec(spec); "
        "assert spec and spec.loader; "
        "spec.loader.exec_module(m); "
        "m.BIND_HOST='127.0.0.1'; "
        "m.PORT_RANGE=range(18730, 18740); "
        "m.main()"
    )
    server_dir = evidence_dir / "server"
    server_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [python, "-u", "-c", code, str(status_server)],
        stdout=(server_dir / "status-server.stdout.txt").open("w", encoding="utf-8"),
        stderr=(server_dir / "status-server.stderr.txt").open("w", encoding="utf-8"),
        cwd=str(status_server.parents[2]),
        env=env,
        text=True,
    )


def _query_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _result_record(
    *,
    run_id: str,
    repo_head: str,
    evidence_dir: Path,
    command_records: list[dict[str, Any]],
    l2_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "phase22.not_tested_worker_result.v1",
        "batch_id": BATCH_ID,
        "run_id": run_id,
        "repo_head": repo_head,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_root": str(evidence_dir),
        "command_records": command_records,
        "l2_results": l2_results,
    }


def test_p22_nt_dag_trace() -> None:
    repo_root = _repo_root()
    fixture_dir = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "not_tested" / "dag_trace"
    request = _read_json(fixture_dir / "request.json")
    workers = fixture_dir / "workers.json"
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    evidence_dir = repo_root / "outputs" / "phase22-not-tested" / BATCH_ID / run_id
    sandbox = repo_root / ".codex-tmp" / "homes" / BATCH_ID / run_id
    result_path = repo_root / ".codex-tmp" / "phase22-worker-results" / BATCH_ID / "result.json"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sandbox.mkdir(parents=True, exist_ok=True)

    python = str(python_executable(repo_root))
    harness_dir = prepare_isolated_harness(repo_root, sandbox)
    _copy_or_link_runtime_dep(repo_root / "harness" / "capability-capsules", harness_dir / "capability-capsules")
    sprints_dir = harness_dir / "sprints"
    sprints_dir.mkdir(parents=True, exist_ok=True)
    workspace = sandbox / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    env = base_env(repo_root, sandbox, allow_live=False)
    env.update(
        {
            "HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_DIR": str(harness_dir),
            "HARNESS_SPRINTS_DIR": str(sprints_dir),
            "SOLAR_BIND_HOST": "127.0.0.1",
            "SOLAR_REQUIRE_TOKEN": "0",
            "PYTHONPATH": str(harness_dir / "lib") + os.pathsep + env.get("PYTHONPATH", ""),
        }
    )

    repo_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True).strip()
    commands: list[dict[str, Any]] = []
    artifact_paths: list[str] = []
    assertions: dict[str, bool] = {}

    pm_sid = f"{request['sprint_id']}-{run_id.lower()}"
    pm_cmd = [
        python,
        str(harness_dir / "tools" / "codex_pm_router.py"),
        "--direct-compile",
        "--text",
        request["request"],
        "--repo-context",
        str(repo_root),
        "--sprint-id",
        pm_sid,
        "--emit-dir",
        str(workspace),
        "--emit-sprint-root",
        str(sprints_dir),
        "--format",
        "json",
    ]
    pm_record = _run_cmd("codex-pm-router-direct-compile", pm_cmd, cwd=repo_root, env=env, evidence_dir=evidence_dir)
    commands.append(pm_record)
    assert pm_record["exit_code"] == 0, pm_record["stderr_tail"]
    graph_path = sprints_dir / f"{pm_sid}.task_graph.json"
    graph = _read_json(graph_path)
    artifact_paths.append(_copy_artifact(graph_path, evidence_dir))
    artifact_paths.append(_copy_artifact(sprints_dir / f"{pm_sid}.capsule_plan.json", evidence_dir))

    nodes = graph.get("nodes") or []
    deps_by_node = {node["id"]: list(node.get("depends_on") or []) for node in nodes}
    assertions["dag_has_multiple_dependency_steps"] = len(nodes) >= 3 and any(deps_by_node.values())
    assertions["dag_is_acyclic_shape"] = all(dep in deps_by_node for deps in deps_by_node.values() for dep in deps)

    scheduler = harness_dir / "lib" / "graph_scheduler.py"
    for label, args in [
        ("validate", ["validate"]),
        ("topo", ["topo"]),
        ("layers", ["layers"]),
        ("ready-initial", ["ready"]),
        ("assign", ["assign", "--workers", str(workers), "--max-parallel", "2"]),
    ]:
        cmd = [python, str(scheduler), *args, "--graph", str(graph_path)]
        record = _run_cmd(f"graph-scheduler-{label}", cmd, cwd=repo_root, env=env, evidence_dir=evidence_dir)
        commands.append(record)
        assert record["exit_code"] == 0, record["stderr_tail"]

    validate_json = commands[-5]["stdout_json"]
    topo_json = commands[-4]["stdout_json"]
    layers_json = commands[-3]["stdout_json"]
    ready_initial = commands[-2]["stdout_json"]
    assign_json = commands[-1]["stdout_json"]
    topo_order = topo_json.get("order") or []
    first_layer = (layers_json.get("layers") or [[]])[0]
    assertions["scheduler_validate_ok"] = validate_json.get("ok") is True
    assertions["topological_order_respects_dependencies"] = all(
        topo_order.index(dep) < topo_order.index(node)
        for node, deps in deps_by_node.items()
        for dep in deps
        if dep in topo_order and node in topo_order
    )
    assertions["initial_ready_is_dependency_free"] = sorted(ready_initial.get("nodes") or []) == sorted(first_layer)
    assigned_or_queued = (assign_json.get("assigned") or []) + (assign_json.get("queued") or [])
    assertions["canonical_worker_selection_participated"] = bool(assigned_or_queued or assign_json.get("batch"))

    ready_sequence = [ready_initial.get("nodes") or []]
    executed_order: list[str] = []
    for node_id in topo_order:
        mark = _mark_node_with_production_scheduler(
            python,
            graph_path,
            node_id,
            repo_root=repo_root,
            env=env,
            evidence_dir=evidence_dir,
        )
        commands.append(mark)
        assert mark["exit_code"] == 0, mark["stderr_tail"]
        executed_order.append(node_id)
        ready = _run_cmd(
            f"ready-after-{node_id}",
            [python, str(scheduler), "ready", "--graph", str(graph_path)],
            cwd=repo_root,
            env=env,
            evidence_dir=evidence_dir,
        )
        commands.append(ready)
        assert ready["exit_code"] == 0, ready["stderr_tail"]
        ready_sequence.append(ready["stdout_json"].get("nodes") or [])

    parent = _run_cmd(
        "graph-scheduler-parent-check",
        [python, str(scheduler), "parent-check", "--graph", str(graph_path)],
        cwd=repo_root,
        env=env,
        evidence_dir=evidence_dir,
    )
    commands.append(parent)
    assert parent["exit_code"] == 0, parent["stderr_tail"]
    state_path = sprints_dir / f"{pm_sid}.task_dag.state.json"
    closure_path = sprints_dir / f"{pm_sid}.closure.json"
    artifact_paths.extend([_copy_artifact(graph_path, evidence_dir), _copy_artifact(state_path, evidence_dir), _copy_artifact(closure_path, evidence_dir)])
    state_after = _read_json(state_path)
    closure_after = _read_json(closure_path)
    assertions["ready_sequence_progressed_in_topological_order"] = executed_order == topo_order and not ready_sequence[-1]
    assertions["parent_ready_after_all_nodes_passed"] = parent["stdout_json"].get("ready") is True
    assertions["trace_state_and_closure_recover_results"] = (
        state_path.exists()
        and closure_path.exists()
        and all((state_after.get("node_results") or {}).get(node_id, {}).get("status") == "passed" for node_id in topo_order)
        and closure_after.get("all_nodes_passed") is True
    )
    runtime_v2_import = _run_cmd(
        "runtime-v2-import-smoke",
        [
            python,
            "-c",
            "import runtime_status, session_log, graph_node_dispatcher; print('runtime-v2-import-ok')",
        ],
        cwd=repo_root,
        env=env,
        evidence_dir=evidence_dir,
    )
    commands.append(runtime_v2_import)
    assertions["runtime_v2_modules_import_on_windows"] = (
        runtime_v2_import["exit_code"] == 0
        and "runtime-v2-import-ok" in Path(runtime_v2_import["stdout_path"]).read_text(encoding="utf-8")
    )

    time.sleep(1.1)
    intake_records = []
    intake_sids = []
    for suffix in ["a", "b"]:
        intake = _run_cmd(
            f"workflow-intake-{suffix}",
            [
                python,
                str(harness_dir / "lib" / "workflow_intake.py"),
                "--workflow-id",
                request["workflow_id"],
                "--request",
                f"{request['request']} trace-run-{suffix}",
                "--workspace-root",
                str(workspace),
                "--input",
                f"tool={request['tool']}_{suffix}",
                "--sprints-dir",
                str(sprints_dir),
                "--workflows-dir",
                str(harness_dir / "config" / "workflows"),
            ],
            cwd=repo_root,
            env=env,
            evidence_dir=evidence_dir,
        )
        commands.append(intake)
        intake_records.append(intake)
        assert intake["exit_code"] == 0, intake["stderr_tail"]
        sid = intake["stdout_json"]["sprint_id"]
        intake_sids.append(sid)
        for suffix_name in ["task_graph.json", "status.json", "events.jsonl"]:
            artifact_paths.append(_copy_artifact(sprints_dir / f"{sid}.{suffix_name}", evidence_dir))
        time.sleep(1.1)

    event_a_path = sprints_dir / f"{intake_sids[0]}.events.jsonl"
    event_b_path = sprints_dir / f"{intake_sids[1]}.events.jsonl"
    events_a = [json.loads(line) for line in event_a_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    events_b = [json.loads(line) for line in event_b_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assertions["trace_created_by_real_execution"] = bool(events_a and events_a[0].get("actor") == "workflow_intake")
    assertions["trace_has_time_actor_run_status"] = all(
        event.get("ts") and event.get("actor") and event.get("sid") == intake_sids[0] and event.get("status")
        for event in events_a
    )
    assertions["trace_run_identity_does_not_cross_files"] = (
        all(event.get("sid") == intake_sids[0] for event in events_a)
        and all(event.get("sid") == intake_sids[1] for event in events_b)
        and intake_sids[0] != intake_sids[1]
    )
    unified_trace = _run_cmd(
        "unified-trace-graph-query",
        [
            python,
            str(harness_dir / "lib" / "trace_graph.py"),
            "query",
            "--harness-dir",
            str(harness_dir),
            "--sprints-dir",
            str(sprints_dir),
            "--sprint-id",
            pm_sid,
        ],
        cwd=repo_root,
        env=env,
        evidence_dir=evidence_dir,
    )
    commands.append(unified_trace)
    unified_payload = unified_trace["stdout_json"]
    unified_path = evidence_dir / "unified-trace-graph-query.json"
    _write_json(unified_path, unified_payload)
    artifact_paths.append(str(unified_path))
    assertions["unified_trace_query_returns_graph_state_and_closure"] = (
        unified_trace["exit_code"] == 0
        and unified_payload.get("schema_version") == "solar.trace_graph_query.v1"
        and unified_payload.get("sprint_id") == pm_sid
        and unified_payload.get("graph", {}).get("node_count") == len(nodes)
        and len(unified_payload.get("graph", {}).get("node_results", {})) == len(nodes)
        and unified_payload.get("graph", {}).get("closure", {}).get("all_nodes_passed") is True
    )

    server = _start_status_server(python, harness_dir / "lib" / "symphony" / "status-server.py", env, evidence_dir)
    try:
        port_file = harness_dir / "run" / "status-server.port"
        deadline = time.time() + 25
        while time.time() < deadline and not port_file.exists():
            if server.poll() is not None:
                break
            time.sleep(0.25)
        assertions["status_server_started_on_assigned_port"] = port_file.exists()
        assert port_file.exists(), "status server did not start"
        port = int(port_file.read_text(encoding="utf-8").strip())
        assert 18730 <= port <= 18739
        base = f"http://127.0.0.1:{port}"
        q_run_a = _query_json(f"{base}/events?sprint_id={intake_sids[0]}&limit=20")
        q_run_b = _query_json(f"{base}/events?sprint_id={intake_sids[1]}&limit=20")
        q_missing = _query_json(f"{base}/events?sprint_id=missing-phase22-nt-dag-trace&limit=20")
        q_wrong_project = _query_json(f"{base}/events?sprint_id={intake_sids[0]}&project=definitely-wrong-project&limit=20")
        q_wrong_actor = _query_json(f"{base}/events?sprint_id={intake_sids[0]}&actor=definitely-wrong-actor&limit=20")
        q_future = _query_json(f"{base}/events?sprint_id={intake_sids[0]}&since=2999-01-01T00:00:00Z&limit=20")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)

    query_payload_path = evidence_dir / "status-event-query-results.json"
    _write_json(
        query_payload_path,
        {
            "run_a": q_run_a,
            "run_b": q_run_b,
            "missing": q_missing,
            "wrong_project": q_wrong_project,
            "wrong_actor": q_wrong_actor,
            "future_since": q_future,
        },
    )
    artifact_paths.append(str(query_payload_path))

    def _event_list(payload: Any) -> list[dict[str, Any]]:
        return payload if isinstance(payload, list) else []

    run_a_events = _event_list(q_run_a)
    run_b_events = _event_list(q_run_b)
    assertions["query_run_filter_returns_only_requested_run"] = (
        bool(run_a_events)
        and bool(run_b_events)
        and all(event.get("sprint_id") == intake_sids[0] for event in run_a_events)
        and all(event.get("sprint_id") == intake_sids[1] for event in run_b_events)
    )
    assertions["query_missing_run_leaks_no_data"] = _event_list(q_missing) == []
    assertions["query_order_is_chronological_for_returned_events"] = [
        event.get("ts") for event in run_a_events
    ] == sorted(event.get("ts") for event in run_a_events)
    assertions["project_filter_is_enforced"] = _event_list(q_wrong_project) == []
    assertions["actor_filter_is_enforced"] = _event_list(q_wrong_actor) == []
    assertions["time_range_filter_is_enforced"] = _event_list(q_future) == []

    algorithm_hits = _scan_named_algorithm_hits(repo_root)
    named_algorithm_present = any(algorithm_hits.values())
    search_filters_pass = (
        assertions["query_run_filter_returns_only_requested_run"]
        and assertions["query_missing_run_leaks_no_data"]
        and assertions["query_order_is_chronological_for_returned_events"]
        and assertions["project_filter_is_enforced"]
        and assertions["actor_filter_is_enforced"]
        and assertions["time_range_filter_is_enforced"]
    )
    trace_management_pass = (
        assertions["trace_created_by_real_execution"]
        and assertions["trace_has_time_actor_run_status"]
        and assertions["trace_run_identity_does_not_cross_files"]
        and assertions["trace_state_and_closure_recover_results"]
        and assertions["runtime_v2_modules_import_on_windows"]
        and assertions["unified_trace_query_returns_graph_state_and_closure"]
    )

    l2_results = [
        {
            "level_2_feature": L2_DAG,
            "implementation_state": "IMPLEMENTED_CURRENT_SUBSET",
            "production_entrypoint": "harness/tools/codex_pm_router.py --direct-compile; harness/lib/graph_scheduler.py validate/topo/layers/ready/assign plus production scheduler mark/save API",
            "selector": "tests/journeys/phase22/code/test_p22_nt_dag_trace.py::test_p22_nt_dag_trace",
            "exact_command": pm_record["command"],
            "exit_code": pm_record["exit_code"],
            "assertions": {key: assertions[key] for key in [
                "dag_has_multiple_dependency_steps",
                "scheduler_validate_ok",
                "topological_order_respects_dependencies",
                "initial_ready_is_dependency_free",
                "ready_sequence_progressed_in_topological_order",
                "canonical_worker_selection_participated",
            ]},
            "evidence_paths": artifact_paths,
            "limitations": [
                "AFlow/MCTS/ADAS named production implementation was not found under harness/lib, harness/tools, or core.",
                "graph_node_dispatcher.py is the advanced dispatcher; this selector proves import portability but does not execute the full pane-dispatch lifecycle.",
            ],
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS" if named_algorithm_present else "NOT_AVAILABLE",
            "named_algorithm_hits": algorithm_hits,
        },
        {
            "level_2_feature": L2_TRACE,
            "implementation_state": "IMPLEMENTED_CURRENT_SUBSET",
            "production_entrypoint": "harness/lib/workflow_intake.py; harness/lib/graph_scheduler.py save_graph state/closure projection",
            "selector": "tests/journeys/phase22/code/test_p22_nt_dag_trace.py::test_p22_nt_dag_trace",
            "exact_command": intake_records[0]["command"],
            "exit_code": intake_records[0]["exit_code"],
            "assertions": {key: assertions[key] for key in [
                "trace_created_by_real_execution",
                "trace_has_time_actor_run_status",
                "trace_run_identity_does_not_cross_files",
                "trace_state_and_closure_recover_results",
                "runtime_v2_modules_import_on_windows",
                "unified_trace_query_returns_graph_state_and_closure",
            ]},
            "evidence_paths": artifact_paths,
            "limitations": [
                "The exercised local JSONL and DAG-state path is unified and portable; distributed trace backends and remote-host aggregation are not inferred.",
            ],
            "recommended_status": "PASS_WITH_KNOWN_LIMITATIONS" if trace_management_pass else "FAIL",
        },
        {
            "level_2_feature": L2_SEARCH,
            "implementation_state": "PARTIAL_IMPLEMENTATION",
            "production_entrypoint": "harness/lib/symphony/status-server.py /events",
            "selector": "tests/journeys/phase22/code/test_p22_nt_dag_trace.py::test_p22_nt_dag_trace",
            "exact_command": f"{python} -u -c <status-server wrapper setting PORT_RANGE=18730..18739> {harness_dir / 'lib' / 'symphony' / 'status-server.py'}",
            "exit_code": 0 if assertions["status_server_started_on_assigned_port"] else 1,
            "assertions": {key: assertions[key] for key in [
                "status_server_started_on_assigned_port",
                "query_run_filter_returns_only_requested_run",
                "query_missing_run_leaks_no_data",
                "query_order_is_chronological_for_returned_events",
                "project_filter_is_enforced",
                "actor_filter_is_enforced",
                "time_range_filter_is_enforced",
            ]},
            "evidence_paths": artifact_paths,
            "limitations": [
                "/events now enforces sprint_id, project, actor, since/time-range, and limit filters for the local status-server event source.",
                "core daemon /orchestrator/events source inspection shows taskId/type/since filters only, not the requested project/run/actor/time-range surface.",
            ],
            "recommended_status": "PASS" if search_filters_pass else "FAIL",
        },
    ]

    _write_json(
        result_path,
        _result_record(
            run_id=run_id,
            repo_head=repo_head,
            evidence_dir=evidence_dir,
            command_records=commands,
            l2_results=l2_results,
        ),
    )

    assert assertions["dag_has_multiple_dependency_steps"]
    assert assertions["scheduler_validate_ok"]
    assert assertions["topological_order_respects_dependencies"]
    assert assertions["ready_sequence_progressed_in_topological_order"]
    assert assertions["runtime_v2_modules_import_on_windows"]
    assert assertions["unified_trace_query_returns_graph_state_and_closure"]
    assert trace_management_pass
    assert assertions["query_run_filter_returns_only_requested_run"]
    assert assertions["query_missing_run_leaks_no_data"]
    assert assertions["query_order_is_chronological_for_returned_events"]
    assert assertions["project_filter_is_enforced"]
    assert assertions["actor_filter_is_enforced"]
    assert assertions["time_range_filter_is_enforced"]
