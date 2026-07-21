from pathlib import Path
import importlib.util


MODULE = Path(__file__).resolve().parents[2] / "lib" / "multi_task_runner.py"
spec = importlib.util.spec_from_file_location("multi_task_runner", MODULE)
multi_task_runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(multi_task_runner)


def test_runner_script_auto_closes_terminal_window(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    graph = tmp_path / "graph.json"
    graph.write_text('{"nodes":[]}\n', encoding="utf-8")
    handoff = tmp_path / "handoff.md"
    payload = {
        "graph": str(graph),
        "handoff": str(handoff),
        "node_id": "N1",
        "sprint_id": "sprint-demo",
        "role": "builder",
        "profile": "builder",
        "backend": "claude-cli",
        "model": "sonnet",
        "provider": "anthropic",
        "capability_status": "ok",
        "approval_mode": "auto_edit",
        "window": "mt-demo-window",
    }

    runner = multi_task_runner.runner_script(task_dir, payload)
    script = runner.read_text(encoding="utf-8")

    assert "AUTO_CLOSE_TERMINAL_WINDOWS=1" in script
    assert "WINDOW_NAME=mt-demo-window" in script or 'WINDOW_NAME="mt-demo-window"' in script
    assert 'auto_close_window() {' in script
    assert 'tmux kill-window -t "${MT_SESSION}:${WINDOW_NAME}"' in script
    assert 'auto_close_window "terminal"' in script
