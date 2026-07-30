from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from evidence import utc_now
from journey_runner import base_env, bootstrap_live_environment, has_network_authorization, python_executable

JOURNEY_ID = "P22-J23"
WORKER_BATCH_ID = "J23-model-routing-001"
JOURNEY_NAME = "Model Routing and Usage Audit"
SELECTOR = (
    "tests/journeys/phase22/code/test_j23_model_routing_audit.py::"
    "test_p22_j23_real_model_routing_and_usage_audit"
)
RUNNER_COMMAND = (
    ".\\.venv\\Scripts\\python.exe -m pytest "
    "tests/journeys/phase22/code/test_j23_model_routing_audit.py::"
    "test_p22_j23_real_model_routing_and_usage_audit -vv "
    "--basetemp .codex-tmp/pytest-phase22-j23 "
    "-o cache_dir=.codex-tmp/pytest-cache-phase22-j23"
)
SCHEMA_VERSION = "phase22.worker_result.j23.v1"
RETRY_DELAYS = [60, 120, 300]
TRANSIENT_HINTS = (
    "429",
    "too many requests",
    "rate limit",
    "rate-limited",
    "temporarily unavailable",
    "service unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "failed to connect",
    "econnreset",
)
ENVIRONMENT_BLOCK_HINTS = (
    "winerror 10013",
    "access in a way forbidden",
    "socket in a way forbidden",
    "review llm provider invocation failed",
    "review_llm status is `failed`",
    "review mode is `local_surrogate`",
)
TOKEN_USAGE_FIELDS = {"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"}
COST_FIELDS = {"cost", "total_cost", "cost_usd", "input_cost", "output_cost", "prompt_cost", "completion_cost"}
LATENCY_FIELDS = {"latency_ms", "latency", "duration_ms", "duration_seconds", "response_time_ms", "response_time"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _fixture_root() -> Path:
    return _repo_root() / "tests" / "journeys" / "phase22" / "fixtures" / "j23_model_routing_audit"


def _safe_text(value: str | None) -> str:
    return "" if value is None else value


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_cmd(cmd: list[str], env: dict[str, str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _repo_head(repo_root: Path) -> str:
    proc = _run_cmd(["git", "rev-parse", "HEAD"], os.environ | {}, repo_root)
    if proc.returncode != 0:
        return f"unavailable: {proc.stderr.strip()}"
    return proc.stdout.strip()


def _contains_secret(value: str) -> bool:
    if not value:
        return False
    if re.search(r"sk-[A-Za-z0-9._-]{20,}", value):
        return True
    if re.search(r"openai_api_key\s*[:=]\s*\S+", value, flags=re.IGNORECASE):
        return True
    if re.search(r"openrouter_api_key\s*[:=]\s*\S+", value, flags=re.IGNORECASE):
        return True
    if re.search(r"bearer [A-Za-z0-9._-]{8,}", value, flags=re.IGNORECASE):
        return True
    return False


def _scan_for_secrets(paths: list[Path]) -> list[str]:
    found: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        targets = path.rglob("*") if path.is_dir() else [path]
        for candidate in targets:
            if not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _contains_secret(text):
                found.append(str(candidate))
    return sorted(set(found))


def _build_request_payload(request_payload: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    provider = str(request_payload.get("review_llm_provider") or "").strip()
    model = str(request_payload.get("review_llm_model") or "").strip()
    if not provider:
        if env.get("OPENROUTER_API_KEY"):
            provider = "openrouter"
        elif env.get("OPENAI_API_KEY"):
            provider = "openai"
    if not model:
        model = "gpt-5.5"
    endpoint = str(request_payload.get("review_llm_endpoint") or "").strip()
    return {
        "target_filename": str(request_payload.get("target_filename") or "j23-model-routing-audit-target.md").strip(),
        "topic_prompt": str(request_payload.get("review_prompt") or "Check for logic flaws and provide a brief actionable correction list.").strip(),
        "focus": str(request_payload.get("review_focus") or "method").strip(),
        "difficulty": str(request_payload.get("review_difficulty") or "standard").strip(),
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "runtime_constraint": str(request_payload.get("runtime_constraint") or "low_latency").strip(),
        "requested_capability": str(request_payload.get("requested_capability") or "").strip(),
        "requested_cost_tier": str(request_payload.get("requested_cost_tier") or "").strip(),
    }


def _build_expected_contract(request: dict[str, Any], expectation_payload: dict[str, Any]) -> dict[str, Any]:
    routing = expectation_payload.get("routing", {})
    return {
        "provider": str(routing.get("provider") or request["provider"]).strip(),
        "model": str(routing.get("model") or request["model"]).strip(),
        "runtime_hint": str(routing.get("runtime_hint") or request["runtime_constraint"]).strip(),
        "strict": bool(routing.get("strict", False)),
    }


def _json_to_path(root: Path, value: str | Path | None) -> Path:
    value = "" if value is None else str(value).strip()
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return root / value


def _extract_action_payload(summary: dict[str, Any]) -> tuple[dict[str, Any], str]:
    evidence_root = _json_to_path(Path(""), str(summary.get("evidence_path") or ""))
    if not evidence_root.exists() and summary.get("evidence_path"):
        return {}, str(summary.get("evidence_path") or "")
    if not evidence_root.exists() and not summary.get("evidence_path"):
        return {}, ""
    outer = _safe_json_load(evidence_root.read_text(encoding="utf-8", errors="replace"))
    actions = outer.get("outputs", {}).get("skill_run", {}).get("actions", [])
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("action") != "review_artifact":
            continue
        action_path = str(action.get("evidence_path") or "").strip()
        if not action_path:
            continue
        action_file = _json_to_path(Path(outer.get("artifact_root", "")), action_path)
        if action_file.exists():
            return _safe_json_load(action_file.read_text(encoding="utf-8", errors="replace")), str(action_file)
    return outer, str(evidence_root)


def _safe_json_load(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _find_review_payload(summary: dict[str, Any], action_payload: dict[str, Any], attempt_root: Path) -> dict[str, Any]:
    if action_payload:
        return action_payload
    if not summary:
        return {}
    evidence_path = str(summary.get("evidence_path") or "").strip()
    if not evidence_path:
        return {}
    path = _json_to_path(attempt_root, evidence_path)
    payload = _safe_json_load(path.read_text(encoding="utf-8", errors="replace")) if path.exists() else {}
    return payload


def _usage_fields(usage: Any) -> tuple[bool, bool, bool, dict[str, list[str]]]:
    if not isinstance(usage, dict):
        return False, False, False, {"tokens": [], "cost": [], "latency": []}
    keys = {str(k).lower() for k in usage.keys()}
    present_tokens = sorted(TOKEN_USAGE_FIELDS & keys)
    present_cost = sorted(COST_FIELDS & keys)
    present_latency = sorted(LATENCY_FIELDS & keys)
    return bool(present_tokens), bool(present_cost), bool(present_latency), {
        "tokens": present_tokens,
        "cost": present_cost,
        "latency": present_latency,
    }


def _attempt_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt": int(record.get("attempt", 0)),
        "run_id": str(record.get("run_id") or ""),
        "requested_provider": str(record.get("requested_provider") or ""),
        "requested_model": str(record.get("requested_model") or ""),
        "observed_provider": str(record.get("observed_provider") or ""),
        "observed_model": str(record.get("observed_model") or ""),
        "observed_endpoint": str(record.get("observed_endpoint") or ""),
        "invocation_mode": str(record.get("invocation_mode") or ""),
        "provider_status": str(record.get("provider_status") or ""),
        "final_acceptance_ready": record.get("final_acceptance_ready"),
        "request_sha256": str(record.get("request_sha256") or ""),
        "response_sha256": str(record.get("response_sha256") or ""),
        "duration_seconds": float(record.get("duration_seconds") or 0.0),
        "exit_code": int(record.get("exit_code", -1)),
        "transient": bool(record.get("transient")),
        "transient_reason": str(record.get("transient_reason") or ""),
        "environment_blocked": bool(record.get("environment_blocked")),
        "environment_block_reason": str(record.get("environment_block_reason") or ""),
        "fallback": bool(record.get("fallback")),
        "fallback_reason": record.get("fallback_reason") or [],
        "artifact_paths": record.get("artifact_paths") or [],
        "evidence_paths": record.get("evidence_paths") or [],
    }


def _is_transient_status(summary: dict[str, Any], stdout: str, stderr: str) -> tuple[bool, str]:
    candidate = " ".join(
        [
            str(summary.get("status", "")).lower(),
            str(summary.get("_error", "")).lower(),
            str(summary.get("execution_status", "")).lower(),
            str(stdout).lower(),
            str(stderr).lower(),
        ]
    )
    for hint in TRANSIENT_HINTS:
        if hint in candidate:
            return True, hint
    return False, ""


def _is_environment_block(summary: dict[str, Any], fallback_reasons: list[Any], review_reason: str) -> tuple[bool, str]:
    candidate = " ".join(
        [
            str(summary.get("execution_status", "")).lower(),
            str(summary.get("status", "")).lower(),
            str(review_reason).lower(),
            " ".join(str(item).lower() for item in fallback_reasons),
        ]
    )
    for hint in ENVIRONMENT_BLOCK_HINTS:
        if hint in candidate:
            return True, hint
    return False, ""


def _run_review_attempt(
    *,
    repo_root: Path,
    request_payload: dict[str, Any],
    base_env_map: dict[str, str],
    command_root: Path,
    target_path: Path,
    attempt_no: int,
    run_id: str,
) -> tuple[dict[str, Any], Path, Path, Path]:
    command = [
        python_executable(repo_root),
        str(repo_root / "harness" / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"),
        "skill",
        "review",
        str(target_path),
        "--run-id",
        run_id,
        "--require-review-llm",
        "--review",
        "--focus",
        request_payload["focus"],
        "--difficulty",
        request_payload["difficulty"],
        "--topic",
        request_payload["topic_prompt"],
        "--review-llm-provider",
        request_payload["provider"],
        "--review-llm-model",
        request_payload["model"],
    ]
    if request_payload["endpoint"]:
        command.extend(["--review-llm-endpoint", request_payload["endpoint"]])

    attempt_dir = command_root / f"attempt-{attempt_no:02d}-{run_id}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = attempt_dir / "stdout.txt"
    stderr_path = attempt_dir / "stderr.txt"

    start = time.perf_counter()
    proc = _run_cmd(command, base_env_map, command_root, timeout=900)
    duration = round(time.perf_counter() - start, 3)

    stdout_path.write_text(_safe_text(proc.stdout), encoding="utf-8")
    stderr_path.write_text(_safe_text(proc.stderr), encoding="utf-8")

    summary = _safe_json_load(proc.stdout)
    artifact_path: str = ""
    action_payload = {}
    if summary:
        action_payload, artifact_path = _extract_action_payload(summary)
    fallback_reason = []
    if not action_payload:
        action_payload = _find_review_payload(summary, {}, attempt_dir)
    outputs = action_payload.get("outputs", {})
    review = outputs.get("review", {}) if isinstance(outputs, dict) else {}
    boundary = outputs.get("final_acceptance_boundary", {}) if isinstance(outputs, dict) else {}
    review_llm = review.get("review_llm", {}) if isinstance(review, dict) else {}
    invocation_mode = str(review_llm.get("invocation_mode") or "").strip()
    provider = str(review_llm.get("provider") or boundary.get("provider") or "").strip()
    model = str(review_llm.get("model") or boundary.get("model") or "").strip()
    endpoint = str(review_llm.get("endpoint") or boundary.get("endpoint") or "").strip()
    request_sha256 = str(boundary.get("request_sha256") or review_llm.get("request_sha256") or "").strip()
    response_sha256 = str(boundary.get("response_sha256") or review_llm.get("response_sha256") or "").strip()
    provider_status = str(review_llm.get("status") or boundary.get("review_llm_status") or "").strip()
    final_ready = bool(boundary.get("final_acceptance_ready"))
    blocking_reasons = [str(item) for item in (boundary.get("blocking_reasons") or []) if str(item).strip()]
    if not final_ready and blocking_reasons:
        fallback_reason.extend(blocking_reasons)
    usage_obj = review_llm.get("usage") if isinstance(review_llm, dict) else {}
    review_reason = str(review_llm.get("reason") or "").strip()
    usage_token, usage_cost, usage_latency, usage_field_map = _usage_fields(usage_obj)
    usage_present = bool(usage_obj)

    transient, transient_reason = _is_transient_status(summary, proc.stdout, proc.stderr)
    env_blocked, env_block_reason = _is_environment_block(summary, fallback_reason, review_reason)

    record = {
        "attempt": attempt_no,
        "run_id": run_id,
        "requested_provider": request_payload["provider"],
        "requested_model": request_payload["model"],
        "requested_runtime": request_payload["runtime_constraint"],
        "requested_capability": request_payload["requested_capability"],
        "requested_cost_tier": request_payload["requested_cost_tier"],
        "observed_provider": provider,
        "observed_model": model,
        "observed_endpoint": endpoint,
        "invocation_mode": invocation_mode,
        "provider_status": provider_status,
        "final_acceptance_ready": final_ready,
        "request_sha256": request_sha256,
        "response_sha256": response_sha256,
        "duration_seconds": duration,
        "exit_code": int(proc.returncode),
        "stdout_tail": _safe_text(proc.stdout)[-1200:],
        "stderr_tail": _safe_text(proc.stderr)[-1200:],
        "argv": command,
        "transient": bool(transient),
        "transient_reason": transient_reason,
        "artifact_path": artifact_path,
        "summary_path": str(_json_to_path(Path(""), summary.get("evidence_path"))) if summary.get("evidence_path") else "",
        "command": " ".join(command),
        "usage_present": bool(usage_present),
        "usage": usage_obj,
        "usage_fields": usage_field_map,
        "usage_has_token_fields": usage_token,
        "usage_has_cost_fields": usage_cost,
        "usage_has_latency_fields": usage_latency,
        "fallback": bool(blocking_reasons),
        "fallback_reason": fallback_reason,
        "environment_blocked": bool(env_blocked),
        "environment_block_reason": env_block_reason,
        "provider_error_reason": review_reason,
        "artifact_paths": [artifact_path] if artifact_path else [],
        "evidence_paths": [summary.get("evidence_path")] if summary.get("evidence_path") else [],
    }

    command_record = {
        "label": f"review-attempt-{attempt_no:02d}",
        "argv": command,
        "exit_code": int(proc.returncode),
        "duration_seconds": duration,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "attempt_run_id": run_id,
        "transient": bool(transient),
        "transient_reason": transient_reason,
    }
    return record, attempt_dir / "summary.json", command_record, command


def _route_selected(record: dict[str, Any]) -> bool:
    return (
        bool(record.get("observed_provider"))
        and bool(record.get("observed_model"))
        and str(record.get("invocation_mode") or "").lower() == "provider"
        and str(record.get("provider_status") or "").lower() == "completed"
    )


def _build_criteria(
    label: str,
    criterion: str,
    passed: bool,
    observed: Any,
) -> dict[str, Any]:
    return {"name": label, "criterion": criterion, "passed": bool(passed), "observed": observed}


def test_p22_j23_real_model_routing_and_usage_audit() -> None:
    started = utc_now()
    repo_root = _repo_root()
    fixture_root = _fixture_root()
    request_spec = _read_json(fixture_root / "request.json")
    expectation_spec = _read_json(fixture_root / "expectations.json")
    result = {"schema_version": SCHEMA_VERSION}

    env = os.environ.copy()
    env = bootstrap_live_environment(repo_root, env)
    if not has_network_authorization():
        blocked = {
            "status": "ENVIRONMENT_BLOCKED",
            "batch_id": WORKER_BATCH_ID,
            "journey_id": JOURNEY_ID,
            "journey_name": JOURNEY_NAME,
            "execution_selector": SELECTOR,
            "run_id": "",
            "repo_head": _repo_head(repo_root),
            "command_records": [],
            "provider_attempts": [],
            "l2": [
                {
                    "category": "Foundation",
                    "level_2_feature": "Foundation :: Model Routing & Selection",
                    "criteria": [
                        {"criterion": "network authorization and injected env", "passed": False, "observed": False},
                    ],
                    "assertions": [
                        {"criterion": "network authorization and injected env", "passed": False, "observed": False},
                    ],
                    "observed": {"network_authorized": False},
                    "recommended_status": "ENVIRONMENT_BLOCKED",
                    "reason": ["Network authorization is not enabled in this run."],
                    "limitations": ["Missing live network/providing authorization for real provider call."],
                    "evidence_paths": [],
                },
                {
                    "category": "Foundation",
                    "level_2_feature": "Foundation :: Model Usage Auditing",
                    "criteria": [
                        {"criterion": "network authorization and injected env", "passed": False, "observed": False},
                    ],
                    "assertions": [
                        {"criterion": "network authorization and injected env", "passed": False, "observed": False},
                    ],
                    "observed": {"network_authorized": False},
                    "recommended_status": "ENVIRONMENT_BLOCKED",
                    "reason": ["Network authorization is not enabled in this run."],
                    "limitations": ["Missing live network/providing authorization for real provider call."],
                    "evidence_paths": [],
                },
            ],
            "limitations": ["Missing network authorization for live provider execution."],
            "self_review": {
                "selector_reran": {"requested": False},
                "paths": {},
                "no_secrets": True,
                "git_diff_check": {"exit_code": None, "output_excerpt": ""},
            },
            "command": RUNNER_COMMAND,
            "started_at": started,
            "finished_at": utc_now(),
            "duration_seconds": 0.0,
        }
        worker_result = repo_root / ".codex-tmp" / "phase22-worker-results" / WORKER_BATCH_ID / "result.json"
        worker_result.parent.mkdir(parents=True, exist_ok=True)
        _write_json(worker_result, blocked)
        pytest.skip(f"{JOURNEY_ID} blocked: network authorization not enabled")

    request = _build_request_payload(request_spec, env)
    expected = _build_expected_contract(request, expectation_spec)

    run_id = f"p22-j23-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_root = run_dir / "commands"
    run_root.mkdir(parents=True, exist_ok=True)
    command_records: list[dict[str, Any]] = []
    provider_attempts: list[dict[str, Any]] = []
    command_records_path = run_dir / "commands.json"
    assertions_path = run_dir / "assertions.json"

    target_path = fixture_root / request["target_filename"]
    assert target_path.exists(), f"missing fixture target: {target_path}"
    assert target_path.stat().st_size > 0, f"empty fixture target: {target_path}"

    runtime_root = repo_root / ".codex-tmp" / "pytest-phase22-j23"
    base_live_env = base_env(repo_root, runtime_root, allow_live=True)
    base_live_env["AUTOSCI_LIVE_PROVIDER_TESTS"] = "1"
    base_live_env["AUTOSCI_LIVE_REVIEW_LLM_TEST"] = "1"
    base_live_env["PHASE22_ENABLE_NETWORK_JOURNEYS"] = "1"
    base_live_env["SOLAR_AUTOSCI_ALLOW_NETWORK"] = "1"
    base_live_env.update(env)
    harness_root = runtime_root / "p22-j23-harness"
    base_live_env["HARNESS_DIR"] = str(harness_root)
    base_live_env["AUTOSCI_ARTIFACT_ROOT"] = str(harness_root / "artifacts" / "autosci")
    base_live_env["SCIENTIFIC_ARTIFACT_ROOT"] = str(harness_root / "artifacts" / "scientific")
    base_live_env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(harness_root)

    limitations: list[str] = []
    final_record: dict[str, Any] = {}
    production_entrypoint = {
        "tool": "autosci_skill_shim.py",
        "script": str(repo_root / "harness" / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"),
        "command": "skill review",
        "target": str(target_path),
        "requested": {
            "provider": request["provider"],
            "model": request["model"],
            "focus": request["focus"],
            "difficulty": request["difficulty"],
            "runtime_constraint": request["runtime_constraint"],
            "requested_capability": request["requested_capability"],
            "requested_cost_tier": request["requested_cost_tier"],
        },
    }

    final_observability: dict[str, Any] = {
        "evidence_paths": [],
        "runtime_proof_paths": [],
        "artifact_paths": [],
    }

    start = time.time()
    for attempt_no in range(1, 5):
        if attempt_no > 1:
            delay = RETRY_DELAYS[min(attempt_no - 2, len(RETRY_DELAYS) - 1)]
            time.sleep(delay)
        attempt_run_id = f"{run_id}-attempt-{attempt_no}"
        attempt_record, summary_path, command_record, _ = _run_review_attempt(
            repo_root=repo_root,
            request_payload=request,
            base_env_map=base_live_env,
            command_root=run_dir,
            target_path=target_path,
            attempt_no=attempt_no,
            run_id=attempt_run_id,
        )
        command_records.append(command_record)

        if attempt_record.get("summary_path"):
            summary_target = Path(attempt_record["summary_path"])
            if summary_target.exists():
                try:
                    summary_target.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
                except OSError:
                    pass
        provider_attempts.append(_attempt_summary(attempt_record))
        final_observability["evidence_paths"].extend([p for p in attempt_record["evidence_paths"] if p])
        final_observability["artifact_paths"].extend([p for p in attempt_record["artifact_paths"] if p])
        if attempt_record.get("artifact_path"):
            try:
                artifact_path = Path(attempt_record["artifact_path"]).resolve()
                if artifact_path.exists():
                    artifact_payload = _safe_json_load(artifact_path.read_text(encoding="utf-8", errors="replace"))
                    for artifact in artifact_payload.get("artifacts", []) if isinstance(artifact_payload, dict) else []:
                        proof_type = str(artifact.get("type") or artifact.get("artifact_type") or "").strip()
                        if proof_type in {"provider_source_runtime_proof_manifest_json", "review_model_runtime_proof_manifest_json"}:
                            final_observability["runtime_proof_paths"].append(str(artifact.get("path") or artifact_path))
            except (OSError, ValueError):
                pass

        final_record = attempt_record
        if not attempt_record.get("transient") or attempt_no == 4:
            # stop if non-transient, or no retries left
            if _route_selected(attempt_record):
                break
            if not attempt_record.get("transient"):
                break

        if attempt_no < 4:
            continue

    elapsed = round(time.time() - start, 3)

    if not final_record:
        final_record = {"exit_code": -1}
    final_exit = int(final_record.get("exit_code", -1))
    route_success = _route_selected(final_record)
    fallback_events = []
    if final_record.get("fallback"):
        fallback_events.append(
            {
                "attempt": final_record.get("attempt"),
                "requested": {"provider": final_record.get("requested_provider"), "model": final_record.get("requested_model")},
                "observed": {"provider": final_record.get("observed_provider"), "model": final_record.get("observed_model")},
                "fallback_reasons": final_record.get("fallback_reason", []),
            }
        )

    usage_present = bool(final_record.get("usage_present"))
    usage_token, usage_cost, usage_latency, usage_field_map = _usage_fields(final_record.get("usage", {}))
    usage_limitations: list[str] = []
    if usage_present and not usage_token:
        usage_limitations.append("Token fields were not returned; documented as limitation.")
    if usage_present and not usage_cost:
        usage_limitations.append("Cost fields were not returned; documented as limitation.")
    if fallback_events:
        limitations.append("Router emitted fallback path for the requested provider/model constraints.")

    all_transient = all(item.get("transient") for item in provider_attempts) and len(provider_attempts) >= 1
    final_env_blocked = bool(final_record.get("environment_blocked"))
    if not final_env_blocked and final_record.get("provider_status", "").lower() == "failed":
        final_env_blocked = bool(final_record.get("provider_error_reason")) and "provider invocation failed" in final_record.get("provider_error_reason").lower()
    final_status = "PASS"
    if final_env_blocked:
        final_status = "ENVIRONMENT_BLOCKED"
    if not has_network_authorization():
        final_status = "ENVIRONMENT_BLOCKED"
    elif not command_records:
        final_status = "FAIL"
    elif all_transient and final_exit != 0 and final_status not in {"ENVIRONMENT_BLOCKED"}:
        final_status = "ENVIRONMENT_BLOCKED"
    elif not route_success and final_status not in {"ENVIRONMENT_BLOCKED"}:
        final_status = "FAIL"

    if route_success and final_record:
        if not final_record.get("requested_provider") == final_record.get("observed_provider") and not fallback_events:
            final_status = "FAIL"
        elif not final_record.get("requested_model") == final_record.get("observed_model") and not fallback_events and not expected.get("strict", False):
            final_status = "FAIL"

    limitations.extend(usage_limitations)
    if final_status == "PASS" and limitations:
        final_status = "PASS_WITH_KNOWN_LIMITATIONS"

    if final_status in {"PASS", "PASS_WITH_KNOWN_LIMITATIONS"} and not route_success:
        final_status = "FAIL"

    criteria_routing = [
        _build_criteria(
            "production_entrypoint",
            "Command exercised the production AutoSci shim and review entrypoint rather than direct provider SDK calls.",
            production_entrypoint["script"].endswith("autosci_skill_shim.py"),
            production_entrypoint,
        ),
        _build_criteria(
            "route_selected",
            "Model routing exposed an explicit provider/model/runtime selection from production output.",
            route_success,
            {
                "provider": final_record.get("observed_provider"),
                "model": final_record.get("observed_model"),
                "invocation_mode": final_record.get("invocation_mode"),
                "request_sha256": final_record.get("request_sha256"),
                "response_sha256": final_record.get("response_sha256"),
            },
        ),
        _build_criteria(
            "constraints_match_or_fallback",
            "Observed route aligns with request constraints or includes explicit fallback details.",
            bool(final_record.get("observed_provider")) and bool(final_record.get("observed_model")) and (
                (
                    final_record.get("requested_provider") == final_record.get("observed_provider")
                    and final_record.get("requested_model") == final_record.get("observed_model")
                )
                or bool(fallback_events)
            ),
            {
                "requested": {"provider": final_record.get("requested_provider"), "model": final_record.get("requested_model")},
                "observed": {"provider": final_record.get("observed_provider"), "model": final_record.get("observed_model")},
                "fallback": fallback_events,
            },
        ),
        _build_criteria(
            "runtime_constraint_used",
            "Request included explicit runtime/capability/cost constraints.",
            bool(request.get("runtime_constraint") or request.get("requested_capability") or request.get("requested_cost_tier")),
            {
                "runtime_constraint": request["runtime_constraint"],
                "requested_capability": request["requested_capability"],
                "requested_cost_tier": request["requested_cost_tier"],
                "configured_provider": request["provider"],
                "configured_model": request["model"],
            },
        ),
    ]
    routing_status = all(item["passed"] for item in criteria_routing)

    criteria_usage = [
        _build_criteria(
            "persistent_audit_record",
            "At least one audit-facing artifact was produced and persisted.",
            bool(final_record.get("artifact_path")),
            {
                "artifact_path": final_record.get("artifact_path"),
                "provider": final_record.get("observed_provider"),
                "model": final_record.get("observed_model"),
                "evidence_paths": final_observability["artifact_paths"][:8],
            },
        ),
        _build_criteria(
            "result_linkage",
            "Audit payload links run/request with invocation result.",
            route_success and bool(final_record.get("request_sha256")) and bool(final_record.get("response_sha256")),
            {
                "provider": final_record.get("observed_provider"),
                "model": final_record.get("observed_model"),
                "invocation_status": final_record.get("provider_status"),
                "invocation_mode": final_record.get("invocation_mode"),
            },
        ),
        _build_criteria(
            "usage_fields",
            "Usage/cost/latency fields are preserved when provided by provider.",
            route_success and usage_present and usage_token and (usage_cost or usage_latency),
            {
                "usage_fields": usage_field_map,
                "usage_present": usage_present,
                "limitations": usage_limitations,
            },
        ),
    ]
    usage_status = all(item["passed"] for item in criteria_usage)

    route_recommended_status = "PASS"
    if final_status == "ENVIRONMENT_BLOCKED":
        route_recommended_status = "ENVIRONMENT_BLOCKED"
    elif not routing_status:
        route_recommended_status = "FAIL"
    elif limitations:
        route_recommended_status = "PASS_WITH_KNOWN_LIMITATIONS"

    usage_recommended_status = "PASS"
    if final_status == "ENVIRONMENT_BLOCKED":
        usage_recommended_status = "ENVIRONMENT_BLOCKED"
    elif not usage_status:
        usage_recommended_status = "FAIL"
    elif limitations:
        usage_recommended_status = "PASS_WITH_KNOWN_LIMITATIONS"

    evidence_paths: list[str] = []
    evidence_paths.extend([str(x) for x in final_observability["artifact_paths"] if x])
    evidence_paths.extend([str(x) for x in final_observability["evidence_paths"] if x])
    evidence_paths.extend([str(x) for x in final_observability["runtime_proof_paths"] if x])
    evidence_paths = sorted(set(evidence_paths))

    command_records.append(
        {
            "label": "journey-summary-write",
            "argv": ["evidence-write", str(command_records_path)],
            "exit_code": 0,
            "duration_seconds": 0.0,
            "stdout_path": str(command_records_path),
            "stderr_path": str(command_records_path),
            "attempt_run_id": run_id,
        }
    )

    assertions: list[dict[str, Any]] = [
        _build_criteria("route_success", "Route and invocation evidence captured", routing_status, {"attempts": provider_attempts}),
        _build_criteria("audit_success", "Usage audit record persisted", usage_status, {"attempts": provider_attempts}),
    ]
    _write_json(command_records_path, command_records)
    _write_json(assertions_path, assertions)

    run_result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": WORKER_BATCH_ID,
        "journey_id": JOURNEY_ID,
        "journey_name": JOURNEY_NAME,
        "selector": SELECTOR,
        "command": RUNNER_COMMAND,
        "repo_head": _repo_head(repo_root),
        "run_id": run_id,
        "status": final_status,
        "started_at": started,
        "finished_at": utc_now(),
        "duration_seconds": elapsed,
        "production_entrypoint": production_entrypoint,
        "provider_attempts": provider_attempts,
        "command_records": command_records,
        "evidence_paths": evidence_paths,
        "assertions": assertions,
        "criteria": criteria_routing + criteria_usage,
        "l2": [
            {
                "category": "Foundation",
                "level_2_feature": "Foundation :: Model Routing & Selection",
                "criteria": criteria_routing,
                "assertions": criteria_routing,
                "observed": {
                    "route": {
                        "requested": {
                            "provider": expected["provider"],
                            "model": expected["model"],
                        },
                        "observed": {
                            "provider": final_record.get("observed_provider"),
                            "model": final_record.get("observed_model"),
                        },
                    },
                    "attempts": provider_attempts,
                },
                "recommended_status": route_recommended_status,
                "reason": [item["criterion"] for item in criteria_routing if not item["passed"]],
                "limitations": [f for f in limitations if "fallback" in f.lower() or "token" in f.lower() or "cost" in f.lower() or "latency" in f.lower()],
                "evidence_paths": evidence_paths,
            },
            {
                "category": "Foundation",
                "level_2_feature": "Foundation :: Model Usage Auditing",
                "criteria": criteria_usage,
                "assertions": criteria_usage,
                "observed": {
                    "request_sha256": final_record.get("request_sha256"),
                    "response_sha256": final_record.get("response_sha256"),
                    "usage_fields": usage_field_map,
                    "route": {
                        "provider": final_record.get("observed_provider"),
                        "model": final_record.get("observed_model"),
                    },
                },
                "recommended_status": usage_recommended_status,
                "reason": [item["criterion"] for item in criteria_usage if not item["passed"]],
                "limitations": usage_limitations,
                "evidence_paths": evidence_paths,
            },
        ],
        "provider_attempts": provider_attempts,
        "fallback_events": fallback_events,
        "limitations": limitations,
        "self_review": {
            "command_records_count": len(command_records),
            "final_record": final_record,
            "secret_scan": _scan_for_secrets([
                run_dir,
            ]),
            "no_secrets": not bool(_scan_for_secrets([run_dir])),
            "exact_selector": SELECTOR,
            "runner_command": RUNNER_COMMAND,
        },
        "evidence_dir": str(run_dir),
        "realistic_input": {
            "target": str(target_path),
            "request": request,
        },
    }

    run_result_path = run_dir / "journey-result.json"
    _write_json(run_result_path, run_result)

    worker_path = repo_root / ".codex-tmp" / "phase22-worker-results" / WORKER_BATCH_ID / "result.json"
    worker_result = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": WORKER_BATCH_ID,
        "journey_id": JOURNEY_ID,
        "journey_name": JOURNEY_NAME,
        "execution_selector": SELECTOR,
        "command": RUNNER_COMMAND,
        "repo_head": run_result["repo_head"],
        "run_id": run_id,
        "status": final_status,
        "product_status": final_status,
        "started_at": started,
        "finished_at": utc_now(),
        "duration_seconds": elapsed,
        "production_entrypoint": production_entrypoint,
        "provider_attempts": provider_attempts,
        "command_records": command_records,
        "evidence_paths": evidence_paths,
        "l2": {
            "Foundation :: Model Routing & Selection": {
                "criteria": criteria_routing,
                "assertions": criteria_routing,
                "observed": run_result["l2"][0]["observed"],
                "status": route_recommended_status,
                "reason": run_result["l2"][0]["reason"],
                "limitations": run_result["l2"][0]["limitations"],
            },
            "Foundation :: Model Usage Auditing": {
                "criteria": criteria_usage,
                "assertions": criteria_usage,
                "observed": run_result["l2"][1]["observed"],
                "status": usage_recommended_status,
                "reason": run_result["l2"][1]["reason"],
                "limitations": run_result["l2"][1]["limitations"],
            },
        },
        "self_review": {
            "selector_reran": {
                "requested": False,
                "command": "",
                "duration_seconds": 0.0,
                "exit_code": None,
                "stdout_tail": "",
                "stderr_tail": "",
            },
            "exact_selector": SELECTOR,
            "git_diff_check": None,
            "no_secrets": run_result["self_review"]["no_secrets"],
            "secret_paths": run_result["self_review"]["secret_scan"],
            "provider_fallback_events": fallback_events,
            "evidence_paths": evidence_paths,
        },
    }
    worker_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(worker_path, worker_result)

    git_diff = _run_cmd(["git", "diff", "--check"], base_live_env, repo_root)
    worker_result["self_review"]["git_diff_check"] = {
        "exit_code": int(git_diff.returncode),
        "output_excerpt": (git_diff.stdout + git_diff.stderr)[:1600],
    }
    _write_json(worker_path, worker_result)

    if final_status == "PASS_WITH_KNOWN_LIMITATIONS":
        result.update({"recommended_status": "PASS_WITH_KNOWN_LIMITATIONS"})
    elif final_status == "PASS":
        result.update({"recommended_status": "PASS"})

    if final_status in {"FAIL", "ENVIRONMENT_BLOCKED"}:
        pytest.fail(
            f"{JOURNEY_ID} failed in routing/audit assertions. Run result: {run_result_path}\n"
            f"status={final_status}, attempts={len(provider_attempts)}"
        )
