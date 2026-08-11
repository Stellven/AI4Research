"""Provider-backed research lifecycle with evidence-first state advancement.

This module is deliberately independent of the legacy wiki write path.  It is
the canonical adapter for a live discovery -> survey -> synthesis run: every
node produces durable evidence, that evidence is evaluated, and only then is
the next node admitted.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from research.source_pack import write_source_pack
from research.sources.base import FetchResult
from research.state_machine import DataPlaneState, ResearchStateMachine
from research.storage import ResearchRunStateStore


RETRYABLE_ERRORS = {"provider_rate_limited", "provider_http_error", "provider_unavailable"}

_SIGNAL_CUES = {
    "method": re.compile(
        r"(?:^|\b)methods?\s*:|\b(?:we|this\s+(?:paper|study|work))\s+"
        r"(?:propose|introduce|develop|employ|use|evaluate|conduct|search|present|provide|compile|design)|"
        r"\bour\s+(?:approach|method|framework|pipeline|algorithm)|"
        r"\b(?:systematic(?:ally)?\s+review|meta-analysis|experimental\s+(?:design|evaluation)|"
        r"using\s+(?:a|an|the|our)\s+\w+)",
        re.IGNORECASE,
    ),
    "result": re.compile(
        r"(?:^|\b)results?\s*:|\b(?:our\s+results?|the\s+results?|findings?)\s+(?:show|indicate|demonstrate|confirm)|"
        r"\bwe\s+(?:find|show|demonstrate|observe)|\b(?:outperforms?|achiev(?:e|es|ed)|"
        r"reduc(?:e|es|ed|tion)|speedup)\b|"
        r"\b(?:improv(?:e|es|ed|ement)|correlation|accuracy|precision|recall)\b[^.]{0,100}"
        r"\d+(?:\.\d+)?\s*(?:%|times|x|Ã—|×)|\d+(?:\.\d+)?\s*(?:%|times|x|Ã—|×)",
        re.IGNORECASE,
    ),
    "limitation": re.compile(
        r"\b(?:limitations?|however|challenge|bias|heterogeneity|no\s+meta-analysis|restricted|excluded|uncertainty|failure|concern|struggl\w*)\b",
        re.IGNORECASE,
    ),
}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+_-]{2,}")
_THEME_STOPWORDS = {
    "about", "across", "after", "also", "among", "based", "been", "before", "between", "both",
    "could", "each", "from", "have", "into", "more", "most", "other", "over", "paper", "results",
    "show", "study", "such", "than", "that", "their", "these", "they", "this", "through", "using",
    "were", "where", "which", "while", "with", "within", "without", "work", "approach", "method",
    "methods", "framework", "evaluation", "evaluating", "analysis", "survey", "review", "propose",
    "proposed", "introduce", "introduced", "demonstrate", "demonstrates", "however", "limitation",
    "limitations", "result", "findings", "technical", "evidence",
    "language", "languages", "large", "model", "models", "retrieval", "augmented", "generation",
}


def _sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(
        r"\S(?:.*?)(?:[.!?](?=\s+[A-Z0-9]|[A-Z]|\s*$)|$)",
        str(text or ""),
        flags=re.DOTALL,
    ):
        sentence = " ".join(match.group(0).split())
        if len(sentence) >= 30:
            spans.append((match.start(), match.end(), sentence))
    return spans


def _extract_technical_signals(
    *,
    evidence_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sources = {str(row.get("source_id") or ""): row for row in source_rows}
    signals: list[dict[str, Any]] = []
    for evidence in evidence_rows:
        source_id = str(evidence.get("source_id") or "")
        source = sources.get(source_id, {})
        content = str(evidence.get("content") or "")
        found_for_source: set[str] = set()
        for start, end, sentence in _sentence_spans(content):
            for signal_type, cue in _SIGNAL_CUES.items():
                if signal_type in found_for_source or not cue.search(sentence):
                    continue
                if signal_type == "method" and sentence.lower().startswith("proceedings of"):
                    continue
                if signal_type == "result" and re.search(
                    r"\b(?:propos(?:e|ed)|aim(?:s|ed)?|designed?)\b[^.]{0,80}\bimprov",
                    sentence,
                    flags=re.IGNORECASE,
                ):
                    continue
                signal_id = "signal-" + _sha256(
                    {"source_id": source_id, "type": signal_type, "start": start, "content": sentence}
                )[:16]
                signals.append(
                    {
                        "signal_id": signal_id,
                        "signal_type": signal_type,
                        "content": sentence,
                        "source_id": source_id,
                        "source_url": str(source.get("url") or ""),
                        "evidence_id": str(evidence.get("evidence_id") or evidence.get("id") or ""),
                        "evidence_span": {"start": start, "end": end},
                        "content_sha256": str(evidence.get("content_hash") or source.get("content_sha256") or ""),
                        "extraction_basis": "content_bearing_source_sentence",
                    }
                )
                found_for_source.add(signal_type)
    return signals


def _cross_source_themes(signals: list[dict[str, Any]], *, topic: str) -> list[dict[str, Any]]:
    query_tokens = {token.lower() for token in _TOKEN_RE.findall(topic)}
    sources_by_phrase: dict[str, set[str]] = defaultdict(set)
    signals_by_phrase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        tokens = [
            token.lower()
            for token in _TOKEN_RE.findall(str(signal.get("content") or ""))
            if token.lower() not in _THEME_STOPWORDS and token.lower() not in query_tokens
        ]
        phrases = {" ".join(tokens[index : index + 2]) for index in range(len(tokens) - 1)}
        phrases.update(token for token in tokens if len(token) >= 10)
        phrases = {
            phrase
            for phrase in phrases
            if not (
                (parts := [item for item in re.split(r"[-_\s]+", phrase) if item])
                and all(item in query_tokens for item in parts)
            )
        }
        for phrase in phrases:
            source_id = str(signal.get("source_id") or "")
            if source_id and source_id not in sources_by_phrase[phrase]:
                sources_by_phrase[phrase].add(source_id)
                signals_by_phrase[phrase].append(signal)
    ranked = sorted(
        (phrase for phrase, source_ids in sources_by_phrase.items() if len(source_ids) >= 2),
        key=lambda phrase: (-len(sources_by_phrase[phrase]), -len(phrase.split()), phrase),
    )
    trends: list[dict[str, Any]] = []
    for phrase in ranked[:3]:
        basis = signals_by_phrase[phrase]
        source_ids = sorted(sources_by_phrase[phrase])
        trends.append(
            {
                "trend_id": "trend-" + _sha256({"phrase": phrase, "source_ids": source_ids})[:16],
                "trend_type": "cross_source_technical_convergence",
                "theme": phrase,
                "statement": (
                    f"Across {len(source_ids)} independent source extracts, '{phrase}' recurs in technical "
                    "method, result, or limitation passages; this is a content-level cross-source pattern."
                ),
                "source_ids": source_ids,
                "evidence_ids": sorted({str(item.get("evidence_id") or "") for item in basis}),
                "signal_ids": [str(item.get("signal_id") or "") for item in basis],
                "evidence_quotes": [str(item.get("content") or "") for item in basis],
            }
        )
    return trends


def _evidence_gaps(
    *,
    source_rows: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_source_ids = [str(row.get("source_id") or "") for row in source_rows if str(row.get("source_id") or "")]
    by_type = {
        signal_type: [item for item in signals if item.get("signal_type") == signal_type]
        for signal_type in _SIGNAL_CUES
    }
    gaps: list[dict[str, Any]] = []
    for signal_type, label in (("limitation", "limitations or failure boundaries"), ("result", "results")):
        present = sorted({str(item.get("source_id") or "") for item in by_type[signal_type]})
        missing = sorted(set(all_source_ids) - set(present))
        if missing:
            basis = by_type[signal_type]
            gaps.append(
                {
                    "gap_id": "gap-" + _sha256({"type": signal_type, "missing": missing})[:16],
                    "gap_type": "cross_source_coverage_gap",
                    "statement": (
                        f"Only {len(present)} of {len(all_source_ids)} content-bearing sources explicitly state {label}; "
                        "the bounded evidence cannot support a complete cross-source comparison for this dimension."
                    ),
                    "source_ids": all_source_ids,
                    "evidence_ids": sorted({str(item.get("evidence_id") or "") for item in basis}),
                    "supporting_signal_ids": [str(item.get("signal_id") or "") for item in basis],
                    "missing_explicit_evidence_source_ids": missing,
                    "uncertainty": "Absence is assessed only within the persisted source extracts, not unseen full text.",
                }
            )
    return gaps


def _build_technical_synthesis(*, topic: str, pack: dict[str, Any]) -> dict[str, Any]:
    source_rows = _read_jsonl(pack["sources_path"])
    evidence_rows = _read_jsonl(pack["evidence_path"])
    signals = _extract_technical_signals(evidence_rows=evidence_rows, source_rows=source_rows)
    trends = _cross_source_themes(signals, topic=topic)
    gaps = _evidence_gaps(source_rows=source_rows, signals=signals)
    signal_types = sorted({str(item.get("signal_type") or "") for item in signals})
    assertions = [
        {"name": "content_bearing_signals_present", "passed": bool(signals)},
        {"name": "method_result_limitation_present", "passed": {"method", "result", "limitation"}.issubset(signal_types)},
        {"name": "signals_trace_to_exact_source_spans", "passed": bool(signals) and all(item.get("evidence_id") and item.get("content_sha256") and item.get("evidence_span") for item in signals)},
        {"name": "cross_source_trend_present", "passed": bool(trends) and all(len(item.get("source_ids") or []) >= 2 for item in trends)},
        {"name": "evidence_gap_with_uncertainty_present", "passed": bool(gaps) and all(item.get("uncertainty") for item in gaps)},
    ]
    return {
        "schema": "opensolar.technical_research_synthesis.v1",
        "status": "completed" if all(item["passed"] for item in assertions) else "incomplete",
        "topic": topic,
        "source_count": len(source_rows),
        "sources": [
            {
                "source_id": str(item.get("source_id") or ""),
                "title": str(item.get("title") or ""),
                "source_url": str(item.get("url") or ""),
                "content_sha256": str(item.get("content_sha256") or ""),
            }
            for item in source_rows
        ],
        "signal_count": len(signals),
        "signal_types": signal_types,
        "technical_signals": signals,
        "trends": trends,
        "evidence_gaps": gaps,
        "assertions": assertions,
        "limitations": [
            "Extraction is limited to content-bearing provider extracts (normally abstracts or fetched visible text), not unseen full text.",
            "Cross-source trends report recurring technical content and do not imply longitudinal causality.",
        ],
    }


def _technical_report_markdown(synthesis: dict[str, Any]) -> str:
    lines = [f"# {synthesis['topic']}", "", "## Source-linked technical signals", ""]
    for signal_type in ("method", "result", "limitation"):
        lines.extend([f"### {signal_type.title()}", ""])
        selected = [item for item in synthesis["technical_signals"] if item["signal_type"] == signal_type]
        if not selected:
            lines.append("- No explicit passage was found in the bounded source extracts.")
        for item in selected:
            lines.append(f"- {item['content']} [source:{item['source_id']}; evidence:{item['evidence_id']}]")
        lines.append("")
    lines.extend(["## Cross-source trends", ""])
    for trend in synthesis["trends"]:
        lines.append(f"- {trend['statement']} [sources:{', '.join(trend['source_ids'])}]")
    lines.extend(["", "## Evidence gaps and uncertainty", ""])
    for gap in synthesis["evidence_gaps"]:
        lines.append(f"- {gap['statement']} *{gap['uncertainty']}*")
    lines.extend(["", "## Evidence boundary", ""])
    lines.extend(f"- {item}" for item in synthesis["limitations"])
    lines.extend(["", "## Sources", ""])
    lines.extend(
        f"- [{item['title']}]({item['source_url']}) [source:{item['source_id']}]"
        for item in synthesis["sources"]
    )
    return "\n".join(lines).rstrip() + "\n"


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
    technical_synthesis = _build_technical_synthesis(topic=topic, pack=pack)
    synthesis_path = root / "technical-synthesis.json"
    synthesis_path.write_text(
        json.dumps(technical_synthesis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    survey_evidence = {
        "signals": technical_synthesis["technical_signals"],
        "trends": technical_synthesis["trends"],
        "evidence_gaps": technical_synthesis["evidence_gaps"],
        "source_pack": pack["sources_path"],
        "technical_synthesis_path": str(synthesis_path),
        "content_sha256": _sha256(technical_synthesis),
    }
    machine.transition(
        DataPlaneState.EVIDENCE_PRODUCED,
        stage="survey",
        extra={
            "signal_count": technical_synthesis["signal_count"],
            "trend_count": len(technical_synthesis["trends"]),
            "gap_count": len(technical_synthesis["evidence_gaps"]),
        },
    )
    machine.transition(DataPlaneState.EVIDENCE_EVALUATED, stage="survey")
    if "survey" not in completed:
        completed.append("survey")
    store.commit(state="executing", completed_nodes=completed, evidence_refs=pack.get("provider_evidence") or [])
    machine.transition(DataPlaneState.EXECUTING, stage="research")
    report = _technical_report_markdown(technical_synthesis)
    report_path = root / "research-report.md"
    report_path.write_text(report, encoding="utf-8")
    report_ok = (
        topic.lower() in report.lower()
        and technical_synthesis["status"] == "completed"
        and all(item["source_id"] in report for item in pack["provider_evidence"])
    )
    machine.transition(DataPlaneState.EVIDENCE_PRODUCED, stage="research", extra={"report_sha256": _sha256(report)})
    if not report_ok:
        raise RuntimeError("generated report is not relevant to the requested topic and sources")
    machine.transition(DataPlaneState.EVIDENCE_EVALUATED, stage="research")
    if "research" not in completed:
        completed.append("research")
    state = store.commit(state="completed", completed_nodes=completed, evidence_refs=pack["provider_evidence"])
    machine.transition(DataPlaneState.FINALIZED, stage="research")
    return {
        "status": "PASS",
        "attempts": attempts,
        "state": state,
        "provider_result": provider_result,
        "source_pack": pack,
        "survey_evidence": survey_evidence,
        "technical_synthesis": technical_synthesis,
        "technical_synthesis_path": str(synthesis_path),
        "report_path": str(report_path),
    }
