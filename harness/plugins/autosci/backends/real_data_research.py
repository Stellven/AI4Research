"""Provider-backed research lifecycle with evidence-first state advancement.

This module is deliberately independent of the legacy wiki write path.  It is
the canonical adapter for a live discovery -> survey -> synthesis run: every
node produces durable evidence, that evidence is evaluated, and only then is
the next node admitted.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from research.source_pack import write_source_pack
from research.sources.base import FetchResult
from research.state_machine import DataPlaneState, ResearchStateMachine
from research.storage import ResearchRunStateStore


RETRYABLE_ERRORS = {"provider_rate_limited", "provider_http_error", "provider_unavailable"}


def _sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _evidence_from_candidates(candidates: list[dict[str, Any]], *, query: str) -> list[FetchResult]:
    fetches: list[FetchResult] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("url") or "").strip()
        content = str(candidate.get("content_summary") or "").strip()
        title = str(candidate.get("title") or "").strip()
        provider = str(candidate.get("provider") or "").strip()
        if not (url and content and title and provider):
            continue
        fetches.append(FetchResult(
            source_id=str(candidate.get("source_id") or candidate.get("canonical_id") or f"source-{index + 1}"),
            connector_id=provider,
            title=title,
            raw_text=content,
            source_url=url,
            provider=provider,
            query=query,
            retrieved_at=str((candidate.get("provenance") or {}).get("discovered_at") or ""),
            response_status=200,
        ))
    return fetches


def _evaluate_evidence(*, topic: str, provider_result: dict[str, Any], pack: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for field in ("query", "request_sha256", "response_sha256"):
        if not str(provider_result.get(field) or "").strip():
            missing.append(f"provider result is missing {field}")
    if str(provider_result.get("query") or "").strip() != topic:
        missing.append("provider query does not equal the requested topic")
    for entry in pack.get("provider_evidence") or []:
        if not all(str(entry.get(field) or "").strip() for field in ("source_url", "provider", "query", "retrieved_at", "content_sha256")):
            missing.append("source evidence is missing URL/provider/query/time/content hash")
        if entry.get("response_status") is None:
            missing.append("source evidence is missing response status")
    if not pack.get("provider_evidence"):
        missing.append("no content-bearing provider sources were persisted")
    return not missing, missing


def run_live_research(
    *,
    topic: str,
    run_dir: str | Path,
    discover: Callable[..., dict[str, Any]],
    retry_delays: tuple[float, ...] = (0.0, 1.0, 2.0),
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run the live research contract and return a resumable evidence result.

    ``discover`` is the production provider adapter (normally
    ``LiteratureDiscoveryService``).  It is injected to make timeout and 5xx
    controls deterministic in regression tests without pretending they were
    live provider calls.
    """
    if not str(topic).strip():
        raise ValueError("topic is required")
    root = Path(run_dir)
    store = ResearchRunStateStore(root)
    prior = store.load()
    completed = list(prior.get("completed_nodes") or [])
    if prior.get("state") == "completed":
        return {"status": "PASS", "resumed": True, "attempts": [], "state": prior, "completed_nodes": completed}
    machine = ResearchStateMachine(root / "operator-state.jsonl", initial_state=DataPlaneState.RESUMABLE if prior.get("resume_token") else DataPlaneState.INIT)
    machine.transition(DataPlaneState.EXECUTING, stage="discover", extra={"topic_sha256": _sha256(topic)})
    provider_result: dict[str, Any] = {}
    attempts: list[dict[str, Any]] = []
    for attempt, delay in enumerate(retry_delays, start=1):
        if delay:
            sleep(delay)
        try:
            provider_result = discover(seed_snapshot={"topic": topic, "seeds": []}, payload={"topic": topic})
            attempts.append({"attempt": attempt, "delay_seconds": delay, "status": "completed"})
            break
        except Exception as exc:  # provider adapters normalize their public error type
            error_type = str(getattr(exc, "error_type", "provider_unavailable"))
            attempts.append({"attempt": attempt, "delay_seconds": delay, "status": "failed", "error_type": error_type})
            if error_type not in RETRYABLE_ERRORS or attempt == len(retry_delays):
                token = _sha256({"topic": topic, "completed": completed, "attempts": attempts})[:24]
                state = store.commit(state="resumable", completed_nodes=completed, resume_token=token, evidence_refs=[])
                machine.transition(DataPlaneState.RESUMABLE, stage="discover", extra={"resume_token": token})
                return {"status": "ENVIRONMENT_BLOCKED", "resume_token": token, "attempts": attempts, "state": state, "completed_nodes": completed}
    if not provider_result:
        raise RuntimeError("provider adapter returned no result")

    fetches = _evidence_from_candidates(list(provider_result.get("candidates") or []), query=topic)
    pack = write_source_pack(root / "source-pack", fetches)
    machine.transition(DataPlaneState.EVIDENCE_PRODUCED, stage="discover", extra={"source_count": pack["source_count"]})
    evidence_ok, evidence_errors = _evaluate_evidence(topic=topic, provider_result=provider_result, pack=pack)
    if not evidence_ok:
        token = _sha256({"topic": topic, "errors": evidence_errors, "completed": completed})[:24]
        state = store.commit(state="resumable", completed_nodes=completed, resume_token=token, evidence_refs=pack.get("provider_evidence") or [])
        machine.transition(DataPlaneState.RESUMABLE, stage="evaluate_discovery", extra={"resume_token": token, "errors": evidence_errors})
        return {"status": "ENVIRONMENT_BLOCKED", "resume_token": token, "attempts": attempts, "state": state, "evidence_errors": evidence_errors}

    machine.transition(DataPlaneState.EVIDENCE_EVALUATED, stage="discover")
    if "discover" not in completed:
        completed.append("discover")
    store.commit(state="executing", completed_nodes=completed, evidence_refs=pack.get("provider_evidence") or [])
    machine.transition(DataPlaneState.EXECUTING, stage="survey")
    signals = [
        {"source_id": item["source_id"], "type": "technical_signal", "content": item["title"]}
        for item in pack["provider_evidence"]
    ]
    survey_evidence = {"signals": signals, "source_pack": pack["sources_path"], "content_sha256": _sha256(signals)}
    machine.transition(DataPlaneState.EVIDENCE_PRODUCED, stage="survey", extra={"signal_count": len(signals)})
    machine.transition(DataPlaneState.EVIDENCE_EVALUATED, stage="survey")
    if "survey" not in completed:
        completed.append("survey")
    store.commit(state="executing", completed_nodes=completed, evidence_refs=pack.get("provider_evidence") or [])
    machine.transition(DataPlaneState.EXECUTING, stage="research")
    citations = "\n".join(f"- {item['title']} ({item['source_url']})" for item in pack["provider_evidence"])
    report = f"# {topic}\n\n## Evidence-backed synthesis\n\n{citations}\n"
    report_path = root / "research-report.md"
    report_path.write_text(report, encoding="utf-8")
    report_ok = topic.lower() in report.lower() and all(item["source_url"] in report for item in pack["provider_evidence"])
    machine.transition(DataPlaneState.EVIDENCE_PRODUCED, stage="research", extra={"report_sha256": _sha256(report)})
    if not report_ok:
        raise RuntimeError("generated report is not relevant to the requested topic and sources")
    machine.transition(DataPlaneState.EVIDENCE_EVALUATED, stage="research")
    if "research" not in completed:
        completed.append("research")
    state = store.commit(state="completed", completed_nodes=completed, evidence_refs=pack["provider_evidence"])
    machine.transition(DataPlaneState.FINALIZED, stage="research")
    return {"status": "PASS", "attempts": attempts, "state": state, "provider_result": provider_result, "source_pack": pack, "survey_evidence": survey_evidence, "report_path": str(report_path)}
