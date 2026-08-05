from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from research_orchestration.transport import ResearchTransportError, run_json_worker  # noqa: E402


def _worker(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "worker.py"
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def test_completed_worker_receives_request_on_stdin_only(tmp_path: Path) -> None:
    command = _worker(
        tmp_path,
        """
import json, sys
request = json.loads(sys.stdin.read())
print(json.dumps({"ok": True, "request": request, "argv": sys.argv[1:]}))
""",
    )
    result = run_json_worker(
        command,
        {"task_id": "task-1", "unicode": "hello"},
        cwd=tmp_path,
        timeout_seconds=5,
    )
    assert result["request"]["task_id"] == "task-1"
    assert result["argv"] == []


def test_command_injection_characters_do_not_pass_through_shell(tmp_path: Path) -> None:
    marker = tmp_path / "shell-would-create-this.txt"
    command = _worker(
        tmp_path,
        """
import json, sys
json.loads(sys.stdin.read())
print(json.dumps({"argv": sys.argv[1:]}))
""",
    )
    injected_arg = f"literal; echo bad > {marker}"
    result = run_json_worker(
        [*command, injected_arg],
        {"task_id": "task-1"},
        cwd=tmp_path,
        timeout_seconds=5,
    )
    assert result["argv"] == [injected_arg]
    assert not marker.exists()


def test_nonzero_exit_and_secret_stderr_are_structured_and_scrubbed(tmp_path: Path) -> None:
    command = _worker(
        tmp_path,
        """
import sys
sys.stderr.write("token=sk-" + "a" * 40)
sys.exit(7)
""",
    )
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(command, {"task_id": "task-1"}, cwd=tmp_path, timeout_seconds=5)
    payload = excinfo.value.to_dict()
    assert payload["error_type"] == "nonzero_exit"
    assert payload["exit_code"] == 7
    assert "sk-" not in payload["stderr"]
    assert "[SCRUBBED]" in payload["stderr"]


@pytest.mark.parametrize(
    ("stdout", "error_type"),
    [
        ("", "empty_stdout"),
        ("not-json", "invalid_json"),
        ('{"a": 1}\n{"b": 2}', "multiple_json_values"),
    ],
)
def test_malformed_stdout_is_classified(tmp_path: Path, stdout: str, error_type: str) -> None:
    command = _worker(
        tmp_path,
        f"""
import sys
sys.stdout.write({stdout!r})
""",
    )
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(command, {"task_id": "task-1"}, cwd=tmp_path, timeout_seconds=5)
    assert excinfo.value.error_type == error_type


def test_oversized_output_is_rejected(tmp_path: Path) -> None:
    command = _worker(
        tmp_path,
        """
print("x" * 200)
""",
    )
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(
            command,
            {"task_id": "task-1"},
            cwd=tmp_path,
            timeout_seconds=5,
            max_stdout_bytes=20,
        )
    assert excinfo.value.error_type == "oversized_output"


def test_timeout_kills_worker(tmp_path: Path) -> None:
    command = _worker(
        tmp_path,
        """
import time
time.sleep(30)
""",
    )
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(command, {"task_id": "task-1"}, cwd=tmp_path, timeout_seconds=1)
    assert excinfo.value.error_type == "timeout"


def test_env_allowlist_blocks_provider_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "b" * 40)
    monkeypatch.setenv("ALLOWED_VALUE", "visible")
    command = _worker(
        tmp_path,
        """
import json, os, sys
json.loads(sys.stdin.read())
print(json.dumps({
  "allowed": os.environ.get("ALLOWED_VALUE"),
  "secret": os.environ.get("OPENAI_API_KEY"),
}))
""",
    )
    result = run_json_worker(
        command,
        {"task_id": "task-1"},
        cwd=tmp_path,
        timeout_seconds=5,
        env_allowlist={"ALLOWED_VALUE"},
    )
    assert result["allowed"] == "visible"
    assert result["secret"] is None


def test_request_is_not_placed_in_process_argv(tmp_path: Path) -> None:
    command = _worker(
        tmp_path,
        """
import json, sys
request = json.loads(sys.stdin.read())
print(json.dumps({"argv_text": " ".join(sys.argv), "saw": request["secret_prompt"]}))
""",
    )
    result = run_json_worker(
        command,
        {"secret_prompt": "do-not-put-me-in-argv"},
        cwd=tmp_path,
        timeout_seconds=5,
    )
    assert "do-not-put-me-in-argv" not in result["argv_text"]
    assert result["saw"] == "do-not-put-me-in-argv"


def test_missing_cwd_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ResearchTransportError, match="cwd"):
        run_json_worker(
            [sys.executable, "-c", "print('{}')"],
            {"task_id": "task-1"},
            cwd=tmp_path / "missing",
            timeout_seconds=5,
        )
