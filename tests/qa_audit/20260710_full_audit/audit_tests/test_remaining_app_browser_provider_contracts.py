from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


LOCKED_ROOT = Path(os.environ["QA_LOCKED_ROOT"]).resolve()
HARNESS = LOCKED_ROOT / "harness"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        cwd=cwd or LOCKED_ROOT,
        env=merged,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _social_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE social_posts ("
        "post_id TEXT, author_handle TEXT, text TEXT, created_at TEXT, "
        "post_url TEXT, reply_count INTEGER, repost_count INTEGER, "
        "like_count INTEGER, view_count INTEGER, urls TEXT)"
    )
    return conn


def test_browser_job_capture_unifies_source_timestamp_and_artifacts(tmp_path, monkeypatch):
    sys.path.insert(0, str(HARNESS / "lib"))
    import browser_job_runtime as runtime

    jobs = tmp_path / "jobs"
    results = tmp_path / "results"
    monkeypatch.setattr(runtime, "BROWSER_JOBS_DIR", jobs)
    monkeypatch.setattr(runtime, "OPERATOR_RESULTS_DIR", results)

    capture = tmp_path / "capture"
    capture.mkdir()
    screenshot = capture / "screenshot.png"
    page_html = capture / "page.html"
    page_text = capture / "page.txt"
    screenshot.write_bytes(b"fixture-png")
    page_html.write_text("<html><title>Fixture</title></html>", encoding="utf-8")
    page_text.write_text("fixture page", encoding="utf-8")

    def fake_probe(job_id, envelope, timeout):
        return {
            "ok": True,
            "state": "done",
            "login_state": "healthy",
            "title": "Fixture",
            "final_url": "https://example.test/source",
            "text_excerpt": "fixture page",
            "artifacts": {
                "screenshot_path": str(screenshot),
                "html_path": str(page_html),
                "text_path": str(page_text),
            },
        }

    monkeypatch.setattr(runtime, "_run_real_browser_probe", fake_probe)
    job_id = runtime.submit_browser_job(
        "audit-browser",
        {"task_id": "capture-1", "url": "https://example.test/source"},
    )
    state = runtime.poll_browser_job(job_id)
    result = runtime.collect_browser_job(job_id, output_dir=results / "capture-1")
    metadata = json.loads((results / "capture-1" / "page.json").read_text(encoding="utf-8"))

    assert state["state"] == "done"
    assert metadata["final_url"] == "https://example.test/source"
    assert result["started_at"] and result["finished_at"]
    assert {Path(path).name for path in result["artifacts"]} >= {
        "screenshot.png",
        "page.html",
        "page.txt",
        "page.json",
    }


def test_browser_job_terminal_failure_is_checkpointed_and_idempotent(tmp_path, monkeypatch):
    sys.path.insert(0, str(HARNESS / "lib"))
    import browser_job_runtime as runtime

    monkeypatch.setattr(runtime, "BROWSER_JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(runtime, "OPERATOR_RESULTS_DIR", tmp_path / "results")
    job_id = runtime.submit_browser_job(
        "audit-browser",
        {"task_id": "failure-1"},
        mock_sequence=["running", "failed"],
    )
    runtime.poll_browser_job(job_id)
    failed = runtime.poll_browser_job(job_id)
    checkpoint = (tmp_path / "jobs" / job_id / "state.json").read_bytes()
    repeated = runtime.poll_browser_job(job_id)
    checkpoint_after = (tmp_path / "jobs" / job_id / "state.json").read_bytes()

    out = tmp_path / "collected"
    first = runtime.collect_browser_job(job_id, output_dir=out)
    files_first = sorted(path.relative_to(out).as_posix() for path in out.rglob("*"))
    second = runtime.collect_browser_job(job_id, output_dir=out)
    files_second = sorted(path.relative_to(out).as_posix() for path in out.rglob("*"))

    assert failed["state"] == repeated["state"] == "failed"
    assert checkpoint == checkpoint_after
    assert first["status"] == second["status"] == "failed"
    assert files_first == files_second


def test_social_cli_reports_unavailable_browser_deterministically():
    sys.path.insert(0, str(HARNESS / "lib"))
    from social_browser_backend_x import cli

    outputs: list[tuple[int, dict[str, object], str]] = []
    for _ in range(2):
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = cli.main(["--backend", "browser", "--json-only"], stdout=stdout, stderr=stderr)
        outputs.append((code, json.loads(stdout.getvalue()), stderr.getvalue()))

    assert outputs[0] == outputs[1]
    code, payload, stderr = outputs[0]
    assert code == cli.EXIT_LEASE_FALLBACK
    assert payload["exit_code"] == cli.EXIT_LEASE_FALLBACK
    assert payload["status"]["browser_ready"] == 0
    assert "no pipeline wired" in payload["message"]
    assert stderr == ""


def test_social_capture_output_contains_source_timestamp_and_artifacts(tmp_path, monkeypatch):
    sys.path.insert(0, str(HARNESS / "lib"))
    from social_browser_backend_x.hard_blocker_guard import CallableResolver, HardBlockerGuard
    from social_browser_backend_x.pipeline import AccountConfig, Pipeline

    monkeypatch.setenv("BROWSER_AGENT_MOCK_MODE", "1")
    socket_path = tmp_path / "thunderomlx.socket"
    socket_path.write_text("fixture", encoding="utf-8")
    pipeline = Pipeline(
        _social_conn(),
        guard=HardBlockerGuard(resolver=CallableResolver(lambda: False), mock_mode_probe=lambda: True),
        thunderomlx_socket=socket_path,
        artifact_root=tmp_path / "artifacts",
    )
    result = pipeline.run(
        accounts=[AccountConfig(handle="karpathy", profile_url="https://x.com/karpathy")],
        requested_backend="auto",
    )
    assert result.posts_stored == 1
    scan = result.scans[0]
    assert scan.post_record is not None
    raw_path = Path(scan.knowledge_raw_path or "")
    queue_path = Path(scan.extract_queue_path or "")
    assert raw_path.is_file() and queue_path.is_file()
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    # The atomic contract requires one captured output to bind provenance,
    # timestamp, and concrete capture artifacts. These assertions expose the
    # current split/omission if the sidecars do not carry them.
    assert raw["source_url"] == scan.post_record.post_url
    assert raw["collected_at"]
    assert queue["artifacts"]["screenshot_path"]


def test_office_supported_and_unsupported_requests_have_executable_contract():
    skill_dir = LOCKED_ROOT / "skills" / "office"
    implementations = [
        path
        for path in skill_dir.rglob("*")
        if path.is_file() and path.name != "SKILL.md" and path.suffix in {".py", ".sh", ".js", ".ts"}
    ]
    assert implementations, "office ships only prose; no executable accepts/rejects requests"


def test_office_missing_provider_emits_structured_failure_contract():
    skill_dir = LOCKED_ROOT / "skills" / "office"
    implementations = [
        path
        for path in skill_dir.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh", ".js", ".ts"}
    ]
    assert implementations, "office has no executable provider boundary to emit failed/inconclusive state"


def test_obsidian_cli_accepts_supported_input_and_rejects_unsupported(tmp_path):
    cli = LOCKED_ROOT / "skills" / "obsidian-direct" / "scripts" / "obsidian_cli.py"
    vault = tmp_path / "vault"
    vault.mkdir()
    created = _run(
        [sys.executable, str(cli), "--vault", str(vault), "--json", "create", "Audit Note", "--content", "fixture"],
    )
    unsupported = _run(
        [sys.executable, str(cli), "--vault", str(vault), "not-a-command"],
    )

    assert created.returncode == 0, created.stderr
    assert (vault / "Audit Note.md").is_file()
    assert unsupported.returncode != 0
    assert "invalid choice" in unsupported.stderr.lower()


def test_obsidian_cli_missing_vault_is_explicit_and_nonfabricating(tmp_path):
    cli = LOCKED_ROOT / "skills" / "obsidian-direct" / "scripts" / "obsidian_cli.py"
    missing = tmp_path / "missing-vault"
    result = _run([sys.executable, str(cli), "--vault", str(missing), "list"])
    assert result.returncode != 0
    assert "Vault not found" in result.stderr
    assert not missing.exists()


def test_calendar_accepts_supported_request_and_rejects_bad_request(tmp_path):
    ops = LOCKED_ROOT / "skills" / "email-to-calendar" / "scripts" / "utils" / "calendar_ops.py"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gog = fake_bin / "gog"
    fake_gog.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"id\":\"fixture-event\",\"status\":\"confirmed\"}'\n",
        encoding="utf-8",
    )
    fake_gog.chmod(0o755)
    env = {"HOME": str(tmp_path / "home"), "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]}
    valid = _run(
        [
            sys.executable,
            str(ops),
            "create",
            "--summary",
            "Audit fixture",
            "--from",
            "2026-07-14T09:00:00",
            "--to",
            "2026-07-14T10:00:00",
            "--provider",
            "gog",
        ],
        env=env,
    )
    invalid = _run([sys.executable, str(ops), "create", "--summary", "missing dates"], env=env)
    unsupported = _run([sys.executable, str(ops), "unknown-action"], env=env)

    assert valid.returncode == 0, valid.stderr
    assert json.loads(valid.stdout)["data"]["id"] == "fixture-event"
    assert invalid.returncode != 0 and "required" in invalid.stderr
    assert unsupported.returncode != 0 and "Unknown action" in unsupported.stderr


def test_calendar_missing_or_unknown_provider_is_typed_failure(tmp_path):
    ops = LOCKED_ROOT / "skills" / "email-to-calendar" / "scripts" / "utils" / "calendar_ops.py"
    env = {"HOME": str(tmp_path / "home"), "PATH": str(tmp_path / "empty-bin")}
    missing = _run(
        [sys.executable, str(ops), "search", "--provider", "gog"],
        env=env,
    )
    unknown = _run(
        [sys.executable, str(ops), "search", "--provider", "not-a-provider"],
        env=env,
    )

    assert missing.returncode != 0
    assert json.loads(missing.stdout) == {"success": False, "error": "gog command not found"}
    assert unknown.returncode != 0
    assert json.loads(unknown.stdout) == {"success": False, "error": "Unknown provider: not-a-provider"}


def test_browser_skill_records_explicit_unavailable_setup_state():
    setup = json.loads(
        (LOCKED_ROOT / "skills" / "browser-automation" / "setup.json").read_text(encoding="utf-8")
    )
    assert setup["setupComplete"] is False
    required = setup["prerequisites"]
    assert required["chrome"] == {
        "required": True,
        "installed": False,
        "description": "Google Chrome browser",
    }
    assert required["apiKey"]["configured"] is False
    assert required["browserCommand"]["installed"] is False


def test_obsidian_wiki_unconfigured_state_is_explicit_and_nonfabricating(tmp_path):
    integration = HARNESS / "integrations" / "obsidian-wiki.sh"
    home = tmp_path / "home"
    result = _run(
        ["bash", str(integration), "status", "--json"],
        env={
            "HOME": str(home),
            "HARNESS_DIR": str(HARNESS),
            "OBSIDIAN_WIKI_OFFLINE": "1",
        },
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["configured"] is False
    assert payload["repo_path"] == ""
    assert payload["vault_path"] == ""
    assert payload["skills_installed"] == {
        "codex": False,
        "claude": False,
        "agents": False,
    }


def test_ragflow_supported_and_unsupported_inputs_are_distinguished(tmp_path):
    adapter = HARNESS / "tools" / "ragflow_adapter.py"
    env = {
        "HOME": str(tmp_path / "home"),
        "HARNESS_DIR": str(HARNESS),
        "SOLAR_RAGFLOW_CONFIG": str(tmp_path / "missing-config.json"),
    }
    supported = _run(
        [sys.executable, str(adapter), "search", "--query", "fixture", "--source", "both", "--json"],
        env=env,
    )
    unsupported = _run(
        [sys.executable, str(adapter), "search", "--query", "fixture", "--source", "bad-source", "--json"],
        env=env,
    )

    assert supported.returncode == 2
    payload = json.loads(supported.stdout)
    assert payload["hits"] == []
    assert payload["degraded"] == ["ragflow:missing_base_url"]
    assert unsupported.returncode != 0
    assert "invalid choice" in unsupported.stderr.lower()


def test_ragflow_unavailable_provider_is_typed_and_never_fakes_hits(tmp_path):
    adapter = HARNESS / "tools" / "ragflow_adapter.py"
    env = {
        "HOME": str(tmp_path / "home"),
        "HARNESS_DIR": str(HARNESS),
        "SOLAR_RAGFLOW_CONFIG": str(tmp_path / "missing-config.json"),
    }
    result = _run(
        [sys.executable, str(adapter), "search", "--query", "fixture", "--json"],
        env=env,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["hits"] == []
    assert payload["degraded"] == ["ragflow:missing_base_url"]


def test_codex_operator_accepts_supported_dispatch_and_rejects_empty(tmp_path):
    operator = HARNESS / "tools" / "codex_operator.py"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        "out=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = '--output-last-message' ]; then shift; out=$1; fi\n"
        "  shift\n"
        "done\n"
        "printf '%s\\n' 'fixture codex result' > \"$out\"\n"
        "printf '%s\\n' 'fixture codex stdout'\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    task_dir = tmp_path / "task"
    env = {
        "HOME": str(tmp_path / "home"),
        "HARNESS_DIR": str(tmp_path / "harness"),
        "TASK_DIR": str(task_dir),
        "CODEX_WORKDIR": str(tmp_path),
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "CODEX_OPERATOR_TIMEOUT_SECONDS": "5",
    }
    valid = _run([sys.executable, str(operator)], env=env, input_text="Perform fixture audit")
    empty = _run([sys.executable, str(operator)], env=env, input_text="")

    assert valid.returncode == 0, valid.stderr
    assert (task_dir / "codex-last-message.md").read_text(encoding="utf-8").strip() == "fixture codex result"
    assert empty.returncode == 64
    assert "empty dispatch" in empty.stderr


def test_codex_operator_missing_cli_emits_structured_failure(tmp_path):
    operator = HARNESS / "tools" / "codex_operator.py"
    env = {
        "HOME": str(tmp_path / "home"),
        "HARNESS_DIR": str(tmp_path / "harness"),
        "TASK_DIR": str(tmp_path / "task"),
        "CODEX_WORKDIR": str(tmp_path),
        "PATH": str(tmp_path / "empty-bin"),
        "CODEX_OPERATOR_TIMEOUT_SECONDS": "5",
    }
    result = _run([sys.executable, str(operator)], env=env, input_text="Perform fixture audit")
    combined = result.stdout + result.stderr

    assert result.returncode != 0
    assert "Traceback" not in combined
    payload_path = tmp_path / "task" / "codex-operator-status.json"
    assert payload_path.is_file()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"failed", "inconclusive"}
    assert payload["reason"] == "codex_cli_unavailable"


def test_browser_automation_unavailable_is_structured_and_nonfabricating():
    setup_path = LOCKED_ROOT / "skills" / "browser-automation" / "setup.json"
    setup = json.loads(setup_path.read_text(encoding="utf-8"))
    skill_dir = setup_path.parent
    runtime_files = [
        path
        for path in skill_dir.rglob("*")
        if path.is_file() and path.suffix in {".py", ".sh", ".js", ".ts", ".mjs", ".cjs"}
    ]

    assert setup["setupComplete"] is False
    assert all(not details.get("installed", details.get("configured", False)) for details in setup["prerequisites"].values())
    assert runtime_files, "setup reports unavailable, but the mapped skill ships no executable that can emit runtime failure evidence"


def test_gemini_deep_research_accepts_supported_request_and_rejects_invalid():
    capabilities = HARNESS / "lib" / "capabilities"
    sys.path.insert(0, str(capabilities))
    from gemini_deep_research.schemas import InvalidResearchRequest, ResearchRequest, Source

    request = ResearchRequest.create("Audit supported request", source="user")
    round_trip = ResearchRequest.from_dict(request.to_dict())
    assert round_trip.question == "Audit supported request"
    assert round_trip.source == Source.USER
    with pytest.raises(InvalidResearchRequest):
        ResearchRequest.create("   ")
    with pytest.raises(InvalidResearchRequest):
        ResearchRequest(question="valid text", source="unsupported", request_id="id", created_at="now")
