from __future__ import annotations

import concurrent.futures
import builtins
import hashlib
import importlib.util
import json
import multiprocessing
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_observability():
    path = ROOT / "harness" / "lib" / "developer_observability.py"
    spec = importlib.util.spec_from_file_location("developer_observability_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_process_registry():
    path = ROOT / "harness" / "lib" / "run_process_registry.py"
    spec = importlib.util.spec_from_file_location("run_process_registry_observability_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _multiprocess_emit(arguments) -> bool:
    trace, worker, count = arguments
    os.environ["SOLAR_DEVELOPER_OBSERVABILITY"] = "1"
    os.environ["SOLAR_OBSERVABILITY_TRACE"] = trace
    module = _load_observability()
    return all(
        module.observe(
            "multiprocess.event",
            component="test",
            operation_id=f"worker-{worker}-event-{index}",
            data={"worker": worker, "index": index},
        )
        for index in range(count)
    )


def test_disabled_mode_creates_no_trace(tmp_path, monkeypatch):
    module = _load_observability()
    trace = tmp_path / "trace.jsonl"
    monkeypatch.delenv("SOLAR_DEVELOPER_OBSERVABILITY", raising=False)
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))

    assert module.observe("test.event", component="test") is False
    assert not trace.exists()


def test_event_has_stable_identity_and_two_clocks(tmp_path, monkeypatch):
    module = _load_observability()
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))
    monkeypatch.setenv("SOLAR_OBSERVABILITY_RUN_ID", "run-1")

    assert module.observe(
        "operator.enqueued",
        component="test",
        identifiers={"sprint_id": "sprint-1", "task_id": "task-1"},
        data={"duration_ms": 1.25},
    )
    row = _rows(trace)[0]
    assert row["schema_version"] == "solar.observability.event.v1"
    assert row["event"] == row["operation"] == "operator.enqueued"
    assert row["run_id"] == "run-1"
    assert row["sprint_id"] == "sprint-1"
    assert row["task_id"] == "task-1"
    assert isinstance(row["observed_time_ns"], int)
    assert isinstance(row["monotonic_ns"], int)
    assert row["provenance"] == "observed"


def test_sensitive_bodies_are_removed_recursively(tmp_path, monkeypatch):
    module = _load_observability()
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "true")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))

    module.observe(
        "privacy.test",
        component="test",
        data={
            "model": "gpt-test",
            "raw_prompt": "do not retain",
            "prompt": "also do not retain",
            "nested": {"access_token": "secret", "count": 2},
            "raw_command": "rm something",
            "tool_output": "sensitive",
            "first_output_observed": True,
        },
    )
    serialized = trace.read_text(encoding="utf-8")
    assert "do not retain" not in serialized
    assert "secret" not in serialized
    assert "rm something" not in serialized
    assert "sensitive" not in serialized
    assert _rows(trace)[0]["data"] == {
        "first_output_observed": True,
        "model": "gpt-test",
        "nested": {"count": 2},
    }


def test_secret_values_under_benign_keys_are_removed_without_false_positives(tmp_path, monkeypatch):
    module = _load_observability()
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))

    module.observe(
        "privacy.values",
        component="test",
        data={
            "message": "Bearer abcdefghijklmnopqrstuvwxyz012345",
            "note": "sk-proj-abcdefghijklmno123456",
            "description": "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "detail": "AKIAABCDEFGHIJKLMNOP",
            "context": "eyJabcdefghijk.eyJmnopqrstuv.abcdefghijklmno",
            "label": "token=generic_credential_value_12345",
            "ordinary": "sketch-based-selection",
            "config_key": "OPENAI_API_KEY",
        },
    )

    row = _rows(trace)[0]
    assert row["data"]["message"] is None
    assert row["data"]["note"] is None
    assert row["data"]["description"] is None
    assert row["data"]["detail"] is None
    assert row["data"]["context"] is None
    assert row["data"]["label"] is None
    assert row["data"]["ordinary"] == {
        "bytes": len("sketch-based-selection"),
        "sha256": hashlib.sha256(b"sketch-based-selection").hexdigest(),
    }
    assert row["data"]["config_key"] == "OPENAI_API_KEY"
    serialized = trace.read_text(encoding="utf-8")
    assert "abcdefghijklmnopqrstuvwxyz012345" not in serialized
    assert "abcdefghijklmno123456" not in serialized
    assert "ghp_" not in serialized
    assert "AKIAABCDEFGHIJKLMNOP" not in serialized
    assert "generic_credential_value" not in serialized


def test_operation_and_span_identity_is_stable_and_attempt_safe(monkeypatch):
    module = _load_observability()
    operation_one = module.stable_id("operation", "dispatch-1", "1", "worker")
    operation_repeat = module.stable_id("operation", "dispatch-1", "1", "worker")
    operation_retry = module.stable_id("operation", "dispatch-1", "2", "worker")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_SPAN_ID", "span-parent")

    row = module.build_event(
        "worker.started",
        component="test",
        operation_id=operation_one,
        phase="started",
        identifiers={"span_id": module.stable_id("span", operation_one)},
    )

    assert operation_one == operation_repeat
    assert operation_one != operation_retry
    assert row["operation_id"] == operation_one
    assert row["span_id"].startswith("span-")
    assert row["parent_span_id"] == "span-parent"
    assert row["phase"] == "started"
    assert row["terminal"] is False


def test_concurrent_appends_remain_valid_json_lines(tmp_path, monkeypatch):
    module = _load_observability()
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "yes")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))

    def emit(index: int) -> bool:
        return module.observe("parallel.event", component="test", data={"index": index})

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(emit, range(100)))
    rows = _rows(trace)
    assert len(rows) == 100
    assert {row["data"]["index"] for row in rows} == set(range(100))


def test_multiprocess_appends_have_no_corruption_or_loss(tmp_path):
    trace = tmp_path / "multiprocess.jsonl"
    workers = 8
    per_worker = 75
    start_method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
    context = multiprocessing.get_context(start_method)
    with context.Pool(workers) as pool:
        assert all(pool.map(
            _multiprocess_emit,
            [(str(trace), worker, per_worker) for worker in range(workers)],
        ))

    rows = _rows(trace)
    assert len(rows) == workers * per_worker
    assert len({row["event_id"] for row in rows}) == workers * per_worker
    assert {
        (row["data"]["worker"], row["data"]["index"])
        for row in rows
    } == {(worker, index) for worker in range(workers) for index in range(per_worker)}


def test_forced_partial_writes_are_completed_without_corruption(tmp_path, monkeypatch):
    module = _load_observability()
    trace = tmp_path / "partial-write.jsonl"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))
    real_write = module.os.write

    def partial_write(file_descriptor, data):
        return real_write(file_descriptor, bytes(data[:7]))

    monkeypatch.setattr(module.os, "write", partial_write)
    assert all(
        module.observe(
            "partial.event",
            component="test",
            operation_id=f"partial-{index}",
            data={"index": index},
        )
        for index in range(125)
    )

    rows = _rows(trace)
    assert len(rows) == 125
    assert {row["data"]["index"] for row in rows} == set(range(125))


def test_registry_teardown_reports_actual_term_kill_and_survivor_targets(monkeypatch):
    module = _load_process_registry()
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    target = {"pid": 4242, "role": "worker", "signal_scope": "pid", "_index": 1}
    signals = []
    appended = []
    waits = iter([[target], [target]])
    monkeypatch.setattr(module, "mark_terminal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_registered_entries", lambda *_args, **_kwargs: [target])
    monkeypatch.setattr(module, "_running", lambda _pid: True)
    monkeypatch.setattr(module, "_identity_matches", lambda _entry: True)
    monkeypatch.setattr(module, "_signal_entry", lambda entry, sig: signals.append((entry["pid"], sig)))
    monkeypatch.setattr(module, "_wait_entries_gone", lambda *_args, **_kwargs: next(waits))
    monkeypatch.setattr(module, "_entry_live_pids", lambda entry: [entry["pid"]])
    monkeypatch.setattr(module, "_append", lambda _run_id, record, _harness=None: appended.append(record))

    result = module.teardown("test-run", grace_s=0, kill_grace_s=0)

    hard_kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    assert signals == [(4242, signal.SIGTERM), (4242, hard_kill_signal)]
    assert result["term_signalled"] == [4242]
    assert result["kill_signalled"] == [4242]
    assert result["survivors"] == [4242]
    assert result["ok"] is False
    assert appended == [result]


def test_registry_teardown_default_off_preserves_legacy_result_and_record_bytes(monkeypatch):
    module = _load_process_registry()
    appended = []
    monkeypatch.setattr(module, "mark_terminal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_registered_entries", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(module, "_append", lambda _run_id, record, _harness=None: appended.append(record))
    monkeypatch.setattr(module, "_now", lambda: "2026-08-11T00:00:00Z")

    expected = {
        "event": "teardown",
        "run_id": "test-run",
        "ok": True,
        "killed": [],
        "sigkilled": [],
        "already_gone": [],
        "skipped": [],
        "survivors": [],
        "finished_at": "2026-08-11T00:00:00Z",
    }

    for setting in (None, "0", "false", "off"):
        if setting is None:
            monkeypatch.delenv("SOLAR_DEVELOPER_OBSERVABILITY", raising=False)
        else:
            monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", setting)
        appended.clear()
        result = module.teardown("test-run")
        assert result == expected
        assert list(result) == list(expected)
        assert appended == [expected]
        assert json.dumps(result, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
        assert "term_signalled" not in result
        assert "kill_signalled" not in result


def test_unwritable_destination_is_fail_open(tmp_path, monkeypatch):
    module = _load_observability()
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(blocking_file / "trace.jsonl"))

    assert module.observe("failure.test", component="test") is False


def test_null_fields_are_not_invented():
    module = _load_observability()
    row = module.build_event("null.test", component="test", data={"tokens": None})
    assert row["invocation_id"] is None
    assert row["data"]["tokens"] is None


def test_pm_selection_emits_candidate_scores_without_task_body(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))
    tools = ROOT / "harness" / "tools"
    library = ROOT / "harness" / "lib"
    monkeypatch.syspath_prepend(str(library))
    spec = importlib.util.spec_from_file_location("pm_dispatch_observability", tools / "pm_dispatch.py")
    assert spec and spec.loader
    pm_dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm_dispatch)
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", [])
    monkeypatch.setattr(pm_dispatch, "_load_concurrency_policy_module", lambda: None)
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda _op: (True, ""))
    monkeypatch.setattr(
        pm_dispatch,
        "load_registry",
        lambda: {
            "operators": {
                "builder-a": {
                    "enabled": True,
                    "available": True,
                    "roles": ["builder"],
                    "launch_cmd_kind": "command",
                    "task_classes": ["implementation"],
                    "provider": "openai",
                    "model": "gpt-test",
                }
            }
        },
    )

    operator_id, _operator, reason = pm_dispatch.select_operator_by_role(
        "builder",
        task_type="implementation",
        observation_identifiers={"sprint_id": "s1", "task_id": "t1"},
    )

    assert operator_id == "builder-a"
    assert reason == ""
    row = _rows(trace)[0]
    assert row["event"] == "operator.selection.completed"
    assert row["task_id"] == "t1"
    assert row["data"]["selected_operator_id"] == "builder-a"
    assert row["data"]["candidates"][0]["model"] == "gpt-test"
    assert "objective" not in trace.read_text(encoding="utf-8")


def test_pm_attempt_identity_predicts_builder_sequence_and_preserves_eval_generation(monkeypatch):
    tools = ROOT / "harness" / "tools"
    library = ROOT / "harness" / "lib"
    monkeypatch.syspath_prepend(str(library))
    spec = importlib.util.spec_from_file_location(
        "pm_dispatch_attempt_identity", tools / "pm_dispatch.py"
    )
    assert spec and spec.loader
    pm_dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm_dispatch)

    attempt = {
        "schema_version": "solar.node_attempt.v1",
        "phase": "execution",
        "sequence": 3,
        "repair_generation": 2,
        "task_id": "pm-builder-attempt",
        "dispatch_id": "graph-builder-dispatch",
    }

    assert pm_dispatch._execution_attempt_id({"execution_attempt": attempt}) == "4"
    assert "{" not in pm_dispatch._execution_attempt_id({"execution_attempt": attempt})
    assert pm_dispatch._execution_attempt_id({"repair_attempts": 4}) == "1"
    assert pm_dispatch._execution_attempt_id(
        {
            "execution_attempt": {},
            "execution_attempt_history": [{"sequence": 2}, {"sequence": 5}],
        }
    ) == "6"
    assert pm_dispatch._execution_attempt_id({"execution_attempt": {}}) == "1"
    assert pm_dispatch._execution_attempt_id(
        {"repair_attempts": 0}, role="evaluator"
    ) == "0"
    assert pm_dispatch._execution_attempt_id(
        {"execution_attempt": attempt, "repair_attempts": 2},
        role="evaluator",
        explicit_attempt_id="7",
    ) == "7"


def test_graph_event_bridge_preserves_eval_repair_identity(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    sprints = tmp_path / "sprints"
    sprints.mkdir()
    graph_bytes = b'{"schema_version":"solar.task_graph.v1","nodes":[]}\n'
    (sprints / "sprint-1.task_graph.json").write_bytes(graph_bytes)
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))
    monkeypatch.setenv("HARNESS_SPRINTS_DIR", str(sprints))
    monkeypatch.syspath_prepend(str(ROOT / "harness" / "lib"))
    path = ROOT / "harness" / "lib" / "graph_node_dispatcher.py"
    spec = importlib.util.spec_from_file_location("graph_observability", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module._append_event(
        "sprint-1",
        {
            "event": "graph_repair_started",
            "by": "policy",
            "severity": "warning",
            "data": {
                "node": "S1",
                "pm_task_id": "task-1",
                "eval_dispatch_id": "dispatch-1",
                "repair_attempt": 2,
                "evaluation_attempt": 2,
                "reason": "evaluation_failed",
            },
        },
    )

    row = _rows(trace)[0]
    assert row["event"] == "graph_repair_started"
    assert row["sprint_id"] == "sprint-1"
    assert row["node_id"] == "S1"
    assert row["task_id"] == "task-1"
    assert row["attempt_id"] == "2"
    assert row["data"]["reason"] == "evaluation_failed"
    assert row["data"]["eval_dispatch_id"] == "dispatch-1"
    assert row["data"]["graph_revision_sha256"] == hashlib.sha256(graph_bytes).hexdigest()
    assert row["data"]["graph_revision_bytes"] == len(graph_bytes)


def test_operatord_propagates_retry_and_trace_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.syspath_prepend(str(ROOT / "harness" / "lib"))
    path = ROOT / "harness" / "tools" / "operatord.py"
    spec = importlib.util.spec_from_file_location("operatord_identity_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result_dir = tmp_path / "result"
    result_dir.mkdir()

    env = module._materialize_envelope_context(result_dir, {
        "task_id": "task-1",
        "dispatch_id": "dispatch-1",
        "attempt_id": 3,
        "correlation_id": "sprint-1:S1",
        "causation_id": "dispatch-parent",
        "span_id": "span-child",
        "parent_span_id": "span-parent",
        "work_dir": str(tmp_path / "work"),
    })

    assert env["DISPATCH_ID"] == "dispatch-1"
    assert env["ATTEMPT_ID"] == "3"
    assert env["CORRELATION_ID"] == "sprint-1:S1"
    assert env["CAUSATION_ID"] == "dispatch-parent"
    assert env["SOLAR_OBSERVABILITY_SPAN_ID"] == "span-child"
    assert env["SOLAR_OBSERVABILITY_PARENT_SPAN_ID"] == "span-parent"


def test_product_path_default_off_and_on_have_functional_parity(tmp_path, monkeypatch):
    library = ROOT / "harness" / "lib"
    tools = ROOT / "harness" / "tools"
    monkeypatch.syspath_prepend(str(library))
    pm_spec = importlib.util.spec_from_file_location("pm_dispatch_parity", tools / "pm_dispatch.py")
    assert pm_spec and pm_spec.loader
    pm = importlib.util.module_from_spec(pm_spec)
    pm_spec.loader.exec_module(pm)
    monkeypatch.setattr(pm, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(pm, "_now", lambda: "2026-08-11T00:00:00Z")
    dispatch_file = tmp_path / "dispatch.md"
    dispatch_file.write_text("functional dispatch\n", encoding="utf-8")
    common = dict(
        task_id="task-1",
        dispatch_id="dispatch-1",
        attempt_id="2",
        correlation_id="sprint-1:S1",
        sprint_id="sprint-1",
        node_id="S1",
        operator_id="builder-a",
        operator={"provider": "openai", "backend": "command", "model": "gpt-test"},
        task_type="implementation",
        objective="bounded objective",
        dispatch_file=dispatch_file,
        result_path=str(tmp_path / "work" / "result.md"),
        role="builder",
        work_dir=str(tmp_path / "work"),
        expected_artifacts=[str(tmp_path / "work" / "result.md")],
    )
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "0")
    off_envelope = pm._build_pm_operator_envelope(**common)
    telemetry_keys = {
        "dispatch_id", "attempt_id", "correlation_id", "span_id", "parent_span_id", "causation_id"
    }
    assert telemetry_keys.isdisjoint(off_envelope)
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    on_envelope = pm._build_pm_operator_envelope(**common)
    assert {key: value for key, value in on_envelope.items() if key not in telemetry_keys} == off_envelope

    operator_spec = importlib.util.spec_from_file_location("operatord_parity", tools / "operatord.py")
    assert operator_spec and operator_spec.loader
    operatord = importlib.util.module_from_spec(operator_spec)
    operator_spec.loader.exec_module(operatord)
    off_dir = tmp_path / "off"
    on_dir = tmp_path / "on"
    off_dir.mkdir()
    on_dir.mkdir()
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "0")
    off_env = operatord._materialize_envelope_context(off_dir, off_envelope)
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    on_env = operatord._materialize_envelope_context(on_dir, on_envelope)
    identity_env = {
        "DISPATCH_ID", "ATTEMPT_ID", "CORRELATION_ID", "CAUSATION_ID",
        "SOLAR_OBSERVABILITY_SPAN_ID", "SOLAR_OBSERVABILITY_PARENT_SPAN_ID",
    }
    def functional_env(env, result_dir):
        return {
            key: value.replace(str(result_dir), "<result-dir>")
            for key, value in env.items()
            if key != "SOLAR_OPERATOR_ENVELOPE_JSON" and key not in identity_env
        }

    off_functional_env = functional_env(off_env, off_dir)
    on_functional_env = functional_env(on_env, on_dir)
    assert identity_env.isdisjoint(off_env)
    assert on_functional_env == off_functional_env
    assert (off_dir / "dispatch.md").read_bytes() == (on_dir / "dispatch.md").read_bytes()
    assert {
        key: value
        for key, value in json.loads((on_dir / "envelope.json").read_text()).items()
        if key not in telemetry_keys
    } == json.loads((off_dir / "envelope.json").read_text())
    command = [sys.executable, "-c", "raise SystemExit(0)"]
    assert subprocess.run(command, env={**os.environ, **off_env}, check=False).returncode == 0
    assert subprocess.run(command, env={**os.environ, **on_env}, check=False).returncode == 0


def test_codex_spawn_exception_emits_one_terminal_event(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    task_dir = tmp_path / "task"
    monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1")
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))
    monkeypatch.setenv("TASK_DIR", str(task_dir))
    monkeypatch.setenv("CODEX_WORKDIR", str(tmp_path))
    monkeypatch.setenv("TASK_ID", "task-1")
    monkeypatch.setenv("DISPATCH_ID", "dispatch-1")
    monkeypatch.setenv("ATTEMPT_ID", "2")
    monkeypatch.syspath_prepend(str(ROOT / "harness" / "lib"))
    path = ROOT / "harness" / "tools" / "codex_operator.py"
    spec = importlib.util.spec_from_file_location("codex_operator_spawn_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_read_dispatch", lambda: "bounded dispatch")
    monkeypatch.setattr(module, "_codex_exec_env", lambda _task_dir: dict(os.environ))
    monkeypatch.setattr(module, "_codex_exec_command", lambda *_args: ["codex", "exec", "payload"])
    monkeypatch.setattr(module, "_filesystem_isolated_command", lambda command, **_kwargs: (command, {"mode": "test"}))

    def spawn_failure(*_args, **_kwargs):
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(module.subprocess, "Popen", spawn_failure)

    try:
        module.main()
    except OSError as exc:
        assert "synthetic spawn failure" in str(exc)
    else:
        raise AssertionError("spawn failure was not propagated")

    rows = _rows(trace)
    terminal = [row for row in rows if row["terminal"]]
    assert len(terminal) == 1
    assert terminal[0]["event"] == "codex_cli.invocation.completed"
    assert terminal[0]["status"] == "spawn_error"
    assert terminal[0]["dispatch_id"] == "dispatch-1"
    assert terminal[0]["attempt_id"] == "2"
    assert terminal[0]["invocation_id"]
    assert terminal[0]["data"]["provider_latency_ms"] is None
    assert terminal[0]["data"]["model_latency_ms"] is None
    assert {row["operation_id"] for row in rows} == {terminal[0]["operation_id"]}


def test_hot_path_module_loads_when_observability_import_is_missing(monkeypatch):
    path = ROOT / "harness" / "tools" / "pm_dispatch.py"
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "developer_observability":
            raise ImportError("telemetry package intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    spec = importlib.util.spec_from_file_location("pm_dispatch_no_observability", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._observe("test", component="test") is False


def test_representative_collection_overhead_is_below_five_percent(tmp_path, monkeypatch):
    trace = tmp_path / "overhead.jsonl"
    tools = ROOT / "harness" / "tools"
    library = ROOT / "harness" / "lib"
    monkeypatch.syspath_prepend(str(library))
    spec = importlib.util.spec_from_file_location("pm_dispatch_benchmark", tools / "pm_dispatch.py")
    assert spec and spec.loader
    pm_dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm_dispatch)
    monkeypatch.setattr(pm_dispatch, "DEFAULT_OPERATOR_PROVIDERS", [])
    monkeypatch.setattr(pm_dispatch, "_load_concurrency_policy_module", lambda: None)
    monkeypatch.setattr(pm_dispatch, "is_dispatchable", lambda _op: (True, ""))
    monkeypatch.setattr(pm_dispatch, "load_registry", lambda: {"operators": {
        "builder-a": {
            "enabled": True,
            "available": True,
            "roles": ["builder"],
            "launch_cmd_kind": "command",
            "task_classes": ["implementation"],
            "provider": "openai",
            "model": "gpt-test",
        }
    }})
    monkeypatch.setenv("SOLAR_OBSERVABILITY_TRACE", str(trace))
    payload = bytes(range(256)) * 256

    def run(enabled: bool, output: Path) -> tuple[float, bytes]:
        monkeypatch.setenv("SOLAR_DEVELOPER_OBSERVABILITY", "1" if enabled else "0")
        started = time.perf_counter()
        digest = hashlib.sha256()
        for _ in range(1600):
            digest.update(payload)
        operator_id, _operator, reason = pm_dispatch.select_operator_by_role(
            "builder",
            task_type="implementation",
            observation_identifiers={"sprint_id": "benchmark", "task_id": "task-1"},
        )
        product_result = json.dumps({
            "digest": digest.hexdigest(),
            "operator_id": operator_id,
            "reason": reason,
        }, sort_keys=True).encode()
        output.write_bytes(product_result)
        return time.perf_counter() - started, product_result

    # Warm imports, allocator policy and file-system paths before comparison.
    run(False, tmp_path / "warm-off.json")
    run(True, tmp_path / "warm-on.json")
    disabled_runs = [run(False, tmp_path / f"off-{index}.json") for index in range(11)]
    enabled_runs = [run(True, tmp_path / f"on-{index}.json") for index in range(11)]
    disabled = statistics.median(item[0] for item in disabled_runs)
    enabled = statistics.median(item[0] for item in enabled_runs)
    regression = (enabled - disabled) / disabled

    assert {item[1] for item in disabled_runs + enabled_runs}.__len__() == 1
    assert trace.is_file() and trace.stat().st_size > 0
    assert regression <= 0.05, {
        "disabled_seconds": disabled,
        "enabled_seconds": enabled,
        "regression": regression,
    }
