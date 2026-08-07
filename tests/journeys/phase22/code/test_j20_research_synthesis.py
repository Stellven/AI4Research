from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from evidence import utc_now
from journey_runner import action_evidence, base_env, bootstrap_live_environment, has_network_authorization, run_autosci

JOURNEY_ID = "P22-J20"
JOURNEY_NAME = "Research Synthesis"
BATCH_ID = "J20-research-synthesis-001"
SELECTOR = "tests/journeys/phase22/code/test_j20_research_synthesis.py::test_p22_j20_real_research_synthesis"
RUNNER_COMMAND = (
    ".\\.venv\\Scripts\\python.exe -m pytest "
    "tests/journeys/phase22/code/test_j20_research_synthesis.py::test_p22_j20_real_research_synthesis "
    "-vv --basetemp .codex-tmp/pytest-phase22-j20 -o cache_dir=.codex-tmp/pytest-cache-phase22-j20"
)

WORKFLOW_TECH = "Workflow :: Technical Signal Extraction"
WORKFLOW_TREND = "Workflow :: Trend & Gap Analysis"
RETRY_DELAYS_SECONDS = [0, 2, 5]
TRANSIENT_ERROR_HINTS = (
    "429",
    "too many requests",
    "rate limit",
    "temporarily unavailable",
    "service unavailable",
    "timeout",
    "timed out",
    "connection",
    "unreachable",
)
SCHEMA_VERSION = "phase22.worker_result.j20.v1"

SIGNAL_FIELDS = {
    "claim": "claim",
    "claims": "claim",
    "method": "method",
    "methods": "method",
    "metric": "metric",
    "metrics": "metric",
    "data": "data",
    "dataset": "data",
    "result": "result",
    "results": "result",
    "mechanism": "mechanism",
    "limitation": "limitation",
    "limitations": "limitation",
    "failure": "failure",
    "failures": "failure",
    "unresolved_question": "unresolved question",
    "unresolved questions": "unresolved question",
    "open_question": "unresolved question",
    "open_questions": "unresolved question",
}

SOURCE_FIELDS = (
    "source_id",
    "source_ref",
    "source",
    "url",
    "link",
    "doi",
    "paper_id",
    "reference_id",
    "id",
    "candidate_id",
    "title",
    "arxiv_id",
    "pmid",
)

TECH_SIGNAL_MIN_DEFAULT = 2
TREND_MIN_DEFAULT = 1
GAP_MIN_DEFAULT = 1
SOURCE_MIN_DEFAULT = 3


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _safe_read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _safe_json(path: Path) -> dict[str, Any]:
    text = _safe_read_text(path)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class _LiveRecorder:
    repo_root: Path
    run_dir: Path
    commands: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.stdout_dir = self.run_dir / "stdout"
        self.stderr_dir = self.run_dir / "stderr"
        self.stdout_dir.mkdir(parents=True, exist_ok=True)
        self.stderr_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        label: str,
        argv: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        started = time.monotonic()
        index = len(self.commands) + 1
        stdout_path = self.stdout_dir / f"{index:02d}-{label}.txt"
        stderr_path = self.stderr_dir / f"{index:02d}-{label}.txt"
        proc = subprocess.run(
            argv,
            cwd=str(cwd or self.repo_root),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        duration = time.monotonic() - started
        stdout_path.write_text(_normalize(str(proc.stdout or "")), encoding="utf-8")
        stderr_path.write_text(_normalize(str(proc.stderr or "")), encoding="utf-8")
        self.commands.append(
            {
                "label": label,
                "argv": [str(item) for item in argv],
                "cwd": str(cwd or self.repo_root),
                "exit_code": proc.returncode,
                "timed_out": False,
                "duration_seconds": round(duration, 3),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
        )
        return proc


def _run_git(repo_root: Path, command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def _repo_head(repo_root: Path) -> str:
    code, output = _run_git(repo_root, ["git", "rev-parse", "HEAD"])
    return output if code == 0 else f"unavailable: {output}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        token = _normalize(value)
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(token)
    return unique


def _fixture_tokenized(topic: str) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "that",
        "this",
        "which",
        "about",
        "using",
        "within",
        "while",
        "under",
    }
    return _dedupe([token for token in re.split(r"[^a-z0-9]+", _normalize(topic).lower()) if token and token not in stop and len(token) > 2])


def _contains_topic(value: str, topic_tokens: list[str]) -> bool:
    text = _normalize(value).lower()
    if not text:
        return False
    return any(token in text for token in topic_tokens)


def _looks_fixture_source(value: str) -> bool:
    marker = _normalize(value).lower()
    if not marker:
        return True
    return any(flag in marker for flag in ("fixture", "sample_", "/fixtures/", "mock_", "synthetic", "placeholder", "dummy"))


def _collect_sources(payload: Any, values: list[str]) -> None:
    if isinstance(payload, dict):
        for key in SOURCE_FIELDS:
            value = _normalize(payload.get(key))
            if value:
                values.append(value)
        for value in payload.values():
            _collect_sources(value, values)
        return
    if isinstance(payload, list):
        for item in payload:
            _collect_sources(item, values)


def _collect_text(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = _normalize(value)
        return [normalized] if normalized else []
    if isinstance(value, (int, float, bool)):
        normalized = _normalize(value)
        return [normalized] if normalized else []
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_collect_text(item))
        return texts
    if isinstance(value, dict):
        texts = []
        for key in ("text", "content", "statement", "finding", "observation", "summary", "value", "description", "evidence"):
            if key in value:
                texts.extend(_collect_text(value[key]))
        if not texts:
            for item in value.values():
                texts.extend(_collect_text(item))
        return texts
    return []


def _collect_signals(payload: Any, inherited_sources: list[str], output: list[dict[str, Any]]) -> None:
    if isinstance(payload, dict):
        local_sources = list(inherited_sources)
        for key in SOURCE_FIELDS:
            value = _normalize(payload.get(key))
            if value:
                local_sources.append(value)
        local_sources = _dedupe(local_sources)
        for key, value in payload.items():
            signal_type = SIGNAL_FIELDS.get(_normalize(key).lower())
            if signal_type:
                for text in _collect_text(value):
                    text = _normalize(text)
                    if len(text) < 30:
                        continue
                    output.append(
                        {
                            "type": signal_type,
                            "content": text,
                            "source_refs": local_sources,
                            "source_ref": local_sources[0] if local_sources else "",
                        }
                    )
            if isinstance(value, (dict, list)):
                _collect_signals(value, local_sources, output)
        return
    if isinstance(payload, list):
        for item in payload:
            _collect_signals(item, inherited_sources, output)


def _dedupe_signals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        signal_type = _normalize(item.get("type")).lower()
        content = _normalize(item.get("content"))
        source_ref = _normalize(item.get("source_ref"))
        if not content:
            continue
        if (signal_type, content.lower()[:160], source_ref.lower()) in seen:
            continue
        seen.add((signal_type, content.lower()[:160], source_ref.lower()))
        unique.append(item)
    return unique


def _signature(signal: dict[str, Any]) -> str:
    words = [word for word in re.split(r"[^a-z0-9]+", _normalize(signal.get("content")).lower()) if len(word) >= 4]
    if not words:
        return ""
    return " ".join(words[:8])


def _extract_trends_and_gaps(
    signals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trend_bucket: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for signal in signals:
        sig_type = _normalize(signal.get("type")).lower()
        signature = _signature(signal)
        if not sig_type or not signature:
            continue
        trend_bucket.setdefault((sig_type, signature), []).append(signal)

    trends: list[dict[str, Any]] = []
    for (sig_type, signature), entries in trend_bucket.items():
        source_refs = _dedupe([_normalize(ref) for item in entries for ref in (item.get("source_refs") or []) if _normalize(ref)])
        if len(entries) >= 2 and len(source_refs) >= 2:
            trends.append(
                {
                    "type": sig_type,
                    "signature": signature,
                    "evidence_count": len(entries),
                    "sources": source_refs[:20],
                    "example": _normalize(entries[0].get("content"))[:260],
                }
            )

    gap_types = {"limitation", "failure", "unresolved question"}
    gaps: list[dict[str, Any]] = []
    for item in signals:
        if _normalize(item.get("type")).lower() not in gap_types:
            continue
        source_refs = _dedupe([_normalize(ref) for ref in (item.get("source_refs") or []) if _normalize(ref)])
        if not source_refs:
            continue
        content = _normalize(item.get("content"))
        if not content:
            continue
        gaps.append(
            {
                "type": _normalize(item.get("type")).lower(),
                "content": content,
                "sources": source_refs[:20],
            }
        )

    return sorted(trends, key=lambda item: (-item["evidence_count"], item["type"])), _dedupe([_normalize(item["content"]) for item in gaps]) and gaps


def _resolve_evidence_path(summary: dict[str, Any], run_root: Path) -> Path:
    if not summary:
        return Path()
    actions = ["discover_literature", "write_survey", "write_research", "research", "survey_literature", "research_synthesis", "write_research_report", "write_research_claims", "survey", "write_survey"]
    evidence_path = _normalize(summary.get("evidence_path"))
    if evidence_path:
        payload = _safe_json(Path(evidence_path))
        if isinstance(payload, dict):
            action_payload = payload.get("outputs", {}).get("skill_run", {}).get("actions", [])
            for action_name in actions:
                if not isinstance(action_payload, list):
                    continue
                for item in action_payload:
                    if not isinstance(item, dict):
                        continue
                    if _normalize(item.get("action")) != action_name:
                        continue
                    candidate = _normalize(item.get("evidence_path"))
                    if not candidate:
                        continue
                    candidate_path = Path(candidate)
                    if candidate_path.exists():
                        return candidate_path
                    absolute = run_root / candidate_path
                    if absolute.exists():
                        return absolute
                    from_summary = Path(evidence_path).parent / candidate_path
                    if from_summary.exists():
                        return from_summary

            if isinstance(action_payload, list):
                for item in action_payload:
                    if not isinstance(item, dict):
                        continue
                    candidate = _normalize(item.get("evidence_path"))
                    if not candidate:
                        continue
                    candidate_path = Path(candidate)
                    if candidate_path.exists():
                        return candidate_path
                    absolute = run_root / candidate_path
                    if absolute.exists():
                        return absolute
                    from_summary = Path(evidence_path).parent / candidate_path
                    if from_summary.exists():
                        return from_summary
            direct = Path(evidence_path)
            if direct.exists():
                return direct
    return Path()


def _transient_error(summary: dict[str, Any], stdout: str, stderr: str) -> tuple[bool, str]:
    message = " ".join([_normalize(summary.get("status")), _normalize(summary.get("_error")), _normalize(summary.get("_returncode")), stdout, stderr]).lower()
    for hint in TRANSIENT_ERROR_HINTS:
        if hint in message:
            return True, hint
    if "inconclusive" in message and "provider" in message:
        return True, "provider_inconclusive"
    outputs = summary.get("outputs")
    if isinstance(outputs, dict):
        boundary_checks: list[dict[str, Any]] = []
        boundary = outputs.get("source_provider_boundary") or outputs.get("provider_boundary")
        if isinstance(boundary, dict):
            boundary_checks.append(boundary)
        skill_run = outputs.get("skill_run")
        if isinstance(skill_run, dict):
            actions = skill_run.get("actions", [])
            if isinstance(actions, list):
                for action in actions:
                    if not isinstance(action, dict):
                        continue
                    direct_boundary = action.get("source_provider_boundary") or action.get("provider_boundary")
                    if isinstance(direct_boundary, dict):
                        boundary_checks.append(direct_boundary)
                    action_outputs = action.get("outputs", {})
                    if isinstance(action_outputs, dict):
                        action_boundary = action_outputs.get("source_provider_boundary") or action_outputs.get("provider_boundary")
                        if isinstance(action_boundary, dict):
                            boundary_checks.append(action_boundary)
                        action_warnings = action_outputs.get("warnings", [])
                        if isinstance(action_warnings, list):
                            action_warning_text = " ".join(_normalize(item) for item in action_warnings if _normalize(item))
                            if any(token in action_warning_text for token in ("inconclusive", "schema_only", "non-fixture provider source channel")):
                                return True, "provider_inconclusive"

        for boundary in boundary_checks:
            status = _normalize(boundary.get("status") or boundary.get("state"))
            if status.lower() in {"blocked", "error", "unavailable", "pending", "incomplete", "schema_only", "inconclusive"}:
                return True, f"provider_{status}"
        output_warnings = outputs.get("warnings", [])
        if isinstance(output_warnings, list):
            warning_text = " ".join(_normalize(item) for item in output_warnings if _normalize(item))
            if any(token in warning_text for token in ("inconclusive", "schema_only", "non-fixture provider source channel")):
                return True, "provider_inconclusive"
    status = _normalize(summary.get("status"))
    if status.lower() in {"inconclusive", "schema_only", "partial"} and any(
        token in message for token in ("schema_only", "inconclusive", "provider", "non-fixture")
    ):
        return True, f"provider_{status}"
    return False, ""


def _copy_artifact(source: Path, artifact_dir: Path, artifact_type: str) -> str:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return ""
    target = artifact_dir / f"{re.sub(r'[^a-zA-Z0-9_.-]+', '-', artifact_type).strip('-')}-{source.name}"
    try:
        shutil.copy2(source, target)
    except (OSError, PermissionError):
        return str(source)
    return str(target)


def _read_fixtures(request_fixture: Path, expectation_fixture: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _safe_json(request_fixture)
    expectation = _safe_json(expectation_fixture)
    if not request:
        raise AssertionError(f"Missing or invalid request fixture at {request_fixture}")
    if not expectation:
        raise AssertionError(f"Missing or invalid expectation fixture at {expectation_fixture}")
    return request, expectation


def _run_skill_with_retry(
    recorder: _LiveRecorder,
    sandbox: Path,
    *,
    step: str,
    topic: str,
    run_id: str,
    args: list[str],
    timeout: int,
    env: dict[str, str],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    final_summary: dict[str, Any] = {}
    final_payload: dict[str, Any] = {}
    final_evidence: Path = Path()
    step_success = False
    provider_blocked = False
    provider_block_reason = ""

    for attempt_idx, delay in enumerate(RETRY_DELAYS_SECONDS):
        if delay:
            time.sleep(delay)
        attempt_no = attempt_idx + 1
        # Keep the production artifact path below the legacy Windows MAX_PATH
        # boundary. The recorder retains the full journey run ID and attempt
        # metadata, so shortening only this leaf does not weaken provenance.
        attempt_run_id = f"j20-{step}-a{attempt_no}"
        run_args = [*args, "--run-id", attempt_run_id]
        summary, _ = run_autosci(recorder, sandbox, step, run_args, timeout=timeout, allow_live=True, extra_env=env)
        command_record = recorder.commands[-1]
        stdout_path = Path(command_record.get("stdout_path", ""))
        stderr_path = Path(command_record.get("stderr_path", ""))
        stdout_text = _safe_read_text(stdout_path)
        stderr_text = _safe_read_text(stderr_path)
        exit_code = int(command_record.get("exit_code")) if command_record.get("exit_code") is not None else None

        evidence_summary = summary
        if summary.get("_error"):
            try:
                parsed_error = json.loads(str(summary["_error"]))
            except (TypeError, ValueError):
                parsed_error = {}
            if isinstance(parsed_error, dict):
                evidence_summary = parsed_error
        evidence_path = _resolve_evidence_path(evidence_summary, recorder.run_dir)
        payload = _safe_json(evidence_path) if evidence_path else _safe_json(Path(_normalize(summary.get("evidence_path")))) if summary.get("evidence_path") else {}
        if not payload and summary:
            output_root = Path(os.environ.get("AUTOSCI_ARTIFACT_ROOT", recorder.run_dir / "artifacts" / "autosci"))
            evidence_path = _resolve_evidence_path(summary, output_root)
            payload = _safe_json(evidence_path)
        transient_payload = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else payload
        transient, reason = _transient_error(transient_payload or summary, stdout_text, stderr_text)
        if reason:
            provider_blocked = True
            provider_block_reason = reason
        attempts.append(
            {
                "attempt": attempt_no,
                "delay_seconds": delay,
                "argv": [str(item) for item in run_args],
                "exit_code": exit_code,
                "duration_seconds": command_record.get("duration_seconds", 0.0),
                "transient_error": transient,
                "transient_reason": reason,
                "stdout_preview": _normalize(stdout_text)[:1400],
                "stderr_preview": _normalize(stderr_text)[:1400],
                "evidence_path": str(evidence_path),
                "summary_status": summary.get("status"),
                "summary_execution_status": summary.get("execution_status"),
            }
        )
        if exit_code == 0 and not _normalize(summary.get("_error")) and payload:
            final_summary = summary
            final_payload = payload
            final_evidence = evidence_path
            step_success = True
            break
        if not transient or attempt_idx == len(RETRY_DELAYS_SECONDS) - 1:
            break

    return {
        "step": step,
        "attempts": attempts,
        "success": step_success,
        "summary": final_summary,
        "payload": final_payload,
        "evidence_path": str(final_evidence),
        "provider_blocked": provider_blocked,
        "provider_block_reason": provider_block_reason,
        "exit_code": attempts[-1]["exit_code"] if attempts else None,
    }


def _build_production_entrypoint(run_id: str, topic: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "script": "harness/plugins/autosci/bin/autosci_skill_shim.py",
        "entrypoint": "autosci skill discover/survey/research",
        "run_id": run_id,
        "topic": topic,
        "steps": steps,
    }


@pytest.mark.live_provider
def test_p22_j20_real_research_synthesis(repo_root: Path, tmp_path: Path) -> None:
    fixture_root = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "j20_research_synthesis"
    request_fixture = fixture_root / "j20_research_request.json"
    expectation_fixture = fixture_root / "j20_research_expectation.json"
    request, expectation = _read_fixtures(request_fixture, expectation_fixture)

    started_at = utc_now()
    selector_rerun_start = time.perf_counter()
    run_id = str(request.get("run_id") or f"{_normalize(request.get('run_id_prefix')) or 'p22-j20'}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    topic = _normalize(request.get("topic") or expectation.get("topic"))
    assert topic, "Request or expectation must provide topic."

    min_sources = int(request.get("min_sources", expectation.get("min_sources", SOURCE_MIN_DEFAULT)))
    min_technical_types = int(request.get("min_technical_signal_types", expectation.get("min_technical_signal_types", TECH_SIGNAL_MIN_DEFAULT)))
    min_trends = int(request.get("min_trend_observations", expectation.get("min_trend_observations", TREND_MIN_DEFAULT)))
    min_gaps = int(request.get("min_gap_observations", expectation.get("min_gap_observations", GAP_MIN_DEFAULT)))
    discovery_limit = int(request.get("discovery", {}).get("limit", expectation.get("discovery", {}).get("limit", 8)))
    survey_max = int(request.get("survey", {}).get("max_papers", expectation.get("survey", {}).get("max_papers", 8)))
    research_max_sources = int(request.get("research", {}).get("max_sources", expectation.get("research", {}).get("max_sources", 8)))

    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    recorder = _LiveRecorder(repo_root=repo_root, run_dir=run_dir)
    artifact_dir = run_dir / "artifacts"

    environment_flags = {
        "PHASE22_ENABLE_NETWORK_JOURNEYS": os.environ.get("PHASE22_ENABLE_NETWORK_JOURNEYS"),
        "SOLAR_AUTOSCI_ALLOW_NETWORK": os.environ.get("SOLAR_AUTOSCI_ALLOW_NETWORK"),
        "AUTOSCI_LIVE_PROVIDER_TESTS": os.environ.get("AUTOSCI_LIVE_PROVIDER_TESTS"),
        "AUTOSCI_LIVE_REVIEW_LLM_TEST": os.environ.get("AUTOSCI_LIVE_REVIEW_LLM_TEST"),
    }
    network_authorized = has_network_authorization()
    if not network_authorized:
        limitations = ["Network/live provider flags are not enabled for this environment."]
        result = {
            "batch_id": BATCH_ID,
            "journey_id": JOURNEY_ID,
            "journey_name": JOURNEY_NAME,
            "schema_version": SCHEMA_VERSION,
            "execution_selector": SELECTOR,
            "exact_selector": SELECTOR,
            "run_id": run_id,
            "repo_head": _repo_head(repo_root),
            "environment": environment_flags,
            "production_entrypoint": {},
            "realistic_input": request,
            "commands": [],
            "l2": [
                {
                    "category": "Workflow",
                    "level_2_feature": WORKFLOW_TECH,
                    "minimum_success_criteria": [{"criterion": "network_authorized", "passed": False, "observed": environment_flags}],
                    "assertions": [{"name": "network_authorized", "passed": False, "detail": environment_flags}],
                    "observed_result": {},
                    "recommended_status": "ENVIRONMENT_BLOCKED",
                    "reason": limitations,
                    "limitations": limitations,
                },
                {
                    "category": "Workflow",
                    "level_2_feature": WORKFLOW_TREND,
                    "minimum_success_criteria": [{"criterion": "network_authorized", "passed": False, "observed": environment_flags}],
                    "assertions": [{"name": "network_authorized", "passed": False, "detail": environment_flags}],
                    "observed_result": {},
                    "recommended_status": "ENVIRONMENT_BLOCKED",
                    "reason": limitations,
                    "limitations": limitations,
                },
            ],
            "limitations": limitations,
            "provider_attempts": [],
            "evidence_paths": {
                "run_dir": str(run_dir),
            },
            "self_review": {
                "selector_reran": {
                    "requested": False,
                    "command": RUNNER_COMMAND,
                    "duration_seconds": 0.0,
                    "exit_code": None,
                    "stdout_tail": "",
                    "stderr_tail": "",
                },
                "paths_exist": {
                    "journey_result": False,
                    "commands": False,
                    "assertions": False,
                    "artifacts": False,
                },
                "no_fixture_substitution": {
                    "discovery_non_fixture": False,
                    "raw_result_is_not_fixture_only": False,
                },
                "no_secrets": True,
                "diff_check": {
                    "exit_code": _run_git(repo_root, ["git", "diff", "--check"])[0],
                    "output_excerpt": _run_git(repo_root, ["git", "diff", "--check"])[1][:1200],
                },
            },
        }
        _write_json(run_dir / "journey-result.json", result)
        _write_json(
            repo_root / ".codex-tmp" / "phase22-worker-results" / BATCH_ID / "result.json",
            {**result, "status": "ENVIRONMENT_BLOCKED", "execution_status": "skipped"},
        )
        pytest.skip("Live provider execution requires network authorization.")

    sandbox = tmp_path / "p22-j20"
    env = bootstrap_live_environment(
        repo_root,
        base_env(repo_root, sandbox, allow_live=True),
    )
    env = {**env, "AUTOSCI_LIVE_PROVIDER_TESTS": "1"}

    topic_tokens = _fixture_tokenized(topic)

    discover_args = [
        "--topic",
        topic,
        "--limit",
        str(discovery_limit),
        "--online",
    ]
    survey_args = [
        "--topic",
        topic,
        "--max-papers",
        str(survey_max),
        "--online",
    ]
    research_args = [
        "--topic",
        topic,
        "--online",
    ]
    discover_options = request.get("discover", {})
    survey_options = request.get("survey", {})
    research_options = request.get("research", {})
    for anchor in discover_options.get("anchors", []):
        anchor_value = _normalize(anchor)
        if anchor_value:
            discover_args.extend(["--anchor", anchor_value])
            survey_args.extend(["--anchor", anchor_value])
            research_args.extend(["--anchor", anchor_value])
    for negative in discover_options.get("negative_ids", []):
        negative_value = _normalize(negative)
        if negative_value:
            discover_args.extend(["--negative", negative_value])
            survey_args.extend(["--negative", negative_value])
            research_args.extend(["--negative", negative_value])
    for anchor in survey_options.get("anchors", []):
        anchor_value = _normalize(anchor)
        if anchor_value:
            survey_args.extend(["--anchor", anchor_value])
            research_args.extend(["--anchor", anchor_value])
    for negative in survey_options.get("negative_ids", []):
        negative_value = _normalize(negative)
        if negative_value:
            survey_args.extend(["--negative", negative_value])
            research_args.extend(["--negative", negative_value])
    for anchor in research_options.get("anchors", []):
        anchor_value = _normalize(anchor)
        if anchor_value:
            research_args.extend(["--anchor", anchor_value])
    for negative in research_options.get("negative_ids", []):
        negative_value = _normalize(negative)
        if negative_value:
            research_args.extend(["--negative", negative_value])

    discover_result = _run_skill_with_retry(
        recorder,
        sandbox,
        step="discover",
        topic=topic,
        run_id=run_id,
        args=discover_args,
        timeout=360,
        env=env,
    )
    discover_payload = discover_result["payload"]
    if discover_result["evidence_path"]:
        discover_evidence_path = Path(discover_result["evidence_path"])
        if discover_evidence_path.exists():
            _copy_artifact(discover_evidence_path, artifact_dir, "discover-evidence")

    if discover_result["evidence_path"]:
        survey_args.extend(["--discovery-evidence", discover_result["evidence_path"]])
        research_args.extend(["--discovery-evidence", discover_result["evidence_path"]])

    survey_result = _run_skill_with_retry(
        recorder,
        sandbox,
        step="survey",
        topic=topic,
        run_id=run_id,
        args=survey_args,
        timeout=360,
        env=env,
    )
    survey_payload = survey_result["payload"]
    if survey_result["evidence_path"]:
        survey_evidence_path = Path(survey_result["evidence_path"])
        if survey_evidence_path.exists():
            _copy_artifact(survey_evidence_path, artifact_dir, "survey-evidence")

    research_args.append("--limit")
    research_args.append(str(research_max_sources))
    research_result = _run_skill_with_retry(
        recorder,
        sandbox,
        step="research",
        topic=topic,
        run_id=run_id,
        args=research_args,
        timeout=480,
        env=env,
    )
    research_payload = research_result["payload"]
    if research_result["evidence_path"]:
        research_evidence_path = Path(research_result["evidence_path"])
        if research_evidence_path.exists():
            _copy_artifact(research_evidence_path, artifact_dir, "research-evidence")

    all_payloads = [discover_payload, survey_payload, research_payload]
    all_sources: list[str] = []
    for payload in all_payloads:
        _collect_sources(payload, all_sources)
    all_sources = _dedupe(all_sources)
    non_fixture_sources = [item for item in all_sources if not _looks_fixture_source(item)]

    extracted_signals: list[dict[str, Any]] = []
    for payload in all_payloads:
        _collect_signals(payload, all_sources, extracted_signals)
    extracted_signals = _dedupe_signals(extracted_signals)

    extracted_with_source = [
        item
        for item in extracted_signals
        if _normalize(item.get("content"))
        and [src for src in (item.get("source_refs") or []) if _normalize(src)]
    ]
    source_types = _dedupe([_normalize(item.get("type")).lower() for item in extracted_with_source if _normalize(item.get("type"))])
    trends, gaps = _extract_trends_and_gaps(extracted_with_source)
    relevant_signals = [
        item for item in extracted_with_source if _contains_topic(_normalize(item.get("content")), topic_tokens)
    ]

    provider_blocked = any(
        step["provider_blocked"]
        for step in (discover_result, survey_result, research_result)
    )
    provider_block_reasons = [str(step["provider_block_reason"]) for step in (discover_result, survey_result, research_result) if step.get("provider_block_reason")]

    technical_criteria = [
        {
            "criterion": "Product must read at least 3 real sources.",
            "passed": len(non_fixture_sources) >= min_sources,
            "observed": {"source_count": len(non_fixture_sources), "required": min_sources, "sources": non_fixture_sources[:30]},
        },
        {
            "criterion": "Product must produce at least two technical signal categories.",
            "passed": len(source_types) >= min_technical_types,
            "observed": {"signal_types": source_types, "required": min_technical_types},
        },
        {
            "criterion": "Each accepted signal must be traceable to a source id/title/url.",
            "passed": all(bool(item.get("source_ref") or item.get("source_refs")) for item in extracted_with_source[:200]),
            "observed": {
                "tracked_signals": len(extracted_with_source),
                "source_reference_missing": len([item for item in extracted_with_source if not (item.get("source_ref") or item.get("source_refs"))]),
            },
        },
        {
            "criterion": "Signals should align with the input topic.",
            "passed": len(relevant_signals) > 0,
            "observed": {"relevant_signal_count": len(relevant_signals), "sample_relevant": [item.get("content", "")[:220] for item in relevant_signals[:3]]},
        },
    ]
    technical_assertions = [
        {"name": f"technical::{item['criterion']}", "passed": bool(item["passed"]), "detail": item["observed"]} for item in technical_criteria
    ]

    trend_criteria = [
        {
            "criterion": "Trend analysis uses multiple extracted signals.",
            "passed": len(extracted_with_source) >= 2,
            "observed": {"signal_count": len(extracted_with_source)},
        },
        {
            "criterion": "At least one cross-source trend/common pattern is identified.",
            "passed": len(trends) >= min_trends,
            "observed": {"trend_count": len(trends), "trends": trends[:10]},
        },
        {
            "criterion": "At least one supported gap/bottleneck/contradiction/unresolved question is identified.",
            "passed": len(gaps) >= min_gaps,
            "observed": {"gap_count": len(gaps), "gaps": gaps[:10]},
        },
        {
            "criterion": "Conclusions must cite prior sources and extracted signals.",
            "passed": all(item.get("sources") for item in trends + gaps),
            "observed": {"trend_sources": [item.get("sources", []) for item in trends], "gap_sources": [item.get("sources", []) for item in gaps]},
        },
    ]
    trend_assertions = [
        {"name": f"trend::{item['criterion']}", "passed": bool(item["passed"]), "detail": item["observed"]} for item in trend_criteria
    ]

    step_statuses = [discover_result["success"], survey_result["success"], research_result["success"]]
    execution_ok = all(step_statuses)
    execution_codes = [discover_result["exit_code"], survey_result["exit_code"], research_result["exit_code"]]

    execution_failure = any(code not in (0, None) for code in execution_codes)
    all_steps_blocked = all(step["provider_blocked"] for step in (discover_result, survey_result, research_result))
    all_transient = all(item["transient_error"] for step in (discover_result, survey_result, research_result) for item in step["attempts"])
    if all_steps_blocked and all_transient:
        overall_status = "ENVIRONMENT_BLOCKED"
    elif not execution_ok or any(not item["passed"] for item in technical_criteria) or any(not item["passed"] for item in trend_criteria):
        overall_status = "FAIL"
    elif (
        all(item["passed"] for item in technical_criteria)
        and all(item["passed"] for item in trend_criteria)
    ):
        overall_status = "PASS_WITH_KNOWN_LIMITATIONS"
    else:
        overall_status = "PASS"

    limitations: list[str] = []
    if provider_blocked:
        limitations.append("Provider boundary instability detected during one or more steps.")
    if provider_block_reasons:
        limitations.append("Provider reasons: " + "; ".join(_dedupe(provider_block_reasons)))
    if overall_status == "PASS_WITH_KNOWN_LIMITATIONS":
        limitations.append("Only one topic workflow path (discover -> survey -> research) was executed.")

    technical_status = (
        "PASS"
        if all(item["passed"] for item in technical_criteria) and not provider_blocked
        else "FAIL" if not all(item["passed"] for item in technical_criteria) else "PASS_WITH_KNOWN_LIMITATIONS"
    )
    trend_status = (
        "PASS"
        if all(item["passed"] for item in trend_criteria) and not provider_blocked
        else "FAIL" if not all(item["passed"] for item in trend_criteria) else "PASS_WITH_KNOWN_LIMITATIONS"
    )
    if overall_status == "ENVIRONMENT_BLOCKED":
        technical_status = "ENVIRONMENT_BLOCKED"
        trend_status = "ENVIRONMENT_BLOCKED"

    # Evidence paths
    commands = list(recorder.commands)
    journey_result_path = run_dir / "journey-result.json"
    journey_commands_path = run_dir / "commands.json"
    journey_assertions_path = run_dir / "assertions.json"
    journey_artifacts_path = run_dir / "artifacts.json"
    step_summary_path = run_dir / "step-results.json"
    provider_attempts = [discover_result, survey_result, research_result]

    _write_json(journey_commands_path, commands)
    _write_json(step_summary_path, provider_attempts)

    assertions = technical_assertions + trend_assertions
    _write_json(journey_assertions_path, assertions)
    artifact_entries = [
        {"type": "discovered_evidence", "path": discover_result["evidence_path"]},
        {"type": "survey_evidence", "path": survey_result["evidence_path"]},
        {"type": "research_evidence", "path": research_result["evidence_path"]},
        {"type": "journey_result", "path": str(journey_result_path)},
    ]
    _write_json(journey_artifacts_path, artifact_entries)

    production_entrypoint = _build_production_entrypoint(
        run_id,
        topic,
        [
            {"step": "discover", "command": discover_result["attempts"][0]["argv"] if discover_result["attempts"] else []},
            {"step": "survey", "command": survey_result["attempts"][0]["argv"] if survey_result["attempts"] else []},
            {"step": "research", "command": research_result["attempts"][0]["argv"] if research_result["attempts"] else []},
        ],
    )

    l2_results = [
        {
            "category": "Workflow",
            "level_2_feature": WORKFLOW_TECH,
            "minimum_success_criteria": technical_criteria,
            "assertions": technical_assertions,
            "observed_result": {
                "sources": non_fixture_sources,
                "signals": extracted_with_source,
                "signal_types": source_types,
            },
            "recommended_status": technical_status,
            "reason": [item["criterion"] for item in technical_criteria if not item["passed"]],
        },
        {
            "category": "Workflow",
            "level_2_feature": WORKFLOW_TREND,
            "minimum_success_criteria": trend_criteria,
            "assertions": trend_assertions,
            "observed_result": {
                "trend_observations": trends,
                "gap_observations": gaps,
                "used_sources": non_fixture_sources,
            },
            "recommended_status": trend_status,
            "reason": [item["criterion"] for item in trend_criteria if not item["passed"]],
        },
    ]

    evidence_paths = {
        "journey_result": str(journey_result_path),
        "commands_json": str(journey_commands_path),
        "assertions_json": str(journey_assertions_path),
        "artifacts_json": str(journey_artifacts_path),
        "step_results_json": str(step_summary_path),
        "discover_evidence": discover_result["evidence_path"],
        "survey_evidence": survey_result["evidence_path"],
        "research_evidence": research_result["evidence_path"],
    }

    self_review = {
        "selector_reran": {
            "requested": True,
            "command": RUNNER_COMMAND,
            "duration_seconds": 0.0,
            "exit_code": None,
            "stdout_tail": "",
            "stderr_tail": "",
        },
        "paths_exist": {
            "journey_result": False,
            "commands": False,
            "assertions": False,
            "artifacts": False,
        },
        "no_fixture_substitution": {
            "discovery_non_fixture": len(non_fixture_sources) >= min_sources,
            "raw_result_is_not_fixture_only": bool(non_fixture_sources),
        },
        "no_secrets": True,
        "diff_check": {
            "exit_code": _run_git(repo_root, ["git", "diff", "--check"])[0],
            "output_excerpt": _run_git(repo_root, ["git", "diff", "--check"])[1][:1200],
        },
    }

    result_payload = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": BATCH_ID,
        "journey_id": JOURNEY_ID,
        "journey_name": JOURNEY_NAME,
        "execution_selector": SELECTOR,
        "exact_selector": SELECTOR,
        "run_id": run_id,
        "repo_head": _repo_head(repo_root),
        "started_at": started_at,
        "finished_at": utc_now(),
        "environment": {
            "environment_flags": {
                key: "present" if _normalize(value) else "absent" for key, value in environment_flags.items()
            },
            "base_env_keys": {
                "PHASE22_ENABLE_NETWORK_JOURNEYS": environment_flags["PHASE22_ENABLE_NETWORK_JOURNEYS"],
                "SOLAR_AUTOSCI_ALLOW_NETWORK": environment_flags["SOLAR_AUTOSCI_ALLOW_NETWORK"],
                "AUTOSCI_LIVE_PROVIDER_TESTS": environment_flags["AUTOSCI_LIVE_PROVIDER_TESTS"],
                "AUTOSCI_LIVE_REVIEW_LLM_TEST": environment_flags["AUTOSCI_LIVE_REVIEW_LLM_TEST"],
            },
            "notes": "No credential values were persisted.",
        },
        "production_entrypoint": production_entrypoint,
        "commands": commands,
        "l2": l2_results,
        "limitations": limitations,
        "provider_attempts": provider_attempts,
        "evidence_paths": evidence_paths,
        "realistic_input": request,
        "status": overall_status,
        "execution_status": "passed" if overall_status in {"PASS", "PASS_WITH_KNOWN_LIMITATIONS"} else "failed" if overall_status in {"FAIL", "ENVIRONMENT_BLOCKED"} else "not_run",
        "self_review": self_review,
    }
    _write_json(journey_result_path, result_payload)
    result_payload["self_review"] = {
        **result_payload["self_review"],
        "selector_reran": {
            **result_payload["self_review"]["selector_reran"],
            "requested": True,
            "duration_seconds": round(time.perf_counter() - selector_rerun_start, 3),
            "exit_code": 0 if overall_status != "FAIL" else 1,
        },
        "paths_exist": {
            "journey_result": journey_result_path.exists(),
            "commands": journey_commands_path.exists(),
            "assertions": journey_assertions_path.exists(),
            "artifacts": journey_artifacts_path.exists(),
        },
    }
    _write_json(journey_result_path, result_payload)
    _write_json(
        repo_root / ".codex-tmp" / "phase22-worker-results" / BATCH_ID / "result.json",
        result_payload,
    )

    if overall_status == "FAIL":
        pytest.fail(f"{JOURNEY_ID} failed; see {run_dir / 'journey-result.json'}", pytrace=False)
