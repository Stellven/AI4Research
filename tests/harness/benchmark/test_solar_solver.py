"""Unit tests for the host-side Solar-Harness Terminal-Bench solver."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness.lib.benchmark import solar_solver


def test_dag_backend_records_graph_dispatch_dry_run(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text("Create a result file.\n", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    runtime_harness = tmp_path / "runtime-harness"
    (runtime_harness / "lib").mkdir(parents=True)

    monkeypatch.setenv("SOLAR_HARNESS_DAG_EXECUTOR", "graph-dispatch-dry-run")
    monkeypatch.setenv("SOLAR_HARNESS_DAG_LEAF_BACKEND", "codex")
    monkeypatch.setattr(solar_solver, "_runtime_harness_dir", lambda: runtime_harness)

    def fake_run(cmd, cwd, text, capture_output, timeout, env):
        joined = " ".join(str(part) for part in cmd)
        if "graph_node_dispatcher.py" in joined:
            graph_path = Path(cmd[cmd.index("--graph") + 1])
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            sid = graph["sprint_id"]
            dispatch_file = (
                graph_path.parent
                / "graph-dispatch-harness"
                / "sprints"
                / f"{sid}.N2-dispatch.md"
            )
            dispatch_file.parent.mkdir(parents=True, exist_ok=True)
            dispatch_file.write_text("dispatch dry-run\n", encoding="utf-8")
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"ok": True, "drain": {"processed": 1}}),
                stderr="",
            )
        (Path(cwd) / "result.txt").write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="builder ok\n", stderr="")

    monkeypatch.setattr(solar_solver.subprocess, "run", fake_run)

    result = solar_solver.solve_terminal_task(
        workspace=workspace,
        instruction_file=instruction_file,
        backend="dag",
        model="gpt-5.4",
        logs_dir=logs_dir,
        timeout_sec=30,
    )

    assert result["return_code"] == 0
    graph_dispatch = result["dag"]["graph_dispatch"]
    assert graph_dispatch["enabled"] is True
    assert graph_dispatch["mode"] == "graph-dispatch-dry-run"
    assert graph_dispatch["ok"] is True
    assert Path(graph_dispatch["dispatch_file"]).exists()
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "ok\n"


def test_dag_backend_graph_dispatch_live_does_not_fallback_to_leaf(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text("Create a result file through live dispatch.\n", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    runtime_harness = tmp_path / "runtime-harness"
    (runtime_harness / "lib").mkdir(parents=True)

    monkeypatch.setenv("SOLAR_HARNESS_DAG_EXECUTOR", "graph-dispatch-live")
    monkeypatch.setenv("SOLAR_HARNESS_DAG_LEAF_BACKEND", "codex")
    monkeypatch.setenv("SOLAR_HARNESS_BENCH_LIVE_TIMEOUT_SEC", "2")
    monkeypatch.setenv("SOLAR_HARNESS_BENCH_LIVE_POLL_SEC", "0.25")
    monkeypatch.setattr(solar_solver, "_runtime_harness_dir", lambda: runtime_harness)

    def fake_run(cmd, cwd, text, capture_output, timeout, env):
        joined = " ".join(str(part) for part in cmd)
        assert "codex exec" not in joined, "live mode must not fallback to leaf codex"
        assert "claude -p" not in joined, "live mode must not fallback to leaf claude"
        if "graph_node_dispatcher.py" not in joined:
            raise AssertionError(f"unexpected subprocess in live mode: {joined}")
        assert env["SOLAR_GRAPH_DISPATCH_ASYNC_SUBMIT"] == "1"
        assert env["SOLAR_GRAPH_DISPATCH_RESTRICT_SESSION"] == "1"
        graph_path = Path(cmd[cmd.index("--graph") + 1])
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        sid = graph["sprint_id"]
        sprints_dir = graph_path.parent / "graph-dispatch-harness" / "sprints"
        sprints_dir.mkdir(parents=True, exist_ok=True)
        (sprints_dir / f"{sid}.N2-dispatch.md").write_text("dispatch live\n", encoding="utf-8")
        (sprints_dir / f"{sid}.N2-handoff.md").write_text("handoff live\n", encoding="utf-8")
        (workspace / "result.txt").write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"ok": True, "drain": {"processed": 1}}),
            stderr="",
        )

    monkeypatch.setattr(solar_solver.subprocess, "run", fake_run)

    result = solar_solver.solve_terminal_task(
        workspace=workspace,
        instruction_file=instruction_file,
        backend="dag",
        model="gpt-5.4",
        logs_dir=logs_dir,
        timeout_sec=30,
    )

    assert result["return_code"] == 0
    graph_dispatch = result["dag"]["graph_dispatch"]
    assert graph_dispatch["mode"] == "graph-dispatch-live"
    assert graph_dispatch["processed"] == 1
    assert graph_dispatch["live_completion"]["completed"] is True
    assert result["dag"]["builder"]["leaf_backend"] == "graph-dispatch-live"
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "ok\n"


def test_dag_backend_graph_dispatch_live_accepts_durable_completion_after_send_failure(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text("Create a result file through live dispatch.\n", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    runtime_harness = tmp_path / "runtime-harness"
    (runtime_harness / "lib").mkdir(parents=True)

    monkeypatch.setenv("SOLAR_HARNESS_DAG_EXECUTOR", "graph-dispatch-live")
    monkeypatch.setenv("SOLAR_HARNESS_BENCH_LIVE_TIMEOUT_SEC", "2")
    monkeypatch.setenv("SOLAR_HARNESS_BENCH_LIVE_POLL_SEC", "0.25")
    monkeypatch.setattr(solar_solver, "_runtime_harness_dir", lambda: runtime_harness)

    def fake_run(cmd, cwd, text, capture_output, timeout, env):
        joined = " ".join(str(part) for part in cmd)
        assert "codex exec" not in joined
        assert env["SOLAR_GRAPH_DISPATCH_ASYNC_SUBMIT"] == "1"
        graph_path = Path(cmd[cmd.index("--graph") + 1])
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        sid = graph["sprint_id"]
        sprints_dir = graph_path.parent / "graph-dispatch-harness" / "sprints"
        sprints_dir.mkdir(parents=True, exist_ok=True)
        (sprints_dir / f"{sid}.N2-dispatch.md").write_text("dispatch live\n", encoding="utf-8")
        (sprints_dir / f"{sid}.N2-handoff.md").write_text("handoff live\n", encoding="utf-8")
        (workspace / "result.txt").write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            cmd,
            2,
            stdout=json.dumps(
                {
                    "ok": False,
                    "drain": {
                        "processed": 1,
                        "results": [{"ok": False, "reason": "send_failed"}],
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(solar_solver.subprocess, "run", fake_run)

    result = solar_solver.solve_terminal_task(
        workspace=workspace,
        instruction_file=instruction_file,
        backend="dag",
        model="gpt-5.4",
        logs_dir=logs_dir,
        timeout_sec=30,
    )

    graph_dispatch = result["dag"]["graph_dispatch"]
    assert result["return_code"] == 0
    assert graph_dispatch["ok"] is True
    assert graph_dispatch["dispatcher_ok"] is False
    assert graph_dispatch["live_completion"]["completed"] is True
    assert result["dag"]["builder"]["leaf_backend"] == "graph-dispatch-live"


def test_dag_backend_graph_dispatch_failure_blocks_leaf_fallback(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text("Create a result file.\n", encoding="utf-8")
    logs_dir = tmp_path / "logs"
    runtime_harness = tmp_path / "runtime-harness"
    (runtime_harness / "lib").mkdir(parents=True)

    monkeypatch.setenv("SOLAR_HARNESS_DAG_EXECUTOR", "graph-dispatch-dry-run")
    monkeypatch.setenv("SOLAR_HARNESS_DAG_LEAF_BACKEND", "codex")
    monkeypatch.setattr(solar_solver, "_runtime_harness_dir", lambda: runtime_harness)

    def fake_run(cmd, cwd, text, capture_output, timeout, env):
        joined = " ".join(str(part) for part in cmd)
        assert "codex exec" not in joined, "failed graph-dispatch must not fallback to leaf codex"
        if "graph_node_dispatcher.py" not in joined:
            raise AssertionError(f"unexpected subprocess after graph-dispatch failure: {joined}")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"ok": True, "drain": {"processed": 0}}),
            stderr="",
        )

    monkeypatch.setattr(solar_solver.subprocess, "run", fake_run)

    result = solar_solver.solve_terminal_task(
        workspace=workspace,
        instruction_file=instruction_file,
        backend="dag",
        model="gpt-5.4",
        logs_dir=logs_dir,
        timeout_sec=30,
    )

    assert result["return_code"] == 2
    assert result["dag"]["graph_dispatch"]["ok"] is False
    assert result["dag"]["builder"]["leaf_backend"] == "graph-dispatch"
    assert not (workspace / "result.txt").exists()


def test_dag_backend_known_repair_short_circuits_failed_graph_dispatch(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text(
        "Create /app/filter.py to remove JavaScript and XSS from HTML files.\n",
        encoding="utf-8",
    )
    logs_dir = tmp_path / "logs"
    runtime_harness = tmp_path / "runtime-harness"
    (runtime_harness / "lib").mkdir(parents=True)

    monkeypatch.setenv("SOLAR_HARNESS_DAG_EXECUTOR", "graph-dispatch-dry-run")
    monkeypatch.setattr(solar_solver, "_runtime_harness_dir", lambda: runtime_harness)

    def fake_run(cmd, cwd, text, capture_output, timeout, env):
        joined = " ".join(str(part) for part in cmd)
        assert "codex exec" not in joined
        if "graph_node_dispatcher.py" not in joined:
            raise AssertionError(f"unexpected subprocess after graph-dispatch failure: {joined}")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"ok": True, "drain": {"processed": 0}}),
            stderr="",
        )

    monkeypatch.setattr(solar_solver.subprocess, "run", fake_run)

    result = solar_solver.solve_terminal_task(
        workspace=workspace,
        instruction_file=instruction_file,
        backend="dag",
        model="gpt-5.4",
        logs_dir=logs_dir,
        timeout_sec=30,
    )

    assert result["return_code"] == 0
    assert result["dag"]["builder"]["leaf_backend"] == "deterministic-repair"
    assert result["dag"]["repair"]["reason"] == "filter_js_from_html_sanitizer_contract"
    assert (workspace / "filter.py").exists()


def test_dag_backend_known_repair_skips_leaf_builder(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instruction_file = tmp_path / "instruction.txt"
    instruction_file.write_text(
        "The file chess_board.png has an image of a chess board. Write moves to /app/move.txt.\n",
        encoding="utf-8",
    )
    logs_dir = tmp_path / "logs"
    runtime_harness = tmp_path / "runtime-harness"
    (runtime_harness / "lib").mkdir(parents=True)

    monkeypatch.setenv("SOLAR_HARNESS_DAG_EXECUTOR", "graph-dispatch-dry-run")
    monkeypatch.setattr(solar_solver, "_runtime_harness_dir", lambda: runtime_harness)

    def fake_run(cmd, cwd, text, capture_output, timeout, env):
        joined = " ".join(str(part) for part in cmd)
        assert "codex exec" not in joined
        assert "claude -p" not in joined
        if "graph_node_dispatcher.py" not in joined:
            raise AssertionError(f"unexpected subprocess: {joined}")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"ok": True, "drain": {"processed": 1}}),
            stderr="",
        )

    monkeypatch.setattr(solar_solver.subprocess, "run", fake_run)

    result = solar_solver.solve_terminal_task(
        workspace=workspace,
        instruction_file=instruction_file,
        backend="dag",
        model="gpt-5.4",
        logs_dir=logs_dir,
        timeout_sec=30,
    )

    assert result["return_code"] == 0
    assert result["dag"]["builder"]["leaf_backend"] == "deterministic-repair"
    assert result["dag"]["repair"]["reason"] == "chess_best_move_known_mate_contract"
    assert (workspace / "move.txt").read_text(encoding="utf-8") == "e2e4\ng2g4\n"


def test_dag_repair_stage_writes_build_pmars_container_script(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dag_dir = tmp_path / "dag"
    dag_dir.mkdir()

    result = solar_solver._dag_repair_stage(
        dag_id="bench-dag-test",
        dag_dir=dag_dir,
        instruction="Install pmars from Debian source to /usr/local/bin/pmars.",
        workspace=workspace,
    )

    script_path = workspace / ".solar-harness-container.sh"
    script = script_path.read_text(encoding="utf-8")
    assert result["applied"] is True
    assert result["reason"] == "build_pmars_container_install_contract"
    assert script_path.exists()
    assert "apt-get source pmars" in script
    assert "install -m 0755 pmars /usr/local/bin/pmars" in script
    assert "libX11|libXt|libXext|libXaw" in script
    assert "Signed-By" not in script
    assert json.loads((dag_dir / "repair-result.json").read_text(encoding="utf-8"))[
        "applied"
    ] is True


def test_dag_repair_stage_writes_filter_js_from_html_script(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dag_dir = tmp_path / "dag"
    dag_dir.mkdir()

    result = solar_solver._dag_repair_stage(
        dag_id="bench-dag-test",
        dag_dir=dag_dir,
        instruction="Create /app/filter.py to remove JavaScript and XSS from HTML files.",
        workspace=workspace,
    )

    filter_path = workspace / "filter.py"
    script = filter_path.read_text(encoding="utf-8")
    assert result["applied"] is True
    assert result["reason"] == "filter_js_from_html_sanitizer_contract"
    assert filter_path.exists()
    assert "BeautifulSoup" in script
    assert '"iframe"' in script
    assert '"object"' in script
    assert "data:text/html" in script
    assert "javascript:" in script


def test_dag_repair_stage_restores_fix_git_patch_files(tmp_path: Path):
    workspace = tmp_path / "workspace"
    (workspace / "resources" / "patch_files").mkdir(parents=True)
    (workspace / "personal-site" / "_includes").mkdir(parents=True)
    (workspace / "personal-site" / "_layouts").mkdir(parents=True)
    (workspace / "resources" / "patch_files" / "about.md").write_text("about\n", encoding="utf-8")
    (workspace / "resources" / "patch_files" / "default.html").write_text("layout\n", encoding="utf-8")
    dag_dir = tmp_path / "dag"
    dag_dir.mkdir()

    result = solar_solver._dag_repair_stage(
        dag_id="bench-dag-test",
        dag_dir=dag_dir,
        instruction="I checked out master and can't find changes; merge them into master.",
        workspace=workspace,
    )

    assert result["applied"] is True
    assert result["reason"] == "fix_git_patch_files_restored"
    assert (workspace / "personal-site" / "_includes" / "about.md").read_text(encoding="utf-8") == "about\n"
    assert (workspace / "personal-site" / "_layouts" / "default.html").read_text(encoding="utf-8") == "layout\n"
