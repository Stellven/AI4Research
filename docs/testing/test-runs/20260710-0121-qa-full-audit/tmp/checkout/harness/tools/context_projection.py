"""Solar Harness — Context Projection Policy.

Builds model-visible context views from session events and optional
KB hits. Context is a projection, never a source of truth — it
never deletes or rewrites session events.

Provenance tracks: included event IDs, summarized event ranges,
dropped event ranges, and KB/knowledge hits.
"""
from __future__ import annotations

import json
import os
import re
import sys
import hashlib
import importlib.util
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from runtime_interfaces import ContextView
from session_log import DuplicateEventError, SessionLog

HARNESS_DIR = os.path.expanduser("~/.solar/harness")

# Default secret patterns for redaction
_SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*\S+"),
    re.compile(r"(?i)token\s*[=:]\s*\S{8,}"),
    re.compile(r"(?i)password\s*[=:]\s*\S+"),
    re.compile(r"(?i)secret\s*[=:]\s*\S+"),
    re.compile(r"(?i)credential\s*[=:]\s*\S+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[0-9a-zA-Z]{36}"),
    re.compile(r"sk-[0-9a-zA-Z]{20,}"),
]

# Event types that are always included in context
_HIGH_VALUE_TYPES = frozenset({
    "command_issued", "activity_started", "activity_succeeded",
    "activity_failed", "activity_handoff", "state_transition",
    "human_feedback", "context_injected", "model_call_requested",
    "model_call_succeeded", "model_call_failed", "model_session_started",
    "model_session_ended",
})

# Event types that can be summarized/dropped to save tokens
_LOW_VALUE_TYPES = frozenset({
    "log_message", "activity_retry_scheduled",
})


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def _redact_secrets(text: str) -> str:
    result = text
    for pat in _SECRET_PATTERNS:
        result = pat.sub("[REDACTED]", result)
    return result


def _load_unified_context_module() -> Any:
    path = os.path.join(HARNESS_DIR, "lib", "solar-unified-context.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("solar_unified_context", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _retrieve_kb_hits(
    query: str,
    *,
    max_hits: int = 6,
    max_chars: int = 2200,
    timeout_ms: int = 2500,
) -> List[Dict[str, Any]]:
    """Retrieve KB hits via the unified Mirage/QMD/Obsidian/Solar DB path.

    This is fail-open by design: context projection must remain available even
    if QMD/Mirage are temporarily down, but it must not pretend a placeholder is
    real recall evidence.
    """
    try:
        module = _load_unified_context_module()
        if module is None or not hasattr(module, "retrieve"):
            return [{
                "source": "context_projection",
                "title": "unified context unavailable",
                "relevance_score": 0.0,
                "note": "solar-unified-context.py missing or not importable",
                "degraded": True,
            }]
        data = module.retrieve(
            query,
            max_hits=max_hits,
            max_chars=max_chars,
            timeout_ms=timeout_ms,
        )
        hits: List[Dict[str, Any]] = []
        for hit in data.get("hits", []):
            if not isinstance(hit, dict):
                continue
            hits.append({
                "source": hit.get("source") or "unknown",
                "mount": hit.get("mount") or "",
                "path": hit.get("path") or "",
                "title": hit.get("title") or hit.get("path") or "untitled",
                "snippet": _redact_secrets(str(hit.get("snippet") or ""))[:500],
                "provenance": hit.get("provenance") or "",
                "layer": hit.get("layer") or "",
                "score": hit.get("score", 0),
                "relevance_score": hit.get("score", 0),
                "source_hash": hit.get("source_hash") or "",
                "lineage": hit.get("lineage") or [],
                "degraded_reason": hit.get("degraded_reason"),
            })
        for degraded in data.get("degraded_sources", []) or []:
            hits.append({
                "source": "degraded",
                "title": str(degraded),
                "relevance_score": 0.0,
                "note": "unified context degraded source",
                "degraded": True,
            })
        return hits
    except Exception as exc:
        return [{
            "source": "context_projection",
            "title": "unified context error",
            "relevance_score": 0.0,
            "note": f"{type(exc).__name__}: {exc}",
            "degraded": True,
        }]


def _source_counts(kb_hits: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for hit in kb_hits:
        source = str(hit.get("source") or "unknown")
        if source == "degraded":
            continue
        counts[source] = counts.get(source, 0) + 1
    return counts


def _degraded_sources(kb_hits: List[Dict[str, Any]]) -> List[str]:
    degraded: List[str] = []
    for hit in kb_hits:
        if hit.get("degraded") or hit.get("source") == "degraded":
            degraded.append(str(hit.get("degraded_reason") or hit.get("title") or hit.get("source") or "unknown"))
    return sorted(set(degraded))


def _lineage_refs(kb_hits: List[Dict[str, Any]]) -> List[str]:
    refs: List[str] = []
    for hit in kb_hits:
        lineage = hit.get("lineage") or []
        if isinstance(lineage, list):
            refs.extend(str(x) for x in lineage if x)
        elif lineage:
            refs.append(str(lineage))
        path = hit.get("path")
        if path:
            refs.append(str(path))
    return sorted(set(refs))[:50]


def _source_hash_refs(kb_hits: List[Dict[str, Any]]) -> List[str]:
    return sorted({str(hit.get("source_hash")) for hit in kb_hits if hit.get("source_hash")})[:50]


class ContextProjection:
    """Builds model-visible context from session events."""

    def __init__(
        self,
        session_id: str,
        *,
        harness_dir: Optional[str] = None,
    ) -> None:
        self.session_id = session_id
        self._harness_dir = harness_dir or HARNESS_DIR
        self._log = SessionLog(session_id, harness_dir=harness_dir)

    def build_context(
        self,
        *,
        policy_name: str = "default",
        query: Optional[str] = None,
        budget_tokens: Optional[int] = None,
    ) -> ContextView:
        """Build a ContextView from session events.

        The view includes:
        - included_event_ids: events that are included verbatim
        - summarized_ranges: ranges of events that were summarized
        - dropped_ranges: ranges of events that were dropped entirely
        - kb_hits: Mirage/QMD/Obsidian/Solar DB recall evidence when query is set
        """
        budget = budget_tokens or 8000  # default ~32K chars
        events = self._log.all_events()
        if not events:
            kb_hits: List[Dict[str, Any]] = []
            if query:
                kb_hits = _retrieve_kb_hits(query)
            return ContextView(
                session_id=self.session_id,
                policy_name=policy_name,
                built_at=_now_ts(),
                budget_tokens=budget,
                kb_hits=kb_hits,
            )

        included_ids: List[str] = []
        included_events: List[Dict[str, Any]] = []
        summarized_ranges: List[Dict[str, Any]] = []
        dropped_ranges: List[Dict[str, Any]] = []
        total_tokens = 0

        # Phase 1: Include high-value events, summarize/drop low-value
        current_summary_start: Optional[int] = None
        current_summary_events: List[Dict[str, Any]] = []

        for ev in events:
            etype = ev.get("type", "")
            event_json = json.dumps(ev, ensure_ascii=False)
            event_tokens = _estimate_tokens(event_json)
            is_high_value = etype in _HIGH_VALUE_TYPES
            is_low_value = etype in _LOW_VALUE_TYPES

            if is_low_value:
                # Summarize low-value events
                if current_summary_start is None:
                    current_summary_start = ev.get("seq", 0)
                current_summary_events.append(ev)
                continue

            # Flush any pending summary range
            if current_summary_events:
                summarized_ranges.append({
                    "start_seq": current_summary_start,
                    "end_seq": current_summary_events[-1].get("seq", 0),
                    "summary": f"{len(current_summary_events)} {current_summary_events[0].get('type', 'log')} events summarized",
                    "event_count": len(current_summary_events),
                })
                current_summary_start = None
                current_summary_events = []

            if is_high_value:
                if total_tokens + event_tokens <= budget:
                    included_ids.append(ev.get("event_id", ""))
                    included_events.append(ev)
                    total_tokens += event_tokens
                else:
                    # Budget exceeded — drop remaining
                    break
            else:
                # Medium-value events: include if budget allows
                if total_tokens + event_tokens <= budget * 0.8:
                    included_ids.append(ev.get("event_id", ""))
                    included_events.append(ev)
                    total_tokens += event_tokens
                # else: silently drop (no range tracking for medium-value)

        # Flush final summary range
        if current_summary_events:
            summarized_ranges.append({
                "start_seq": current_summary_start,
                "end_seq": current_summary_events[-1].get("seq", 0),
                "summary": f"{len(current_summary_events)} {current_summary_events[0].get('type', 'log')} events summarized",
                "event_count": len(current_summary_events),
            })

        # Track dropped ranges (events after budget cutoff)
        if events and included_events:
            last_included_seq = included_events[-1].get("seq", 0)
            last_event_seq = events[-1].get("seq", 0)
            if last_event_seq > last_included_seq:
                dropped_ranges.append({
                    "start_seq": last_included_seq + 1,
                    "end_seq": last_event_seq,
                    "reason": "budget exceeded",
                })

        # Phase 2: Build text from included events
        included_event_data = []
        for ev in included_events:
            payload = ev.get("payload", {})
            event_text = json.dumps({
                "seq": ev.get("seq"),
                "type": ev.get("type"),
                "actor": ev.get("actor"),
                "activity_id": ev.get("activity_id"),
                "payload": payload,
            }, ensure_ascii=False)
            included_event_data.append(_redact_secrets(event_text))

        # Phase 3: KB hits via unified Mirage/QMD/Obsidian/Solar DB recall.
        kb_hits: List[Dict[str, Any]] = []
        if query:
            kb_hits = _retrieve_kb_hits(query)

        return ContextView(
            session_id=self.session_id,
            included_event_ids=included_ids,
            summarized_ranges=summarized_ranges,
            dropped_ranges=dropped_ranges,
            kb_hits=kb_hits,
            token_estimate=total_tokens,
            budget_tokens=budget,
            policy_name=policy_name,
            built_at=_now_ts(),
            _included_event_data=included_event_data,
        )

    def build_context_text(
        self,
        *,
        policy_name: str = "default",
        query: Optional[str] = None,
        budget_tokens: Optional[int] = None,
    ) -> str:
        """Build a text representation of the context view."""
        view = self.build_context(
            policy_name=policy_name,
            query=query,
            budget_tokens=budget_tokens,
        )

        parts = [
            f"# Context Projection: {view.session_id}",
            f"Policy: {view.policy_name} | "
            f"Tokens: ~{view.token_estimate}/{view.budget_tokens or 'unlimited'} | "
            f"Built: {view.built_at}",
        ]

        if view.included_event_ids:
            parts.append(f"\n## Included Events ({len(view.included_event_ids)})")
            parts.append(f"Event IDs: {', '.join(view.included_event_ids[:20])}")

            # Include redacted event data for model consumption
            event_data = getattr(view, '_included_event_data', [])
            if event_data:
                parts.append("\n### Event Details (redacted)")
                for ed in event_data[:50]:  # cap at 50 events
                    parts.append(f"```json\n{ed}\n```")

        if view.summarized_ranges:
            parts.append("\n## Summarized Ranges")
            for sr in view.summarized_ranges:
                parts.append(
                    f"- seq {sr['start_seq']}-{sr['end_seq']}: "
                    f"{sr['summary']}"
                )

        if view.dropped_ranges:
            parts.append("\n## Dropped Ranges")
            for dr in view.dropped_ranges:
                parts.append(
                    f"- seq {dr['start_seq']}-{dr['end_seq']}: {dr['reason']}"
                )

        if view.kb_hits:
            parts.append("\n## Knowledge Base Hits")
            for hit in view.kb_hits:
                parts.append(f"- [{hit['source']}] {hit.get('title', '')}")

        parts.append("\n## Provenance")
        parts.append("This context is a projection over session events.")
        parts.append("It does not modify or replace the source event log.")
        parts.append(f"Total events in session: see SessionLog.replay()")

        text = "\n".join(parts)
        return _redact_secrets(text)

    def record_context_injected(
        self,
        *,
        query: Optional[str] = None,
        policy_name: str = "default",
        budget_tokens: Optional[int] = None,
        actor: str = "coordinator",
        activity_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        source: str = "context_projection",
    ) -> Dict[str, Any]:
        """Append a durable `context_injected` audit event.

        The event stores the redacted model-visible context and provenance. It
        is the explicit boundary where a projection becomes part of the durable
        session history; plain `build_context*` remains read-only.
        """
        view = self.build_context(
            policy_name=policy_name,
            query=query,
            budget_tokens=budget_tokens,
        )
        text = self.build_context_text(
            policy_name=policy_name,
            query=query,
            budget_tokens=budget_tokens,
        )
        existing = self._log.all_events()
        last_seq = existing[-1].get("seq", 0) if existing else 0
        digest_src = json.dumps(
            {
                "session_id": self.session_id,
                "query": query or "",
                "policy_name": policy_name,
                "budget_tokens": budget_tokens or view.budget_tokens,
                "last_seq": last_seq,
                "included_event_ids": view.included_event_ids,
                "kb_paths": [h.get("path") for h in view.kb_hits[:8]],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:16]
        payload = {
            "query": query,
            "policy_name": policy_name,
            "built_at": view.built_at,
            "token_estimate": view.token_estimate,
            "budget_tokens": view.budget_tokens,
            "included_event_ids": view.included_event_ids,
            "summarized_ranges": view.summarized_ranges,
            "dropped_ranges": view.dropped_ranges,
            "kb_hits": view.kb_hits[:8],
            "context_sources": _source_counts(view.kb_hits),
            "degraded_sources": _degraded_sources(view.kb_hits),
            "lineage_refs": _lineage_refs(view.kb_hits),
            "source_hash_refs": _source_hash_refs(view.kb_hits),
            "context_text": text,
            "redaction_policy": "default_secret_patterns",
            "provenance": "projection over append-only session events plus unified knowledge recall",
        }
        idem = f"context_injected:{self.session_id}:{digest}"
        try:
            event_id = self._log.append(
                "context_injected",
                actor=actor,
                source=source,
                sprint_id=self.session_id,
                activity_id=activity_id,
                correlation_id=correlation_id,
                idempotency_key=idem,
                payload=payload,
            )
            duplicate = False
        except DuplicateEventError:
            event_id = ""
            duplicate = True
        return {
            "ok": True,
            "duplicate": duplicate,
            "event_id": event_id,
            "idempotency_key": idem,
            "session_id": self.session_id,
            "payload": payload,
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="solar-harness context projection over session log + unified KB"
    )
    parser.add_argument("session_id")
    parser.add_argument("--query", default=None)
    parser.add_argument("--policy", default="default")
    parser.add_argument("--budget-tokens", type=int, default=None)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--record", action="store_true",
                        help="Append a context_injected audit event")
    parser.add_argument("--actor", default="coordinator")
    parser.add_argument("--activity-id", default=None)
    parser.add_argument("--correlation-id", default=None)
    args = parser.parse_args()

    cp = ContextProjection(args.session_id)
    if args.record:
        result = cp.record_context_injected(
            query=args.query,
            policy_name=args.policy,
            budget_tokens=args.budget_tokens,
            actor=args.actor,
            activity_id=args.activity_id,
            correlation_id=args.correlation_id,
        )
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["payload"]["context_text"])
        return

    if args.format == "json":
        view = cp.build_context(
            query=args.query,
            policy_name=args.policy,
            budget_tokens=args.budget_tokens,
        )
        print(json.dumps({
            "session_id": view.session_id,
            "policy_name": view.policy_name,
            "built_at": view.built_at,
            "included_event_ids": view.included_event_ids,
            "summarized_ranges": view.summarized_ranges,
            "dropped_ranges": view.dropped_ranges,
            "kb_hits": view.kb_hits,
            "token_estimate": view.token_estimate,
            "budget_tokens": view.budget_tokens,
        }, ensure_ascii=False, indent=2))
    else:
        print(cp.build_context_text(
            query=args.query,
            policy_name=args.policy,
            budget_tokens=args.budget_tokens,
        ))


if __name__ == "__main__":
    main()
