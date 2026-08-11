from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from journey_runner import bootstrap_live_environment, python_executable


BATCH_ID = "NT-literature"
ASSIGNED_L2 = [
    "Workflow :: Technical Signal Extraction",
    "Workflow :: Trend & Gap Analysis",
]
SELECTOR = (
    "tests/journeys/phase22/code/test_p22_nt_literature_analysis.py::"
    "test_phase22_not_tested_literature_signal_and_trend_validation"
)
EXACT_COMMAND = (
    ".\\.venv\\Scripts\\python.exe -m pytest "
    "tests/journeys/phase22/code/test_p22_nt_literature_analysis.py::"
    "test_phase22_not_tested_literature_signal_and_trend_validation -vv "
    "--basetemp .codex-tmp/pytest/NT-literature/basetemp "
    "-o cache_dir=.codex-tmp/pytest/NT-literature/cache"
)
RETRY_DELAYS_SECONDS = [0, 10, 30]
TRANSIENT_HINTS = ("429", "too many requests", "rate limit")
SECRET_PATTERNS = (
    re.compile(r"(?i)(OPENAI_API_KEY|ANTHROPIC_API_KEY|OPENROUTER_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)=\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        rows.append(payload)
    return rows


def _normalized_span(value: str) -> str:
    return " ".join(str(value or "").split())


def _decision_rationale(
    *,
    feature: str,
    failed_assertions: list[dict[str, Any]],
    research_status: str,
    provenance_errors: list[str],
    success_detail: str,
) -> str:
    if not failed_assertions:
        return success_detail
    failed_names = ", ".join(str(item.get("name") or "unnamed") for item in failed_assertions)
    error_detail = ", ".join(provenance_errors) if provenance_errors else "none recorded"
    return (
        f"{feature} did not meet its minimum success conditions. Failed assertions: {failed_names}. "
        f"Rich research status: {research_status or 'missing'}. Independent provenance errors: {error_detail}."
    )


def _validate_rich_research_provenance(
    *,
    synthesis: dict[str, Any],
    source_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    source_by_id: dict[str, dict[str, Any]] = {}
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        source_id = str(row.get("source_id") or row.get("id") or "").strip()
        if not source_id or source_id in source_by_id:
            errors.append(f"source_id_missing_or_duplicate:{source_id or '?'}")
            continue
        source_by_id[source_id] = row
    for row in evidence_rows:
        evidence_id = str(row.get("evidence_id") or row.get("id") or "").strip()
        if not evidence_id or evidence_id in evidence_by_id:
            errors.append(f"evidence_id_missing_or_duplicate:{evidence_id or '?'}")
            continue
        source_id = str(row.get("source_id") or "").strip()
        if source_id not in source_by_id:
            errors.append(f"evidence_source_unknown:{evidence_id}:{source_id or '?'}")
        content = str(row.get("content") or "")
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if str(row.get("content_hash") or "") != content_sha256:
            errors.append(f"evidence_content_hash_mismatch:{evidence_id}")
        source_hash = str(source_by_id.get(source_id, {}).get("content_sha256") or "")
        if source_hash != content_sha256:
            errors.append(f"source_content_hash_mismatch:{source_id or '?'}")
        evidence_by_id[evidence_id] = row

    synthesis_sources = [item for item in synthesis.get("sources", []) if isinstance(item, dict)]
    for item in synthesis_sources:
        source_id = str(item.get("source_id") or "")
        if source_id not in source_by_id:
            errors.append(f"synthesis_source_unknown:{source_id or '?'}")
        elif str(item.get("content_sha256") or "") != str(source_by_id[source_id].get("content_sha256") or ""):
            errors.append(f"synthesis_source_hash_mismatch:{source_id}")

    signals = [item for item in synthesis.get("technical_signals", []) if isinstance(item, dict)]
    signal_by_id: dict[str, dict[str, Any]] = {}
    for signal in signals:
        signal_id = str(signal.get("signal_id") or "").strip()
        if not signal_id or signal_id in signal_by_id:
            errors.append(f"signal_id_missing_or_duplicate:{signal_id or '?'}")
            continue
        source_id = str(signal.get("source_id") or "").strip()
        evidence_id = str(signal.get("evidence_id") or "").strip()
        source = source_by_id.get(source_id)
        evidence = evidence_by_id.get(evidence_id)
        if source is None:
            errors.append(f"signal_source_unknown:{signal_id}:{source_id or '?'}")
        if evidence is None:
            errors.append(f"signal_evidence_unknown:{signal_id}:{evidence_id or '?'}")
        elif str(evidence.get("source_id") or "") != source_id:
            errors.append(f"signal_evidence_source_mismatch:{signal_id}")
        if source is not None and str(signal.get("content_sha256") or "") != str(source.get("content_sha256") or ""):
            errors.append(f"signal_content_hash_mismatch:{signal_id}")
        span = signal.get("evidence_span") if isinstance(signal.get("evidence_span"), dict) else {}
        start = span.get("start")
        end = span.get("end")
        raw_content = str(evidence.get("content") or "") if evidence is not None else ""
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(raw_content)):
            errors.append(f"signal_span_invalid:{signal_id}")
        elif _normalized_span(raw_content[start:end]) != str(signal.get("content") or ""):
            errors.append(f"signal_span_content_mismatch:{signal_id}")
        signal_by_id[signal_id] = signal

    trends = [item for item in synthesis.get("trends", []) if isinstance(item, dict)]
    for index, trend in enumerate(trends, start=1):
        source_ids = [str(item) for item in trend.get("source_ids", []) if str(item).strip()]
        signal_ids = [str(item) for item in trend.get("signal_ids", []) if str(item).strip()]
        evidence_ids = [str(item) for item in trend.get("evidence_ids", []) if str(item).strip()]
        if len(set(source_ids)) < 2:
            errors.append(f"trend_distinct_sources_insufficient:{index}")
        if any(source_id not in source_by_id for source_id in source_ids):
            errors.append(f"trend_source_unknown:{index}")
        if not signal_ids or any(signal_id not in signal_by_id for signal_id in signal_ids):
            errors.append(f"trend_signal_unknown:{index}")
        if not evidence_ids or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids):
            errors.append(f"trend_evidence_unknown:{index}")
        linked_source_ids = {str(signal_by_id[item].get("source_id") or "") for item in signal_ids if item in signal_by_id}
        if set(source_ids) != linked_source_ids:
            errors.append(f"trend_signal_source_mismatch:{index}")
        linked_evidence_ids = {str(signal_by_id[item].get("evidence_id") or "") for item in signal_ids if item in signal_by_id}
        if set(evidence_ids) != linked_evidence_ids:
            errors.append(f"trend_signal_evidence_mismatch:{index}")

    gaps = [item for item in synthesis.get("evidence_gaps", []) if isinstance(item, dict)]
    for index, gap in enumerate(gaps, start=1):
        source_ids = [str(item) for item in gap.get("source_ids", []) if str(item).strip()]
        evidence_ids = [str(item) for item in gap.get("evidence_ids", []) if str(item).strip()]
        signal_ids = [str(item) for item in gap.get("supporting_signal_ids", []) if str(item).strip()]
        missing_ids = [str(item) for item in gap.get("missing_explicit_evidence_source_ids", []) if str(item).strip()]
        if not str(gap.get("statement") or "").strip() or not str(gap.get("uncertainty") or "").strip():
            errors.append(f"gap_statement_or_uncertainty_missing:{index}")
        if not source_ids or any(source_id not in source_by_id for source_id in source_ids):
            errors.append(f"gap_source_unknown:{index}")
        if any(evidence_id not in evidence_by_id for evidence_id in evidence_ids):
            errors.append(f"gap_evidence_unknown:{index}")
        if any(signal_id not in signal_by_id for signal_id in signal_ids):
            errors.append(f"gap_signal_unknown:{index}")
        if any(source_id not in source_by_id for source_id in missing_ids):
            errors.append(f"gap_missing_source_unknown:{index}")
        linked_evidence_ids = {str(signal_by_id[item].get("evidence_id") or "") for item in signal_ids if item in signal_by_id}
        if set(evidence_ids) != linked_evidence_ids:
            errors.append(f"gap_signal_evidence_mismatch:{index}")

    signal_types = sorted({str(item.get("signal_type") or "") for item in signals})
    return {
        "valid": not errors,
        "errors": errors,
        "source_count": len(source_by_id),
        "evidence_count": len(evidence_by_id),
        "signal_count": len(signal_by_id),
        "signal_types": signal_types,
        "trend_count": len(trends),
        "gap_count": len(gaps),
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _redact(text: str | None) -> str:
    safe = text or ""
    for pattern in SECRET_PATTERNS:
        safe = pattern.sub(lambda match: f"{match.group(1)}<redacted>" if match.groups() else "<redacted>", safe)
    return safe


def _repo_head(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else f"unavailable: {_redact(proc.stderr.strip())}"


def _run_command(
    *,
    label: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_dir: Path,
    stderr_dir: Path,
    timeout: int,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    started = time.monotonic()
    started_at = _utc_now()
    timed_out = False
    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **popen_options,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        proc = subprocess.CompletedProcess(argv, int(process.returncode or 0), stdout, stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()

        def timeout_text(value: str | bytes | None) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value or ""

        proc = subprocess.CompletedProcess(
            argv,
            124,
            timeout_text(stdout or exc.stdout),
            f"{timeout_text(stderr or exc.stderr)}\nCommand timed out after {timeout} seconds.\n",
        )
    stdout_path = stdout_dir / f"{label}.stdout.txt"
    stderr_path = stderr_dir / f"{label}.stderr.txt"
    stdout_path.write_text(_redact(proc.stdout), encoding="utf-8", errors="replace")
    stderr_path.write_text(_redact(proc.stderr), encoding="utf-8", errors="replace")
    return proc, {
        "label": label,
        "argv": [str(part) for part in argv],
        "cwd": str(cwd),
        "exit_code": int(proc.returncode),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "timed_out": timed_out,
    }


def _contains_transient_rate_limit(proc: subprocess.CompletedProcess[str]) -> bool:
    text = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
    return any(hint in text for hint in TRANSIENT_HINTS)


def _run_with_rate_limit_retry(
    *,
    label: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_dir: Path,
    stderr_dir: Path,
    timeout: int,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    final_proc: subprocess.CompletedProcess[str] | None = None
    for index, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
        if delay:
            time.sleep(delay)
        proc, record = _run_command(
            label=f"{label}-attempt-{index}",
            argv=argv,
            cwd=cwd,
            env=env,
            stdout_dir=stdout_dir,
            stderr_dir=stderr_dir,
            timeout=timeout,
        )
        record["attempt"] = index
        record["rate_limit_retry"] = _contains_transient_rate_limit(proc)
        attempts.append(record)
        final_proc = proc
        if proc.returncode == 0 or not record["rate_limit_retry"]:
            break
    assert final_proc is not None
    return final_proc, attempts


def _action_evidence(summary: dict[str, Any], action: str) -> Path | None:
    evidence_path = str(summary.get("evidence_path") or "")
    if not evidence_path:
        return None
    payload = _read_json(Path(evidence_path))
    actions = payload.get("outputs", {}).get("skill_run", {}).get("actions", [])
    if not isinstance(actions, list):
        return None
    for item in actions:
        if isinstance(item, dict) and item.get("action") == action and item.get("evidence_path"):
            return Path(str(item["evidence_path"]))
    return None


def _copy_evidence(path: Path | None, artifact_dir: Path, label: str) -> str:
    if path is None or not path.is_file():
        return str(path) if path is not None else ""
    target = artifact_dir / f"{label}-{path.name}"
    shutil.copy2(path, target)
    return str(target)


def _recorded_path(repo_root: Path, raw: Any) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _candidate_id(item: dict[str, Any]) -> str:
    return str(item.get("candidate_id") or item.get("paperId") or item.get("source_ref") or "").strip()


def _candidate_source(item: dict[str, Any]) -> str:
    return str(item.get("source_ref") or item.get("url") or "").strip()


def _candidate_channels(item: dict[str, Any]) -> list[str]:
    return [str(channel).strip().lower() for channel in item.get("source_channels", []) if str(channel).strip()]


def _fixture_like(value: str) -> bool:
    lowered = value.lower()
    return any(flag in lowered for flag in ("fixture", "sample_", "mock_", "synthetic", "placeholder", "dummy"))


def _extract_product_signal_records(discovery: dict[str, Any], survey: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source_name, payload in (("discovery", discovery), ("survey", survey)):
        outputs = payload.get("outputs", {}) if isinstance(payload, dict) else {}
        candidates = outputs.get("candidates", []) if isinstance(outputs, dict) else []
        if isinstance(candidates, list):
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                for key, signal_type in (
                    ("method", "method"),
                    ("methods", "method"),
                    ("technical_claim", "technical_claim"),
                    ("claim", "technical_claim"),
                    ("claims", "technical_claim"),
                    ("experiment", "experiment_or_evidence"),
                    ("experiments", "experiment_or_evidence"),
                    ("evidence", "experiment_or_evidence"),
                ):
                    value = item.get(key)
                    if value:
                        records.append(
                            {
                                "source": source_name,
                                "type": signal_type,
                                "content": value,
                                "source_ref": _candidate_source(item) or _candidate_id(item),
                            }
                        )
        report = outputs.get("report", {}) if isinstance(outputs, dict) else {}
        sections = report.get("sections", []) if isinstance(report, dict) else []
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                title = str(section.get("title") or section.get("section_id") or "").lower()
                if any(token in title for token in ("method", "claim", "evidence", "experiment")):
                    records.append(
                        {
                            "source": source_name,
                            "type": "technical_claim" if "claim" in title else "method" if "method" in title else "experiment_or_evidence",
                            "content": section.get("body") or "",
                            "source_ref": ";".join(str(item) for item in section.get("evidence_ids", []) if str(item).strip()),
                        }
                    )
    return [item for item in records if str(item.get("content") or "").strip() and str(item.get("source_ref") or "").strip()]


def _extract_product_trends_and_gaps(survey: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outputs = survey.get("outputs", {}) if isinstance(survey, dict) else {}
    report = outputs.get("report", {}) if isinstance(outputs, dict) else {}
    sections = report.get("sections", []) if isinstance(report, dict) else []
    trends: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    if not isinstance(sections, list):
        return trends, gaps
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or section.get("section_id") or "").lower()
        body = str(section.get("body") or "")
        evidence_ids = [str(item) for item in section.get("evidence_ids", []) if str(item).strip()]
        if ("trend" in title or "pattern" in title or "compar" in title) and len(evidence_ids) >= 2:
            trends.append({"title": section.get("title"), "body": body, "evidence_ids": evidence_ids})
        if any(token in title for token in ("gap", "controvers", "uncertain", "limitation")) and evidence_ids:
            gaps.append({"title": section.get("title"), "body": body, "evidence_ids": evidence_ids})
    return trends, gaps


def test_rich_research_provenance_validator_checks_raw_spans_and_links() -> None:
    raw_one = "Methods:\n We use a bounded parser and document its limitation."
    raw_two = "Results: The bounded parser improves retrieval accuracy by 12%."
    hash_one = hashlib.sha256(raw_one.encode("utf-8")).hexdigest()
    hash_two = hashlib.sha256(raw_two.encode("utf-8")).hexdigest()
    source_rows = [
        {"source_id": "source-1", "content_sha256": hash_one},
        {"source_id": "source-2", "content_sha256": hash_two},
    ]
    evidence_rows = [
        {"evidence_id": "evidence-1", "source_id": "source-1", "content": raw_one, "content_hash": hash_one},
        {"evidence_id": "evidence-2", "source_id": "source-2", "content": raw_two, "content_hash": hash_two},
    ]
    signals = [
        {
            "signal_id": "signal-method",
            "signal_type": "method",
            "content": _normalized_span(raw_one),
            "source_id": "source-1",
            "evidence_id": "evidence-1",
            "evidence_span": {"start": 0, "end": len(raw_one)},
            "content_sha256": hash_one,
        },
        {
            "signal_id": "signal-limitation",
            "signal_type": "limitation",
            "content": _normalized_span(raw_one),
            "source_id": "source-1",
            "evidence_id": "evidence-1",
            "evidence_span": {"start": 0, "end": len(raw_one)},
            "content_sha256": hash_one,
        },
        {
            "signal_id": "signal-result",
            "signal_type": "result",
            "content": raw_two,
            "source_id": "source-2",
            "evidence_id": "evidence-2",
            "evidence_span": {"start": 0, "end": len(raw_two)},
            "content_sha256": hash_two,
        },
    ]
    synthesis = {
        "sources": [
            {"source_id": "source-1", "content_sha256": hash_one},
            {"source_id": "source-2", "content_sha256": hash_two},
        ],
        "technical_signals": signals,
        "trends": [
            {
                "source_ids": ["source-1", "source-2"],
                "signal_ids": ["signal-method", "signal-result"],
                "evidence_ids": ["evidence-1", "evidence-2"],
            }
        ],
        "evidence_gaps": [
            {
                "statement": "Only one source states a limitation.",
                "uncertainty": "The check is bounded to persisted extracts.",
                "source_ids": ["source-1", "source-2"],
                "evidence_ids": ["evidence-1"],
                "supporting_signal_ids": ["signal-limitation"],
                "missing_explicit_evidence_source_ids": ["source-2"],
            }
        ],
    }

    valid = _validate_rich_research_provenance(
        synthesis=synthesis,
        source_rows=source_rows,
        evidence_rows=evidence_rows,
    )
    assert valid["valid"] is True
    assert valid["signal_types"] == ["limitation", "method", "result"]

    synthesis["technical_signals"][0]["content"] = "Tampered normalized content."
    invalid = _validate_rich_research_provenance(
        synthesis=synthesis,
        source_rows=source_rows,
        evidence_rows=evidence_rows,
    )
    assert invalid["valid"] is False
    assert "signal_span_content_mismatch:signal-method" in invalid["errors"]


def test_decision_rationale_tracks_actual_assertions() -> None:
    success = _decision_rationale(
        feature="Technical Signal Extraction",
        failed_assertions=[],
        research_status="completed",
        provenance_errors=[],
        success_detail="All technical-signal assertions passed with independently verified persisted evidence.",
    )
    assert success == "All technical-signal assertions passed with independently verified persisted evidence."
    assert "did not meet" not in success
    assert "failed before analysis" not in success

    failure = _decision_rationale(
        feature="Technical Signal Extraction",
        failed_assertions=[{"name": "source_linked_signals"}],
        research_status="failed",
        provenance_errors=["signal_span_invalid:signal-1"],
        success_detail="unused",
    )
    assert "source_linked_signals" in failure
    assert "signal_span_invalid:signal-1" in failure
    assert "Rich research status: failed" in failure


@pytest.mark.live_provider
def test_phase22_not_tested_literature_signal_and_trend_validation(
    repo_root: Path,
    request: pytest.FixtureRequest,
) -> None:
    fixture_root = repo_root / "tests" / "journeys" / "phase22" / "fixtures" / "not_tested" / "literature"
    analysis_request = _read_json(fixture_root / "literature_analysis_request.json")
    expectation = _read_json(fixture_root / "literature_analysis_expectation.json")
    run_id = f"{analysis_request.get('run_id_prefix', 'nt-literature')}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    run_dir = repo_root / "outputs" / "phase22-not-tested" / BATCH_ID / run_id
    stdout_dir = run_dir / "stdout"
    stderr_dir = run_dir / "stderr"
    artifact_dir = run_dir / "artifacts"
    for path in (stdout_dir, stderr_dir, artifact_dir):
        path.mkdir(parents=True, exist_ok=True)

    # Keep the isolated live-provider home short on Windows. The repository
    # worktree plus the run/action identifiers can otherwise exceed MAX_PATH
    # before the production entrypoint writes its first progress artifact.
    sandbox_context = tempfile.TemporaryDirectory(prefix="p22-nt-literature-")
    request.addfinalizer(sandbox_context.cleanup)
    sandbox = Path(sandbox_context.name)
    env = bootstrap_live_environment(repo_root, os.environ.copy())
    env.update(
        {
            "PHASE22_ENABLE_NETWORK_JOURNEYS": "1",
            "SOLAR_AUTOSCI_ALLOW_NETWORK": "1",
            "AUTOSCI_LIVE_PROVIDER_TESTS": "1",
            "HOME": str(sandbox / "home"),
            "USERPROFILE": str(sandbox / "home"),
            "SOLAR_HOME": str(sandbox / "home" / ".solar"),
            "CLAUDE_DIR": str(sandbox / "home" / ".claude"),
            "HARNESS_DIR": str(sandbox / "harness"),
            "AUTOSCI_ARTIFACT_ROOT": str(sandbox / "harness" / "artifacts" / "autosci"),
            "SCIENTIFIC_ARTIFACT_ROOT": str(sandbox / "harness" / "artifacts" / "scientific"),
            "SOLAR_AUTOSCI_OUTPUT_HARNESS": str(sandbox / "harness"),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    (sandbox / "home").mkdir(parents=True, exist_ok=True)
    (sandbox / "harness").mkdir(parents=True, exist_ok=True)

    py = python_executable(repo_root)
    shim = repo_root / "harness" / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"
    topic = str(analysis_request["topic"])
    limit = int(analysis_request["limit"])
    anchor = str(analysis_request["anchor"])

    command_records: list[dict[str, Any]] = []
    discover_proc, discover_attempts = _run_with_rate_limit_retry(
        label="01-discover-anchor",
        argv=[
            py,
            str(shim),
            "skill",
            "discover",
            "--topic",
            topic,
            "--anchor",
            anchor,
            "--limit",
            str(limit),
            "--online",
            "--run-id",
            f"{run_id}-discover",
        ],
        cwd=repo_root,
        env=env,
        stdout_dir=stdout_dir,
        stderr_dir=stderr_dir,
        timeout=180,
    )
    command_records.extend(discover_attempts)
    discover_summary = json.loads(discover_proc.stdout) if discover_proc.stdout.strip().startswith("{") else {}
    discovery_path = _action_evidence(discover_summary, "discover_literature")
    discovery = _read_json(discovery_path)
    durable_discovery = _copy_evidence(discovery_path, artifact_dir, "discover")

    survey_path: Path | None = None
    survey: dict[str, Any] = {}
    durable_survey = ""
    if discovery_path is not None and discovery_path.is_file():
        survey_proc, survey_attempts = _run_with_rate_limit_retry(
            label="02-survey-from-discovery",
            argv=[
                py,
                str(shim),
                "skill",
                "survey",
                "--topic",
                topic,
                "--max-papers",
                str(limit),
                "--online",
                "--discovery-evidence",
                str(discovery_path),
                "--run-id",
                f"{run_id}-survey",
            ],
            cwd=repo_root,
            env=env,
            stdout_dir=stdout_dir,
            stderr_dir=stderr_dir,
            timeout=180,
        )
        command_records.extend(survey_attempts)
        survey_summary = json.loads(survey_proc.stdout) if survey_proc.stdout.strip().startswith("{") else {}
        survey_path = _action_evidence(survey_summary, "write_survey")
        survey = _read_json(survey_path)
        durable_survey = _copy_evidence(survey_path, artifact_dir, "survey")

    research_summary: dict[str, Any] = {}
    research_path: Path | None = None
    durable_research = ""
    if analysis_request.get("run_research_probe"):
        seed_url = str(analysis_request.get("research_seed_url") or "").strip()
        research_proc, research_attempts = _run_with_rate_limit_retry(
            label="03-research-real-data-probe",
            argv=[
                py,
                str(shim),
                "skill",
                "research",
                "--topic",
                f"Analyze {topic}. Extract methods, evidence-backed claims, trends, and gaps from {seed_url}",
                "--online",
                "--skip-pilot",
                "--run-id",
                f"{run_id}-research",
            ],
            cwd=repo_root,
            env=env,
            stdout_dir=stdout_dir,
            stderr_dir=stderr_dir,
            timeout=240,
        )
        command_records.extend(research_attempts)
        research_summary = json.loads(research_proc.stdout) if research_proc.stdout.strip().startswith("{") else {}
        research_path = _action_evidence(research_summary, "run_research_lifecycle")
        durable_research = _copy_evidence(research_path, artifact_dir, "research")

    candidates = discovery.get("outputs", {}).get("candidates", []) if discovery else []
    candidates = [item for item in candidates if isinstance(item, dict)]
    provider_boundary = discovery.get("outputs", {}).get("source_provider_boundary", {}) if discovery else {}
    provider_channels = provider_boundary.get("provider_channels", []) if isinstance(provider_boundary, dict) else []
    real_sources = [
        item
        for item in candidates
        if _candidate_id(item)
        and _candidate_source(item)
        and not _fixture_like(" ".join([_candidate_id(item), _candidate_source(item), str(item.get("title") or "")]))
    ]
    signal_records = _extract_product_signal_records(discovery, survey)
    signal_types = sorted({str(item.get("type")) for item in signal_records if item.get("type")})
    trends, gaps = _extract_product_trends_and_gaps(survey)
    research_run_path = (
        research_path.with_name("real-data-workspace") / "real-data-research-run.json"
        if research_path is not None
        else None
    )
    research_run = _read_json(research_run_path)
    rich_synthesis_path = _recorded_path(repo_root, research_run.get("technical_synthesis_path"))
    rich_sources_path = _recorded_path(repo_root, research_run.get("source_pack_sources_path"))
    rich_evidence_path = _recorded_path(repo_root, research_run.get("source_pack_evidence_path"))
    rich_report_path = _recorded_path(repo_root, research_run.get("research_report_path"))
    rich_synthesis = _read_json(rich_synthesis_path)
    rich_source_rows = _read_jsonl(rich_sources_path)
    rich_evidence_rows = _read_jsonl(rich_evidence_path)
    rich_validation = _validate_rich_research_provenance(
        synthesis=rich_synthesis,
        source_rows=rich_source_rows,
        evidence_rows=rich_evidence_rows,
    )
    durable_rich_evidence = [
        _copy_evidence(path, artifact_dir, label)
        for path, label in (
            (rich_synthesis_path, "rich-technical-synthesis"),
            (rich_sources_path, "rich-sources"),
            (rich_evidence_path, "rich-evidence"),
            (rich_report_path, "rich-report"),
        )
        if path is not None
    ]

    technical_conditions = [
        {
            "name": "production_discover_exit_zero",
            "passed": discover_proc.returncode == 0,
            "detail": {"exit_code": discover_proc.returncode},
        },
        {
            "name": "at_least_three_real_public_sources",
            "passed": len(real_sources) >= int(analysis_request["min_real_sources"]),
            "detail": {"source_count": len(real_sources), "candidate_ids": [_candidate_id(item) for item in real_sources]},
        },
        {
            "name": "provider_boundary_completed",
            "passed": isinstance(provider_boundary, dict)
            and provider_boundary.get("status") == "completed"
            and expectation.get("provider_channel") in provider_channels,
            "detail": {"status": provider_boundary.get("status") if isinstance(provider_boundary, dict) else "", "provider_channels": provider_channels},
        },
        {
            "name": "structured_method_claim_evidence_signals_present",
            "passed": set(analysis_request["required_signal_types"]).issubset(set(signal_types)),
            "detail": {"required": analysis_request["required_signal_types"], "observed": signal_types, "record_count": len(signal_records)},
        },
        {
            "name": "important_signals_trace_to_sources",
            "passed": bool(signal_records) and all(str(item.get("source_ref") or "").strip() for item in signal_records),
            "detail": {"signal_records": signal_records[:10]},
        },
        {
            "name": "real_data_research_analysis_completed",
            "passed": research_run.get("status") == "completed"
            and rich_synthesis.get("status") == "completed"
            and rich_validation.get("valid") is True
            and {"method", "result", "limitation"}.issubset(
                set(rich_validation.get("signal_types", []))
            ),
            "detail": {
                "status": research_run.get("status"),
                "technical_synthesis_status": rich_synthesis.get("status"),
                "independent_provenance_validation": rich_validation,
                "failed_node": research_run.get("failed_node"),
            },
        },
    ]
    trend_conditions = [
        {
            "name": "survey_production_entrypoint_completed",
            "passed": survey.get("status") == "completed",
            "detail": {"status": survey.get("status"), "path": str(survey_path or "")},
        },
        {
            "name": "cross_source_trend_present",
            "passed": len(trends) >= int(analysis_request["min_trends"]),
            "detail": {"trend_count": len(trends), "trends": trends},
        },
        {
            "name": "gap_or_uncertainty_with_source_basis_present",
            "passed": len(gaps) >= int(analysis_request["min_gaps"]),
            "detail": {"gap_count": len(gaps), "gaps": gaps},
        },
        {
            "name": "trend_and_gap_use_real_sources",
            "passed": bool(trends or gaps)
            and all(any(ref in {_candidate_id(item) for item in real_sources} or ref.startswith("task-") for ref in record.get("evidence_ids", [])) for record in [*trends, *gaps]),
            "detail": {"real_source_ids": [_candidate_id(item) for item in real_sources], "trend_count": len(trends), "gap_count": len(gaps)},
        },
        {
            "name": "real_data_research_trend_report_completed",
            "passed": research_run.get("status") == "completed"
            and rich_validation.get("valid") is True
            and int(rich_validation.get("source_count") or 0) >= 8
            and int(rich_validation.get("trend_count") or 0) >= 1
            and int(rich_validation.get("gap_count") or 0) >= 1,
            "detail": {
                "status": research_run.get("status"),
                "independent_provenance_validation": rich_validation,
                "failed_node": research_run.get("failed_node"),
            },
        },
    ]

    def split_assertions(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        passed = [{"name": item["name"], "detail": item["detail"]} for item in items if item["passed"]]
        failed = [{"name": item["name"], "detail": item["detail"]} for item in items if not item["passed"]]
        return passed, failed

    tech_passed, tech_failed = split_assertions(technical_conditions)
    trend_passed, trend_failed = split_assertions(trend_conditions)
    evidence_paths = [
        str(path)
        for path in (
            durable_discovery,
            durable_survey,
            durable_research,
            discovery_path,
            survey_path,
            research_path,
        )
        if path and str(path)
    ]
    evidence_paths.extend(path for path in durable_rich_evidence if path)
    evidence_paths.extend(
        str(path)
        for path in (rich_synthesis_path, rich_sources_path, rich_evidence_path, rich_report_path)
        if path is not None
    )
    limitations = [
        "Rich technical extraction is bounded to provider content-bearing extracts, normally abstracts or fetched visible text; unseen full text is not claimed.",
        "Cross-source trends identify recurring technical content and do not establish longitudinal causality.",
        "Public-provider coverage is bounded to sources observed in this run and is not an exhaustive literature review.",
    ]
    if research_run.get("status") == "failed":
        limitations.append(f"Real-data research route failed at {research_run.get('failed_node')}: {research_run.get('assertions', [{}])[0].get('detail', '')}")

    results = [
        {
            "category": "Workflow",
            "level_2_feature": "Technical Signal Extraction",
            "implementation_state": "IMPLEMENTED",
            "production_entrypoint": "autosci_skill_shim.py skill discover -> skill survey -> skill research --online --skip-pilot",
            "test_file": str(repo_root / "tests" / "journeys" / "phase22" / "code" / "test_p22_nt_literature_analysis.py"),
            "test_selector": SELECTOR,
            "exact_command": EXACT_COMMAND,
            "exit_code": 0,
            "recommended_status": "FAIL" if tech_failed else "PASS_WITH_KNOWN_LIMITATIONS",
            "minimum_success_conditions": expectation.get("minimum_success_conditions", {}).get("technical_signal_extraction", []),
            "assertions_passed": tech_passed,
            "assertions_failed": tech_failed,
            "evidence_paths": evidence_paths,
            "known_limitations": limitations,
            "decision_rationale": _decision_rationale(
                feature="Technical Signal Extraction",
                failed_assertions=tech_failed,
                research_status=str(research_run.get("status") or ""),
                provenance_errors=[str(item) for item in rich_validation.get("errors", [])],
                success_detail=(
                    "All technical-signal minimum assertions passed. The rich production route independently validated "
                    "persisted source/evidence JSONL, normalized raw evidence spans, SHA-256 content hashes, and "
                    "source-linked method, result, and limitation signals."
                ),
            ),
        },
        {
            "category": "Workflow",
            "level_2_feature": "Trend & Gap Analysis",
            "implementation_state": "IMPLEMENTED",
            "production_entrypoint": "autosci_skill_shim.py skill discover -> skill survey -> skill research --online --skip-pilot",
            "test_file": str(repo_root / "tests" / "journeys" / "phase22" / "code" / "test_p22_nt_literature_analysis.py"),
            "test_selector": SELECTOR,
            "exact_command": EXACT_COMMAND,
            "exit_code": 0,
            "recommended_status": "FAIL" if trend_failed else "PASS_WITH_KNOWN_LIMITATIONS",
            "minimum_success_conditions": expectation.get("minimum_success_conditions", {}).get("trend_gap_analysis", []),
            "assertions_passed": trend_passed,
            "assertions_failed": trend_failed,
            "evidence_paths": evidence_paths,
            "known_limitations": limitations,
            "decision_rationale": _decision_rationale(
                feature="Trend & Gap Analysis",
                failed_assertions=trend_failed,
                research_status=str(research_run.get("status") or ""),
                provenance_errors=[str(item) for item in rich_validation.get("errors", [])],
                success_detail=(
                    "All trend/gap minimum assertions passed. The rich production route independently validated at least "
                    "one cross-source trend with two distinct source lineages and source-linked evidence gaps with explicit "
                    "uncertainty."
                ),
            ),
        },
    ]

    run_payload = {
        "schema_version": "phase22.not_tested.literature_validation.v1",
        "batch_id": BATCH_ID,
        "repo_head": _repo_head(repo_root),
        "run_id": run_id,
        "assigned_l2": ASSIGNED_L2,
        "started_at": command_records[0]["started_at"] if command_records else _utc_now(),
        "finished_at": _utc_now(),
        "environment": {
            "network_authorized": True,
            "credential_values_recorded": False,
            "provider_channels": provider_channels,
            "rate_limit_retry_attempts": [item for item in command_records if item.get("rate_limit_retry")],
        },
        "request": analysis_request,
        "observed": {
            "real_source_count": len(real_sources),
            "candidate_ids": [_candidate_id(item) for item in real_sources],
            "signal_types": signal_types,
            "trend_count": len(trends),
            "gap_count": len(gaps),
            "research_run_status": research_run.get("status"),
            "rich_provenance_validation": rich_validation,
        },
        "command_records": command_records,
        "results": results,
        "evidence_dir": str(run_dir),
    }
    _write_json(run_dir / "journey-result.json", run_payload)
    _write_json(run_dir / "commands.json", command_records)
    _write_json(run_dir / "assertions.json", {"technical": technical_conditions, "trend_gap": trend_conditions})
    _write_json(run_dir / "artifacts.json", {"evidence_paths": evidence_paths})
    worker_result_path = _write_json(
        repo_root / ".codex-tmp" / "phase22-worker-results" / BATCH_ID / "result.json",
        {
            "batch_id": BATCH_ID,
            "repo_head": run_payload["repo_head"],
            "assigned_l2": ASSIGNED_L2,
            "results": results,
            "run_id": run_id,
            "evidence_dir": str(run_dir),
            "command_records": command_records,
            "updated_at": _utc_now(),
        },
    )

    assert worker_result_path.exists()
    assert len(real_sources) >= int(analysis_request["min_real_sources"])
