from __future__ import annotations

import os
import sys
import time
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
    monkeypatch.setenv("HOME", str(tmp_path / "private-home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "private-profile"))
    monkeypatch.setenv("TEMP", str(tmp_path / "private-temp"))
    monkeypatch.setenv("ALLOWED_VALUE", "visible")
    command = _worker(
        tmp_path,
        """
import json, os, sys
json.loads(sys.stdin.read())
print(json.dumps({
  "allowed": os.environ.get("ALLOWED_VALUE"),
  "secret": os.environ.get("OPENAI_API_KEY"),
  "home": os.environ.get("HOME"),
  "profile": os.environ.get("USERPROFILE"),
  "temp": os.environ.get("TEMP"),
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
    assert result["home"] is None
    assert result["profile"] is None
    assert result["temp"] is None


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


def test_failed_worker_diagnostics_omit_request_body(tmp_path: Path) -> None:
    command = _worker(
        tmp_path,
        """
import json, sys
request = json.loads(sys.stdin.read())
query = request["typed_inputs"]["payload"]["query"]
sys.stdout.write("echoed request: " + query)
sys.stderr.write("failed while handling " + query)
sys.exit(2)
""",
    )
    request = {
        "typed_inputs": {"payload": {"query": "private research body canary"}}
    }
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(command, request, cwd=tmp_path, timeout_seconds=5)
    rendered = str(excinfo.value.to_dict())
    assert "private research body canary" not in rendered
    assert "[SCRUBBED]" in rendered


def test_missing_cwd_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ResearchTransportError, match="cwd"):
        run_json_worker(
            [sys.executable, "-c", "print('{}')"],
            {"task_id": "task-1"},
            cwd=tmp_path / "missing",
            timeout_seconds=5,
        )


@pytest.mark.parametrize("stream_fd", [1, 2])
def test_malicious_subprocess_is_stopped_while_streaming_over_limit(
    tmp_path: Path, stream_fd: int
) -> None:
    command = _worker(
        tmp_path,
        f"""
import os, time
chunk = b"x" * 65536
for _ in range(256):
    os.write({stream_fd}, chunk)
time.sleep(30)
""",
    )
    started = time.monotonic()
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(
            command,
            {"task_id": "task-1"},
            cwd=tmp_path,
            timeout_seconds=10,
            max_stdout_bytes=32_768,
            max_stderr_bytes=32_768,
        )
    elapsed = time.monotonic() - started
    payload = excinfo.value.to_dict()
    assert payload["error_type"] == "oversized_output"
    assert elapsed < 5
    assert len(payload.get("stdout", "").encode("utf-8")) <= 32_768
    assert len(payload.get("stderr", "").encode("utf-8")) <= 32_768


def test_timeout_kills_spawned_child_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived.txt"
    child_code = (
        "import time; from pathlib import Path; time.sleep(2); "
        f"Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    command = _worker(
        tmp_path,
        f"""
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", {child_code!r}])
time.sleep(30)
""",
    )
    with pytest.raises(ResearchTransportError) as excinfo:
        run_json_worker(command, {"task_id": "task-1"}, cwd=tmp_path, timeout_seconds=1)
    assert excinfo.value.error_type == "timeout"
    time.sleep(2.5)
    assert not marker.exists()


def test_nested_transport_diagnostics_scrub_keys_values_and_request_bodies() -> None:
    canary = "explicit-diagnostic-canary-123456"
    error = ResearchTransportError(
        "provider_error",
        f"Bearer bearer-secret-value-12345 api_key={canary}",
        stderr="password=visible-password",
        details={
            "nested": {"token": canary},
            "request_body": {"prompt": "must-not-be-recorded"},
        },
        secret_values=(canary,),
    )
    rendered = str(error.to_dict())
    assert canary not in rendered
    assert "bearer-secret-value" not in rendered
    assert "visible-password" not in rendered
    assert "must-not-be-recorded" not in rendered

    json_error = ResearchTransportError(
        "provider_error",
        "provider failed",
        stderr='{"api_key":"json-secret-value-12345"}',
    )
    assert "json-secret-value" not in str(json_error.to_dict())
