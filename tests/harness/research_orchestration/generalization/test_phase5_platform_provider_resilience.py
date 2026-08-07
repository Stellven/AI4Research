from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import uuid
from pathlib import Path
from typing import Any

try:
    import pytest
except ModuleNotFoundError:  # direct WSL probe mode does not need pytest itself
    class _Mark:
        @staticmethod
        def parametrize(*_args: Any, **_kwargs: Any) -> Any:
            def decorate(func: Any) -> Any:
                return func

            return decorate

    class _PytestFallback:
        mark = _Mark()

        class MonkeyPatch:
            pass

    pytest = _PytestFallback()  # type: ignore[assignment]


ROOT = (Path(__file__).resolve().parents[4] / 'harness')
REPO = ROOT.parent
TEST_ROOT = REPO / "tests" / "harness"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from harness.lib.research_orchestration.runtime import (  # noqa: E402
    FileWorkflowCatalog,
    SolarResearchRuntime,
    default_production_resolver,
)
from harness.plugins.autosci.operators.research_synthesis.base import ResearchOperatorError  # noqa: E402
from harness.plugins.autosci.services import production_research  # noqa: E402
from harness.plugins.autosci.services.production_research import (  # noqa: E402
    ResearchModelService,
    _ProviderRoute,
)
from research_orchestration.resolver import PhysicalOperatorBinding, PhysicalOperatorResolver  # noqa: E402


FIXTURE = (
    TEST_ROOT
    / "research_orchestration"
    / "fixtures"
    / "phase5"
    / "platform_provider"
    / "sample synthesis source.md"
)
REPO_FIXTURE = (
    TEST_ROOT
    / "research_orchestration"
    / "fixtures"
    / "phase5"
    / "platform_provider"
    / "sample repo with spaces"
)
# Exercise the checked-out repository with the interpreter that launched the
# test. A developer-specific absolute virtualenv path made this test silently
# depend on another worktree.
WINDOWS_PYTHON = Path(sys.executable).resolve()
BRIDGE = ROOT / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
WORKFLOW_SELECTION = ROOT / "config" / "research-workflow-selection.v1.json"
PROMPT = "Synthesize the Markdown source into a concise resilience report with repository evidence."
CREDENTIAL_CANARY = "phase5CredentialCanaryValue1234567890"
PROVIDER_TOKEN = "phase5-provider-token"
LIVE_PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "AUTOSCI_REVIEW_LLM_API_KEY",
    "AUTOSCI_RESEARCH_LLM_API_KEY",
    "AUTOSCI_RESEARCH_LLM_ENDPOINT",
    "AUTOSCI_RESEARCH_LLM_PROVIDER",
    "AUTOSCI_RESEARCH_ALLOW_OPENAI_FALLBACK",
    "SEMANTIC_SCHOLAR_API_KEY",
)


class _JsonResponse:
    def __init__(self, payload: dict[str, Any] | bytes):
        self.payload = payload

    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class _UrlopenSequence:
    def __init__(self, *items: Any):
        self.items = list(items)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: Any, *, timeout: int) -> _JsonResponse:
        self.calls.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "body_sha256": hashlib.sha256(request.data or b"").hexdigest(),
            }
        )
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _JsonResponse(item)


def _http_error(status: int, *, retry_after: str = "") -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError(
        "https://provider.test/chat/completions",
        status,
        f"HTTP {status}",
        headers,
        None,
    )


def _model_payload(content: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "phase5/fake-model",
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    }


def _service(tmp_path: Path, urlopen: Any) -> ResearchModelService:
    return ResearchModelService(
        workspace_root=tmp_path,
        routes=[
            _ProviderRoute(
                "openai_compatible",
                "https://provider.test/chat/completions",
                "phase5/fake-model",
                PROVIDER_TOKEN,
            )
        ],
        timeout_seconds=4,
        max_attempts=3,
        retry_max_sleep_seconds=0.25,
        urlopen=urlopen,
        clock=lambda: "2026-08-05T00:00:00Z",
    )


def _call_synthesis_model(service: ResearchModelService) -> dict[str, Any]:
    return service(
        node_id="evidence_synthesis",
        task_contract={"user_intent": "Synthesize provider resilience evidence."},
        validated_sources=[
            {
                "source_id": "source-1",
                "title": "Provider resilience source",
                "url": "https://example.test/source",
                "content_summary": "Bounded retry and failure classification evidence.",
            }
        ],
    )


def _single_node_workflow(artifact_root: Path) -> dict[str, Any]:
    return {
        "workflow_id": "phase5_provider_probe_v1",
        "version": 1,
        "workflow_kind": "research_synthesis",
        "start_node": "provider_probe",
        "nodes": [
            {
                "node_id": "provider_probe",
                "depends_on": [],
                "required_for_completion": True,
                "logical_operator": "Phase5ProviderProbe",
                "physical_operator": "phase5_provider_probe_operator",
                "required_capabilities": ["cap.research.synthesis"],
                "read_scope": [str(artifact_root)],
                "write_scope": [str(artifact_root / "provider out")],
                "allow_network": True,
                "allow_live_provider": True,
                "timeout_seconds": 4,
                "max_attempts": 2,
                "gate": "G_PHASE5_PROVIDER_PROBE",
            }
        ],
    }


def _node_result(
    request: dict[str, Any],
    *,
    artifact_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    write_scope = request.get("write_scope") or [str(artifact_root / "provider out")]
    output = Path(str(write_scope[0])) / f"{request['node_id']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact_payload = {
        **payload,
        "artifact_id": "phase5-provider-probe",
        "task_id": request["task_id"],
        "run_id": request["run_id"],
        "workflow_id": request["workflow_id"],
        "node_id": request["node_id"],
    }
    output.write_text(json.dumps(artifact_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "schema": "research_node_result.v1",
        "task_id": request["task_id"],
        "run_id": request["run_id"],
        "workflow_id": request["workflow_id"],
        "node_id": request["node_id"],
        "status": "completed",
        "status_is_terminal": True,
        "output_artifacts": [
            {
                "artifact_id": "phase5-provider-probe",
                "path": str(output),
                "schema": str(artifact_payload.get("schema") or "phase5.provider.probe.v1"),
                "sha256": digest,
            }
        ],
        "evidence": [
            {
                "evidence_id": "phase5-provider-probe-evidence",
                "kind": "provider_probe",
                "summary": "Production provider adapter returned bounded JSON.",
                "artifact_id": "phase5-provider-probe",
            }
        ],
        "hashes": [{"hash_id": "phase5-provider-probe", "algorithm": "sha256", "value": digest}],
        "model_provider_usage": payload.get("provider_usage") or [],
        "errors": [],
        "limitations": [],
        "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
    }


def _failed_node_result(
    request: dict[str, Any],
    *,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema": "research_node_result.v1",
        "task_id": request["task_id"],
        "run_id": request["run_id"],
        "workflow_id": request["workflow_id"],
        "node_id": request["node_id"],
        "status": "failed",
        "status_is_terminal": True,
        "output_artifacts": [],
        "evidence": [],
        "hashes": [],
        "model_provider_usage": [],
        "errors": [{"error_id": "phase5.provider", "error_type": error_type, "message": message[:500]}],
        "limitations": ["Provider failure stopped before accepted node evidence was produced."],
        "secret_redaction_assertion": {"no_secrets_observed": True, "redaction_review": "passed"},
    }


def _scrubbed_env(artifact_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in LIVE_PROVIDER_ENV:
        env.pop(name, None)
    env["HARNESS_DIR"] = str(ROOT)
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(artifact_root)
    env["AUTOSCI_ARTIFACT_ROOT"] = str(artifact_root / "artifacts" / "autosci")
    env["SCIENTIFIC_ARTIFACT_ROOT"] = str(artifact_root / "artifacts" / "scientific")
    env["PHASE5_CREDENTIAL_CANARY"] = CREDENTIAL_CANARY
    return env


def _bridge_args(
    *,
    prompt: str,
    repository: str,
    run_id: str,
    artifact_root: str,
    source: str = "",
) -> list[str]:
    args = [
        "research",
        "--prompt",
        prompt,
        "--repository",
        repository,
        "--run-id",
        run_id,
        "--artifact-root",
        artifact_root,
        "--max-steps",
        "60",
        "--workflow",
        "research_synthesis",
        "--output-language",
        "English",
    ]
    if source:
        args[3:3] = ["--source", source]
    return args


def _host_path(raw_path: str) -> Path:
    text = str(raw_path)
    if text.startswith("/mnt/") and len(text) > 6 and text[6] == "/":
        drive = text[5].upper()
        rest = text[7:].replace("/", "\\")
        return Path(f"{drive}:\\{rest}")
    return Path(text)


def _artifact_path(raw_path: str, *, artifact_root: Path) -> Path:
    path = _host_path(raw_path)
    if path.is_absolute():
        return path
    return artifact_root / path


def _short_artifact_root(label: str) -> Path:
    return REPO / ".codex-tmp" / f"p5 {label} {uuid.uuid4().hex[:8]} root"


def _assert_no_canary_persisted(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt", ".py"}:
            body = path.read_text(encoding="utf-8", errors="ignore")
            assert CREDENTIAL_CANARY not in body, path
            assert PROVIDER_TOKEN not in body, path


def _assert_state_artifacts_hashes(
    payload: dict[str, Any],
    *,
    run_id: str,
    artifact_root: Path,
    expected_status: str,
) -> int:
    assert payload["schema"] == "solar_research_runtime_result.v1"
    assert payload["run_id"] == run_id
    assert payload["task_id"] == f"{run_id}.research"
    assert payload["final_status"] == expected_status
    assert payload["state_path"]
    assert " " in payload["state_path"]
    state_path = _host_path(str(payload["state_path"]))
    assert state_path.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["run_id"] == run_id
    assert state["task_id"] == f"{run_id}.research"
    assert state["final_status"] == expected_status
    verified_hashes = 0
    for node_state in state["node_states"].values():
        result_ref = node_state.get("result_ref")
        if not result_ref:
            continue
        record_path = _host_path(str(result_ref))
        assert record_path.is_file()
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if expected_status == "completed":
            assert record["result"]["status"] == "completed"
        for artifact in record.get("result", {}).get("output_artifacts") or []:
            artifact_path = _artifact_path(str(artifact["path"]), artifact_root=artifact_root)
            assert artifact_path.is_file()
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            assert digest == artifact["sha256"]
            verified_hashes += 1
    return verified_hashes


def _assert_entrypoint_smoke(payload: dict[str, Any], *, run_id: str, artifact_root: Path) -> None:
    _assert_state_artifacts_hashes(
        payload,
        run_id=run_id,
        artifact_root=artifact_root,
        expected_status="awaiting_external",
    )
    _assert_no_canary_persisted(artifact_root)


def _fake_discover_sources(**_kwargs: Any) -> dict[str, Any]:
    return {
        "trace": "phase5_controlled_local_discovery",
        "candidates": [
            {
                "source_id": "source-1",
                "title": "Phase 5 path handling evidence",
                "url": "https://example.test/phase5/path",
                "provider": "local_fixture",
                "metadata": {"fixture": "platform_provider"},
                "content_summary": "Artifact roots and repository inputs with spaces are preserved.",
            },
            {
                "source_id": "source-2",
                "title": "Phase 5 provider resilience evidence",
                "url": "https://example.test/phase5/provider",
                "provider": "local_fixture",
                "metadata": {"fixture": "platform_provider"},
                "content_summary": "Provider failures are classified without credential persistence.",
            },
        ],
        "limitations": ["Controlled local discovery fixture; no live provider or network call was used."],
        "provider_usage": [],
    }


class _ControlledModel:
    def __call__(self, *, node_id: str, **_kwargs: Any) -> dict[str, Any]:
        usage = [
            {
                "provider": "controlled_local",
                "model": "phase5-deterministic",
                "usage_kind": "llm",
                "input_tokens": 0,
                "output_tokens": 0,
            }
        ]
        if node_id == "evidence_synthesis":
            return {
                "claims": [
                    {
                        "claim_id": "claim-001",
                        "text": "Paths with spaces are preserved through the Solar runtime artifact contract.",
                        "evidence_ids": ["source-1"],
                        "uncertainty": "low",
                        "limitations": [],
                    },
                    {
                        "claim_id": "claim-002",
                        "text": "Provider resilience outcomes are explicit and do not persist credentials.",
                        "evidence_ids": ["source-2"],
                        "uncertainty": "low",
                        "limitations": [],
                    },
                ],
                "limitations": ["Deterministic local model fixture; no live provider was called."],
                "provider_usage": usage,
            }
        if node_id == "report_draft":
            return {
                "report": {
                    "title": "Phase 5 Platform Provider Resilience",
                    "body": (
                        "# Phase 5 Platform Provider Resilience\n\n"
                        "## Findings\n\n"
                        "Paths with spaces are preserved through the Solar runtime artifact contract.\n\n"
                        "Provider resilience outcomes are explicit and do not persist credentials.\n\n"
                        "## Limitations\n\n"
                        "Deterministic local model fixture; no live provider was called."
                    ),
                    "sections": [
                        {
                            "title": "Methods",
                            "body": "The run uses production routing with controlled local services.",
                        }
                    ],
                    "conclusions": [
                        {
                            "conclusion_id": "conclusion-001",
                            "text": "Paths with spaces are preserved through the Solar runtime artifact contract.",
                            "evidence_ids": ["claim-001"],
                        },
                        {
                            "conclusion_id": "conclusion-002",
                            "text": "Provider resilience outcomes are explicit and do not persist credentials.",
                            "evidence_ids": ["claim-002"],
                        },
                    ],
                },
                "limitations": ["Deterministic local model fixture; no live provider was called."],
                "provider_usage": usage,
            }
        if node_id == "independent_review":
            return {
                "findings": [
                    {
                        "finding_id": "review-001",
                        "severity": "low",
                        "category": "scope",
                        "message": "Review used controlled local evidence only.",
                    }
                ],
                "verdict_suggestion": "accept",
                "limitations": ["Controlled local review fixture."],
                "provider_usage": usage,
            }
        raise AssertionError(f"unexpected model node: {node_id}")


def _run_completed_platform_probe(artifact_root: Path, *, run_id: str) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    model = _ControlledModel()
    runtime = SolarResearchRuntime(
        artifact_root=artifact_root,
        workflow_loader=FileWorkflowCatalog(
            harness_root=ROOT,
            selection_path=WORKFLOW_SELECTION,
            entrypoint_aliases={"research_synthesis": {"web_fetch": "seed_fetch"}},
        ).load,
        operator_resolver=default_production_resolver(
            services={
                "discover_sources": _fake_discover_sources,
                "model_generate": model,
                "review_model_generate": model,
            },
            workspace_root=artifact_root,
        ),
        authorization={
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "phase5-controlled-local-provider",
            "secret_values": [CREDENTIAL_CANARY],
        },
    )
    return runtime.run(
        prompt=PROMPT,
        run_id=run_id,
        seed_inputs=[{"seed_kind": "topic", "value": PROMPT}],
        explicit_workflow="research_synthesis",
        repository_paths=[str(REPO_FIXTURE)],
        output_language="English",
        max_steps=60,
    )


def _assert_completed_platform_path(payload: dict[str, Any], *, run_id: str, artifact_root: Path) -> None:
    hashes = _assert_state_artifacts_hashes(
        payload,
        run_id=run_id,
        artifact_root=artifact_root,
        expected_status="completed",
    )
    assert hashes > 0
    copied_repo_files = list(artifact_root.rglob("resilience_probe.py"))
    assert copied_repo_files
    original_hash = hashlib.sha256((REPO_FIXTURE / "resilience_probe.py").read_bytes()).hexdigest()
    assert any(hashlib.sha256(path.read_bytes()).hexdigest() == original_hash for path in copied_repo_files)
    assert any(" " in str(path) for path in [artifact_root, *copied_repo_files])
    _assert_no_canary_persisted(artifact_root)


def _wsl_path(path: Path) -> str:
    proc = subprocess.run(
        ["wsl.exe", "-d", "Ubuntu", "--", "wslpath", "-a", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def _wsl_python() -> str:
    venv = REPO / ".codex-tmp" / "phase5-platform-rerun-final-venv" / "bin" / "python"
    return f"{_wsl_path(REPO)}/.codex-tmp/phase5-platform-rerun-final-venv/bin/python" if venv.exists() else "python3"


def test_windows_entrypoint_smoke_is_awaiting_external_not_completed_e2e(tmp_path: Path) -> None:
    del tmp_path
    artifact_root = _short_artifact_root("windows entrypoint")
    run_id = "phase5-windows-entrypoint-smoke"
    assert WINDOWS_PYTHON.is_file()
    command = [
        str(WINDOWS_PYTHON),
        str(BRIDGE),
        *_bridge_args(
            prompt=PROMPT,
            repository=str(REPO_FIXTURE),
            run_id=run_id,
            artifact_root=str(artifact_root),
        ),
    ]
    proc = subprocess.run(
        command,
        cwd=REPO,
        env=_scrubbed_env(artifact_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    _assert_entrypoint_smoke(json.loads(proc.stdout), run_id=run_id, artifact_root=artifact_root)


def test_windows_completed_platform_path_uses_controlled_services_and_hash_contract(tmp_path: Path) -> None:
    del tmp_path
    artifact_root = _short_artifact_root("windows completed")
    run_id = "phase5-windows-completed-platform"

    payload = _run_completed_platform_probe(artifact_root, run_id=run_id)

    _assert_completed_platform_path(payload, run_id=run_id, artifact_root=artifact_root)


def test_wsl_entrypoint_smoke_uses_linux_paths_and_is_not_completed_e2e(tmp_path: Path) -> None:
    del tmp_path
    artifact_root = _short_artifact_root("wsl entrypoint")
    run_id = "phase5-wsl-entrypoint-smoke"
    wsl_root = _wsl_path(ROOT)
    wsl_repo = _wsl_path(REPO)
    wsl_bridge = _wsl_path(BRIDGE)
    wsl_source = _wsl_path(FIXTURE)
    wsl_repository = _wsl_path(REPO_FIXTURE)
    wsl_artifact_root = _wsl_path(artifact_root)
    bridge_args = _bridge_args(
        prompt=PROMPT,
        repository=wsl_repository,
        run_id=run_id,
        artifact_root=wsl_artifact_root,
    )
    script = " ".join(
        [
            f"cd {shlex.quote(wsl_repo)}",
            ";",
            f"HARNESS_DIR={shlex.quote(wsl_root)}",
            f"SOLAR_AUTOSCI_OUTPUT_HARNESS={shlex.quote(wsl_artifact_root)}",
            f"AUTOSCI_ARTIFACT_ROOT={shlex.quote(wsl_artifact_root + '/artifacts/autosci')}",
            f"SCIENTIFIC_ARTIFACT_ROOT={shlex.quote(wsl_artifact_root + '/artifacts/scientific')}",
            f"PHASE5_CREDENTIAL_CANARY={shlex.quote(CREDENTIAL_CANARY)}",
            "env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u AUTOSCI_REVIEW_LLM_API_KEY",
            "-u AUTOSCI_RESEARCH_LLM_API_KEY -u AUTOSCI_RESEARCH_LLM_ENDPOINT",
            "-u AUTOSCI_RESEARCH_LLM_PROVIDER -u AUTOSCI_RESEARCH_ALLOW_OPENAI_FALLBACK",
            "-u SEMANTIC_SCHOLAR_API_KEY",
            shlex.quote(_wsl_python()),
            shlex.quote(wsl_bridge),
            *(shlex.quote(item) for item in bridge_args),
        ]
    )
    proc = subprocess.run(
        ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    _assert_entrypoint_smoke(json.loads(proc.stdout), run_id=run_id, artifact_root=artifact_root)


def test_wsl_completed_platform_path_uses_linux_paths_and_hash_contract(tmp_path: Path) -> None:
    del tmp_path
    artifact_root = _short_artifact_root("wsl completed")
    run_id = "phase5-wsl-completed-platform"
    wsl_repo = _wsl_path(REPO)
    wsl_test = _wsl_path(Path(__file__))
    wsl_artifact_root = _wsl_path(artifact_root)
    script = " ".join(
        [
            f"cd {shlex.quote(wsl_repo)}",
            ";",
            f"HARNESS_DIR={shlex.quote(_wsl_path(ROOT))}",
            shlex.quote(_wsl_python()),
            shlex.quote(wsl_test),
            "--phase5-completed-probe",
            shlex.quote(wsl_artifact_root),
            shlex.quote(run_id),
        ]
    )
    proc = subprocess.run(
        ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    _assert_completed_platform_path(json.loads(proc.stdout), run_id=run_id, artifact_root=artifact_root)


def test_production_provider_adapter_429_retry_after_recovers_on_same_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(production_research.time, "sleep", sleeps.append)
    urlopen = _UrlopenSequence(
        _http_error(429, retry_after="999"),
        _model_payload(
            {
                "claims": [
                    {
                        "claim_id": "claim-001",
                        "text": "Retry-After was capped before provider recovery.",
                        "evidence_ids": ["source-1"],
                        "uncertainty": "low",
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        ),
    )

    response = _call_synthesis_model(_service(tmp_path, urlopen))

    assert response["claims"][0]["claim_id"] == "claim-001"
    assert len(urlopen.calls) == 2
    assert sleeps == [0.25]
    retry_events = response["provider_usage"][0]["retry_events"]
    assert retry_events[0]["status_code"] == 429
    assert retry_events[0]["retry_after"] == "999"
    assert retry_events[0]["delay_seconds"] == 0.25
    assert response["provider_usage"][0]["attempt_count"] == 2


def test_persistent_429_returns_failure_without_infinite_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(production_research.time, "sleep", sleeps.append)
    urlopen = _UrlopenSequence(
        _http_error(429, retry_after="1"),
        _http_error(429, retry_after="1"),
        _http_error(429, retry_after="1"),
    )
    service = _service(tmp_path, urlopen)

    with pytest.raises(ResearchOperatorError) as excinfo:
        _call_synthesis_model(service)

    assert excinfo.value.error_type == "provider_unavailable"
    assert "provider_rate_limited" in str(excinfo.value)
    assert "attempts=3" in str(excinfo.value)
    assert len(urlopen.calls) == 3
    assert sleeps == [0.25, 0.25]


def test_provider_timeout_uses_finite_retry_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(production_research.time, "sleep", sleeps.append)
    urlopen = _UrlopenSequence(
        TimeoutError("deterministic provider timeout"),
        _model_payload(
            {
                "claims": [
                    {
                        "claim_id": "claim-001",
                        "text": "Timeout recovered on bounded retry.",
                        "evidence_ids": ["source-1"],
                        "uncertainty": "medium",
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        ),
    )

    response = _call_synthesis_model(_service(tmp_path, urlopen))

    assert response["claims"][0]["claim_id"] == "claim-001"
    assert len(urlopen.calls) == 2
    assert sleeps == [0.25]
    retry_events = response["provider_usage"][0]["retry_events"]
    assert retry_events[0]["failure"] == "TimeoutError"
    assert retry_events[0]["delay_seconds"] == 0.25


@pytest.mark.parametrize(
    ("stubbed_failure", "expected_text"),
    [
        (_http_error(401), "provider_http_error"),
        (_http_error(503), "provider_http_error"),
        (b"{not-json", "provider_contract"),
    ],
)
def test_provider_hard_failures_are_not_written_as_completed(
    tmp_path: Path,
    stubbed_failure: Any,
    expected_text: str,
) -> None:
    del tmp_path
    artifact_root = _short_artifact_root("hard failure")
    urlopen = _UrlopenSequence(stubbed_failure)
    service = _service(artifact_root, urlopen)

    def run(request: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = _call_synthesis_model(service)
        except ResearchOperatorError as exc:
            return _failed_node_result(
                request,
                error_type=exc.error_type,
                message=str(exc),
            )
        return _node_result(request, artifact_root=artifact_root, payload=payload)

    runtime = SolarResearchRuntime(
        artifact_root=artifact_root,
        workflow_loader=lambda _decision: _single_node_workflow(artifact_root),
        operator_resolver=PhysicalOperatorResolver(
            [PhysicalOperatorBinding("phase5_provider_probe_operator", run, version="phase5.test")]
        ),
        authorization={
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "phase5-local-stub-approval",
        },
    )

    result = runtime.run(
        prompt="Synthesize provider hard failure behavior.",
        run_id=f"phase5-hard-failure-{expected_text.replace('_', '-')}",
        max_steps=4,
    )

    assert result["final_status"] == "failed"
    assert result["node_states"]["provider_probe"]["status"] == "failed"
    record = json.loads(
        Path(result["node_states"]["provider_probe"]["result_ref"]).read_text(encoding="utf-8")
    )
    assert record["result"]["status"] == "failed"
    assert expected_text in json.dumps(record, sort_keys=True)
    assert PROVIDER_TOKEN not in json.dumps(record, sort_keys=True)
    _assert_no_canary_persisted(artifact_root)


def test_retry_does_not_resubmit_completed_upstream_node_after_provider_failure(tmp_path: Path) -> None:
    del tmp_path
    artifact_root = _short_artifact_root("dedupe")
    calls = {"seed": 0, "provider": 0}

    def workflow(_decision: Any) -> dict[str, Any]:
        return {
            "workflow_id": "phase5_retry_dedupe_v1",
            "version": 1,
            "workflow_kind": "research_synthesis",
            "start_node": "seed_probe",
            "nodes": [
                {
                    "node_id": "seed_probe",
                    "depends_on": [],
                    "required_for_completion": True,
                    "logical_operator": "Phase5SeedProbe",
                    "physical_operator": "phase5_seed_probe_operator",
                    "required_capabilities": [],
                    "read_scope": [str(artifact_root)],
                    "write_scope": [str(artifact_root / "seed out")],
                    "allow_network": False,
                    "allow_live_provider": False,
                },
                {
                    "node_id": "provider_probe",
                    "depends_on": ["seed_probe"],
                    "required_for_completion": True,
                    "logical_operator": "Phase5ProviderProbe",
                    "physical_operator": "phase5_provider_probe_operator",
                    "required_capabilities": [],
                    "read_scope": [str(artifact_root)],
                    "write_scope": [str(artifact_root / "provider out")],
                    "allow_network": False,
                    "allow_live_provider": False,
                },
            ],
        }

    def seed_runner(request: dict[str, Any]) -> dict[str, Any]:
        calls["seed"] += 1
        return _node_result(
            request,
            artifact_root=artifact_root,
            payload={"schema": "phase5.seed.v1", "status": "completed"},
        )

    def provider_runner(request: dict[str, Any]) -> dict[str, Any]:
        calls["provider"] += 1
        return _failed_node_result(
            request,
            error_type="provider_unavailable",
            message="provider returned sustained 429",
        )

    runtime = SolarResearchRuntime(
        artifact_root=artifact_root,
        workflow_loader=workflow,
        operator_resolver=PhysicalOperatorResolver(
            [
                PhysicalOperatorBinding("phase5_seed_probe_operator", seed_runner, version="phase5.test"),
                PhysicalOperatorBinding("phase5_provider_probe_operator", provider_runner, version="phase5.test"),
            ]
        ),
        authorization={
            "allow_network": True,
            "allow_live_provider": True,
            "approval_ref": "phase5-local-stub-approval",
        },
    )

    first = runtime.run(prompt="Check retry dedupe.", run_id="phase5-dedupe", max_steps=4)
    resumed = runtime.run(prompt="Check retry dedupe.", run_id="phase5-dedupe", run_mode="resume")

    assert first["final_status"] == "failed"
    assert resumed["final_status"] == "failed"
    assert calls == {"seed": 1, "provider": 1}
    _assert_no_canary_persisted(artifact_root)


def _main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "--phase5-completed-probe":
        payload = _run_completed_platform_probe(Path(argv[2]), run_id=argv[3])
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
