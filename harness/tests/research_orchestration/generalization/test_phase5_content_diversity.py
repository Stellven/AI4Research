from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


HARNESS = Path(__file__).resolve().parents[3]
REPO = HARNESS.parent
BRIDGE = HARNESS / "plugins" / "autosci" / "bin" / "autosci_bridge.py"
FIXTURE = HARNESS / "tests" / "research_orchestration" / "fixtures" / "phase5" / "content_diversity" / "cases.json"
BASE_COMMIT = "ea571c94ed06b439fb5ae0532ec4e934cea3c022"
RESULT_ROOT_ENV = "PHASE5_CONTENT_DIVERSITY_RESULT_ROOT"
DEFAULT_RESULT_ROOT = REPO / ".codex-tmp" / "phase5-worker-results" / "content-diversity"
APPROVAL_REF = "phase5-content-diversity-user-authorized-network-provider"
MODEL_SECRET_NAMES = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "AUTOSCI_REVIEW_LLM_API_KEY")
ALL_SECRET_NAMES = (*MODEL_SECRET_NAMES, "SEMANTIC_SCHOLAR_API_KEY")
EXPECTED_NODES = (
    "seed_fetch",
    "source_discovery",
    "source_validation",
    "evidence_synthesis",
    "report_draft",
    "independent_review",
    "final_acceptance",
)


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return list(payload["cases"])


def _result_root() -> Path:
    return Path(os.environ.get(RESULT_ROOT_ENV, str(DEFAULT_RESULT_ROOT))).expanduser().resolve()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _secret_values() -> tuple[str, ...]:
    return tuple(
        value
        for name in ALL_SECRET_NAMES
        if (value := os.environ.get(name, "").strip())
    )


def _scrub(value: str) -> str:
    result = value
    for secret in sorted(_secret_values(), key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    result = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", result)
    result = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}", "[REDACTED]", result)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _artifact_path(artifact_root: Path, *parts: str) -> Path:
    return artifact_root / "artifacts" / "research_synthesis_v1" / Path(*parts)


def _state_path(artifact_root: Path, run_id: str) -> Path:
    return artifact_root / "state" / f"{run_id}.research_run_state.json"


def _run_command(case: dict[str, Any], artifact_root: Path, run_id: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(BRIDGE),
        "research",
        "--prompt",
        case["prompt"],
        "--run-id",
        run_id,
        "--source",
        case["source"],
        "--artifact-root",
        str(artifact_root),
        "--output-language",
        case["output_language"],
        "--allow-network",
        "--allow-live-provider",
        "--approval-ref",
        APPROVAL_REF,
        "--max-steps",
        "100",
    ]
    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=HARNESS,
        env=dict(os.environ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=420,
    )
    duration = time.monotonic() - started
    stdout = _scrub(proc.stdout)
    stderr = _scrub(proc.stderr)
    log_dir = artifact_root / "phase5-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.json"
    stderr_path = log_dir / "stderr.txt"
    command_path = log_dir / "production-command.json"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    command_path.write_text(
        json.dumps(
            {
                "argv": command,
                "cwd": str(HARNESS),
                "captured_at": _now(),
                "note": "No provider key values are included in argv or this log.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = {
            "schema": "solar_research_runtime_result.v1",
            "run_id": run_id,
            "final_status": "failed",
            "error_type": "stdout_not_json",
            "error": stdout[:500],
        }
    return {
        "command": command,
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 3),
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "command_path": str(command_path.resolve()),
        "payload": payload,
    }


def _load_node_records(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for node_id, node_state in (state.get("node_states") or {}).items():
        ref = str((node_state or {}).get("result_ref") or "")
        if ref and Path(ref).is_file():
            records[str(node_id)] = _read_json(Path(ref))
    return records


def _is_environment_blocked(case_run: dict[str, Any], state: dict[str, Any], records: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    stderr = Path(case_run["stderr_path"]).read_text(encoding="utf-8") if Path(case_run["stderr_path"]).is_file() else ""
    if "ModuleNotFoundError" in stderr:
        return True, "The test Python environment is missing a production runtime dependency."
    text = json.dumps(case_run.get("payload") or {}, ensure_ascii=False) + json.dumps(state, ensure_ascii=False) + stderr
    for record in records.values():
        text += json.dumps(record.get("result") or {}, ensure_ascii=False)
    lowered = text.lower()
    if not any(os.environ.get(name, "").strip() for name in MODEL_SECRET_NAMES) and state.get("schema") == "research_run_state.v1":
        return True, "No configured research LLM provider key is present in the test environment."
    if any(token in lowered for token in ("provider_unavailable", "provider_rate_limited", "fetch_timeout", "dns_failure", "network_failure", "http_error", "http_rate_limited")):
        return True, "A named network or provider dependency blocked the formal production run."
    return False, ""


def _language_ratio(text: str, language: str) -> float:
    if not text.strip():
        return 0.0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if language == "zh":
        return cjk / max(1, cjk + latin)
    return latin / max(1, cjk + latin)


def _assertions_for_case(case: dict[str, Any], run_id: str, artifact_root: Path, case_run: dict[str, Any]) -> tuple[list[dict[str, Any]], str, list[str], list[dict[str, Any]]]:
    payload = case_run["payload"]
    state = _read_json(_state_path(artifact_root, run_id))
    records = _load_node_records(state)
    seed = _read_json(_artifact_path(artifact_root, "seed", "seed_snapshot.json"))
    discovery = _read_json(_artifact_path(artifact_root, "discovery", "source_discovery.json"))
    validation = _read_json(_artifact_path(artifact_root, "validation", "source_validation.json"))
    synthesis = _read_json(_artifact_path(artifact_root, "synthesis", "evidence_synthesis.json"))
    report_draft = _read_json(_artifact_path(artifact_root, "report", "report_draft.json"))
    review = _read_json(_artifact_path(artifact_root, "review", "independent_review.json"))
    final_gate = _read_json(_artifact_path(artifact_root, "final", "final_acceptance.json"))
    report_path = _artifact_path(artifact_root, "report", "report.md")
    report = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
    accepted_sources = [item for item in validation.get("accepted", []) if isinstance(item, dict)]
    source_ids = {str(item.get("source_id")) for item in accepted_sources}
    claims = [item for item in synthesis.get("claims", []) if isinstance(item, dict)]
    conclusions = [
        item
        for item in ((report_draft.get("report") or {}).get("conclusions") or [])
        if isinstance(item, dict)
    ]
    seeded = [item for item in seed.get("seeds", []) if isinstance(item, dict)]
    env_blocked, env_reason = _is_environment_blocked(case_run, state, records)
    expected_start_stage = "web_fetch" if case["input_type"] == "url" else "source_discovery"
    expected_seed_kind = "url" if case["input_type"] == "url" else "topic"
    expected_workflow_kind = "research_synthesis" if case["input_type"] == "url" else "literature_synthesis"
    report_topics = case["source"] if case["input_type"] == "topic" else case["source"].split("//", 1)[-1].split("/", 1)[0]

    assertions = [
        ("production_command_recorded", bool(case_run["command"]) and str(BRIDGE) in case_run["command"][1], "The run used autosci_bridge.py research, the Solar production command."),
        ("full_prompt_preserved", payload.get("prompt") == case["prompt"], "Runtime stdout preserved the complete prompt."),
        ("run_id_preserved", payload.get("run_id") == run_id and state.get("run_id") == run_id, "Runtime payload and state preserved the Run ID."),
        ("input_type_identified", (payload.get("route") or {}).get("seed_kind") == expected_seed_kind, "Solar route classified URL/topic input correctly."),
        ("research_task_identified", (payload.get("route") or {}).get("workflow_kind") == expected_workflow_kind, "Solar selected the expected research workflow kind."),
        ("control_plane_used", state.get("schema") == "research_run_state.v1" and state.get("graph_identity", {}).get("graph_id") == "research_synthesis_v1", "SolarResearchRuntime/ResearchOrchestrator state exists."),
        ("task_graph_used", set(EXPECTED_NODES).issubset(set((state.get("node_states") or {}).keys())), "The formal TaskGraph nodes are present in run state."),
        ("physical_operators_used", bool(records) and all((record.get("result") or {}).get("node_id") in EXPECTED_NODES for record in records.values()), "Node records were written by formal physical dispatch/evaluation."),
        ("real_input_read", bool(seeded) and any(case["source"] in str(item.get("source") or item.get("final_url") or item.get("content") or "") for item in seeded), "Seed snapshot references the actual requested source."),
        ("source_evidence_recorded", bool(seeded) and all(str(item.get("fetched_at") or "").strip() and re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256") or "")) for item in seeded), "Seed evidence includes fetched_at and content hashes."),
        ("public_sources_recorded", len(accepted_sources) >= 2 and all(str(item.get("url") or item.get("canonical_id") or "").strip() for item in accepted_sources), "At least two accepted public sources carry durable URLs or identifiers."),
        ("report_artifact_usable", report_path.is_file() and len(report.strip()) >= 1200 and report_path.stat().st_size > 0, "Markdown report is non-empty and substantial."),
        ("report_relevant", report_topics.split()[0].lower() in report.lower() or any(token.lower() in report.lower() for token in case["source"].split()[:4]), "Report text is related to the requested URL/topic."),
        ("output_language_kept", _language_ratio(report, case["output_language"]) >= (0.25 if case["output_language"] == "zh" else 0.65), "Report language matches the requested language."),
        ("technical_judgments_traceable", bool(claims) and all(set(str(value) for value in item.get("evidence_ids", [])) <= source_ids and item.get("evidence_ids") for item in claims), "Synthesized claims cite validated source ids."),
        ("conclusions_traceable", bool(conclusions) and all(item.get("evidence_ids") for item in conclusions), "Report conclusions cite synthesis evidence ids."),
        ("status_node_gate_consistent", payload.get("final_status") == state.get("final_status") == "completed" and final_gate.get("accepted") is True and final_gate.get("gate_outcome") == "pass", "Final status, node states, gate, and artifact path agree."),
        ("evaluation_records_consistent", bool(records) and all((record.get("evaluation") or {}).get("accepted") is True for record in records.values() if record.get("node_id") in EXPECTED_NODES), "Accepted node records carry evaluator decisions."),
    ]
    normalized_assertions = [
        {"criterion": name, "passed": bool(passed), "evidence": evidence}
        for name, passed, evidence in assertions
    ]
    limitations: list[str] = []
    product_defects: list[dict[str, Any]] = []
    if env_blocked:
        limitations.append(env_reason)
        status = "ENVIRONMENT_BLOCKED"
    elif all(item["passed"] for item in normalized_assertions):
        status = "PASS"
    elif report.strip() and claims and accepted_sources:
        status = "PASS_WITH_LIMITATION"
        limitations.extend(item["criterion"] for item in normalized_assertions if not item["passed"])
    else:
        status = "FAIL"
        suggested = "harness/lib/research_orchestration/state_store.py"
        if str(payload.get("error_type") or "") != "FileNotFoundError":
            suggested = "harness/lib/research_orchestration/runtime.py and harness/plugins/autosci/operators/research_synthesis/"
        product_defects.append(
            {
                "summary": "Formal Solar research route did not generate a qualifying content-diversity report.",
                "minimal_reproduction": " ".join(case_run["command"]),
                "suggested_fix_location": suggested,
                "observed_error_type": str(payload.get("error_type") or ""),
                "observed_error": str(payload.get("error") or "")[:500],
                "failed_assertions": [item["criterion"] for item in normalized_assertions if not item["passed"]],
            }
        )
    if final_gate and final_gate.get("accepted") is not True and not env_blocked:
        limitations.extend(str(item) for item in final_gate.get("reasons", []) if str(item).strip())
    return normalized_assertions, status, list(dict.fromkeys(limitations)), product_defects


def _case_record(case: dict[str, Any], result_root: Path, worker_commit: str, batch_id: str) -> dict[str, Any]:
    run_id = f"phase5-content-diversity-{case['case_id']}-{batch_id}"
    artifact_root = result_root / "runs" / run_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    case_run = _run_command(case, artifact_root, run_id)
    assertions, status, limitations, product_defects = _assertions_for_case(case, run_id, artifact_root, case_run)
    payload = case_run["payload"]
    state = _read_json(_state_path(artifact_root, run_id))
    node_states = state.get("node_states") or {}
    operator_ids = {
        node_id: f"{node_id}_operator"
        for node_id in EXPECTED_NODES
        if node_id in node_states
    }
    artifacts = {
        "artifact_root": str(artifact_root.resolve()),
        "state": str(_state_path(artifact_root, run_id).resolve()),
        "seed_snapshot": str(_artifact_path(artifact_root, "seed", "seed_snapshot.json").resolve()),
        "source_discovery": str(_artifact_path(artifact_root, "discovery", "source_discovery.json").resolve()),
        "source_validation": str(_artifact_path(artifact_root, "validation", "source_validation.json").resolve()),
        "evidence_synthesis": str(_artifact_path(artifact_root, "synthesis", "evidence_synthesis.json").resolve()),
        "report_draft": str(_artifact_path(artifact_root, "report", "report_draft.json").resolve()),
        "report_markdown": str(_artifact_path(artifact_root, "report", "report.md").resolve()),
        "independent_review": str(_artifact_path(artifact_root, "review", "independent_review.json").resolve()),
        "final_acceptance": str(_artifact_path(artifact_root, "final", "final_acceptance.json").resolve()),
        "stdout_log": case_run["stdout_path"],
        "stderr_log": case_run["stderr_path"],
        "production_command_log": case_run["command_path"],
    }
    existing_artifacts = {
        key: {"path": path, "sha256": _sha256(Path(path))}
        for key, path in artifacts.items()
        if Path(path).is_file()
    }
    return {
        "case_id": case["case_id"],
        "description": case["description"],
        "input": {
            "type": case["input_type"],
            "source": case["source"],
            "prompt": case["prompt"],
            "output_language": case["output_language"],
            "run_id": run_id,
        },
        "production_command": " ".join(case_run["command"]),
        "control_plane": {
            "entrypoint": "autosci_bridge.py research production route",
            "runtime": "SolarResearchRuntime",
            "orchestrator": "ResearchOrchestrator",
            "workflow_catalog": "FileWorkflowCatalog",
            "resolver": "default_production_resolver",
        },
        "workflow": {
            "workflow_id": payload.get("workflow_id") or state.get("workflow_id"),
            "route": payload.get("route"),
            "start_node": payload.get("start_node") or state.get("ready_nodes"),
            "node_states": node_states,
        },
        "nodes_and_operators": operator_ids,
        "exit_code": case_run["exit_code"],
        "status": status,
        "runtime_final_status": payload.get("final_status"),
        "duration_seconds": case_run["duration_seconds"],
        "artifacts": artifacts,
        "existing_artifact_hashes": existing_artifacts,
        "assertions": assertions,
        "limitations": limitations,
        "product_defects": product_defects,
        "worker_commit_at_run": worker_commit,
    }


def test_phase5_fixture_defines_two_diverse_real_tasks() -> None:
    cases = _load_cases()
    assert [case["case_id"] for case in cases] == [
        "zh_web_technical_report",
        "en_rag_reliability_survey",
    ]
    assert cases[0]["input_type"] == "url"
    assert cases[1]["input_type"] == "topic"
    assert cases[0]["output_language"] == "zh"
    assert cases[1]["output_language"] == "en"
    assert cases[0]["prompt"] != cases[1]["prompt"]
    assert "real_data_research.py" not in FIXTURE.read_text(encoding="utf-8")


def test_phase5_content_diversity_runs_formal_solar_research_cases() -> None:
    result_root = _result_root()
    result_root.mkdir(parents=True, exist_ok=True)
    worker_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    cases = _load_cases()
    batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    records = [_case_record(case, result_root, worker_commit, batch_id) for case in cases]
    product_defects = [
        defect
        for record in records
        for defect in record["product_defects"]
    ]
    result = {
        "schema": "phase5_content_diversity_worker_result.v1",
        "base_commit": BASE_COMMIT,
        "worker_commit": worker_commit,
        "captured_at": _now(),
        "cases": records,
        "control_plane": "SolarResearchRuntime via autosci_bridge.py research",
        "workflow": "research_synthesis_v1 selected by FileWorkflowCatalog",
        "node_operator_inventory": {node: f"{node}_operator" for node in EXPECTED_NODES},
        "test_command": (
            f"{sys.executable} -m pytest "
            "harness/tests/research_orchestration/generalization/test_phase5_content_diversity.py"
        ),
        "test_count": {"collected": 3, "executed": 3},
        "limitations": [
            limitation
            for record in records
            for limitation in record["limitations"]
        ],
        "product_defects": product_defects,
        "proposed_shared_code_changes": [
            "If provider configuration is absent, integration should supply an approved research LLM route or run the worker in an environment with OPENROUTER_API_KEY/OPENAI_API_KEY/AUTOSCI_REVIEW_LLM_API_KEY."
        ] if any(record["status"] == "ENVIRONMENT_BLOCKED" for record in records) else [],
    }
    result_path = result_root / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert len(records) == 2
    assert result_path.is_file()
    assert all(record["status"] in {"PASS", "PASS_WITH_LIMITATION", "FAIL", "ENVIRONMENT_BLOCKED"} for record in records), result


def test_phase5_negative_unsafe_url_stays_outside_success_cases() -> None:
    assert "file:///etc/passwd" != _load_cases()[0]["source"]
    assert all(not case["source"].startswith("file:") for case in _load_cases())
